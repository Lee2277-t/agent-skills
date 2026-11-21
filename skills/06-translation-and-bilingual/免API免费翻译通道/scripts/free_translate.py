#!/usr/bin/env python3
"""Free translation channel with no API key: Bing web endpoint, MyMemory fallback.

Importable (BingEngine / MyMemoryEngine / TranslationCache / Translator) and CLI:
    python free_translate.py --probe
    python free_translate.py --text "Some English sentence"
    python free_translate.py --file segments.txt --cache cache/translations.db
Stdlib only. Translations go to stdout, progress/summary to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import http.client
import http.cookiejar
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

TARGET_LANG = "zh-Hans"
BING_CHUNK = 900
MYMEMORY_CHUNK = 450
BING_BATCH_CHARS = 820
BING_BATCH_ITEMS = 10
BING_BATCH_MARKER_COST = 28
TOKEN_TTL = 2400
BING_HOSTS = ("https://cn.bing.com", "https://www.bing.com")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
)

KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
GREEK_RE = re.compile(r"[\u0370-\u03ff]")


class TranslationError(RuntimeError):
    pass


def normalize_source(text: str) -> str:
    return text.replace("\u00a0", " ").replace("\u200b", "").strip()


def guess_lang_pair(text: str, target: str) -> str:
    if KANA_RE.search(text):
        source = "ja"
    elif HANGUL_RE.search(text):
        source = "ko"
    elif CYRILLIC_RE.search(text):
        source = "ru"
    elif ARABIC_RE.search(text):
        source = "ar"
    elif THAI_RE.search(text):
        source = "th"
    elif DEVANAGARI_RE.search(text):
        source = "hi"
    elif GREEK_RE.search(text):
        source = "el"
    else:
        source = "en"
    return f"{source}|{target}"


def split_for_api(text: str, limit: int) -> list[str]:
    """Chunk on sentence boundaries, then on spaces, never above limit.

    Joining the pieces back must be "".join(), not " ".join(): the engine is
    asked to translate up to `limit` characters including the trailing space of
    each chunk, so re-adding separators duplicates whitespace.
    """
    text = normalize_source(text)
    if len(text) <= limit:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?;:])\s+|\n+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            piece, sentence = sentence[:cut].strip(), sentence[cut:].lstrip()
            if piece:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(piece)
        if not sentence:
            continue
        if len(current) + 1 + len(sentence) <= limit:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


class BingEngine:
    """Microsoft Translate web endpoint. Unofficial: markup may change any time."""

    def __init__(self, log=None, target: str = TARGET_LANG) -> None:
        self.log = log or (lambda message: None)
        self.target = target
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.host = ""
        self.ig = ""
        self.iid = ""
        self.key = ""
        self.token = ""
        self.obtained_at = 0.0
        self.host_index = 0
        self._conn: http.client.HTTPSConnection | None = None
        self._conn_host = ""
        self._cookie_header = ""

    def _page_headers(self) -> dict[str, str]:
        return {
            "User-Agent": UA,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }

    def _api_headers(self) -> dict[str, str]:
        return {
            "User-Agent": UA,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": f"{self.host}/translator",
            "Origin": self.host,
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Accept-Encoding": "identity",
            "Cookie": self._cookie_header,
        }

    def _close_connection(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._conn_host = ""

    def _connection(self) -> http.client.HTTPSConnection:
        host = urllib.parse.urlparse(self.host).hostname or "cn.bing.com"
        if self._conn is None or self._conn_host != host:
            self._close_connection()
            self._conn = http.client.HTTPSConnection(host, timeout=35)
            self._conn_host = host
        return self._conn

    def refresh(self) -> None:
        """Fetch /translator once and scrape the three credentials from the HTML."""
        errors: list[str] = []
        for offset in range(len(BING_HOSTS)):
            index = (self.host_index + offset) % len(BING_HOSTS)
            host = BING_HOSTS[index]
            try:
                request = urllib.request.Request(
                    f"{host}/translator", headers=self._page_headers()
                )
                with self.opener.open(request, timeout=30) as response:
                    page = response.read().decode("utf-8", "ignore")
                ig = re.search(r'IG:"([^"]+)"', page)
                iid = re.search(r'data-iid="([^"]+)"', page)
                token_info = re.search(
                    r"params_AbusePreventionHelper\s*=\s*(\[[^\]]+\])", page
                )
                if not (ig and iid and token_info):
                    raise TranslationError(
                        "credential scrape failed - endpoint markup changed"
                    )
                values = json.loads(token_info.group(1))
                self.host = host
                self.ig = ig.group(1)
                self.iid = iid.group(1)
                self.key = str(values[0])
                self.token = values[1]
                self.obtained_at = time.time()
                self.host_index = index
                self._cookie_header = "; ".join(
                    f"{cookie.name}={cookie.value}" for cookie in self.cookie_jar
                )
                self._close_connection()
                return
            except Exception as exc:
                errors.append(f"{host.split('//')[-1]}: {type(exc).__name__}")
        raise TranslationError("cannot reach Microsoft Translate: " + "; ".join(errors))

    def _ensure_token(self) -> None:
        if not self.token or time.time() - self.obtained_at > TOKEN_TTL:
            self.refresh()

    def _post_once(self, text: str) -> str:
        self._ensure_token()
        connection = self._connection()
        body = urllib.parse.urlencode(
            {
                "fromLang": "auto-detect",
                "to": self.target,
                "text": text,
                "token": self.token,
                "key": self.key,
            }
        ).encode("utf-8")
        path = f"/ttranslatev3?isVertical=1&IG={self.ig}&IID={self.iid}"
        connection.request("POST", path, body=body, headers=self._api_headers())
        response = connection.getresponse()
        status = response.status
        location = response.getheader("Location")
        raw = response.read().decode("utf-8", "ignore")
        if status in (301, 302, 303, 307, 308):
            target = urllib.parse.urlparse(location or "")
            new_host = f"https://{target.netloc}" if target.netloc else ""
            if new_host in BING_HOSTS and new_host != self.host:
                # Credentials belong to the old host - drop them and the socket.
                self.host = new_host
                self.host_index = BING_HOSTS.index(new_host)
                self.token = ""
                self._close_connection()
            raise TranslationError(f"endpoint redirected to {new_host or location}")
        if status != 200:
            raise TranslationError(f"endpoint returned HTTP {status}")
        payload = json.loads(raw)
        if isinstance(payload, list) and payload:
            translations = payload[0].get("translations") or []
            if translations:
                translated = translations[0].get("text", "")
                if translated.strip():
                    return translated
        raise TranslationError("unexpected response shape")

    def _post(self, text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._post_once(text)
            except Exception as exc:
                last_error = exc
                self._close_connection()
                if attempt == 0:
                    time.sleep(0.8)
                    try:
                        self.refresh()
                    except Exception as refresh_error:
                        last_error = refresh_error
        raise TranslationError(f"request failed: {type(last_error).__name__}")

    def translate(self, text: str) -> str:
        result = "".join(self._post(chunk) for chunk in split_for_api(text, BING_CHUNK))
        if not result.strip():
            raise TranslationError("empty result")
        return result

    def translate_batch(self, texts: list[str]) -> list[str]:
        """Pack up to 10 segments into one request, split them back on sentinels."""
        if len(texts) == 1:
            return [self.translate(texts[0])]
        if len(texts) > BING_BATCH_ITEMS or sum(len(t) for t in texts) > BING_BATCH_CHARS:
            return [self.translate(text) for text in texts]

        marker = secrets.token_hex(3)
        separators = [f"[[[SEG_{marker}_{i}]]]" for i in range(1, len(texts))]
        combined = texts[0]
        for separator, text in zip(separators, texts[1:]):
            combined += f"\n{separator}\n{text}"
        translated = self._post(combined)
        pattern = re.compile(r"\s*\[\[\[SEG_" + re.escape(marker) + r"_(\d+)\]\]\]\s*")
        matches = list(pattern.finditer(translated))

        def fallback() -> list[str]:
            self.log("batch split check failed, falling back to one segment per request")
            return [self.translate(text) for text in texts]

        if len(matches) != len(separators):
            return fallback()
        parts: list[str] = []
        cursor = 0
        expected = 1
        for match in matches:
            if int(match.group(1)) != expected:
                return fallback()
            parts.append(translated[cursor : match.start()].strip())
            cursor = match.end()
            expected += 1
        parts.append(translated[cursor:].strip())
        if len(parts) != len(texts) or any(not part for part in parts):
            return fallback()
        return parts


class MyMemoryEngine:
    """Fallback. Shorter limit, per-request quota checks, script-based langpair."""

    def __init__(self, target: str = TARGET_LANG) -> None:
        self.target = target

    def translate(self, text: str) -> str:
        pieces: list[str] = []
        for chunk in split_for_api(text, MYMEMORY_CHUNK):
            query = urllib.parse.urlencode(
                {"q": chunk, "langpair": guess_lang_pair(chunk, self.target)}
            )
            request = urllib.request.Request(
                f"https://api.mymemory.translated.net/get?{query}",
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
            status = int(payload.get("responseStatus", 0) or 0)
            if status != 200:
                raise TranslationError(f"fallback endpoint returned {status}")
            data = payload.get("responseData") or {}
            translated = html_lib.unescape(data.get("translatedText") or "")
            upper = translated.upper()
            if not translated.strip() or "MYMEMORY WARNING" in upper or "QUOTA" in upper:
                raise TranslationError("fallback endpoint quota exhausted")
            pieces.append(translated)
            time.sleep(0.08)
        result = "".join(pieces)
        if not result.strip():
            raise TranslationError("fallback endpoint returned empty result")
        return result


class TranslationCache:
    """Key MUST include the engine: bing and mymemory results are not equivalent."""

    def __init__(self, path: str | None, target: str = TARGET_LANG) -> None:
        self.target = target
        self._mem: dict[str, str] = {}
        self._conn: sqlite3.Connection | None = None
        if not path:
            return
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS translations ("
                "key TEXT PRIMARY KEY, translated TEXT NOT NULL, "
                "created_at INTEGER NOT NULL)"
            )
            self._conn.commit()
        except Exception:
            self._conn = None

    def _key(self, engine: str, text: str) -> str:
        raw = f"{engine}\0{self.target}\0{text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, engine: str, text: str) -> str | None:
        key = self._key(engine, text)
        if key in self._mem:
            return self._mem[key]
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(
                "SELECT translated FROM translations WHERE key=?", (key,)
            ).fetchone()
        except Exception:
            self._conn = None
            return None
        if row:
            self._mem[key] = row[0]
            return row[0]
        return None

    def set(self, engine: str, text: str, translated: str) -> None:
        key = self._key(engine, text)
        self._mem[key] = translated
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO translations(key, translated, created_at) "
                "VALUES (?, ?, ?)",
                (key, translated, int(time.time())),
            )
            self._conn.commit()
        except Exception:
            self._conn = None


def make_batches(
    indices: list[int], texts: list[str], target_len: int = BING_BATCH_CHARS
) -> list[list[int]]:
    batches: list[list[int]] = []
    current: list[int] = []
    length = 0
    for index in indices:
        size = len(normalize_source(texts[index]))
        if size > target_len:
            if current:
                batches.append(current)
                current = []
                length = 0
            batches.append([index])
            continue
        extra = size + (BING_BATCH_MARKER_COST if current else 0)
        if current and (
            length + extra > target_len or len(current) >= BING_BATCH_ITEMS
        ):
            batches.append(current)
            current = []
            length = 0
            extra = size
        current.append(index)
        length += extra
    if current:
        batches.append(current)
    return batches


class Translator:
    def __init__(
        self,
        cache_path: str | None = None,
        log=None,
        engine: str = "auto",
        target: str = TARGET_LANG,
    ) -> None:
        self.log = log or (lambda message: None)
        self.target = target
        self.bing = BingEngine(self.log, target)
        self.mymemory = MyMemoryEngine(target)
        self.cache = TranslationCache(cache_path, target)
        self.engine = engine
        self.bing_disabled = engine == "mymemory"
        self._preflighted = False
        self._bing_failures = 0
        self._bing_batch_failures = 0
        self.translated_count = 0
        self.cache_hits = 0
        self.failed_count = 0

    def summary(self) -> str:
        return (
            f"translated {self.translated_count}, cache hits {self.cache_hits}, "
            f"failed {self.failed_count}"
        )

    def preflight(self) -> None:
        """Channel probe. Let translate_texts call it - never call it up front."""
        probe = "Hello, how are you?"
        if not self.bing_disabled:
            try:
                result = self.bing.translate(probe)
                if result.strip() and result.strip() != probe:
                    self.log("bing channel ready")
                    self._preflighted = True
                    return
            except Exception as exc:
                self.log(f"bing channel unavailable ({type(exc).__name__}), trying fallback")
        try:
            if self.mymemory.translate(probe).strip():
                self.bing_disabled = True
                self.log("fallback channel ready")
                self._preflighted = True
                return
        except Exception as exc:
            raise TranslationError(f"no channel reachable: {type(exc).__name__}") from exc
        raise TranslationError("channels silent")

    def translate_texts(self, texts: list[str]) -> list[str]:
        total = len(texts)
        results: list[str | None] = [None] * total
        pending: list[int] = []

        for index, source in enumerate(texts):
            normalized = normalize_source(source)
            if not normalized:
                results[index] = source
                continue
            engine = "mymemory" if self.bing_disabled else "bing"
            cached = self.cache.get(engine, normalized)
            if cached is not None:
                results[index] = cached
                self.cache_hits += 1
                continue
            pending.append(index)

        if pending:
            if not self._preflighted:
                self.preflight()
            for batch in make_batches(pending, texts):
                batch_texts = [normalize_source(texts[index]) for index in batch]
                assigned = False
                if not self.bing_disabled:
                    try:
                        translated_list = self.bing.translate_batch(batch_texts)
                        if len(translated_list) != len(batch):
                            raise TranslationError("batch count mismatch")
                        for index, translated in zip(batch, translated_list):
                            results[index] = translated
                            self.cache.set("bing", normalize_source(texts[index]), translated)
                            self.translated_count += 1
                        self._bing_failures = 0
                        self._bing_batch_failures = 0
                        assigned = True
                    except Exception:
                        self._bing_batch_failures += 1
                        self._bing_failures += 1
                        self.log("batch failed, this batch uses the fallback channel")
                        if self._bing_batch_failures >= 2:
                            self.bing_disabled = True
                            self.log("bing failed repeatedly, switching remaining text to fallback")
                if assigned:
                    continue
                for index in batch:
                    source = normalize_source(texts[index])
                    translated, used = self._translate_one(source)
                    results[index] = translated
                    if used:
                        self.cache.set(used, source, translated)
        return [results[index] or texts[index] for index in range(total)]

    def _translate_one(self, text: str) -> tuple[str, str]:
        if not self.bing_disabled:
            try:
                translated = self.bing.translate(text)
                self._bing_failures = 0
                self.translated_count += 1
                return translated, "bing"
            except Exception:
                self._bing_failures += 1
                if self._bing_failures >= 3:
                    self.bing_disabled = True
                    self.log("bing failed 3 times, switching remaining text to fallback")
        try:
            translated = self.mymemory.translate(text)
            self.translated_count += 1
            return translated, "mymemory"
        except Exception:
            self.failed_count += 1
            self.log("segment failed, keeping source text")
            return text, ""


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probe", action="store_true", help="test both channels and exit")
    parser.add_argument("--text", action="append", default=[], help="segment to translate")
    parser.add_argument("--file", help="file with one segment per line")
    parser.add_argument("--cache", help="sqlite cache path")
    parser.add_argument("--engine", choices=("auto", "bing", "mymemory"), default="auto")
    parser.add_argument("--to", default=TARGET_LANG, help="target language code")
    args = parser.parse_args(argv)

    try:
        translator = Translator(args.cache, log=_log, engine=args.engine, target=args.to)
        if args.probe:
            translator.preflight()
            print(translator.bing.host if not translator.bing_disabled else "mymemory")
            return 0
        texts = list(args.text)
        if args.file:
            with open(args.file, encoding="utf-8") as handle:
                texts.extend(line for line in handle.read().splitlines() if line.strip())
        if not texts:
            _log("nothing to translate (use --text or --file)")
            return 2
        for translated in translator.translate_texts(texts):
            print(translated)
        _log(translator.summary())
        return 0 if translator.failed_count == 0 else 1
    except TranslationError as exc:
        _log(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        _log("ERROR: interrupted")
        return 130
    except Exception as exc:
        _log(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

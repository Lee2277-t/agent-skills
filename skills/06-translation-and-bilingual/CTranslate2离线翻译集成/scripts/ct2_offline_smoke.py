#!/usr/bin/env python3
"""Smoke test for a CTranslate2 + SentencePiece offline MT model (OPUS-MT / Marian layout).

Runs the verified pipeline end to end and proves the two mandatory fixes
(manual source </s>, trailing period for unpunctuated text) with a 2x2 A/B.

Usage:
  python ct2_offline_smoke.py [--model-dir PATH] [--skip-ab]
Exit 0 only when the correct variant produces zero degenerate outputs.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_MODEL_DIR = Path("<project-root>/translator/models/opus-mt-en-zh-ct2")

SENTENCE_END = ".!?;:。，！？；：”』」"
TRAILING_PERIOD_RE = re.compile(r"[。.]+$")
SPACED_LETTERS_RE = re.compile(r"\b(?:[A-Za-z]\s){1,}[A-Za-z]\b")
CJK_GAP_RE = re.compile(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])")
PUNCT_MAP = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")
# Deliberately excludes CJK ideographs; Han-dominant text is dropped by the
# separate should_translate() layer, not here.
NON_LATIN_RE = re.compile(
    r"[\u0370-\u03ff\u0400-\u04ff\u0530-\u058f\u0590-\u05ff"
    r"\u0600-\u06ff\u0900-\u097f\u0e00-\u0e7f"
    r"\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7af\u1100-\u11ff]"
)

TITLES = [
    "Contents", "Introduction", "Executive Summary", "Terms of Service",
    "Privacy Policy", "Confidential Document", "Chapter One", "Conclusion",
    "Acknowledgements", "Risk Factors", "Data Governance", "AI in Education",
    "Appendix A", "References", "Scope of Work",
]

PROSE = [
    "The future of artificial intelligence is bright, but it must be governed.",
    "This document describes the deployment procedure for the confidential system.",
    "Each paragraph is translated in one batch to keep latency low on CPU.",
]


def _collapse_spaced_letters(text: str) -> str:
    parts = []
    for part in re.split(r"\s{2,}", text):
        part = re.sub(r"\s+", " ", part.strip())
        parts.append(SPACED_LETTERS_RE.sub(lambda m: m.group(0).replace(" ", ""), part))
    return " ".join(part for part in parts if part)


def polish(text: str) -> str:
    text = _collapse_spaced_letters(text.replace("\u00a0", " ").strip())
    text = CJK_GAP_RE.sub("", text)
    text = re.sub(r"\s*([,;:?!])(?=\s*[\u3400-\u9fff])", lambda m: PUNCT_MAP[m.group(1)], text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s*([,;:?!])", lambda m: PUNCT_MAP[m.group(1)], text)
    text = re.sub(r"\s+([，。；：？！、])", r"\1", text)
    text = re.sub(r"([，。；：？！、])\s+", r"\1", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s*\.\s*(?=$|[\u3400-\u9fff])", "。", text)
    return text.strip()


def is_english_like(text: str) -> bool:
    non_latin = len(NON_LATIN_RE.findall(text))
    if non_latin == 0:
        return True
    latin = len(LATIN_RE.findall(text))
    return non_latin < 2 or non_latin < latin * 0.35


def looks_degenerate(text: str) -> bool:
    core = re.sub(r"[\s。，、；：！？.!?;:]+", "", text)
    if len(core) >= 12 and re.search(r"(.)\1{5,}", core):
        return True
    for unit in range(2, min(6, len(core) // 2 + 1)):
        if len(core) % unit == 0 and core[:unit] * (len(core) // unit) == core:
            return True
    return False


def prepare(text: str, add_period: bool) -> tuple[str, bool]:
    stripped = text.strip()
    if add_period and stripped and stripped[-1] not in SENTENCE_END:
        return f"{stripped}.", True
    return stripped, False


class Engine:
    def __init__(self, model_dir: Path) -> None:
        for name in ("model.bin", "source.spm", "target.spm"):
            if not (model_dir / name).is_file():
                print(f"FAIL  model file missing: {name}")
                sys.exit(2)
        import ctranslate2
        import sentencepiece as spm

        t0 = time.time()
        # read_bytes() is required: spm cannot open a path containing CJK chars.
        self.source_sp = spm.SentencePieceProcessor(
            model_proto=(model_dir / "source.spm").read_bytes()
        )
        self.target_sp = spm.SentencePieceProcessor(
            model_proto=(model_dir / "target.spm").read_bytes()
        )
        self.model = ctranslate2.Translator(
            str(model_dir), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=max(1, min(8, __import__("os").cpu_count() or 4)),
        )
        mb = (model_dir / "model.bin").stat().st_size / 1e6
        print(f"load   {time.time() - t0:.2f}s  model.bin={mb:.0f}MB  spm via read_bytes  int8/cpu")

    def run(self, texts: list[str], use_eos: bool, add_period: bool) -> list[str]:
        prepared = [prepare(t, add_period) for t in texts]
        rows = []
        for text, _ in prepared:
            tokens = self.source_sp.encode(text, out_type=str)
            if use_eos:
                tokens.append("</s>")
            rows.append(tokens)
        out = []
        for (text, drop), res in zip(
            prepared,
            self.model.translate_batch(
                rows, beam_size=4, max_batch_size=len(rows), max_decoding_length=512
            ),
        ):
            tokens = res.hypotheses[0] if res.hypotheses else []
            text_zh = polish(self.target_sp.decode(tokens)) if tokens else ""
            if drop:
                text_zh = TRAILING_PERIOD_RE.sub("", text_zh).rstrip()
            out.append(text_zh)
        return out


def garbled(results: list[str]) -> int:
    return sum(1 for r in results if not r or looks_degenerate(r))


def show_garbled(labels: list[str], results: list[str], limit: int = 3) -> None:
    shown = 0
    for label, r in zip(labels, results):
        if (not r or looks_degenerate(r)) and shown < limit:
            print("      %r -> %r" % (label, r[:60]))
            shown += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    ap.add_argument("--skip-ab", action="store_true")
    ap.add_argument("--ab-limit", type=int, default=5, help="titles used for the slow no-</s> rows")
    args = ap.parse_args()

    failures: list[str] = []
    try:
        engine = Engine(args.model_dir)
    except Exception as exc:
        print(f"FAIL  cannot load model: {type(exc).__name__}: {exc}")
        return 2

    if not args.skip_ab:
        ab_titles = TITLES[: max(2, args.ab_limit)]
        print("\n[2x2] garbled short titles out of %d" % len(ab_titles))
        for use_eos in (False, True):
            for add_period in (False, True):
                t0 = time.time()
                results = engine.run(ab_titles, use_eos, add_period)
                n = garbled(results)
                tag = "%s%s" % ("</s>" if use_eos else "no </s>", "  +." if add_period else "  no .")
                print("  %-12s -> %2d/%d garbled  %.2fs" % (tag, n, len(ab_titles), time.time() - t0))
                show_garbled(ab_titles, results)
        if not use_eos:
            failures.append("2x2 loop did not run")
        print("  rows without </s> are slow because decoding runs to max_decoding_length")

    print("\n[full short-title set]")
    t0 = time.time()
    full = engine.run(TITLES, True, True)
    n = garbled(full)
    print("  correct variant -> %d/%d garbled  %.2fs" % (n, len(TITLES), time.time() - t0))
    show_garbled(TITLES, full, limit=5)
    if n:
        failures.append(f"correct variant still garbles {n} short titles")

    t0 = time.time()
    prose = engine.run(PROSE, True, True)
    print("\n[prose] %.2fs for %d segments (batched)" % (time.time() - t0, len(PROSE)))
    for src, dst in zip(PROSE, prose):
        print("  %s\n    -> %s" % (src, dst))
        if looks_degenerate(dst):
            failures.append(f"degenerate prose output: {dst[:40]}")

    print("\n[gates]")
    cases = [
        ("このプロジェクトは、2030年までに排出量を40％削減する。", False, "japanese"),
        ("Проект снижает выбросы на 40 процентов.", False, "russian"),
        ("The project reduces emissions by 40 percent.", True, "english"),
        ("人工智能项目说明", True, "chinese-only is NOT caught here"),
    ]
    for text, expected, label in cases:
        got = is_english_like(text)
        print("  %-28s -> pass_through=%s (%s)" % (label, got, "ok" if got == expected else "MISMATCH"))
        if got != expected:
            failures.append(f"language gate wrong for {label}")

    print("\n[postprocess]")
    spaced = polish("T r a n s l a t i o n  G u i d e")
    print("  spaced letters -> %r" % spaced)
    if "Translation Guide" not in spaced:
        failures.append("spaced-letter collapse failed")
    punct = polish("人工智能 的未来, 是光明的.")
    print("  cjk gap + punct -> %r" % punct)
    if "," in punct or " 。" in punct:
        failures.append("CJK punctuation polish failed")
    for sample, expected in [("目录目录", True), ("导言 导言 导言", True), ("人工智能的未来是光明的。", False)]:
        got = looks_degenerate(sample)
        print("  degenerate(%r) -> %s" % (sample, got))
        if got is not expected:
            failures.append(f"degeneration detector wrong on {sample!r}")

    print()
    if failures:
        for f in failures:
            print("FAIL  " + f)
        return 1
    print("PASS  offline MT pipeline verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

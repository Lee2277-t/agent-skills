---
name: ctranslate2-offline-mt-integration
description: "Integrate and debug a CTranslate2 + SentencePiece offline MT model (OPUS-MT / Marian) on Windows: load a converted model from a CJK path, add the mandatory source </s>, inject sentence-final punctuation for short titles, batch-decode on CPU with int8, detect repetition degeneration, gate non-English input, and prove a confidential mode makes zero network calls. Use when wiring an offline translation engine, when offline output shows repeated garbage such as 目录目录 or 导言 导言 导言, when sentencepiece fails to open source.spm, when add_source_eos is false in the model config, when offline translation is unexpectedly slow, or when a no-network / no-cache confidentiality claim needs verification. Trigger words: CTranslate2, ct2, OPUS-MT, Marian, SentencePiece, 离线翻译, 保密模式, 断网, add_source_eos, compute_type, translate_batch."
---

# CTranslate2 offline MT integration

## Overview

A converted OPUS-MT/Marian model loaded straight through `ctranslate2` + `sentencepiece`
(no transformers, no torch) translates on CPU in milliseconds — but the defaults are
wrong in four specific ways, and each one produces a distinct failure mode. This skill
records the verified load → encode → decode → post-process → language-gate → zero-network
pipeline so it does not have to be rediscovered by trial and error.

Scope: English → Chinese with `opus-mt-en-zh-ct2` (~150 MB `model.bin`). Other language
pairs need a different converted model and must be re-run through the smoke test; nothing
here was verified for multilingual or NLLB-style models.

## When to use

- Adding a local offline translation engine to an app (Word/PDF/text batch translation).
- Offline output is repetitive garbage, or short headings/titles mistranslate.
- `SentencePieceProcessor` cannot open the `.spm` file (path contains non-ASCII characters).
- Someone claims the process never touches the network and that claim needs proof.

## Stage 1 — load

```python
import ctranslate2, sentencepiece as spm, os
source_sp = spm.SentencePieceProcessor(model_proto=(model_dir / "source.spm").read_bytes())
target_sp = spm.SentencePieceProcessor(model_proto=(model_dir / "target.spm").read_bytes())
engine = ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8",
                                inter_threads=1, intra_threads=max(1, min(8, os.cpu_count() or 4)))
```

Rules that are not optional:

- **Pass the model as bytes.** `spm.SentencePieceProcessor(model_path)` fails to open a
  `.spm` whose path contains CJK characters. `model_proto=(...).read_bytes()` is the
  workaround; keep using it even on ASCII paths so the code has one behaviour.
- **Use the right spm per side.** `source.spm` encodes, `target.spm` decodes. Decoding
  target tokens with `source_sp` leaves `▁` marks in the text.
- **`compute_type="int8"` on CPU.** `float16`/`default` either errors or runs slower with
  more RAM on CPU. (`int8_float16` is the CUDA choice, not this one.)
- Load lazily and cache the engine; first load dominates the cost (measured 0.43 s for a
  156 MB `model.bin` here, but it is the only expensive call — do it once per process).
- Validate `model.bin`, `source.spm`, `target.spm` exist before loading, and raise a
  human-readable error naming the model folder.

## Stage 2 — encode: add `</s>` by hand

**The converted `config.json` is misleading.** It ships `"add_source_eos": false`, which
describes the *transformers* wrapper, not a raw `translate_batch` call. Without the source
end-of-sequence token the model repeats and drifts:

```python
tokens = source_sp.encode(text, out_type=str)
tokens.append("</s>")          # required; config's add_source_eos=false does NOT mean this
```

Missing `</s>` costs far more than quality: decoding runs to `max_decoding_length` (512),
so 15 short titles took 63 s instead of 0.16 s. If an offline job is inexplicably slow,
check the EOS token before tuning anything else.

Do **not** add a `<s>` BOS token — `add_source_bos` is also false for Marian models.

## Stage 3 — decode: inject punctuation for short text

Headings, TOC entries, and labels without sentence-final punctuation are the model's
weakest input class: they collapse into `目录目录`, `导言 导言 导言`. The fix is a
round-trip trick — add a period to the source when there is no sentence-final mark, then
strip it from the translation:

```python
SENTENCE_END = ".!?;:。，！？；：”』」"
TRAILING_PERIOD_RE = re.compile(r"[。.]+$")

def prepare(text, add_period=True):
    s = text.strip()
    if add_period and s and s[-1] not in SENTENCE_END:
        return s + ".", True          # second value = strip the period after decoding
    return s, False

text, drop = prepared
out = polish(target_sp.decode(hypothesis_tokens))
if drop:
    out = TRAILING_PERIOD_RE.sub("", out).rstrip()
```

Track `drop` per item and thread it through batch results (`zip(indices, prepared, rows)`),
otherwise the injected `。` leaks into headings. For a long paragraph split into pieces,
only the **last** piece may drop its period, or sentence boundaries disappear.

Measured on 15 short titles: `</s>` alone → 5 garbled, `</s>` + period → 1.
The original session measured 5 → 0 on its own 15-item set, so treat "0" as
model-dependent, not guaranteed — always re-measure with `scripts/ct2_offline_smoke.py`.

## Stage 4 — batch, with a per-item fallback

Single-sentence `translate()` calls are the wrong shape. Group items and call once:

```python
engine.translate_batch(token_rows, beam_size=4, max_batch_size=len(token_rows),
                       max_decoding_length=512)
```

- Bucket by **both** count and characters (verified values: 24 items / 6000 chars) so a
  batch of long paragraphs does not dominate the batch.
- Over-length text (> ~1200 chars) goes down a separate path: split, translate the pieces
  as one batch, join, then re-polish the joined string. If any piece comes back empty, or
  the joined string looks degenerate, keep the source.
- If `translate_batch` raises, retry the affected items **one at a time** instead of
  failing the document; report the fallback once, not per item.
- Keep a per-process in-memory `{source: translation}` memo — documents repeat headings
  and footers a lot. Do not persist it to disk in confidential mode.

## Stage 5 — post-process

Order matters: collapse letter-spacing → fix CJK gaps/punctuation → drop injected period.

```python
SPACED_LETTERS_RE = re.compile(r"\b(?:[A-Za-z]\s){1,}[A-Za-z]\b")
CJK_GAP_RE = re.compile(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])")
PUNCT_MAP = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
```

- **Letter-spacing carried over from the source.** PDFs often extract as `D e m o`, and the
  model copies it through. Split on runs of 2+ spaces, then remove single spaces inside
  sequences of isolated Latin letters (`T r a n s l a t i o n` → `Translation`).
- **Full-width gaps between CJK characters** from the same extraction: delete whitespace
  between two Han characters.
- Map ASCII `,;:?!` to full-width when adjacent to Han, and drop whitespace around CJK
  punctuation. Convert a leftover `.` sitting between Han characters into `。`.
- **Repetition guard as the last resort** — a guard is still needed because the period
  trick only lowers the failure rate:

```python
def looks_degenerate(text):
    core = re.sub(r"[\s。，、；：！？.!?;:]+", "", text)
    if len(core) >= 12 and re.search(r"(.)\1{5,}", core):
        return True
    for unit in range(2, min(6, len(core) // 2 + 1)):
        if len(core) % unit == 0 and core[:unit] * (len(core) // unit) == core:
            return True
    return False
```

Strip punctuation/whitespace **before** the unit-repetition test, or `目录 目录` slips
through. When it fires, keep the source text, count it as failed, and cap the log lines
(e.g. first 5, then every 25th) so a bad document cannot flood the UI log.

## Stage 6 — language gate

An English→Chinese model mangles any language it was not trained on, and mangling is
silent. Two layers, and they do different jobs:

```python
NON_LATIN_RE = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0530-\u058f\u0590-\u05ff"
                          r"\u0600-\u06ff\u0900-\u097f\u0e00-\u0e7f"
                          r"\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7af\u1100-\u11ff]")
LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")

def is_english_like(text):
    non_latin = len(NON_LATIN_RE.findall(text))
    if non_latin == 0:
        return True
    latin = len(LATIN_RE.findall(text))
    return non_latin < 2 or non_latin < latin * 0.35
```

- `non_latin < 2` keeps acronyms and units (`CO₂ 40 %`, one stray symbol) translatable;
  the 0.35 ratio rejects Japanese/Korean/Russian/Arabic bodies while allowing a mostly
  English sentence that quotes one foreign term.
- **This set deliberately omits CJK ideographs.** A pure-Chinese string is
  "english-like" here by design, because a separate pre-filter (`should_translate`-style:
  URL / e-mail / version-number / symbol-only skip, plus "≥40 % Han → already Chinese,
  don't translate") decides those. Reusing only `is_english_like` sends Chinese text to
  an en→zh model and returns worse Chinese. Keep both layers together.
- Count and report how many segments were kept as "not English", and raise a clear error
  when *nothing* in the document was translatable, instead of returning a silent copy.

## Confidential mode: making the no-network claim real

"Best effort offline" is not a security property. Block at the socket layer inside the
process, before any other import, and disable file logging + the disk cache in the same
branch:

```python
def _block_network(*_args, **_kwargs):
    raise OSError("保密模式已禁用网络连接")

socket.socket.connect = _block_network
socket.socket.connect_ex = _block_network
socket.create_connection = _block_network
socket.getaddrinfo = _block_network
```

All four matter: `getaddrinfo` alone still lets a literal-IP `connect()` through, and
patching only `create_connection` misses `http.client`/`urllib` paths that build a socket
directly. `connect_ex` is patched so the non-raising variant cannot silently return an
error code that callers ignore. `ctranslate2` is C++ and does not route inference through
Python sockets, so the hooks do not break translation — which is exactly what to verify.

Prove it rather than asserting it (run inside the real app process, or with
`scripts/prove_no_network.py`):

1. Snapshot `size` + `mtime` of `logs/app.log` and `cache/*.sqlite` **before** the work.
2. Fire real probes — `urllib.request.urlopen`, `socket.create_connection`,
   `getaddrinfo`, `connect_ex` — every one must raise. A probe that succeeds means the
   block is incomplete.
3. Do the full translation, then re-snapshot: same size and `mtime_ns`, and no new files.
4. Confirm the model itself loads and infers with the hooks installed.
5. UI hygiene for the same mode: no run log file, in-memory-only translation cache, and
   the window log shows file **names**, not full paths.

State two limits whenever shipping this: an offline model's quality is below an online
API (short titles and abbreviations mistranslate — `"AI in Education"` came out as
`《教育法》`, `"Confidential Document"` as `机密化文件`), and running locally is **not** a
security clearance — classified machines still require the organisation's software review
and controlled deployment. Keep the model's licence attribution (OPUS-MT is CC-BY-4.0).

## Troubleshooting

| Symptom | Root cause | Fix |
|---|---|---|
| `目录目录`, `导言 导言 导言` on headings | no sentence-final punctuation in source | Stage 3 period injection + Stage 5 guard |
| Repetition/drift on every sentence | missing source `</s>` | Stage 2; ignore `add_source_eos: false` |
| Offline job takes minutes for one page | missing `</s>` → decoding to `max_decoding_length` | Stage 2, then re-measure |
| `Unable to open ...spm` / spm init error | CJK in model path | `model_proto=read_bytes()` |
| `▁` fragments in output | decoded with `source.spm` | decode with `target.spm` |
| float16 error / huge RSS on CPU | wrong `compute_type` | `int8` on CPU, `int8_float16` on CUDA |
| `D e m o` in the译文 text | letter-spacing copied from the source PDF | Stage 5 `_collapse_spaced_letters` |
| `D e m o` only in the rendered PDF, correct text layer | PDF library's built-in CJK font renders Latin full-width | embed a real TTF (`msyh.ttc`/`simhei.ttf`/`simsun.ttc`) — this is a font bug, not a translation bug |
| Japanese/Russian paragraphs mangled | no language gate | Stage 6 |
| Network call succeeds in confidential mode | fewer than four socket hooks patched | patch `connect`, `connect_ex`, `create_connection`, `getaddrinfo` |

## Scripts

- `scripts/ct2_offline_smoke.py [--model-dir PATH] [--skip-ab] [--ab-limit N]`
  Loads the model and asserts the pipeline: 2×2 A/B (`</s>` × period) with garbled counts
  and timings, prose samples, language-gate cases, post-process checks. UTF-8-forced stdout.
  Exits non-zero when the correct variant still degenerates or a gate/post-process check
  is wrong. Re-run it after changing **any** decoding parameter.
- `scripts/prove_no_network.py --watch FILE [--watch FILE] [--model-dir PATH]`
  Installs the four socket hooks, fires `urlopen`/`create_connection`/`getaddrinfo`/
  `connect_ex` probes, optionally runs inference under the hooks, and diffs size+mtime of
  watched log/cache files. Exits non-zero on any reachable probe or any file change.

Both need `ctranslate2` and `sentencepiece` in the interpreter (an app venv is enough;
no torch, no transformers). Use the app's own venv python, not a system interpreter.

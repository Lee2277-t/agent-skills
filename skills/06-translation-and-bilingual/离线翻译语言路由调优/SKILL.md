---
name: offline-mt-language-routing-tuning
description: "Tune and forensically verify language routing in an offline multi-model MT app (small English model plus an NLLB-style multilingual model): probe every extracted segment's verdict with letter counts and detector confidence, raise the Latin gate so short English titles stay on the English model (measured ≥40 letters AND prob ≥0.9), put an exact-match heading lookup before should_translate to kill whole-sentence hallucinations on short titles and rescue kanji-only Japanese headings skipped as Chinese, then quantify the payoff with a peak-RSS A/B. Use when a plain English document loads the ~800 MB multilingual model, when 意大利文/西班牙文 shows up in the per-language counts of an English file, when short headings translate to unrelated sentences, or when routing thresholds must be re-tuned after a model swap. Trigger words: 语种路由, 语种误判, 多语种模型误加载, langdetect 阈值, 短标题查表, heading lookup, should_translate 顺序, 峰值内存, route probe, NLLB routing."
---

# Offline MT language routing tuning

## Overview

A two-model offline pipeline (fast English→Chinese Marian model + a large multilingual
model) misroutes on **short** segments, and each misroute costs a model load. Fix it in
this order: gather the verdict distribution first, tighten the gate second, cover short
titles with a deterministic lookup third, and prove the payoff in peak memory and time.
Never tune the threshold before printing the per-segment evidence — the numbers that look
reasonable are usually the wrong ones.

Reference implementation that these numbers came from: [<project-root>\translator\core\lang_detect.py](file:///<project-root>/translator/core/lang_detect.py),
[<project-root>\translator\core\heading_terms.py](file:///<project-root>/translator/core/heading_terms.py).

## Boundaries with neighbouring skills

- `ctranslate2-offline-mt-integration` — model loading, `</s>`, decode params, repetition
  garbage, zero-network proof. Not routing thresholds.
- `tkinter-gui-headless-e2e-qa` — driving the GUI and collecting `rss_before/rss_peak`.
  Reuse its harness for stage 6; don't rebuild it here.
- This skill owns only: verdict forensics → gate tuning → heading lookup placement →
  memory/latency quantification.

## Decision pipeline order (the invariant)

Per segment, gates must run in exactly this order:

1. empty after normalisation → keep source.
2. `lookup(text)` exact heading-table hit → return the Chinese term. **Must precede the
   `should_translate` gate**, otherwise a kanji-only Japanese heading (`別添資料`) contains
   no Latin, is judged "already Chinese", and is skipped forever.
3. ambiguous short-fragment gate → keep source, log once.
4. `should_translate` → skip if not translatable.
5. script-dominant detection → language model routing.

Keep the two engines non-overlapping: run the whole English group, `close()` that engine,
then load the multilingual one. Peak RSS is then `max(one model) + ~100 MB`, not the sum.

## Stage 1 — forensics first

Run the probe over the **extracted** segments, i.e. exactly what the translator sees,
including table cells and headers/footers — the misleading verdicts in a real document came
from a header and a table cell, not from body prose:

```
python scripts/route_probe.py --app-dir <project-root>/translator --docx "samples/示例-英文报告.docx"
```

Output is one line per segment (`label letters=NN guess=xx:0.99 | text`) plus a summary of
counts by label and the segments that force the multilingual model to load.

Two hard rules while probing:

- Point the probe at the **same file path the GUI used**. Reading a stale copy under a temp
  QA directory produced a probe/GUI contradiction that looked like a detector bug and cost a
  round of debugging.
- Treat the probe, not the app's per-run summary, as ground truth when they disagree about
  which *short* segments moved.

## Stage 2 — tighten the Latin gate

Require **both** conditions before letting a Latin-script segment leave the English model:

```python
if len(LATIN_RE.findall(sample)) < 40:
    return ENGLISH          # too short for any detector to be trusted
lang, prob = _guess(sample)
if lang == ENGLISH or prob < 0.9:
    return ENGLISH
```

Why the letter count matters more than the confidence — the decisive measurements:

| segment | letters | detector | verdict after gate |
|---|---|---|---|
| `Confidential · Demo Document` | 24 | `es:0.99` | English (prob alone would have routed it away) |
| `Climate model analysis` | 20 | `it:0.86` | English |
| `Le présent accord entre en vigueur à la date de sa signature.` | 62 | `fr:1.00` | French |
| `Il presente accordo entra in vigore alla data della sua firma.` | 68 | `it:1.00` | Italian |

A genuine foreign sentence is routinely >40 letters, so the gate costs almost nothing and
removes almost all false positives. High confidence on short text is **not** evidence.

## Stage 3 — detect by script first, detector second

Decide the script by character ranges (kana, hangul, Cyrillic, Arabic, Devanagari, Thai,
Greek, Hebrew, Georgian, Armenian) and let the statistical detector only *refine* within a
script family. Never let it choose the script: it guessed 日文 for Cyrillic input.

- Latin dominant → refine with the gate above, fall back to English.
- Cyrillic/Arabic/Devanagari dominant → keep the script code, optionally refine within it
  with its own minimum length and a `prob ≥ 0.5`.
- Nothing dominant (numbers, symbols, CJK-only) → return empty and let the caller keep
  source.

Strip digits and non-letters before feeding the detector.

## Stage 4 — deterministic heading lookup

Short document titles are where a 150 MB model hallucinates a whole unrelated sentence.
Measured before a lookup table existed: `Оглавление → 这就是头部`, `Таблица 3 → 现在，我们要做什么呢？`.
After: `目录`, `表3`.

Build `core/heading_terms.py` with:

- A `HEADINGS` dict keyed by normalised text (trim edge punctuation both ways, collapse
  whitespace, lowercase) covering the titles that recur in the target corpus: contents,
  list of figures/tables, appendix, introduction, preface, bibliography, chapter, table,
  figure — per supported language.
- `lookup(text) -> str`: reject keys longer than ~40 chars, try the exact key, then strip a
  trailing 1–3 digit number (`TRAILING_NUMBER_RE`) and format the base entry (`Таблица 3`
  → `表3`). Return `""` on a miss.
- **Exact match only.** A substring or fuzzy match will "translate" genuine Chinese
  headings and turn the lookup into a new bug class.
- Also fix the CJK blind spot: kanji-only headings (`別添資料`) are invisible to any
  Latin-based skip rule, so the lookup is the only thing that saves them.
- Keep the module dependency-free so the online path and the GUI can both import it without
  a circular import back into the translator.

Wire it in **before** `should_translate` (stage order above) and count hits separately so
the summary can say how many segments were served by the table.

## Stage 5 — short-fragment keep-source gate

For fragments too short to detect and too obscure for the table, keep the source instead of
guessing:

```python
def is_ambiguous_fragment(text):
    letters = LATIN_OR_CYRILLIC_RE.findall(text)
    if not letters:
        return False                      # kana/hangul/thai are decided by script alone
    return len(text.split()) <= 3 and len(letters) <= 24
```

Keep source, increment a counter, and log the behaviour **once per run** — not per segment.
State the tradeoff explicitly to the user: a real short French or German sentence will come
back untranslated. Under-translation is the intended failure mode; wrong-language
hallucination is not.

## Stage 6 — quantify the payoff

The point of the gate is memory and time, so measure both, same fixtures, same harness:

| English 26-segment docx | elapsed | peak RSS | cause |
|---|---|---|---|
| before tuning | 3.45 s | 1079 MB | 2 segments judged Italian, 1 Spanish |
| after tuning | 1.7–2.0 s | 443–540 MB | no multilingual load at all |

Load cost of the multilingual model was ~10 s and ~800 MB, so a single false positive is
expensive. Report the A/B numbers, and confirm with the interface log that the "loading
multilingual model" line no longer appears for an English file. Mixed-language documents
should stay near the old peak — that is expected, they genuinely need both models.

## Regression assertions (run in both directions)

After any threshold change:

1. English fixture → probe reports 100% English; app loads only the English model.
2. ≥60-letter foreign sentences → each still routes to its correct language (no loss).
3. Mixed-language fixture → per-language segment counts and placed/skipped counts unchanged.
4. Short-title fixtures per language → served by lookup, output matches the table, and
   Japanese kanji headings are no longer skipped as Chinese.
5. Full GUI pass on every fixture with the usual no-network / no-cache forensics.

## Pitfalls

- Chasing detector randomness: `DetectorFactory.seed` already defaults to `0`, langdetect is
  deterministic. The real cause was short Latin segments — don't add seeding code.
- Probing the document body only and concluding "routing is fine" while a header segment
  moves to the multilingual model.
- Placing the lookup after `should_translate`: the Japanese-kanji case never reaches it.
- Letting the lookup match loosely, or match long text — it becomes a translation oracle.
- Copying 40 / 0.9 / 24 / 3 to a different model pair or corpus without re-running the
  probe. They were fitted to an English→Chinese Marian model plus NLLB-200 int8 on one
  document set.
- Forgetting that a higher gate silently drops short foreign sentences; surface the
  kept-as-source count in the summary.
- On Windows, reconfigure stdout to UTF-8 before printing Chinese labels, or the probe dies
  on a `gbk` encode error.

## Resources

- `scripts/route_probe.py` — per-segment verdict probe. Import path is injected from
  `--app-dir`; run it with the app's own interpreter so `langdetect` (and `python-docx` for
  `--docx`) resolve. `--module` / `--detect` override the routing module and function;
  `--segments FILE` (one segment per line) bypasses document extraction.

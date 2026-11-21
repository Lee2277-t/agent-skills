#!/usr/bin/env python3
"""Print per-segment language-routing verdicts for an offline MT app.

Run with the app's own interpreter so langdetect (and python-docx for --docx) resolve.
"""
import argparse
import io
import re
import sys
from collections import Counter

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LATIN_FALLBACK = re.compile(r"[A-Za-zÀ-ɏ]")


def fail(msg):
    print("FAIL " + msg)
    raise SystemExit(1)


def read_segments(args):
    if args.segments:
        with io.open(args.segments, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    if args.docx:
        try:
            from docx import Document
            from docx.oxml.ns import qn
            from docx.text.paragraph import Paragraph
        except Exception:
            fail("python-docx missing; run with the app interpreter or use --segments")
        doc = Document(args.docx)
        texts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    texts.extend(p.text for p in cell.paragraphs)
        for section in doc.sections:
            for part in (section.header, section.footer,
                         section.first_page_header, section.even_page_header):
                if part is not None:
                    texts.extend(p.text for p in part.paragraphs)
        return [t.strip() for t in texts if t and t.strip()]
    return [line.strip() for line in sys.stdin if line.strip()]


def main():
    ap = argparse.ArgumentParser(description="route verdict probe")
    ap.add_argument("--app-dir", help="project root to prepend to sys.path")
    ap.add_argument("--module", default="core.lang_detect")
    ap.add_argument("--detect", default="detect")
    ap.add_argument("--guess", default="_guess")
    ap.add_argument("--heading-module", default="core.heading_terms")
    ap.add_argument("--docx", help="extract segments from this .docx")
    ap.add_argument("--segments", help="UTF-8 file, one segment per line")
    ap.add_argument("--limit", type=int, default=200, help="max rows to print")
    args = ap.parse_args()

    if args.app_dir:
        sys.path.insert(0, args.app_dir)
    try:
        module = __import__(args.module, fromlist=["*"])
        detect = getattr(module, args.detect)
    except Exception as exc:
        fail("cannot import %s.%s from %s: %s" % (args.module, args.detect,
                                                 args.app_dir or os.getcwd(), exc))

    label = getattr(module, "language_label", lambda code: code or "?")
    latin = getattr(module, "LATIN_RE", LATIN_FALLBACK)
    guess = getattr(module, args.guess, None)
    try:
        heads = __import__(args.heading_module, fromlist=["*"]).lookup
    except Exception:
        heads = lambda text: ""

    segments = read_segments(args)
    if not segments:
        fail("no segments read")

    counts = Counter()
    multilingual = []
    for text in segments:
        code = detect(text) or ""
        counts[label(code)] += 1
        letters = len(latin.findall(text))
        sample = re.sub(r"[0-9\s\W]+", " ", text).strip()
        guess_str = "-"
        if guess:
            try:
                raw, prob = guess(sample)
                guess_str = "%s:%.2f" % (raw, prob)
            except Exception:
                guess_str = "err"
        term = heads(text)
        if code and code not in ("en", "eng_Latn"):
            multilingual.append(text)
        print("%-8s letters=%3d guess=%-9s term=%s | %s" % (
            label(code), letters, guess_str, "Y" if term else "-", text[:70]))

    total = len(segments)
    print("---")
    print("segments %d | %s" % (total, " ".join("%s=%d" % kv for kv in counts.most_common())))
    print("forces-multilingual-load %d" % len(multilingual))
    for text in multilingual[: args.limit]:
        print("  MOVE %s" % text[:70])
    if total > args.limit:
        print("(rows truncated at %d)" % args.limit)


if __name__ == "__main__":
    import os
    main()

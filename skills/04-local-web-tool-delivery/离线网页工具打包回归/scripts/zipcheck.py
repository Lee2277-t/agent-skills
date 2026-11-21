#!/usr/bin/env python3
"""Verify a Windows-built delivery zip round-trips: entry names, CRC, per-file MD5.

Use instead of Git Bash `unzip`, which mis-decodes UTF-8 entry names written by
Compress-Archive and reports mojibake / backslash warnings for a perfectly good zip.

stdout is an ASCII summary; full detail (Chinese entry names intact) goes to a UTF-8
report file. Exit 0 = PASS, 1 = FAIL, 2 = could not run.
"""
import argparse
import hashlib
import os
import sys
import tempfile
import zipfile

SKIP_PARTS = {"__MACOSX", ".git", "node_modules"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def emit(line):
    sys.stdout.write(line.encode("ascii", "replace").decode("ascii") + "\n")
    sys.stdout.flush()


def esc(text):
    return text.encode("unicode_escape").decode("ascii")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def skipped(rel):
    parts = rel.split("/")
    return any(p in SKIP_PARTS for p in parts[:-1]) or parts[-1] in SKIP_NAMES


def src_files(src_dir):
    out = {}
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS]
        for name in files:
            if name in SKIP_NAMES:
                continue
            full = os.path.join(root, name)
            out[os.path.relpath(full, src_dir).replace(os.sep, "/")] = full
    return out


def normalize_entries(entries, src):
    """Compress-Archive usually wraps everything in one folder named after the source dir."""
    if not entries or not src or set(entries) & set(src):
        return entries, False
    if any("/" not in e for e in entries):
        return entries, False
    if len({e.split("/", 1)[0] for e in entries}) != 1:
        return entries, False
    stripped = [e.split("/", 1)[1] for e in entries]
    if set(stripped) & set(src):
        return stripped, True
    return entries, False


def compare(zf, entries, src):
    ok, missing, diff, extra = [], [], [], []
    for rel, source in sorted(src.items()):
        if rel not in entries:
            missing.append(rel)
            continue
        archive_hash = hashlib.md5()
        with zf.open(entries[rel]) as archived:
            for chunk in iter(lambda: archived.read(1 << 20), b""):
                archive_hash.update(chunk)
        (ok if md5(source) == archive_hash.hexdigest() else diff).append(rel)
    extra = sorted(set(entries) - set(src))
    return ok, missing, diff, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path")
    ap.add_argument("src_dir")
    ap.add_argument("--report", default="", help="UTF-8 report path (default: %TEMP%)")
    args = ap.parse_args()

    zip_path, src_dir = os.path.abspath(args.zip_path), os.path.abspath(args.src_dir)
    if not os.path.isfile(zip_path):
        emit("ERROR zip not found: " + esc(zip_path))
        return 2
    if not os.path.isdir(src_dir):
        emit("ERROR src dir not found: " + esc(src_dir))
        return 2

    report_path = args.report or os.path.join(
        os.environ.get("TEMP", tempfile.gettempdir()), "zipcheck-report.txt"
    )
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            original_entries = [i.filename for i in zf.infolist()
                                if not i.is_dir() and not skipped(i.filename.replace("\\", "/"))]
            names = [name.replace("\\", "/") for name in original_entries]
            src = src_files(src_dir)
            entries, top_stripped = normalize_entries(names, src)
            if len(set(entries)) != len(entries):
                emit("ERROR duplicate normalized entry names")
                return 2
            ok, missing, diff, extra = compare(zf, dict(zip(entries, original_entries)), src)
    except zipfile.BadZipFile:
        emit("ERROR not a readable zip")
        return 2

    passed = bool(src) and not missing and not diff and not extra and bad is None

    detail = [
        "ZIP %s" % zip_path,
        "SRC %s" % src_dir,
        "TOP_STRIPPED %s" % ("yes" if top_stripped else "no"),
        "BAD_CRC %s" % (esc(bad) if bad else "none"),
        "SRC_FILES %d  ZIP_FILES %d" % (len(src), len(entries)),
        "OK %d" % len(ok),
    ]
    for label, items in (("MISSING", missing), ("DIFF", diff), ("EXTRA", extra)):
        detail.append("%s %d" % (label, len(items)))
        detail.extend("  %s" % i for i in items)
    detail.append("RESULT %s" % ("PASS" if passed else "FAIL"))
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(detail) + "\n")

    emit("TOP_STRIPPED %s" % ("yes" if top_stripped else "no"))
    emit("BAD_CRC %s" % ("none" if bad is None else "see report"))
    emit("SRC_FILES %d ZIP_FILES %d" % (len(src), len(entries)))
    emit("OK %d MISSING %d DIFF %d EXTRA %d" % (len(ok), len(missing), len(diff), len(extra)))
    emit("REPORT_ESCAPED %s" % esc(report_path))
    emit("RESULT %s" % ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

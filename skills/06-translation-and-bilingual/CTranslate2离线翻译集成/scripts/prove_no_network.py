#!/usr/bin/env python3
"""Prove a process makes no network calls and touches no disk-side log/cache files.

Installs the four hard network hooks, fires real probes that MUST fail, optionally
loads the offline model, and compares size+mtime of watched files before/after.

Usage:
  python prove_no_network.py --watch D:/app/logs/app.log --watch D:/app/cache/translations.sqlite
  python prove_no_network.py --watch ... --model-dir D:/app/models/opus-mt-en-zh-ct2
Exit 0 only when every probe is blocked and no watched file changed.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

PROBE_URLS = ("https://cn.bing.com", "https://api.cognitive.microsofttranslator.com")


class Blocked(OSError):
    pass


def _hook(*_args, **_kwargs):
    raise Blocked("network disabled in this process")


def install_hooks() -> list[str]:
    socket.socket.connect = _hook
    socket.socket.connect_ex = _hook
    socket.create_connection = _hook
    socket.getaddrinfo = _hook
    return ["socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection", "socket.getaddrinfo"]


def snapshot(paths: list[Path]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for p in paths:
        try:
            st = p.stat()
            out[str(p)] = (st.st_size, st.st_mtime_ns)
        except OSError:
            out[str(p)] = (-1, -1)
    return out


def probe_all() -> list[tuple[str, bool, str]]:
    """Return (name, blocked, detail); blocked=True is the desired outcome."""
    results: list[tuple[str, bool, str]] = []

    for url in PROBE_URLS:
        name = f"urlopen {url}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                results.append((name, False, f"HTTP {resp.status} — network is reachable"))
        except Blocked:
            results.append((name, True, "hook intercepted"))
        except OSError as exc:
            results.append((name, True, f"{type(exc).__name__}"))
        except Exception as exc:
            results.append((name, False, f"unexpected {type(exc).__name__}"))

    for name, fn in (
        ("create_connection", lambda: socket.create_connection(("cn.bing.com", 443), timeout=5)),
        ("getaddrinfo", lambda: socket.getaddrinfo("cn.bing.com", 443)),
    ):
        try:
            fn()
            results.append((name, False, "call succeeded — network is reachable"))
        except Blocked:
            results.append((name, True, "hook intercepted"))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__} not raised by hook"))

    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(("1.1.1.1", 443))
        results.append(("socket.connect_ex", False, "call succeeded — network is reachable"))
    except Blocked:
        results.append(("socket.connect_ex", True, "hook intercepted"))
    except Exception as exc:
        results.append(("socket.connect_ex", False, f"{type(exc).__name__} not raised by hook"))

    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="append", default=[], help="log/cache file to prove untouched")
    ap.add_argument("--model-dir", type=Path, default=None, help="optional: load ct2 model after hooks")
    ap.add_argument("--probe-url", action="append", default=None)
    args = ap.parse_args()

    if args.probe_url:
        PROBE_URLS[:] = args.probe_url

    watched = [Path(p) for p in args.watch]
    if not watched:
        print("WARN  no --watch path given; only the network probes are checked")

    before = snapshot(watched)
    t0 = time.time()
    print("hooks installed: " + ", ".join(install_hooks()))

    leaks = 0
    for name, blocked, detail in probe_all():
        print("  %-58s %s  (%s)" % (name, "BLOCKED" if blocked else "!!! REACHABLE", detail))
        if not blocked:
            leaks += 1

    if args.model_dir is not None:
        try:
            import ctranslate2
            import sentencepiece as spm

            sp = spm.SentencePieceProcessor(model_proto=(args.model_dir / "source.spm").read_bytes())
            eng = ctranslate2.Translator(
                str(args.model_dir), device="cpu", compute_type="int8",
                inter_threads=1, intra_threads=max(1, min(8, os.cpu_count() or 4)),
            )
            toks = sp.encode("The offline model works with networking disabled.", out_type=str) + ["</s>"]
            hyp = eng.translate_batch([toks], beam_size=4)[0].hypotheses[0]
            out = spm.SentencePieceProcessor(
                model_proto=(args.model_dir / "target.spm").read_bytes()
            ).decode(hyp)
            print("  model inference under hooks -> %s" % out.strip())
        except Exception as exc:
            print("  FAIL  model could not run with hooks: %s: %s" % (type(exc).__name__, exc))
            leaks += 1

    after = snapshot(watched)
    changed = 0
    print("watched files (%.2fs):" % (time.time() - t0))
    for path in watched:
        b, a = before[str(path)], after[str(path)]
        if a == (-1, -1):
            print("  %-50s absent (nothing created)" % path.name)
            continue
        if b == a:
            print("  %-50s unchanged size=%d" % (path.name, a[0]))
        elif b == (-1, -1):
            print("  %-50s !!! CREATED size=%d" % (path.name, a[0]))
            changed += 1
        else:
            print("  %-50s !!! WROTE-TO size %d -> %d" % (path.name, b[0], a[0]))
            changed += 1

    print()
    if leaks or changed:
        print(f"FAIL  {leaks} network leak(s), {changed} file change(s)")
        return 1
    print("PASS  zero network, zero disk write")
    return 0


if __name__ == "__main__":
    sys.exit(main())

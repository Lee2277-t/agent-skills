#!/usr/bin/env python3
"""Drive a Windows tkinter app end-to-end from the console, then take evidence.

Order that must not change: DPI awareness -> rewrite sys.argv -> import the app
module -> build the window -> drive it -> poll -> harvest UI log + file forensics.

Usage:
    python drive_tk_app.py --app-dir D:/tools/app --module app --class TranslatorApp \
        --flag --offline --file D:/tmp/doc.docx \
        --watch D:/tools/app/logs/app.log --watch D:/tools/app/cache \
        --shot D:/tmp/qa/shot.png --out-dir D:/tmp/qa

stdout lines are machine-readable. Exit 0 = run finished and evidence collected,
2 = timed out or app reported an error, 3 = could not start.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import os
import sys
import time
from pathlib import Path

MINUTE = 60.0


def _set_dpi_awareness() -> str:
    if sys.platform != "win32":
        return "n/a"
    import ctypes

    user32 = ctypes.windll.user32
    try:
        shcore = ctypes.windll.shcore
    except AttributeError:
        shcore = None
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_int
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    for label, call in (("per-monitor", lambda: shcore and shcore.SetProcessDpiAwareness(2) == 0),
                        ("system", lambda: bool(user32.SetProcessDPIAware()))):
        try:
            if call():
                return label
        except (AttributeError, OSError):
            pass
    return "unchanged"


def snapshot(paths: list[str]) -> dict[str, dict]:
    """size + mtime + sha256. mtime alone lies for SQLite (in-place page writes)."""
    state: dict[str, dict] = {}
    for raw in paths:
        root = Path(raw)
        files = [root] if root.is_file() else (sorted(p for p in root.rglob("*") if p.is_file())
                                               if root.is_dir() else [])
        if not files:
            state[str(raw)] = {"missing": True, "kind": "dir" if root.is_dir() else "absent"}
        for file in files:
            try:
                stat = file.stat()
            except OSError:
                continue
            entry = {"bytes": stat.st_size, "mtime": round(stat.st_mtime, 6)}
            if stat.st_size <= 8 * 1024 * 1024:
                digest = hashlib.sha256()
                with file.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(chunk)
                entry["sha256"] = digest.hexdigest()[:16]
            state[str(file)] = entry
    return state


def diff(before: dict, after: dict) -> list[str]:
    changed = []
    for path, entry in before.items():
        new = after.get(path)
        if new is None:
            changed.append(f"{path}=deleted")
        elif new != entry:
            keys = [k for k in entry if new.get(k) != entry[k]]
            changed.append(f"{path}={'+'.join(keys) or 'same'}")
    for path, entry in after.items():
        if path not in before:
            changed.append(f"{path}=created")
    return changed


def read_log_text(app) -> tuple[str, int]:
    for name in ("log_text", "log_widget", "txt_log"):
        widget = getattr(app, name, None)
        if widget is None:
            continue
        try:
            text = widget.get("1.0", "end-1c")
            return text, len([line for line in text.splitlines() if line.strip()])
        except Exception:
            continue
    return "", 0


def main() -> int:
    parser = argparse.ArgumentParser(description="unattended tkinter GUI driver")
    parser.add_argument("--app-dir", required=True, help="folder holding the app module")
    parser.add_argument("--module", default="app")
    parser.add_argument("--class", dest="cls", default="TranslatorApp")
    parser.add_argument("--flag", action="append", default=[],
                        help="mode switch injected into sys.argv BEFORE import (repeat), e.g. --flag --offline")
    parser.add_argument("--file", help="document to feed set_file(); omit to only build the window")
    parser.add_argument("--set-file", default="set_file")
    parser.add_argument("--start", default="start_translation")
    parser.add_argument("--cancel", default="cancel_translation")
    parser.add_argument("--cancel-after", type=float, default=0.0,
                        help="seconds of busy time before requesting cancel (0 = never)")
    parser.add_argument("--busy-attr", default="busy")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--poll", type=float, default=0.1)
    parser.add_argument("--pump-callback", default="_pump_events",
                        help="app method that drains the worker queue, called if update() stalls")
    parser.add_argument("--watch", action="append", default=[], help="file or dir to fingerprint (repeat)")
    parser.add_argument("--shot", help="also capture the window to this PNG")
    parser.add_argument("--out-dir", default="", help="write ui log / shot here")
    parser.add_argument("--onscreen", action="store_true",
                        help="leave the window where the app put it (default moves it off-screen)")
    args = parser.parse_args()

    app_dir = str(Path(args.app_dir).resolve())
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    os.chdir(app_dir)

    dpi = _set_dpi_awareness()

    # 1. argv first: mode switches read at module top level (OFFLINE = "--offline" in sys.argv)
    sys.argv = [args.module] + list(args.flag)
    try:
        module = importlib.import_module(args.module)
    except Exception as exc:
        print(f"DRIVE verdict=fail stage=import module={args.module} error={type(exc).__name__}: {exc}")
        return 3

    try:
        cls = getattr(module, args.cls)
        app = cls()
    except Exception as exc:
        print(f"DRIVE verdict=fail stage=construct class={args.cls} error={type(exc).__name__}: {exc}")
        return 3

    root = getattr(app, "root", None)
    if root is None:
        print(f"DRIVE verdict=fail stage=no-root attr=root class={args.cls}")
        return 3

    # 2. keep the GUI out of the user's way; PrintWindow still renders it
    if not args.onscreen:
        try:
            root.geometry("+%d+%d" % (-32000, -32000))
        except Exception:
            pass
    for _ in range(5):
        root.update()
        time.sleep(0.02)

    title = ""
    try:
        title = root.title()
    except Exception:
        pass

    before = snapshot(args.watch)
    t0 = time.monotonic()
    outcome = "no-file"
    if args.file:
        try:
            getattr(app, args.set_file)(args.file)
            getattr(app, args.start)()
            outcome = "started"
        except Exception as exc:
            print(f"DRIVE verdict=fail stage=drive error={type(exc).__name__}: {exc}")
            print("DRIVE hint=method names must exist on the app; check with grep 'def set_file' / 'def start_translation'")
            return 3

    timed_out = True
    cancelled = False
    deadline = t0 + args.timeout
    while time.monotonic() < deadline:
        try:
            root.update()
        except Exception as exc:  # window destroyed under us
            print(f"DRIVE verdict=fail stage=update error={type(exc).__name__}: {exc}")
            timed_out = False
            break
        if args.cancel_after and not cancelled and time.monotonic() - t0 >= args.cancel_after:
            cancelled = True
            try:
                getattr(app, args.cancel)()
            except Exception as exc:
                print(f"DRIVE note=cancel-failed error={type(exc).__name__}: {exc}")
        if not getattr(app, args.busy_attr, False):
            timed_out = False
            break
        time.sleep(args.poll)
    else:
        print(f"DRIVE verdict=timeout seconds={args.timeout}")

    # let queued done/error callbacks land, then re-check
    for _ in range(8):
        root.update()
        time.sleep(0.05)
    pump = getattr(app, args.pump_callback, None)
    if callable(pump):
        try:
            pump()
        except Exception:
            pass
        root.update()

    elapsed = round(time.monotonic() - t0, 2)
    still_busy = bool(getattr(app, args.busy_attr, False))
    text, log_lines = read_log_text(app)

    output_path = getattr(app, "output_path", None)
    output_exists = bool(output_path) and os.path.exists(str(output_path))
    error_lines = [line for line in text.splitlines() if "失败" in line or "错误" in line or "Error" in line]

    after = snapshot(args.watch)
    changed = diff(before, after)

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ui_log.txt").write_text(text, encoding="utf-8")
    shot_path = args.shot or (str(out_dir / "shot.png") if out_dir else "")
    if args.shot:
        Path(args.shot).parent.mkdir(parents=True, exist_ok=True)
        hwnd = 0
        try:
            root.update_idletasks()
            hwnd = int(root.winfo_id())
            path = root.winfo_pathname(root.winfo_id())
            if not hwnd and path and path != ".":
                hwnd = int(str(path).lstrip("."), 16)
        except Exception as exc:
            print(f"DRIVE note=hwnd-resolution-failed error={type(exc).__name__}: {exc}")
        script = Path(__file__).with_name("capture_window.py")
        spec = importlib.util.spec_from_file_location("capture_window", script)
        if spec and spec.loader:
            capture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(capture)
            argv = [sys.executable, str(script), "--hwnd", hex(hwnd), "--out", args.shot]
            try:
                code = _run_capture(capture, argv)
            except SystemExit as exc:
                code = int(exc.code or 0)
            print(f"DRIVE shot_exit={code}")

    verdict = "pass" if outcome == "started" and not timed_out and not still_busy else "fail"
    if outcome == "no-file":
        verdict = "built-only"
    if error_lines:
        verdict = "app-error"
    print(
        f"DRIVE verdict={verdict} module={args.module} class={args.cls} flags={args.flag} "
        f"title={title!r} dpi={dpi} elapsed={elapsed}s timed_out={timed_out} busy={still_busy} "
        f"cancelled={cancelled} log_lines={log_lines} output={output_path} output_exists={output_exists}"
    )
    print(f"FORENSICS watched={len(before)} changed={len(changed)}")
    for line in changed:
        print(f"FORENSICS changed {line}")
    for path, entry in before.items():
        print(f"FORENSICS before {path} {entry}")
    for path, entry in after.items():
        print(f"FORENSICS after  {path} {entry}")
    if log_lines:
        print("UI_LOG_BEGIN")
        print(text.strip()[-4000:])
        print("UI_LOG_END")

    try:
        root.destroy()
    except Exception:
        pass
    return 0 if verdict in ("pass", "built-only") else 2


def _run_capture(capture_module, argv: list[str]) -> int:
    saved = sys.argv
    sys.argv = argv
    try:
        return capture_module.main()
    finally:
        sys.argv = saved


if __name__ == "__main__":
    raise SystemExit(main())

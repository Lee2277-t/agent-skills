#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Chrome/Edge headless 截图。无需 playwright / puppeteer。

用法：
    python shot.py <url 或 html 路径> [--out shot.png] [--width 1280] [--height 800]
    python shot.py ./index.html --out before.png
    python shot.py http://127.0.0.1:63270 --out gui.png --width 1440 --height 900
    python shot.py ./index.html --out mobile.png --width 390 --height 844

本机踩过的坑（都已在代码里绕开）：
  1. --screenshot 的路径**必须用正斜杠**。反斜杠会被 Chrome 的启动器吃掉，
     报 `拒绝访问 (0x5)`，且不生成文件。
  2. file:// URL 里中文/空格要转义，且必须是绝对路径。
  3. Chrome 有多个进程，用完要杀干净，否则下次可能连到旧实例。
  4. --headless=new 与旧的 --headless 行为不同，用 new。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\%s\AppData\Local\Google\Chrome\Application\chrome.exe" % os.environ.get("USERNAME", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for c in CANDIDATES:
        if c and Path(c).exists():
            return c
    for name in ("chrome", "msedge", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    return None


def to_url(target):
    if "://" in target:
        return target
    p = Path(target).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"✗ 找不到文件：{p}")
    # file:///C:/path/with space → 空格和中文交给 pathlib 的 as_uri
    return p.as_uri()


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="Chrome headless 截图")
    ap.add_argument("target", help="URL 或 HTML 文件路径")
    ap.add_argument("--out", default="shot.png", help="输出 PNG 路径")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--full-page", action="store_true",
                    help="整页（用 --window-size 撑高，Chrome 无原生全页截图）")
    ap.add_argument("--wait", type=float, default=1.2, help="加载后等待秒数，给 JS 渲染时间")
    ap.add_argument("--dark", action="store_true", help="强制暗色模式")
    ap.add_argument("--keep-temp", action="store_true", help="保留临时 profile 便于排查")
    args = ap.parse_args()

    browser = find_browser()
    if not browser:
        print("✗ 没找到 Chrome 或 Edge。装一个，或用 --browser 指定。", file=sys.stderr)
        return 3

    url = to_url(args.target)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    height = args.height
    if args.full_page:
        height = 6000

    profile = tempfile.mkdtemp(prefix="shot-profile-")

    # 关键：路径用正斜杠
    out_slash = str(out).replace("\\", "/")
    profile_slash = profile.replace("\\", "/")

    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--force-device-scale-factor=1",
        f"--user-data-dir={profile_slash}",
        f"--window-size={args.width},{height}",
        f"--screenshot={out_slash}",
        "--virtual-time-budget=%d" % int(args.wait * 1000),
    ]
    if args.dark:
        cmd.append("--force-dark-mode")
        cmd.append("--enable-features=WebContentsForceDark")

    cmd.append(url)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print("✗ Chrome 超时（90s）。页面可能在等网络请求。", file=sys.stderr)
        return 3
    finally:
        if not args.keep_temp:
            shutil.rmtree(profile, ignore_errors=True)

    if not out.exists() or out.stat().st_size == 0:
        print("✗ 截图没生成。Chrome 输出：", file=sys.stderr)
        print((r.stdout or "")[-800:], file=sys.stderr)
        print((r.stderr or "")[-800:], file=sys.stderr)
        print("\n排查顺序：\n"
              "  1. --screenshot 路径是否被反斜杠吃掉了（本脚本已转正斜杠）\n"
              "  2. 目标 URL 是否可访问（先 curl -I 试）\n"
              "  3. 换个 --user-data-dir（可能连到了正在运行的 Chrome）", file=sys.stderr)
        return 3

    kb = out.stat().st_size / 1024
    print(f"✓ {out}  ({kb:.0f} KB, {args.width}×{height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

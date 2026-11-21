#!/usr/bin/env python3
"""Capture one Windows window's pixels into a PNG without touching the foreground.

Usage:
    python capture_window.py --title 翻译工具 --out shot.png
    python capture_window.py --hwnd 0x00A1234 --out shot.png --pid 4321

stdout is one machine-readable line. Exit 0 = captured non-blank, 2 = blank/unusable,
3 = window not found, 4 = environment missing (PIL / not Windows).
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    print("CAPTURE verdict=fail reason=not-windows")
    raise SystemExit(4)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    shcore = ctypes.windll.shcore
except AttributeError:  # Windows 8.1 and older
    shcore = None

try:
    from PIL import Image, ImageStat
except ImportError:
    print("CAPTURE verdict=fail reason=pillow-missing hint=pip install pillow")
    raise SystemExit(4)

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2
SW_RESTORE = 9
BI_RGB = 0
DIB_RGB_COLORS = 0
_LONG = getattr(ctypes, "LONG", ctypes.c_long)
_CINT = ctypes.c_int


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", _LONG),
        ("biHeight", _LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", _LONG),
        ("biYPelsPerMeter", _LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def _proto() -> None:
    """Keep handles untruncated on 64-bit."""
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, _CINT, _CINT]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, _CINT]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.BitBlt.argtypes = [
        wintypes.HDC, _CINT, _CINT, _CINT, _CINT,
        wintypes.HDC, _CINT, _CINT, wintypes.DWORD,
    ]
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ]


def set_dpi_awareness() -> str:
    """Set before any window handle is touched; a process can only ever have one value.

    Without it GetWindowRect returns virtualized (scaled-down) coordinates on a
    high-DPI desktop, so the crop only covers the top-left corner of the window.
    """
    label = "unchanged"
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        if shcore is not None and shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            return "system"
    except (AttributeError, OSError):
        pass
    if shcore is not None:  # already fixed by the host process; report the real value
        value = ctypes.c_int(-1)
        try:
            if shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
                label = {0: "unaware", 1: "system", 2: "per-monitor"}.get(value.value, str(value.value))
        except OSError:
            pass
    return label


def current_awareness() -> str:
    if shcore is None:
        return "unknown"
    value = ctypes.c_int(-1)
    try:
        if shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
            return {0: "unaware", 1: "system", 2: "per-monitor"}.get(value.value, str(value.value))
    except OSError:
        pass
    return "unknown"


def find_windows(title: str, pid: int | None) -> list[tuple[int, str]]:
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[tuple[int, str]] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        text = buffer.value
        if title and title not in text:
            return True
        if pid:
            got = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(got))
            if got.value != pid:
                return True
        found.append((hwnd, text))
        return True

    user32.EnumWindows(proc(found and None or callback), 0)
    return found


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetWindowRect failed")
    return rect.left, rect.top, rect.right, rect.bottom


def bitmap_to_image(hdc, hbitmap, width: int, height: int):
    info = BITMAPINFO()
    header = info.bmiHeader
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = BI_RGB
    pixels = ctypes.create_string_buffer(width * height * 4)
    lines = gdi32.GetDIBits(hdc, hbitmap, 0, height, pixels, ctypes.byref(info), DIB_RGB_COLORS)
    if lines:
        return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
    header.biBitCount = 24  # some remote/desktop formats refuse 32
    pixels = ctypes.create_string_buffer(width * height * 3)
    lines = gdi32.GetDIBits(hdc, hbitmap, 0, height, pixels, ctypes.byref(info), DIB_RGB_COLORS)
    if not lines:
        raise OSError("GetDIBits failed")
    return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGR", 0, 1)


def grab(hwnd: int, width: int, height: int, method: str):
    if width <= 2 or height <= 2:
        raise OSError(f"window too small: {width}x{height}")
    screen = gdi32.CreateCompatibleDC(None)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(screen, bitmap)
    image = None
    try:
        if method.startswith("PrintWindow"):
            flags = PW_RENDERFULLCONTENT if method.endswith("2") else 0
            window_dc = user32.GetWindowDC(hwnd)
            try:
                if not gdi32.BitBlt(screen, 0, 0, width, height, window_dc, 0, 0, 0x00CC0020):
                    pass
                image = bitmap_to_image(screen, bitmap, width, height)
                user32.PrintWindow(hwnd, screen, flags)
            finally:
                user32.ReleaseDC(hwnd, window_dc)
        else:  # screen scrape: only valid if the window is really visible and unoccluded
            screen_dc = user32.GetDC(None)
            try:
                left, top, _right, _bottom = window_rect(hwnd)
                if not gdi32.BitBlt(screen, 0, 0, width, height, screen_dc, left, top, 0x00CC0020):
                    raise OSError("BitBlt failed")
            finally:
                user32.ReleaseDC(None, screen_dc)
        if image is None:
            image = bitmap_to_image(screen, bitmap, width, height)
    finally:
        gdi32.SelectObject(screen, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(screen)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="PrintWindow capture of one Windows window")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--title", help="substring of the window title")
    selector.add_argument("--hwnd", help="window handle, hex or decimal")
    parser.add_argument("--pid", type=int, help="restrict the title match to this process id")
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--min-stddev", type=float, default=3.0, help="blank threshold")
    parser.add_argument("--restore", action="store_true", help="ShowWindow(SW_RESTORE) if iconic")
    parser.add_argument("--method", default="PrintWindow-2",
                        choices=["PrintWindow-2", "PrintWindow-0", "screen-bitblt"])
    args = parser.parse_args()

    _proto()
    before = current_awareness()
    applied = set_dpi_awareness()
    awareness = current_awareness() if before != "unknown" else applied

    if args.hwnd:
        hwnd = int(args.hwnd, 16) if args.hwnd.lower().startswith("0x") else int(args.hwnd)
        if not user32.IsWindow(hwnd):
            print(f"CAPTURE verdict=fail reason=bad-hwnd hwnd={args.hwnd}")
            return 3
    else:
        matches = find_windows(args.title, args.pid)
        if not matches:
            print(f"CAPTURE verdict=fail reason=no-window title={args.title!r} pid={args.pid}")
            return 3
        if len(matches) > 1:
            names = ";".join(f"0x{h:X}" for h, _ in matches)
            print(f"CAPTURE verdict=fail reason=ambiguous windows={names} titles={[_t for _, _t in matches]}")
            return 3
        hwnd, title_text = matches[0]

    iconic = bool(user32.IsIconic(hwnd))
    restored = ""
    if iconic:
        if not args.restore:
            print(f"CAPTURE verdict=fail reason=minimized hint=--restore")
            return 2
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.UpdateWindow(hwnd)
        restored = "restored"

    left, top, right, bottom = window_rect(hwnd)
    width, height = right - left, bottom - top
    try:
        image = grab(hwnd, width, height, args.method)
    except OSError as exc:
        print(f"CAPTURE verdict=fail reason={exc}")
        return 2

    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    stddev = round(stat.stddev[0], 2)
    mean = round(stat.mean[0], 1)
    image.save(args.out)
    verdict = "nonblank" if stddev >= args.min_stddev else "blank"
    print(
        f"CAPTURE out={args.out} method={args.method} size={width}x{height} rect={left},{top},{right},{bottom} "
        f"awareness={awareness} dpi_set={applied} mean={mean} stddev={stddev} verdict={verdict} {restored}".strip()
    )
    return 0 if verdict == "nonblank" else 2


if __name__ == "__main__":
    raise SystemExit(main())

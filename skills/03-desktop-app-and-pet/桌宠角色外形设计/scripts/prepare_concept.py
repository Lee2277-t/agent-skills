#!/usr/bin/env python3
"""Crop watermark margins and downscale an AI-generated concept image."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def trim_uniform_border(img: Image.Image, tolerance: int) -> Image.Image:
    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        if alpha.getextrema()[0] < 255:
            bbox = alpha.getbbox()
            if bbox:
                return img.crop(bbox)

    rgb = img.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    mask = diff.point(lambda value: 255 if value > tolerance else 0)
    bbox = mask.getbbox()
    return img.crop(bbox) if bbox else img


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crop edge margins (for watermarks) and resize a concept image to PNG."
    )
    parser.add_argument("input", help="source image path")
    parser.add_argument("output", help="output .png path")
    parser.add_argument("--max-size", type=int, default=1400, help="max long edge; 0 disables resizing")
    parser.add_argument("--crop-top", type=int, default=0, help="pixels to remove from the top")
    parser.add_argument("--crop-bottom", type=int, default=0, help="pixels to remove from the bottom")
    parser.add_argument("--crop-left", type=int, default=0, help="pixels to remove from the left")
    parser.add_argument("--crop-right", type=int, default=0, help="pixels to remove from the right")
    parser.add_argument("--trim-bg", action="store_true", help="trim a uniform outer border before cropping")
    parser.add_argument("--bg-tolerance", type=int, default=12, help="color tolerance for --trim-bg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.input)
    output = Path(args.output)

    if not source.is_file():
        print("ERROR: input not found")
        return 2
    if output.suffix.lower() != ".png":
        print("ERROR: output must be a .png path")
        return 2
    if args.max_size < 0:
        print("ERROR: --max-size must be 0 or greater")
        return 2

    try:
        with Image.open(source) as opened:
            img = opened.convert("RGBA")
            original_size = img.size

            if args.trim_bg:
                img = trim_uniform_border(img, args.bg_tolerance)

            width, height = img.size
            crops = (args.crop_left, args.crop_top, args.crop_right, args.crop_bottom)
            if any(value < 0 for value in crops):
                print("ERROR: crop values cannot be negative")
                return 2
            if args.crop_left + args.crop_right >= width - 1:
                print(f"ERROR: horizontal crop removes the full width ({width}px)")
                return 2
            if args.crop_top + args.crop_bottom >= height - 1:
                print(f"ERROR: vertical crop removes the full height ({height}px)")
                return 2

            crop_box = (
                args.crop_left,
                args.crop_top,
                width - args.crop_right,
                height - args.crop_bottom,
            )
            if crop_box != (0, 0, width, height):
                img = img.crop(crop_box)

            resized = False
            if args.max_size and max(img.size) > args.max_size:
                current_width, current_height = img.size
                scale = args.max_size / max(img.size)
                target = (
                    max(1, round(current_width * scale)),
                    max(1, round(current_height * scale)),
                )
                img = img.resize(target, Image.Resampling.LANCZOS)
                resized = True

            output.parent.mkdir(parents=True, exist_ok=True)
            img.save(output, "PNG", optimize=True)
    except Exception as exc:  # noqa: BLE001 - keep CLI output clean for the agent
        print(f"ERROR: {exc}")
        return 1

    print(
        "OK "
        f"original={original_size[0]}x{original_size[1]} "
        f"crop={crop_box[2] - crop_box[0]}x{crop_box[3] - crop_box[1]} "
        f"output={img.size[0]}x{img.size[1]} "
        f"resized={'yes' if resized else 'no'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

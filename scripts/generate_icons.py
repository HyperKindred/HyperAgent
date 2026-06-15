"""
Icon conversion script.

Usage:
    uv run python scripts/generate_icons.py <source_image>

Converts any image to:
  - electron/icon.png       (256x256, window icon)
  - electron/tray-icon.png  (32x32, optimized for system tray area)
  - electron/icon.ico       (multi-size: 16/24/32/48/64/128/256, Windows taskbar)

256x256 PNG for the window icon ensures crisp high-DPI rendering.
32x32 for the tray icon because scaling 256x256 down to 16-24px tray
area loses too much detail. The .ico carries 7 embedded sizes so
Windows picks the perfect one for each context.

Supports: PNG, JPG, JPEG, WEBP, BMP, GIF
"""

import io
import struct
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
ELECTRON_DIR = REPO_ROOT / "electron"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def convert(source_path: str) -> None:
    src = Path(source_path)
    if not src.exists():
        print(f"Error: file not found: {src}")
        sys.exit(1)

    img = Image.open(src).convert("RGBA")
    print(f"[Source] {src.name} ({img.size[0]}x{img.size[1]})")

    # 1. Window icon (256x256 PNG)
    i256 = img.resize((256, 256), Image.LANCZOS)
    i256.save(str(ELECTRON_DIR / "icon.png"), "PNG", icc_profile=None)
    print("  [OK] icon.png - 256x256")

    # 2. Tray icon (32x32, closer to tray display size = less downscale blur)
    i32 = img.resize((32, 32), Image.LANCZOS)
    i32.save(str(ELECTRON_DIR / "tray-icon.png"), "PNG", icc_profile=None)
    print("  [OK] tray-icon.png - 32x32 (optimized for tray)")

    # 3. Windows .ico with multiple embedded sizes
    _write_ico(img, ELECTRON_DIR / "icon.ico")
    print(f"  [OK] icon.ico - {len(ICO_SIZES)} sizes ({ICO_SIZES[0]}-{ICO_SIZES[-1]})")

    print(f"\n[Done] All icons generated from: {src.resolve()}")


def _write_ico(img: Image.Image, path: Path) -> None:
    """Build a multi-size ICO file with PNG-compressed entries."""
    blocks = []
    for s in ICO_SIZES:
        buf = io.BytesIO()
        img.resize((s, s), Image.LANCZOS).save(buf, "PNG")
        blocks.append(buf.getvalue())

    count = len(ICO_SIZES)
    header = struct.pack("<HHH", 0, 1, count)

    offset = 6 + count * 16
    entries = b""
    for i, s in enumerate(ICO_SIZES):
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blocks[i]), offset)
        offset += len(blocks[i])

    with open(str(path), "wb") as f:
        f.write(header + entries)
        for block in blocks:
            f.write(block)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/generate_icons.py <image_path>")
        print("Example: uv run python scripts/generate_icons.py electron/source-agent.png")
        sys.exit(1)

    convert(sys.argv[1])

#!/usr/bin/env python3
"""Generate the application icon set (no external assets required).

The mark is a rounded graphite tile with a cyan chat bubble and a teal
integrity check - original artwork, drawn programmatically.

Usage:  python scripts/generate_icons.py
Writes: src-tauri/icons/{32x32,128x128,128x128@2x,icon,Square*Logo}.png + icon.ico
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src-tauri" / "icons"

BG_TOP = (13, 20, 28)
BG_BOTTOM = (9, 13, 19)
CYAN = (34, 211, 238)
TEAL = (45, 212, 191)
NAVY = (15, 30, 46)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(1, size - 1)
        colour = tuple(round(a + (b - a) * ratio) for a, b in zip(BG_TOP, BG_BOTTOM))
        draw.line([(0, y), (size, y)], fill=colour)
    return image


def draw_mark(image: Image.Image) -> None:
    size = image.size[0]
    draw = ImageDraw.Draw(image)
    unit = size / 64.0

    # Chat bubble body.
    draw.rounded_rectangle(
        (10 * unit, 13 * unit, 54 * unit, 45 * unit),
        radius=11 * unit,
        fill=NAVY,
        outline=CYAN,
        width=max(1, round(1.6 * unit)),
    )
    # Bubble tail.
    draw.polygon(
        [(20 * unit, 44 * unit), (20 * unit, 54 * unit), (31 * unit, 44 * unit)],
        fill=NAVY,
        outline=CYAN,
    )
    # Three evidence bars of ascending height (analytics).
    for index, (x, height) in enumerate([(20, 6), (28, 11), (36, 16)]):
        draw.rounded_rectangle(
            (x * unit, (36 - height) * unit, (x + 5) * unit, 36 * unit),
            radius=1.6 * unit,
            fill=CYAN if index < 2 else TEAL,
        )
    # Integrity check.
    draw.line(
        [(40 * unit, 24 * unit), (44 * unit, 29 * unit), (51 * unit, 18 * unit)],
        fill=TEAL,
        width=max(2, round(2.4 * unit)),
        joint="curve",
    )


def render(size: int) -> Image.Image:
    base = gradient(size).convert("RGBA")
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_mark(overlay)
    base.alpha_composite(overlay)
    base.putalpha(rounded_mask(size, max(2, round(size * 0.2))))
    return base


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (32, 128, 256, 512, 1024):
        render(size).save(OUT / f"_render_{size}.png")
    (OUT / "32x32.png").unlink(missing_ok=True)
    render(32).save(OUT / "32x32.png")
    render(128).save(OUT / "128x128.png")
    render(256).save(OUT / "128x128@2x.png")
    render(512).save(OUT / "icon.png")
    # Windows Store style squares (Tauri's optional `icon` extras).
    for name, size in (
        ("Square30x30Logo.png", 30),
        ("Square44x44Logo.png", 44),
        ("Square71x71Logo.png", 71),
        ("Square89x89Logo.png", 89),
        ("Square107x107Logo.png", 107),
        ("Square142x142Logo.png", 142),
        ("Square150x150Logo.png", 150),
        ("Square284x284Logo.png", 284),
        ("Square310x310Logo.png", 310),
        ("StoreLogo.png", 50),
    ):
        render(size).save(OUT / name)
    render(256).save(
        OUT / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for stale in OUT.glob("_render_*.png"):
        stale.unlink()
    print(f"icons written to {OUT}")


if __name__ == "__main__":
    main()

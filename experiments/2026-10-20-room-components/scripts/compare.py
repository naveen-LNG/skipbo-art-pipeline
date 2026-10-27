#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pillow"]
# ///
"""Side by side: v1's cut-out layer against v2's generated component, one row per item.

  uv run experiments/2026-10-20-room-components/scripts/compare.py

Each row shows the same item three ways at the same box size: the v1 cut-out, the v2 component, and the v2
component laid into the room, so edge quality, palette and whether it sits in the room can be judged in one look.
A missing v2 component is drawn as an explicit gap rather than skipped, so the sheet never implies work that was
not done. Writes out/compare.png.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXP = Path(__file__).resolve().parent.parent
V1 = EXP.parent / "2026-10-16-room-renovate"
SHARED = ["window", "lamp", "fireplace", "sofa", "rug", "mess"]
CELL = 300          # each cell is CELL wide
NOTE = {"tv": "no v1 counterpart: the before-room contains no television, so an in-place edit has nothing to change"}


def font(sz, bold=False):
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def checker(w, h):
    im = Image.new("RGB", (w, h), (235, 235, 235))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 16):
        for x in range(0, w, 16):
            if (x // 16 + y // 16) % 2:
                d.rectangle((x, y, x + 15, y + 15), fill=(214, 214, 214))
    return im


def tile(src: Path, w: int, h: int) -> Image.Image:
    """The component trimmed to its paint, fitted into w x h over a checkerboard, so alpha edges are visible."""
    bg = checker(w, h)
    if not src.exists():
        d = ImageDraw.Draw(bg)
        d.text((10, h // 2 - 10), "not generated", fill=(190, 60, 40), font=font(20, True))
        return bg
    im = Image.open(src).convert("RGBA")
    bb = im.split()[-1].point(lambda v: 255 if v > 8 else 0).getbbox()
    if bb:
        im = im.crop(bb)
    s = min((w - 12) / im.width, (h - 12) / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    bg.paste(im, ((w - im.width) // 2, (h - im.height) // 2), im)
    return bg


def main() -> int:
    lay = json.loads((V1 / "game/assets/layout.json").read_text(encoding="utf-8"))
    comp_dir = EXP / "room" / "components"
    rows = SHARED + (["tv"] if (comp_dir / "tv.png").exists() else [])
    room = Image.open(EXP / "out" / "final.png").convert("RGB") if (EXP / "out" / "final.png").exists() else None

    rh = 300
    head, pad = 92, 14
    W = pad + 3 * (CELL + pad) + 260
    H = head + len(rows) * (rh + pad) + pad
    sheet = Image.new("RGB", (W, H), (248, 247, 244))
    d = ImageDraw.Draw(sheet)
    d.rectangle((0, 0, W, head - 10), fill=(26, 30, 38))
    d.text((pad, 14), "Room makeover: v1 in-place edit vs v2 generated component", fill=(255, 242, 214), font=font(30, True))
    src = "v2 component" if any((comp_dir / f"{i}.png").exists() for i in rows) else "v1 layer (no v2 component generated)"
    d.text((pad, 54), f"left: v1 cut-out layer, on a checkerboard    middle: v2 component    right: the room composited from the {src}",
           fill=(190, 200, 215), font=font(20))

    for r, item in enumerate(rows):
        y = head + r * (rh + pad)
        d.text((pad, y + 4), item, fill=(30, 34, 40), font=font(24, True))
        sheet.paste(tile(V1 / "game/assets/layers" / f"{item}.png", CELL, rh - 34), (pad, y + 34))
        sheet.paste(tile(comp_dir / f"{item}.png", CELL, rh - 34), (pad + CELL + pad, y + 34))
        if room is not None:
            b = lay["items"].get(item) or json.loads((EXP / "game/assets/layout.json").read_text(encoding="utf-8"))["items"][item]
            m = max(b["w"], b["h"]) // 2
            crop = room.crop((max(0, b["x"] - m), max(0, b["y"] - m), min(room.width, b["x"] + b["w"] + m), min(room.height, b["y"] + b["h"] + m)))
            crop.thumbnail((CELL, rh - 34), Image.LANCZOS)
            box = Image.new("RGB", (CELL, rh - 34), (248, 247, 244))
            box.paste(crop, ((CELL - crop.width) // 2, (rh - 34 - crop.height) // 2))
            sheet.paste(box, (pad + 2 * (CELL + pad), y + 34))
        if item in NOTE:
            d.text((pad + 3 * (CELL + pad), y + 34), NOTE[item], fill=(170, 70, 40), font=font(17))
        d.line((pad, y + rh + 6, W - pad, y + rh + 6), fill=(222, 220, 214))

    out = EXP / "out" / "compare.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"{out}  {sheet.size[0]}x{sheet.size[1]}  {out.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""Drop the generated components into the room and render the makeover sequence.

  uv run experiments/2026-10-20-room-components/scripts/compose.py
  uv run .../compose.py --shadow            # also paint a contact shadow under each component
  uv run .../compose.py --source v1         # same pipeline, v1's cut-out layers, for the comparison

Each component is a transparent PNG painted alone (scripts/gen_components.sh). It is trimmed to its own alpha,
fitted into its box in layout.json and laid over the base room. The floor patch (`mess`) is the one component with
no silhouette of its own, so it is stretched to fill its box instead of fitted inside it.

Writes, under the experiment:
  game/assets/layers/<id>.png, game/assets/thumbs/<id>.png, game/assets/layout.json   the playable page's art
  out/final.png     the finished room, every component in place
  out/strip.png     one labelled tile per step: before, each component as it lands, finale
  out/sequence.gif  the same steps as an animation
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

EXP = Path(__file__).resolve().parent.parent
V1 = EXP.parent / "2026-10-16-room-renovate"
# bottom to top, jumping between regions of the screen (Blocks progression rules 11.3)
ORDER = ["mess", "rug", "sofa", "tv", "window", "fireplace", "lamp"]
TV_BOX = {"x": 1020, "y": 2360, "w": 480, "h": 360}   # the only floor pocket clear of all six items: see README
LABELS = {"mess": "floor cleared", "rug": "new rug", "sofa": "new sofa", "tv": "television (new object)",
          "window": "window repaired", "fireplace": "fire lit", "lamp": "new chandelier"}


def layout() -> dict:
    """v1's boxes plus the TV's. v1 is never written to."""
    lay = json.loads((V1 / "game/assets/layout.json").read_text(encoding="utf-8"))
    lay["items"]["tv"] = dict(TV_BOX, px=TV_BOX["w"] * TV_BOX["h"])
    return lay


def fitted(src: Path, box: dict, stretch: bool) -> Image.Image:
    """The component trimmed to its own paint and sized to its box, as an RGBA tile the size of the box."""
    im = Image.open(src).convert("RGBA")
    bbox = im.split()[-1].point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    if stretch:
        return im.resize((box["w"], box["h"]), Image.LANCZOS)
    s = min(box["w"] / im.width, box["h"] / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    tile = Image.new("RGBA", (box["w"], box["h"]), (0, 0, 0, 0))
    tile.paste(im, ((box["w"] - im.width) // 2, box["h"] - im.height), im)   # sit on the bottom of the box
    return tile


def contact_shadow(tile: Image.Image, box: dict, size: tuple) -> Image.Image:
    """A soft shadow for the tile's footprint, as a full-frame RGBA to lay under it.

    Only the bottom eighth of the component's alpha is used, squashed flat, blurred and pushed down and right, so
    it reads as the room's one light (upper left) throwing a shadow away from the contact line.
    """
    a = tile.split()[-1]
    band = a.crop((0, int(a.height * 0.875), a.width, a.height))
    h = max(6, box["h"] // 12)
    band = band.resize((a.width, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(h / 2.2))
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    lay = Image.new("RGBA", (a.width, h), (74, 48, 28, 0))
    lay.putalpha(band.point(lambda v: int(v * 0.42)))
    sh.paste(lay, (box["x"] + h // 3, box["y"] + box["h"] - h // 2), lay)
    return sh


def label(im: Image.Image, text: str, note: str = "", foot: str = "") -> Image.Image:
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("arialbd.ttf", 64)
        fn = ImageFont.truetype("arial.ttf", 44)
    except OSError:                                      # ponytail: default bitmap font if arial is missing
        f = fn = ImageFont.load_default()
    d.rectangle((0, 0, im.width, 150 if note else 100), fill=(20, 24, 32))
    d.text((24, 18), text, fill=(255, 240, 210), font=f)
    if note:
        d.text((24, 96), note, fill=(230, 160, 120), font=fn)
    if foot:                                             # provenance, so a frame can never be read as something it is not
        d.rectangle((0, im.height - 86, im.width, im.height), fill=(126, 26, 18))
        d.text((24, im.height - 68, ), foot, fill=(255, 236, 228), font=fn)
    return im


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="v2", choices=("v1", "v2"), help="v2: the generated components; v1: the cut-out layers, same pipeline")
    ap.add_argument("--shadow", action="store_true", help="paint a contact shadow under each component")
    ap.add_argument("--out", default="out", help="output folder under the experiment")
    ap.add_argument("--note", default="", help="provenance line stamped across the foot of every frame")
    a = ap.parse_args()

    lay = layout()
    lay["source"] = a.source          # the page prints this, so v1 art can never be shown as v2's
    W, H = lay["width"], lay["height"]
    src_dir = EXP / "room" / "components" if a.source == "v2" else V1 / "game/assets/layers"
    base = Image.open(V1 / "game/assets/base.jpg").convert("RGB")
    finale = Image.open(V1 / "game/assets/finale.jpg").convert("RGB").resize((W, H))

    have = [i for i in ORDER if (src_dir / f"{i}.png").exists()]
    missing = [i for i in ORDER if i not in have]
    if not have:
        raise SystemExit(f"no components in {src_dir} - run scripts/gen_components.sh first")
    print(f"source {a.source}: {len(have)} components ({', '.join(have)})" + (f"; MISSING {', '.join(missing)}" if missing else ""))

    out = EXP / a.out
    out.mkdir(parents=True, exist_ok=True)
    assets = EXP / "game" / "assets"
    (assets / "layers").mkdir(parents=True, exist_ok=True)
    (assets / "thumbs").mkdir(parents=True, exist_ok=True)
    for name in ("base.jpg", "finale.jpg"):
        shutil.copy(V1 / "game/assets" / name, assets / name)

    comp = base.copy()
    frames = [label(base.copy(), "0  before", "the room as generated, nothing fixed", a.note)]
    for n, i in enumerate(have, 1):
        box = lay["items"][i]
        tile = fitted(src_dir / f"{i}.png", box, stretch=(i == "mess"))
        tile.save(assets / "layers" / f"{i}.png", optimize=True)
        t = tile.copy()
        t.thumbnail((180, 180), Image.LANCZOS)
        t.save(assets / "thumbs" / f"{i}.png")
        if a.shadow and i != "mess":
            comp = Image.alpha_composite(comp.convert("RGBA"), contact_shadow(tile, box, (W, H))).convert("RGB")
        full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        full.paste(tile, (box["x"], box["y"]), tile)
        comp = Image.alpha_composite(comp.convert("RGBA"), full).convert("RGB")
        frames.append(label(comp.copy(), f"{n}  {i}", LABELS.get(i, ""), a.note))
    label(comp.copy(), "", "", a.note).save(out / "final.png") if a.note else comp.save(out / "final.png")
    frames.append(label(finale.copy(), f"{len(have) + 1}  finale", "walls, ceiling and floor (reused from v1)", a.note))

    cols, s = 4, 0.22
    tw, th = int(W * s), int(H * s)
    sheet = Image.new("RGB", (cols * (tw + 10) + 10, ((len(frames) + cols - 1) // cols) * (th + 10) + 10), (245, 243, 238))
    for k, fr in enumerate(frames):
        sheet.paste(fr.resize((tw, th), Image.LANCZOS), (10 + (k % cols) * (tw + 10), 10 + (k // cols) * (th + 10)))
    sheet.save(out / "strip.png")

    gw = 540
    gif = [f.resize((gw, round(gw * H / W)), Image.LANCZOS).quantize(colors=128, method=Image.MEDIANCUT) for f in frames]
    gif[0].save(out / "sequence.gif", save_all=True, append_images=gif[1:], duration=[1100] * (len(gif) - 1) + [2600],
                loop=0, optimize=True, disposal=2)
    for f in ("final.png", "strip.png", "sequence.gif"):
        print(f"  {(out / f)}  {(out / f).stat().st_size / 1e6:.2f} MB")
    lay["items"] = {k: v for k, v in lay["items"].items() if k in have}
    (assets / "layout.json").write_text(json.dumps(lay, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

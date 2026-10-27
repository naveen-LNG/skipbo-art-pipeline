# Cast animation gallery

One page that plays every animation of every character at once: `index.html` + `manifest.json` +
`assets/<character>-<variant>/` (skeleton JSON, atlas, packed half-size texture pages).

## Rebuild

```sh
python3 tools/build_gallery.py            # discover rigs, rebuild only what changed
python3 tools/build_gallery.py --list     # show which rig folders it would use
python3 tools/build_gallery.py --rig fox:pro=experiments/2026-10-16-spine-pro/fox/rig_pro   # add/override one
python3 tools/build_gallery.py --force    # rebuild everything
```

Without Pillow installed, the script re-runs itself under `uv run --with pillow`.
Rigs are found in `experiments/2026-10-11-rig-annotations/*/rig`, `2026-10-15-beaver-jev-hands/*/rig`,
`2026-10-16-spine-pro/*/rig_legacy|rig_pro` and `2026-10-16-cast/*/rig|rig_legacy|rig_pro` (later folders
win for the same character + variant). Each is copied with textures at 0.5 scale (`--scale`), packed into
power-of-two atlas pages (MaxRects, 4 px padding, mipmapped). Region attachments keep their JSON size, so
the runtime scales the smaller texture back up; meshes map through UVs and need no change. A rig that
fails to build keeps its previous build and shows up under "Problems" on the page.

## Open locally

```sh
python3 -m http.server 8780 --directory gallery   # then http://127.0.0.1:8780/
```

The page needs http (not `file://`) because it fetches `manifest.json`. It loads the Spine runtime
(`@esotericsoftware/spine-webgl@4.2.120`) from jsDelivr and fonts from Google Fonts; nothing else is external.

## Using the page

- One shared clock drives every cell; each cell loops its animation on it. Space = play/pause,
  `,` / `.` = one frame (30 fps), the scrubber sets the clock.
- Rig: Legacy / Pro / Side by side, for all characters at the top or per character in its header.
- Stage: light, dark or checker background. Click any cell for a large view (bones overlay, prev/next).
- `_shots/` holds verification screenshots; it is not part of the gallery and should not be published.

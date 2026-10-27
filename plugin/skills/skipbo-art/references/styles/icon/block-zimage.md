# Style block: item icon for Z-Image (positive-only)

- **Engine:** Z-Image Turbo (`zimage-t2i`, 1024×1024, cfg 1). Positive wording only, so it passes `comfy.py lint --engine zimage`.
- **Derived from:** `icon-2.5d-diagonal.md` / `icon-front.md` (the server's Icon - Skip-Bo notes), rewritten 2026-10-11 so every "no/not/avoid" became the thing that should fill that slot.
- **Use:** write the SUBJECT first (40–90 words: the object's shapes, parts and colours as things you can see, not menu wording), then paste the block. Pick the **diagonal** line for things whose top matters (pots, bowls, crates, food in containers) and the **front** line for flat or tall things (signs, tools, bottles, characters' items).
- **Status:** tested 2026-10-11 on "Honey Dew Mushroom Pot" (see the repo's `experiments/`).

~~~~text
2D hand-painted casual mobile game icon in the style of merge and match-3 item art, semi-flat painted food illustration, simplified into three to five bold chunky elements with rounded, slightly inflated shapes and smooth curves. Clean digital painting with soft gradient shading in clearly defined steps, gentle soft highlights, bright saturated colours with warm or cool hue-shifted shadows in deep saturated tones, thin slightly darker coloured outlines, soft coloured contact shading where elements overlap, crisp clean edges, friendly and polished.
DIAGONAL: Seen from a 45 degree high angle with a long lens, showing the front and the top at once, toy-like proportions, centered with an even margin on a plain flat #E8EEF4 background.
FRONT: Seen straight from the front with a long lens, toy-like proportions, centered with an even margin on a plain flat #E8EEF4 background.
~~~~
Use the first paragraph plus **one** of the DIAGONAL / FRONT lines, without the label. The test icons had a soft ground shadow. If it must go, replace "soft coloured contact shading where elements overlap" with "evenly lit, floating on the background" and cut the result out with `cutout`.

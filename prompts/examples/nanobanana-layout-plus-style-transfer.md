# Template: redraw a layout image in a reference style (two-image roles)

- **Source:** `NanoBananaTest.json`, PrimitiveNode #4 → NanoBananaAIO prompt
- **Status:** verbatim copy from the server snapshot of 2026-10-11. Do not paraphrase. Edit only on purpose and keep a dated note.
- **Engine:** Nano Banana Pro, 1:1, 1K, temperature 0.5. `image_1` = layout, `image_2` = style. A clean pattern for naming each image's role.

~~~~text
You have two reference images.

image_1 = LAYOUT REFERENCE. This is the scene composition 
you must reproduce exactly. Keep all buildings, structures, 
paths, objects, and their positions identical to image_1. 
Do NOT change any elements, layout, or composition.

image_2 = ART STYLE REFERENCE ONLY. Extract only the 
visual rendering style from this image: the color palette, 
outline thickness, shading technique, lighting mood, 
texture style, and cartoon rendering approach. 
Do NOT copy any objects, buildings, or compositions from image_2.

Your task: Redraw image_1 scene in the exact art style of image_2.
Every building, path, and object from image_1 must remain 
in the same position. Only the visual style should change 
to match image_2.

Output: 2D cartoon casual game background scene, 
isometric top-down view, no characters, no people, 
no text, no UI, clean polished game art, 
transparent-ready background.
~~~~

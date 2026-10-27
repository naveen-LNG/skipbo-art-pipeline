# A. Photoshop / PSD prep, PSD to Spine import, skins (Armanimation)

Source: 7 auto-caption transcripts. Caveat up front: **the author never describes an "overdraw" / painting-in-hidden-areas workflow, joint-overlap painting, or deriving parts from one flat master image** in this group. Where a section has no coverage, it says so. What exists is: pre-cut layered PSDs, a straightening tip, a pivot test in Photoshop, and tag-based import.

---
## 1. Per-video summary

### Y01o76_WfqI - "Tracer #1 Preparing in Photoshop" (https://youtu.be/Y01o76_WfqI)
- [0:38-1:10] Source image was a flat downloaded PNG that he "cleaned up in Photoshop" into separated, named layers: "cleaned up and separated into the layers and named them appropriately". Parts kept simple so rigging is the focus.
- [1:45-2:23] Tip 1: for curvy parts (tentacles, hair, cloth) expected to be animated, **ask the artist for a second, straightened version** of the part. If you are the animator and only have the curved one, straighten it yourself (see tricks in section 2).
- [5:00-5:58] Test joints in Photoshop: Transform mode, Alt+drag the pivot to where the joint should be, rotate to check. Suggests **rounded/circular ends** on part endings at joints ("finish endings of the parts in circular way, those work best").
- [5:25-5:58] Layer naming: names are used by the animator and **bones share the same name**; must be meaningful and unique "otherwise you won't be able to export".
- [5:58-7:11] Uses Spine's official "Photoshop to Spine" script (versions exist for Illustrator etc.); has a Help button listing tags; shows an `ignore` group (not exported with everything inside). Tip: record a Photoshop Action + hotkey to apply a tag to selected layers/groups quickly.
- [7:11-7:47] Set the **root/ground point with a ruler guide** (Ctrl+R, drag from top-left corner). Guide only lives in the open session, re-drag after reopening. [7:47-8:27] Export (script produces PNGs + JSON), drag the JSON into Spine, "create a new project".

### _1mkFeOG6RE - "New Way to Import PSD into Spine [skin] and [mesh] tags" (https://youtu.be/_1mkFeOG6RE)
- [0:29-1:00] New Spine PSD import: in Images node, add a PSD file, press the orange refresh/import button. Images get a PSD icon (linked); refresh re-imports. Multiple PSDs can be added "for different skins".
- [1:00-1:56] `[mesh]` tag (front or end of layer name) makes imported layers mesh attachments directly. Re-import does **not** convert existing region attachments (Spine won't disturb prior setup): you must manually delete the existing attachments/slot, then re-import.
- [1:56-3:26] `[mesh:name]` (mesh + name) makes a **linked mesh** whose source is the layer named `name`. Errors arise if there is more than one source or "not found". Limitation (at that version): linked meshes cannot live in separate slots; put them in one slot or use skins.
- [3:26-3:56] Group + `[slot:name]` tag forces all children into one slot. Source mesh is the only one with editable mesh tools; linked ones show "break link"/"select source" buttons.
- [4:24-6:50] Skins: groups tagged `[skin:yellow]`, `[skin:blue]` ... each containing a layer with the **same placeholder name** (e.g. `balloon`). Linked mesh name must be skin-qualified: `[mesh:blue balloon]`-style (source = "blue balloon", i.e. the `skin/attachment` full name). Result: 4 skins, one placeholder slot "balloon", one attachment per skin; must select a skin to see textures.
- [6:50] Mentions further tags (rotation, origin, folder patterns) and a draft tag doc, "not final".

### btrOAIZPWNY - "Photoshop to Spine Import new tags [Overlay] [Origin]" (https://youtu.be/btrOAIZPWNY)
- [0:01-0:57] `[overlay]` tag: a layer becomes a **clipping mask** over the layers/siblings beneath it (pattern over all balloons; scope it by putting some balloons in a group). Not imported as an attachment; applied as clipping. Spine 3.66 beta (as transcribed "366").
- [0:57-1:55] `[origin]` tag: alternative to dragging two guides for root. Draw a small layer where the root should be, tag it `[origin]`; Spine takes the **center of that layer** as the origin/root. Had to delete slot and re-import to see the change.
- [0:30] Also: new skin view buttons (add, duplicate, delete).
- [1:55] Rotation tag teased for next video (not in this group).

### myur8TsuwjI - "Slot game: Planning Stage Part 1" (https://youtu.be/myur8TsuwjI)
- Mostly animation/effect planning and freelancing/budget talk. Starting art = "just generated art ... just a PNG" (flat), client squares (same size).
- [2:29] Plan **what each object does** before cutting; don't cut without knowing the animation ([0:58 in Part 2 repeats this]).
- [4:54-5:24] Decides which pieces to cut: rune cutouts as single textures, extra glow textures with faded edges layered in separate slots.
- [8:57-9:28] Cut-vs-single-texture trade-off: "separate the top part to create a better 3D, otherwise it's going to stretch and break the pieces"; quick alternative = single texture, mesh properly with **"double edges"** to preserve shape under deformation.
- [12:24-14:19] Canvas/size agreement with client: e.g. 512 square, symbols fit in an inner square, leave margin for VFX; PNG sequences get clipped otherwise.

### NSiQXuka5aQ - "Slot game: Cutting in Photoshop Part 2" (https://youtu.be/NSiQXuka5aQ)
- [0:30-3:28] Organizes four similar stone symbols in one PSD folder, converts to Smart Objects to scale to a common size; each symbol sits in its own group tagged as skin, sharing one slot/bone structure across symbols.
- [3:28-6:18] Per symbol: stone texture at 1:1, plus extracted rune and four glow layers (glow 1-4, built with masks/feather/shift-edges from the rune, overlapping fade-in pieces). Glows scaled to 0.3 in a "scale" folder to save size.
- [8:16-8:46] **Same layer name across skins puts attachments in the same slot**; different name creates another slot. Bone name also follows the layer/group name.
- [10:14-10:42] `slot` tag required to force separate slots (e.g. glows in separate slots so alpha can fade; same slot only allows switching).
- [11:11-11:49] Script export settings: Trim, Ignore hidden layers (off), scale 100%, output into the project `images` folder. Imported as new skeleton/skins.
- [11:49-12:18] Root point wrong in the first import; fixed with guidelines. [13:13-14:09] Set glows/runes to additive (linear dodge) in Spine and re-export. [15:10-15:37] Builds a bone controller and binds the mesh to rune container and controller. [16:09] Imports a frame into an existing layer: no conflict if no slot/attachment has that name.

### aFVV7dbFwG4 - "How skins and Skin Placeholders work #1" (https://youtu.be/aFVV7dbFwG4)
- [0:28-1:31] Skins let animations be reused with different attachments (and bones/constraints). Attachment is not just an image: region/mesh carry images; path/bbox/clipping/point do not.
- [2:05-3:07] Bones and constraints can be added to a skin so skin-specific bones only load when active.
- [3:07-6:07] Demo: Spineboy shoes. Select attachments, New > Skin Placeholder (needs an active skin). Default skin is invisible in editor tree; changes apply to active skin. Change attachment color, **not slot color**.
- [6:37-8:21] Preparing skins in PSD: group tagged `[skin]` (group name = skin name), or `[skin:blue]` on layer names; give same layer names across skins so they land in one slot; "avoid creating a slot for each skin part".
- [8:21-8:57] If skins need different layer order (shoes under vs over pants), use 2 slots per part.
- [9:28-11:04] Several attachments in one slot into 3 skins: create the placeholder once, then with each skin active drag its attachment onto the same placeholder; rename placeholder generically.

### B7Zk1bx-tqg - "How to Import Skins #2" (https://youtu.be/B7Zk1bx-tqg)
- [0:38-1:48] Splitting a skin into smaller skins: drag attachments out of placeholders (to "general domain", visible with no skin), create new skin, drag into placeholders. Duplicate the attachment (not placeholder) to keep mesh and weights.
- [2:18-4:47] Use as few slots/placeholders as possible; merging skins; if two skins share placeholders, duplicate slots so both parts coexist.
- [5:14-6:48] Duplicate skin dialog: Rename Attachments, Linked mesh, Inherit Deform, Duplicate keys. Rename Attachments requires matching folder names or paths break.
- [6:48-8:38] Way 1: duplicate skin and modify, new art in `boy2/` folder; reuse mesh and weights if shape same, else re-mesh.
- [8:38-9:16] Way 2: add new skin in PSD with `[skin]` tag (empty name = group name), export with script, import JSON into existing skeleton with the **ignore option**; if named properly new parts land in existing slots/bones, but mesh and weights likely need redoing.
- [9:16-10:22] Adding a bone to a skin also adds it to every skin containing an attachment weighted/inside that bone.

---
## 2. How the animator plans and cuts in Photoshop (as actually stated)

Order observed:
1. **Plan the animation first** (myur8TsuwjI [2:29], NSiQ [0:58]): decide what moves, what is shared between symbols; cut only what the animation needs (Part 2 cuts only the 4 basic stones: "I don't want to separate them and work on them without really understanding what the animation is going to be").
2. **Agree canvas/size with the client** (myur8 [12:24-14:19]): fixed square (e.g. 512), inner safe square for the art, margin for VFX because PNG sequences are cropped.
3. **Normalize scale** (NSiQ [1:29]): convert to Smart Objects so resizing is non-destructive; scale mismatched assets to a common size.
4. **Cut/separate into layers, one per moving part**, named uniquely (Tracer [1:10]). Tracer parts were "nothing much complicated".
5. **Straightened versions of curvy parts** (Tracer [1:45]) for hair, tentacles, cloth.
6. **Test joints** in Photoshop with Alt-dragged pivot in Transform (Tracer [5:00]); finish part ends in rounded/circular shapes for good joints.
7. **Name layers** (names = bone/attachment names), **tag groups/layers**, add ground/root point.
8. Run the **Photoshop to Spine script** (settings noted: Trim on, Ignore hidden layers off in NSiQ [11:11], 100% scale, output to images folder), save PSD first.

Photoshop tricks he names (Tracer [2:23-4:49]):
- **Puppet Warp** to straighten bent parts ("very little destructive").
- **Liquify** (with Show Backdrop toggle) to straighten further.
- A Content-Aware-like stretch/fill tool (similar to Liquify, "much more destructive", stretches and refills but blurs).
- **Hue/Saturation with hand/targeted range** (Ctrl+U) to recolor one color range; **Ctrl+Alt+U** reapplies last settings to another layer.
- Move tool "Auto-select layer + show transform controls" to jump between layers; Ctrl-drag to move a whole group.
- Glow layer building (NSiQ): duplicate the rune, selection, refine (smooth, feather, shift edges, contrast), mask pieces to make overlapping fade-in glows; scale glows to 0.3 (small textures, saves effort).
- Layer masks auto-applied when adding a mask with a selection (NSiQ [9:44]).

**Not covered anywhere in these videos:** painting hidden/overlapped areas ("overdraw"), explicit joint overlap padding, splitting a single flat master automatically, padding/resolution guidance for parts (other than: scale 100%, small glow textures at 0.3, Trim on). Closest hints: the straightened-part tip, the circular joint ends tip (rounded ends so overlap hides the seam on rotation), and myur8 [8:57] ("separate the top part ... otherwise it's going to stretch and break"; "double edges" on mesh).

What gets separated vs kept together (stated reasoning, not a formal rule):
- Separate: parts that move independently or would stretch badly (top lid/cap), glow/rune pieces that animate separately, pieces needing different alpha.
- Keep as a single texture: if quick work is OK, mesh a single texture with extra edge loops ("double edges") rather than cutting.
- Grouping in PSD = structure: group with `[skin]` = skin, group with `[slot]` = one slot for all children, group named `ignore` tag = skipped.

---
## 3. PSD to Spine import

Two importers:
- **Photoshop to Spine script** (older, JSON + PNG export; Tracer, NSiQ, skins #2): run script in Photoshop, drag the JSON into Spine's window, choose new project / import into existing skeleton, with an "ignore" option (existing setup kept) for adding a skin (B7Zk [8:38]).
- **Native PSD import** in newer Spine (_1mk, btrOA, 3.6 beta): add PSD in the Images node, press orange refresh; PSD stays linked, refresh re-imports; multiple PSDs allowed (e.g. one per skin). Re-import overrides images but not existing attachment types (delete first).

Tags (only those evidenced in this group; none of `[bone]`, `[linkedmesh]`, `[merge]`, `[folder]` appear as explicit tag names in these 7 videos):

| Tag | Meaning (from the author) |
|---|---|
| `ignore` | Group not exported, with everything inside (Tracer [6:35]). Used with the old script. Exact syntax shown only visually, likely `[ignore]`. |
| `[slot]` / `[slot:name]` | Forces the tagged group's children into a single slot; name in tag = slot name (_1mk [3:26]; NSiQ [10:14]: needed to get separate slots). |
| `[skin]` / `[skin:name]` | On a group: group name becomes skin name (empty name uses group name). On a layer: `[skin:blue]` assigns that layer to skin blue (aFVV [6:37]; B7Zk [8:38]). Child layer names become the attachments/placeholders. |
| `[mesh]` | Layer imported as mesh attachment, tag can be at start or end of name (_1mk [1:00]). |
| `[mesh:name]` | Makes a linked mesh; `name` is the layer/attachment that is the source. With skins the source name is skin-qualified (e.g. `blue balloon`). Exactly one source must exist else errors (_1mk [2:27]). Linked meshes only inside one slot or via skins. |
| `[overlay]` | Layer becomes a clipping mask over the sibling layers or group (btrOA [0:01]). Not an attachment. |
| `[origin]` | Layer center = root/origin point (btrOA [0:57]); replaces dragging two guides. |
| (rotation tag) | Mentioned as new, not explained. |

Naming to structure mapping:
- Layer name = attachment name and image path; **the bone gets the same name** (Tracer [5:25]; NSiQ [8:46]: "the bone name is also the same, rune bone").
- Same layer name in different groups/skins -> same slot with several attachments (NSiQ [8:16]; aFVV [7:42]). Different name -> new slot.
- Group/folder name -> skin (with tag) or folder in the images path (B7Zk Rename Attachments needs a folder named as the skin).
- Names must be unique, otherwise export fails (Tracer [5:58]).

Origin/pivot:
- Root: either 2 ruler guides in Photoshop (Tracer [7:11]; script uses first two guides; guide lost on reopen) or an `[origin]` layer (center = origin).
- Part pivots: not baked from Photoshop; animator places bones in Spine. The Photoshop Alt-pivot test is only a preview.
- In NSiQ first import the root was off ([11:49-12:18]); he fixed it with a guideline then re-exported.

---
## 4. Skins and skin placeholders

- Skin = set of attachments (plus optional bones and constraints) active one at a time; lets the same rig/animations be reused with different art (aFVV [0:28]).
- Default skin = everything not in a skin; hidden in editor tree. General domain = attachments not in a skin (visible with no skin active).
- **Skin placeholder** = the slot-level entry (hanger icon) that holds a skin's attachment for that slot. Created via New > Skin Placeholder with a skin active. Placeholders don't know about skins: deleting skins leaves them. Rename to generic (e.g. `balloon`).
- Workflow (aFVV [9:28-11:04]): create skins -> activate skin A -> create placeholder from its attachment -> activate B -> drag B's attachment onto the **same** placeholder -> repeat.
- Variation per skin: attachment color (not slot color), different image, different mesh/weights, bones and constraints per skin (so non-shared bones don't bloat rig). Attachments can point at the same image with different deform/color.
- From PSD: `[skin]` group or `[skin:name]` layers with identical layer names across skins so they share a slot (aFVV, _1mk, B7Zk). Slot per skin part is the "common mistake".
- When different skins need different draw order (shoes under/over pants): use two slots per part (aFVV [8:21]).
- Split/merge/duplicate skins (B7Zk): drag out to general domain; duplicate attachment (keeps mesh and weights); merging skins that share placeholders needs duplicate slots; Duplicate Skin options Rename Attachments, Linked mesh, Inherit Deform, Duplicate keys.
- Linked meshes across skins: share vertices, edges, UVs, weights; "Inherit Deform" off to key deform separately (B7Zk [5:45]).
- Adding a bone to a skin also adds it to other skins containing attachments weighted to it (B7Zk [9:16]).
- NSiQ use: four symbols sharing one rig, only textures differ, each symbol a skin; "same structure ... same bones".
- When to use: same animation across variants (colors, outfits, symbols); not needed for a single bespoke character.

---
## 5. Gotchas and do/don't (author's)

- DO provide a straightened version of curvy parts (hair, tail, cloth) (Tracer [1:45]).
- DO end limb parts with rounded shapes at joints.
- DO test pivots with Alt+drag pivot in Transform before cutting is final.
- DO name layers meaningfully and uniquely; duplicates break export.
- DO set the ground/root point (ruler guide) before export; it is lost when Photoshop is closed.
- DO save the PSD before exporting; DO set export Trim and 100% scale; hide helper layers via ignore.
- DO plan animation before cutting; avoid cutting everything blindly.
- DO agree canvas size and VFX margin with client.
- DON'T create a slot per skin part; use same names to share slot.
- DON'T change slot color for skin tints; change attachment color.
- DON'T expect `[mesh]` to convert existing region attachments on re-import; delete and re-import.
- DON'T mix several sources for a linked mesh; need one source with exact name; linked meshes in separate slots weren't supported then.
- DON'T expect to create a placeholder without an active skin.
- DON'T use Rename Attachments without folder/name conventions, or paths break.
- Warning re: new skin from PSD: you will likely have to re-mesh and re-weight it (B7Zk [9:16]).
- Spine would not overwrite prior setup on refresh (design choice); conflicts with names also cause overwrites (NSiQ [16:09]).

---
## 6. Screenshot picks

| videoId | timestamp | what should be on screen | why it matters |
|---|---|---|---|
| Y01o76_WfqI | 1:10 | Photoshop layers panel of the cleaned Tracer, named parts | Shows part granularity and naming of a good animator-ready PSD |
| Y01o76_WfqI | 2:23 | Puppet Warp / Liquify straightening a curved part | The straighten-curvy-part trick |
| Y01o76_WfqI | 5:00 | Transform mode with pivot moved via Alt on an arm | Joint test in Photoshop |
| Y01o76_WfqI | 6:35 | Script dialog / help and layer group tagged ignore | Visible tag syntax |
| Y01o76_WfqI | 8:27 | Spine after JSON import: character assembled | Result of export-import |
| _1mkFeOG6RE | 4:53 | PSD layers panel with `[skin:...]` groups and `[mesh:...]` names | Concrete tag syntax for skins plus linked meshes |
| _1mkFeOG6RE | 6:21 | Spine tree with one placeholder "balloon" plus 4 skins | Resulting hierarchy |
| btrOAIZPWNY | 1:26 | PSD with origin layer then Spine root position | Origin tag effect |
| NSiQXuka5aQ | 3:28 | PSD layer panel with skin folder and glow folders, scale group | Real production PSD structure |
| NSiQXuka5aQ | 11:11 | Photoshop to Spine script settings dialog | Export options |
| aFVV7dbFwG4 | 6:37 | PSD with red shoes group and `[skin]` tag | Basic tag usage |
| B7Zk1bx-tqg | 5:14 | Duplicate Skin dialog with options | Meaning of options |

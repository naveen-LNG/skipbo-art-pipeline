#!/usr/bin/env python3
"""Rebuilt report: every test compared across Clef Flash, Clef 27B and Jev 1.14. Reads metrics.json + result files."""
import html, json, statistics
from pathlib import Path

H = Path(__file__).parent
M = json.load(open(H / "metrics.json"))
A = json.load(open(H / "assets.json"))
NAMES = ["Clef Flash", "Clef 27B", "Jev 1.14"]
KEYS = {"Clef Flash": ("clef-flash", "cloudflare"), "Clef 27B": ("clef", "cloudflare"), "Jev 1.14": ("jev-1.14.0", "typesafe")}
CLS = {"Clef Flash": "m1", "Clef 27B": "m2", "Jev 1.14": "m3"}
esc = html.escape


def load(d, cond, name, swap=False):
    m, p = KEYS[name]; f = H / d / f"results_{cond}{'_swap' if swap else ''}_{p}_{m}.jsonl"
    return {r["id"]: r for r in map(json.loads, open(f)) if r.get("answers")} if f.exists() else {}


def f2(v): return "–" if v is None else f"{v:.2f}"
def pc(v): return "–" if v is None else f"{v:.0%}"


def bars3(vals, label="P(defect)"):
    rows = "".join(f'<div class="b3 {CLS[n]}"><span class="b3n">{n.replace("Clef ", "")}</span><span class="b3t"><span class="b3f" '
                   f'style="width:{(vals.get(n) or 0)*100:.1f}%"></span><span class="half"></span></span><span class="b3v">{f2(vals.get(n))}</span></div>'
                   for n in NAMES if n in vals)
    return f'<div class="bars3"><span class="plabel">{esc(label)}</span>{rows}</div>'


def table(rows, head="Metric", note=None, higher_better=None):
    """rows: [(label, {model: (display, sortvalue)}), ...]; best (max sortvalue) per row is marked."""
    hb = higher_better or [True] * len(rows)
    out = f'<div class="tablewrap"><table class="cmp"><thead><tr><th>{esc(head)}</th>' + "".join(
        f'<th class="{CLS[n]}h">{n}</th>' for n in NAMES) + "</tr></thead><tbody>"
    for (label, vals), better in zip(rows, hb):
        sv = [vals[n][1] for n in NAMES if n in vals and vals[n][1] is not None]
        best = (max(sv) if better else min(sv)) if sv and better is not None else None
        out += f"<tr><td>{label}</td>" + "".join(
            f'<td class="num{" best" if best is not None and n in vals and vals[n][1] == best and len(sv) > 1 else ""}">{vals[n][0] if n in vals else "–"}</td>'
            for n in NAMES) + "</tr>"
    out += "</tbody></table></div>"
    if note: out += f'<p class="tnote">{note}</p>'
    return out


def auc_cell(b, show_ci=True):
    if not b or b.get("auroc") is None: return ("–", None)
    c = b.get("ci"); s = f'{b["auroc"]:.2f}' + (f'<span class="ci">{c[0]:.2f}–{c[1]:.2f}</span>' if show_ci and c else "")
    return (s, b["auroc"])


def per_model(sec, fn):
    return {n: fn(sec[n]) for n in NAMES if n in sec}


# ---------------------------------------------------------------- scoreboard
def sb(sec, fn):
    return {n: fn(M[sec][n]) for n in NAMES if n in M.get(sec, {})}


SCORE = [
    ("Full frame · planted 3–24 px shifts", "AUROC", sb("frames", lambda b: b["auroc"]), "#t-frames"),
    ("Joint crop · render only (audited labels)", "AUROC", sb("joint_render", lambda b: b["audited"]["auroc"]), "#t-joint"),
    ("Joint crop · with the master crop (audited)", "AUROC", sb("joint_master", lambda b: b["audited"]["auroc"]), "#t-joint"),
    ("Joint crop · vs the previous render: says “moved”", "share of shifts", sb("joint_prev", lambda b: b.get("shifted_moved_rate")), "#t-prev"),
    ("Joint crop · fix direction (best condition)", "accuracy", {n: max(M[s][n]["dir"] for s in ("joint_render", "joint_master", "joint_prev") if n in M.get(s, {}) and "dir" in M[s][n]) for n in NAMES}, "#t-dir"),
    ("Real reviewed frames · full body, one frame", "AUROC", sb("real_single", lambda b: b["full_body"]["auroc"]), "#t-real"),
    ("Real rig generations · one frame", "AUROC", sb("rounds_single", lambda b: b["all"]["auroc"]), "#t-rounds"),
    ("Real rig generations · which of two is worse", "accuracy", sb("rounds_pairs", lambda b: b["all"]["right"] / b["all"]["n"]), "#t-rounds"),
    ("Real reviewed pairs · which of two is worse", "accuracy", sb("real_pairs", lambda b: b["all"]["right"] / b["all"]["n"]), "#t-real"),
]


def scoreboard():
    out = '<div class="tablewrap"><table class="score"><thead><tr><th>Test</th><th>Metric</th>' + "".join(
        f'<th class="{CLS[n]}h">{n}</th>' for n in NAMES) + "</tr></thead><tbody>"
    for label, metric, vals, anchor in SCORE:
        sv = [v for v in vals.values() if v is not None]; best = max(sv) if sv else None
        cells = ""
        for n in NAMES:
            v = vals.get(n)
            cells += (f'<td class="meter {CLS[n]}{" best" if v is not None and v == best else ""}"><span class="mfill" style="width:{(v or 0)*100:.0f}%"></span>'
                      f'<span class="mval">{"–" if v is None else (f"{v:.2f}" if metric == "AUROC" else f"{v:.0%}")}</span></td>')
        out += f'<tr><td><a href="{anchor}">{label}</a></td><td class="mut">{metric}</td>{cells}</tr>'
    return out + "</tbody></table></div>"


# ---------------------------------------------------------------- sections
DL = {r["id"]: r for r in map(json.loads, open(H / "data/labels.jsonl"))}
FR = {n: load("data", "solo", n) for n in NAMES}
FRM = {n: load("data", "ref", n) for n in NAMES}


def truth_text(L):
    k = L["kind"]
    if k == "none": return "Clean frame"
    if k == "offset": return f'{L.get("side") or ""} {L["part"]} shifted {L["direction"]} {L["mag"]} px'.strip().capitalize()
    if k == "layer_order": return "Sleeve drawn over the torso" if L["part"] == "arm" else f'{L["part"].capitalize()} drawn in front'
    return "Hand mirrored"


def frame_card(i, R=FR):
    L = DL[i]; img = A.get(i + "__marked", A[i])
    return f'''<figure class="card"><div class="plate"><img class="as-marked" src="{img}" alt=""><img class="as-seen" src="{A[i]}" alt=""></div>
<figcaption><div class="truth-line"><span class="chip {'bad' if L['defect'] else 'ok'}">{'Defect' if L['defect'] else 'Clean'}</span>{esc(truth_text(L))}</div>
{bars3({n: R[n][i]["answers"]["defect"]["noul"] for n in NAMES if i in R[n]})}</figcaption></figure>'''


def frames_section():
    rows = [("Separation, AUROC (95% CI)", per_model(M["frames"], auc_cell)),
            ("Shifted frames caught at 10% false alarms", per_model(M["frames"], lambda b: (pc(b["catch10"]), b["catch10"]))),
            ("Balanced accuracy at P = 0.5", per_model(M["frames"], lambda b: (pc(b["bacc50"]), b["bacc50"]))),
            ("Answered kind = “none” on a defective frame", per_model(M["frames"], lambda b: (pc(b["kind_none"]), b["kind_none"]))),
            ("Right part named (offsets, chance 11%)", per_model(M["frames"], lambda b: (pc(b["part"]), b["part"]))),
            ("Right direction (offsets, chance 25%)", per_model(M["frames"], lambda b: (pc(b["dir"]), b["dir"]))),
            ("Mean P(defect): clean / 24 px shift", per_model(M["frames"], lambda b: (f'{b["by_mag"]["0"]:.2f} / {b["by_mag"]["24"]:.2f}', b["by_mag"]["24"] - b["by_mag"]["0"])))]
    cards = "".join(frame_card(i) for i in ["fox_setup_0.0__clean", "fox_setup_0.0__shift_hand_l_right_24", "fox_setup_0.0__shift_head_down_24",
                                             "moose_setup_0.0__layer_upperarm_l_over_torso", "moose_setup_0.0__mirror_hand_l", "moose_thumbs_up_0.5__shift_hips_down_16"])
    rows2 = [("Mean P(defect) on 60 defective setup frames", per_model(M["frames_master"], lambda b: (f2(b["meanP"]), None))),
             ("Right direction (chance 25%)", per_model(M["frames_master"], lambda b: (pc(b["dir"]), b["dir"]))),
             ("Right part named (chance 11%)", per_model(M["frames_master"], lambda b: (pc(b["part"]), b["part"])))]
    i = "fox_setup_0.0__shift_head_left_24"
    ex = f'''<div class="refrow"><figure class="card"><img src="{A["master_fox"]}" alt="master"><figcaption class="mut">`master`: approved illustration</figcaption></figure>
<figure class="card"><div class="plate"><img class="as-marked" src="{A[i + "__marked"]}" alt=""><img class="as-seen" src="{A[i]}" alt=""></div>
<figcaption><div class="truth-line"><span class="chip bad">Defect</span>Head shifted left 24 px</div>{bars3({n: FRM[n][i]["answers"]["defect"]["noul"] for n in NAMES if i in FRM[n]})}</figcaption></figure></div>'''
    return f'''<section id="t-frames"><span class="eyebrow">Test 1 · full frame</span><h2>A whole frame with one planted defect</h2>
<p class="lede2">Asked of a ~520×720 render: <q>Does the frame show a rigging or stitching defect?</q>, plus kind, part, side, direction and
size. 120 frames from the approved rigs: 38 clean; 82 with one part shifted 3–24 px, a sleeve over the torso, a tail in front, or a
mirrored hand.</p>
{table(rows)}
<div class="cardhead"><h3>What the models saw, and what they said</h3><label class="toggle"><input type="checkbox" class="seen-toggle"> Show exactly what the models saw</label></div>
<div class="grid">{cards}</div>
<p class="tnote">The magenta box marks the planted change for this page; the models got the plain image. None of the three can tell
these frames apart: a 3–24 px shift at this scale is a handful of pixels on a 520 px figure.</p>
<h3>Test 1b · the same frames with the approved master as a second image</h3>
{table(rows2, note="Setup pose only, 60 defective frames (no clean setup frame fell in this sample, so there's no separation score). Jev rates nearly every frame as defective once it sees the master, because the approved rig itself differs from the master.")}
{ex}</section>'''


def joint_section():
    def rows_for(sec):
        S = M[sec]
        return [("AUROC, original labels (15 clean joints)", per_model(S, lambda b: auc_cell(b["original"]))),
                ("AUROC, audited labels (11 clean joints)", per_model(S, lambda b: auc_cell(b["audited"]))),
                ("Caught at 10% false alarms, audited", per_model(S, lambda b: (pc(b["audited"]["catch10"]), b["audited"]["catch10"]))),
                ("Shifted joint scores above its own clean version", per_model(S, lambda b: (pc(b["same_joint"]), b["same_joint"]))),
                ("Mean P(displaced) at 8 / 16 / 24 px", per_model(S, lambda b: (" / ".join(f2(b["by_mag"][k]) for k in ("8", "16", "24")), None))),
                ("Fix direction right (chance 25%)", per_model(S, lambda b: (pc(b["dir"]), b["dir"])))]
    JR, JM = {n: load("jref", "joint", n) for n in NAMES}, {n: load("jref", "jref", n) for n in NAMES}

    def jcard(i, mimg, rimg, note):
        G = {r["id"]: r for r in map(json.loads, open(H / "jref/labels_gt.jsonl"))}[i]
        disp = (G["char"], G["slot"]) in {("fox", "hand_l"), ("fox", "hand_r"), ("moose", "hand_l"), ("moose", "hand_r")} and not G["defect"]
        chip = '<span class="chip warn">Disputed clean</span>' if disp else (f'<span class="chip {"bad" if G["defect"] else "ok"}">{"Defect" if G["defect"] else "Clean"}</span>')
        t = f'{G["slot"].replace("_l", "").replace("_r", "")} shifted {G["direction"]} {G["mag"]} px' if G["defect"] else f'{G["char"]} {G["slot"].replace("_", " ")}, approved rig'
        return f'''<figure class="card"><div class="pairimgs2"><div><img src="{mimg}" alt=""><span class="mini">master</span></div><div><img src="{rimg}" alt=""><span class="mini">render</span></div></div>
<figcaption><div class="truth-line">{chip}{esc(t)}</div>{bars3({n: JR[n][i]["answers"]["detached"]["noul"] for n in NAMES if i in JR[n]}, "render only")}
{bars3({n: JM[n][i]["answers"]["detached"]["noul"] for n in NAMES if i in JM[n]}, "with master")}<span class="note">{esc(note)}</span></figcaption></figure>'''
    cards = (jcard("fox_shift_hand_l_down_24__hand_l", A["r2_fox_shift_hand_l_down_24__hand_l__ref"], A["r2_fox_shift_hand_l_down_24__hand_l"], "A gap opens under the cuff.")
             + jcard("fox_shift_boot_l_right_24__boot_l", A["r2_fox_shift_boot_l_right_24__boot_l__ref"], A["r2_fox_shift_boot_l_right_24__boot_l"], "The boot slides out of the trouser leg.")
             + jcard("fox_shift_hand_l_up_24__hand_l", A["r2_fox_shift_hand_l_up_24__hand_l__ref"], A["r2_fox_shift_hand_l_up_24__hand_l"], "Pushed up into the cuff: the seam hides it.")
             + jcard("fox_clean__boot_l", A["aud_fox_clean__boot_l__ref"], A["aud_fox_clean__boot_l"], "A truly clean joint: all three stay low.")
             + jcard("moose_clean__hand_l", A["aud_moose_clean__hand_l__ref"], A["aud_moose_clean__hand_l"], "Labelled clean, but the wrist band differs from the master. Jev and 27B flag it."))
    return f'''<section id="t-joint"><span class="eyebrow">Tests 2 and 3 · joint close-ups</span><h2>One joint, cropped where the rig says it is</h2>
<p class="lede2">Setup pose. Each crop is a square centred on a bone's attachment point (wrist, neck, waist, ankle, tail and antler roots),
rendered at 2× so render and master are equally sharp. 363 crops: 180 with that joint's part shifted 8, 16 or 24 px in one of four
directions. Two questions: <q>Is the part displaced from its joint?</q> and <q>Which way has it moved?</q>. Test 2 sends the render
crop alone; Test 3 also sends the same square cut from the approved master.</p>
<h3>Test 2 · render crop only</h3>{table(rows_for("joint_render"))}
<h3>Test 3 · master crop + render crop</h3>{table(rows_for("joint_master"), note="Audited labels drop the four approved hand joints that don't match the master from the clean set (see Ground truth). With them counted as clean, every model looks worse, and Jev, which flags them hardest, looks worst.")}
<div class="grid">{cards}</div></section>'''


def prev_section():
    S = M.get("joint_prev", {})
    if not S: return ""
    rows = [("Says “moved” (P > 0.5) on shifted crops", per_model(S, lambda b: (pc(b.get("shifted_moved_rate")), b.get("shifted_moved_rate")))),
            ("Mean P(moved) at 8 / 16 / 24 px", per_model(S, lambda b: (" / ".join(f2(b["by_mag"][k]) for k in ("8", "16", "24")), None))),
            ("Mean P(moved) when before and after are identical", per_model(S, lambda b: (f2(b.get("identical_moved")), -(b.get("identical_moved") or 0)))),
            ("Fix direction right (chance 25%)", per_model(S, lambda b: (pc(b["dir"]), b["dir"]))),
            ("…at 8 / 16 / 24 px", per_model(S, lambda b: (" / ".join(pc(b["dir_by_mag"][k]) for k in ("8", "16", "24")), None))),
            ("Most common direction answer", per_model(S, lambda b: (max(b["dir_answers"], key=b["dir_answers"].get) + f' ({max(b["dir_answers"].values())}/180)', None)))]
    R = {n: load("jref", "cref", n) for n in NAMES}
    G = {r["id"]: r for r in map(json.loads, open(H / "jref/labels_gt.jsonl"))}
    cards = ""
    for i in ["fox_shift_hand_l_down_24__hand_l", "fox_shift_boot_r_right_16__boot_r", "moose_shift_head_up_24__head", "moose_shift_hand_r_left_8__hand_r"]:
        if f"cref_{i}__before" not in A: continue
        L = G[i]
        dirs = " · ".join(f'{n.replace("Clef ", "")}: {max({k: v for k, v in R[n][i]["answers"]["direction"]["probabilities"].items() if k != "none"}.items(), key=lambda x: x[1])[0]}' for n in NAMES if i in R[n])
        cards += f'''<figure class="card"><div class="pairimgs2"><div><img src="{A[f"cref_{i}__before"]}" alt=""><span class="mini">before</span></div><div><img src="{A[f"cref_{i}__after"]}" alt=""><span class="mini">after</span></div></div>
<figcaption><div class="truth-line"><span class="chip bad">Moved</span>{esc(L["slot"].replace("_l","").replace("_r",""))} {L["direction"]} {L["mag"]} px</div>
{bars3({n: R[n][i]["answers"]["detached"]["noul"] for n in NAMES if i in R[n]}, "P(moved)")}<span class="note">Direction answers: {esc(dirs)}</span></figcaption></figure>'''
    return f'''<section id="t-prev"><span class="eyebrow">Test 4 · new · joint close-up against the previous render</span><h2>Did this fix round move the part, and which way?</h2>
<p class="lede2">The fix-loop question. The same joint crop from the approved render (<i>before</i>) and from the shifted render (<i>after</i>),
cut at exactly the same place, so both sides have exact ground truth and the master's own differences are out of the picture.
180 shifted crops, plus the 15 clean joints shown against themselves as a check.</p>
{table(rows)}
<div class="legend-box"><span class="jev">Jev's box</span><span class="gt">True part box (exact, from the rig layer)</span></div>
<div class="grid">{cards}</div>
<p class="tnote">Even with a perfectly clean reference, no model gives a usable fix direction. Each has a favourite answer it gives
whatever the shift. Detecting <i>that</i> something moved works much better than saying which way.</p></section>'''


def real_section():
    S, P = M["real_single"], M["real_pairs"]
    rows = [("All 38 tiles, AUROC (CI)", per_model(S, lambda b: auc_cell(b["all"]))),
            ("Full body (11 rejected + 11 approved)", per_model(S, lambda b: auc_cell(b["full_body"]))),
            ("Sleeve over torso (8 + 8)", per_model(S, lambda b: auc_cell(b["sleeves"]))),
            ("Same pose: rejected scored above its fix", per_model(S, lambda b: (f'{b["same_pose"][0]}/{b["same_pose"][1]}', b["same_pose"][0])))]
    rows2 = [("Pairs right, both orders averaged", per_model(P, lambda b: (f'{b["all"]["right"]}/{b["all"]["n"]}', b["all"]["right"]))),
             ("Full-body pairs: right · mean P(correct)", per_model(P, lambda b: (f'{b["full_body"]["right"]}/{b["full_body"]["n"]} · {b["full_body"]["mean"]:.2f}', b["full_body"]["mean"]))),
             ("Sleeve pairs: right · mean P(correct)", per_model(P, lambda b: (f'{b["sleeves"]["right"]}/{b["sleeves"]["n"]} · {b["sleeves"]["mean"]:.2f}', b["sleeves"]["mean"]))),
             ("Answered “image 1” (no bias = 50%)", per_model(P, lambda b: (pc(b["image1_share"]), -abs(b["image1_share"] - .5))))]

    def tile(i):
        return f'''<div><img src="{A[i]}" alt=""><span class="chip {'bad' if '_r0_' in i else 'ok'}">{'Rejected' if '_r0_' in i else 'Approved fix'}</span>{bars3({n: S[n]["scores"][i] for n in NAMES})}</div>'''
    pairs_html = "".join(f'<figure class="card pairfig2"><div class="pairimgs2">{tile(a)}{tile(b)}</div></figure>' for a, b in [
        ("real_before_after_fox_r0_c0", "real_before_after_fox_r1_c0"), ("real_before_after_moose_r0_c2", "real_before_after_moose_r1_c2"),
        ("real_shoulders_ab_moose_r0_c1", "real_shoulders_ab_moose_r1_c1")])
    return f'''<section id="t-real"><span class="eyebrow">Test 5 · the frames your reviewer actually rejected</span><h2>Real reviewed defects from checkpoint 6</h2>
<p class="lede2">19 rejected/approved pairs sliced from the review sheets, label text cropped out. 11 full-body pairs (old rig vs
annotated rig, six poses) and 8 sleeve pairs (sleeve over vs under the torso). First each frame alone, then both renders of a pose
together: <q>Which one shows a rigging or stitching defect?</q>, asked in both orders and averaged.</p>
{table(rows, head="One frame at a time")}
{table(rows2, head="Two frames: which is worse")}
<div class="pairgrid">{pairs_html}</div>
<p class="tnote">Jev separates the full-body rejects from their fixes almost perfectly, one frame at a time. Sleeve layer order stays
hard for every model. It's a subtle overlap at the shoulder.</p></section>'''


def rounds_section():
    S, P = M.get("rounds_single", {}), M.get("rounds_pairs", {})
    if not S: return ""
    rows = [("All 96 frames, AUROC (CI)", per_model(S, lambda b: auc_cell(b["all"]))),
            ("Oldest build vs approved", per_model(S, lambda b: auc_cell(b["g1"]))),
            ("Previous build vs approved", per_model(S, lambda b: auc_cell(b["g2"]))),
            ("Fox only", per_model(S, lambda b: auc_cell(b["fox"], False))), ("Moose only", per_model(S, lambda b: auc_cell(b["moose"], False))),
            ("Same pose: older build scored above approved", per_model(S, lambda b: (f'{b["same_pose"][0]}/{b["same_pose"][1]}', b["same_pose"][0] / b["same_pose"][1])))]
    rows2 = [("All 58 pairs right (both orders)", per_model(P, lambda b: (f'{b["all"]["right"]}/{b["all"]["n"]} · {b["all"]["mean"]:.2f}', b["all"]["right"]))),
             ("Oldest build vs approved", per_model(P, lambda b: (f'{b["g1"]["right"]}/{b["g1"]["n"]} · {b["g1"]["mean"]:.2f}', b["g1"]["right"]))),
             ("Previous build vs approved", per_model(P, lambda b: (f'{b["g2"]["right"]}/{b["g2"]["n"]} · {b["g2"]["mean"]:.2f}', b["g2"]["right"]))),
             ("Answered “image 1” (no bias = 50%)", per_model(P, lambda b: (pc(b["image1_share"]), -abs(b["image1_share"] - .5))))]
    trip = ""
    for c, pose in [("fox", "setup_0.0"), ("moose", "wave_1.2"), ("fox", "cheer_jump_0.6")]:
        cells = ""
        for g, lbl in (("g1", "Oldest build"), ("g2", "Previous build"), ("g3", "Approved")):
            k = f"{c}_{g}_{pose}"
            if f"rd_{k}" not in A or k not in S["Jev 1.14"]["scores"]: continue
            cells += f'''<div><img src="{A[f"rd_{k}"]}" alt=""><span class="chip {'ok' if g == 'g3' else 'bad'}">{lbl}</span>{bars3({n: S[n]["scores"].get(k) for n in NAMES if k in S[n]["scores"]})}</div>'''
        trip += f'<figure class="card"><div class="trip">{cells}</div></figure>'
    return f'''<section id="t-rounds"><span class="eyebrow">Test 6 · new · three generations of each rig</span><h2>Older rig builds against the approved one</h2>
<p class="lede2">A bigger real set. The two earlier rig builds on disk (<code>fox-parts</code>/<code>moose-parts</code>, then
<code>part-variants</code>, which became the "before" in the review sheets) and the approved build, rendered in the same 19 poses:
setup, idle, wave, cheer, point, thumbs up and hold card. 96 frames (58 from older builds), 58 same-pose pairs. The labels are by
build, not by frame: an older build was rejected as a whole, so a few of its poses may look fine.</p>
{table(rows, head="One frame at a time")}
{table(rows2, head="Two frames: which is worse (right · mean P)")}
<div class="trips">{trip}</div></section>'''


def box_section():
    B = M["box"]
    if not B: return ""
    loc = B["loc_with master"]; lr = B["loc_render only"]
    rel = "".join(f'<tr><td class="num">{c:.2f}</td><td class="num">{h:.0%}</td><td class="num">{n}</td></tr>' for c, h, n in loc["rel"])
    dirrows = [("Master crop box → render crop box (same request)", B["dir_master_boxes"]),
               ("Previous render → new render (same request)", B.get("dir_prev_boxes_same_request")),
               ("Previous render → new render (separate requests)", B["dir_prev_boxes_separate"]),
               ("Two-pass: box, crop tight, box again", B.get("dir_prev_boxes_zoom")),
               ("Perfect boxes (ceiling)", B["dir_true_boxes"])]
    dtab = '<div class="tablewrap"><table class="cmp"><thead><tr><th>Fix direction from two boxes</th><th>Right</th><th>Shifts</th></tr></thead><tbody>' + "".join(
        f'<tr><td>{l}</td><td class="num">{pc(d["acc"]) if d else "–"}</td><td class="num">{d["n"] if d else "–"}</td></tr>' for l, d in dirrows) + "</tbody></table></div>"
    z = B.get("zoom", {})
    boxes = "".join(f'''<figure class="card"><div class="pairimgs2"><div><img src="{A["r4m_" + k]}" alt=""><span class="mini">master</span></div><div><img src="{A["r4r_" + k]}" alt=""><span class="mini">render</span></div></div>
<figcaption class="mut">{esc(note)}</figcaption></figure>''' for k, note in [
        ("fox_shift_hand_l_right_24__hand_l", "Hand moved right 24 px: the render box moves right. Note the master box sits on the master's own hand, not on the rig's dashed position."),
        ("moose_shift_hand_r_down_24__hand_r", "Hand moved down 24 px: the boxes differ mostly sideways, giving the wrong direction.")])
    zoom = (f'''<figure class="card"><div class="pairimgs2"><div><img src="{A["zoom_first"]}" alt=""><span class="mini">pass 1</span></div><div><img src="{A["zoom_second"]}" alt=""><span class="mini">pass 2 (close-up)</span></div></div>
<figcaption class="mut">Two-pass Box: crop tightly around the first box and ask again.</figcaption></figure>''' if "zoom_first" in A else "")
    return f'''<section id="t-box"><span class="eyebrow">Test 7 · Jev only · the new Box question</span><h2>Box: where is the part?</h2>
<p class="lede2">Box takes a target description (<q>the hand that comes out of the sleeve cuff in `render`</q>) and returns four edges as
fractions of the image, plus a confidence. Neither Clef model has an equivalent. Ground truth for render crops is exact (the part's
rig layer). On master crops there's no exact box, so the master boxes are checked against your hand-placed wrist and fingertip
landmarks instead.</p>
<div class="legend-box"><span class="jev">Jev's box</span><span class="gt">True box (on master crops: the clean rig's box, only an approximation)</span></div>
<div class="grid">{boxes}{zoom}</div>
<div class="figs">
  <div class="fig"><span class="v">{lr["miou"]:.2f}</span><span class="k">mean IoU with the true part, render crop alone</span></div>
  <div class="fig"><span class="v">{loc["miou"]:.2f}</span><span class="k">mean IoU on the render crop, with the master also present</span></div>
  <div class="fig"><span class="v">{loc["full"]:.2f}</span><span class="k">mean IoU when the part is fully inside the crop</span></div>
  <div class="fig"><span class="v">{pc(B["master_hand_landmarks"]["rate"])}</span><span class="k">master hand boxes containing both wrist and fingertip landmarks ({B["master_hand_landmarks"]["n"]})</span></div>
  <div class="fig"><span class="v">{B["edge_err"]:.2f}</span><span class="k">median box-edge error, as a share of the crop</span></div>
  <div class="fig"><span class="v">{B["edge_move"]["8"]:.2f} · {B["edge_move"]["16"]:.2f} · {B["edge_move"]["24"]:.2f}</span><span class="k">how far an edge actually moves for an 8 · 16 · 24 px shift</span></div>
</div>
<div class="two">{dtab}
<div class="tablewrap"><table class="cmp"><thead><tr><th colspan="3">Box calibration: confidence vs box right (IoU ≥ 0.5)</th></tr><tr><th>Mean confidence</th><th>Box right</th><th>Boxes</th></tr></thead><tbody>{rel}</tbody></table>
<p class="tnote">Confidence runs only {loc["conf"][0]:.2f}–{loc["conf"][1]:.2f}. Its rank correlation with box quality is
{lr["rho"]:.2f} on the render alone and {loc["rho"]:.2f} with the master. Treat it as a weak ranking signal, not a probability.</p></div></div>
<p class="tnote">Box finds the part well enough to choose where to crop or what to inspect. Its edges are off by about as much as the
shifts move them, so subtracting two boxes can't read an 8–24 px offset yet.{f" The two-pass close-up changed mean IoU from {z['miou_first']:.2f} to {z['miou_second']:.2f}." if z else ""}
On full frames, the box for "the part that looks wrong" landed on the planted change {pc((B.get("point") or {}).get("hit"))} of the time; a random point lands there about 7%.</p></section>'''


def ground_truth_section():
    S = M["joint_master"]
    vals = {n: S[n]["clean_by_joint"] for n in NAMES}
    rows = ""
    for j in ["fox hand_l", "fox hand_r", "moose hand_l", "moose hand_r", "fox boot_l", "moose hips"]:
        disp = "hand" in j
        rows += f'<tr><td>{j}{" <span class=\"chip warn\">disputed</span>" if disp else ""}</td>' + "".join(f'<td class="num">{vals[n][j]:.2f}</td>' for n in NAMES) + "</tr>"
    imgs = "".join(f'''<figure class="card"><div class="pairimgs2"><div><img src="{A[f"aud_{c}_clean__{s}__ref"]}" alt=""><span class="mini">master</span></div><div><img src="{A[f"aud_{c}_clean__{s}"]}" alt=""><span class="mini">approved rig</span></div></div>
<figcaption class="mut">{esc(t)}</figcaption></figure>''' for c, s, t in [
        ("fox", "hand_l", "Fox left hand: the glove sits off-centre and smaller in the cuff (also noted as a deferred T20 issue)."),
        ("moose", "hand_l", "Moose left hand: a furry wrist band shows between the cuff and the glove, which is turned differently."),
        ("moose", "hand_r", "Moose right hand: the same wrist band; a smaller glove."),
        ("fox", "boot_l", "Fox left boot: matches the master. A clean negative.")])
    return f'''<section id="t-gt"><span class="eyebrow">Ground truth · read this before the joint-crop numbers</span><h2>The approved rig isn't perfectly clean</h2>
<p class="lede2">The 183 "clean" joint crops are only <b>15 distinct images</b> (one per joint of the approved setup pose), each
repeated 6–20 times. Four of them are the hands, which don't match the master: the glove fit and the wrist trim are what took the most
fix rounds (T17b to M2). Those four make up 62 of the 183 negatives, and they're where Jev and 27B score highest. So every joint-crop
test is reported twice: as labelled, and <b>audited</b>, with those four joints taken out of the clean set (they stay as positives when
shifted). The real reviewed frames and the rig-generation tests don't depend on this audit.</p>
<div class="grid">{imgs}</div>
<div class="tablewrap"><table class="cmp"><thead><tr><th>P(displaced), clean approved joint vs master</th>{"".join(f'<th class="{CLS[n]}h">{n}</th>' for n in NAMES)}</tr></thead><tbody>{rows}</tbody></table></div></section>'''


def cost_section():
    C = M["cost"]
    rows = [("Calls", per_model(C, lambda b: (f'{b["calls"]:,}', None))), ("Input tokens", per_model(C, lambda b: (f'{b["tokens"]/1e6:.2f}M', None))),
            ("Cost at list price", per_model(C, lambda b: (f'${b["usd"]:.2f}', -b["usd"]))), ("Median latency per call", per_model(C, lambda b: (f'{b["latency"]:.2f} s', -b["latency"]))),
            ("Price per million input tokens", {"Clef Flash": ("$0.038", None), "Clef 27B": ("$0.24", None), "Jev 1.14": ("$0.042", None)}),
            ("Box question", {"Clef Flash": ("no", None), "Clef 27B": ("no", None), "Jev 1.14": ("yes", None)})]
    return f'''<section id="t-cost"><span class="eyebrow">Cost and speed</span><h2>All three are cheap; Jev and Flash are fastest</h2>{table(rows)}
<p class="tnote">Clef ran on Cloudflare Workers AI (the 12 GB local Ollama build doesn't fit this 16 GB Mac's GPU memory). Jev ran on
TypeSafe's API with the images preview header. Output tokens are free on all three.</p></section>'''


CSS = open(H / "page_template.html").read().split("<style>")[1].split("</style>")[0]
EXTRA = """
:root { --m1: #3563c9; --m2: #b7740a; --m3: #6a3fd0; --warn: #a15c00; --warn-soft: #fbefd9; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --m1: #86a8f2; --m2: #e5a940; --m3: #b59bff; --warn: #f0b75a; --warn-soft: #3a2a12; } }
:root[data-theme="dark"] { --m1: #86a8f2; --m2: #e5a940; --m3: #b59bff; --warn: #f0b75a; --warn-soft: #3a2a12; }
.chip.warn { background: var(--warn-soft); color: var(--warn); }
.lede2 { max-width: 75ch; color: var(--muted); }
.tnote { font-size: .86rem; color: var(--muted); max-width: 80ch; }
.mut { color: var(--muted); font-size: .84rem; }
.m1h { color: var(--m1); } .m2h { color: var(--m2); } .m3h { color: var(--m3); }
table.cmp td.best { font-weight: 700; color: var(--ink); background: color-mix(in srgb, var(--accent) 10%, transparent); }
.ci { display: block; font-size: .72rem; color: var(--muted); font-weight: 400; }
table.score td { vertical-align: middle; }
table.score td a { color: var(--ink); text-decoration: none; border-bottom: 1px dotted var(--muted); }
td.meter { position: relative; min-width: 110px; }
td.meter .mfill { position: absolute; left: 10px; top: 50%; height: 8px; margin-top: -4px; max-width: calc(100% - 20px); border-radius: 4px; opacity: .28; }
td.meter.m1 .mfill { background: var(--m1); } td.meter.m2 .mfill { background: var(--m2); } td.meter.m3 .mfill { background: var(--m3); }
td.meter .mval { position: relative; font: 600 .86rem var(--f-mono); font-variant-numeric: tabular-nums; }
td.meter.best .mval { color: var(--accent); }
.bars3 { display: grid; gap: 3px; }
.b3 { display: grid; grid-template-columns: 44px 1fr 36px; gap: 6px; align-items: center; font: .74rem var(--f-mono); }
.b3t { position: relative; height: 7px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.b3f { position: absolute; inset: 0 auto 0 0; }
.b3.m1 .b3f { background: var(--m1); } .b3.m2 .b3f { background: var(--m2); } .b3.m3 .b3f { background: var(--m3); }
.b3 .half { position: absolute; top: -2px; bottom: -2px; left: 50%; width: 2px; background: var(--ink); opacity: .5; }
.b3v { text-align: right; font-variant-numeric: tabular-nums; }
.card { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; display: grid; align-content: start; min-width: 0; }
.card > img { width: 100%; height: auto; display: block; }
.pairimgs2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--line); }
.pairimgs2 > div { background: var(--surface); display: grid; gap: 6px; align-content: start; padding-bottom: 8px; }
.pairimgs2 img { width: 100%; height: auto; display: block; background: #d6d6d6; }
.pairimgs2 .chip, .pairimgs2 .bars3, .trip .chip, .trip .bars3 { margin-inline: 8px; }
.pairimgs2 .chip, .trip .chip { justify-self: start; }
.pairimgs2 .mini { margin-inline: 8px; }
.trips { display: grid; gap: 16px; }
.trip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--line); }
.trip > div { background: var(--surface); display: grid; gap: 6px; align-content: start; padding-bottom: 8px; }
.trip img { width: 100%; height: auto; display: block; }
.pairfig2 .pairimgs2 img { background: #d6d6d6; }
.cardhead { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: end; gap: 12px; }
.toc { display: flex; flex-wrap: wrap; gap: 8px; }
.toc a { font-size: .84rem; border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; color: var(--ink); text-decoration: none; background: var(--surface); }
.models { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.model { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px; display: grid; gap: 4px; border-top: 4px solid var(--c); }
.model b { font-family: var(--f-display); font-size: 1.1rem; }
@media (max-width: 520px) { .trip { grid-template-columns: 1fr; } }
"""
body = f'''<title>Rig Judge Model Trial</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Public+Sans:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}{EXTRA}</style>
<div class="wrap">
<header>
  <span class="eyebrow">Experiment · 12–15 Oct 2026 · rig-annotations branch</span>
  <h1>Rig Judge Model Trial</h1>
  <p class="lede">Can a fast decision model look at a rendered rig and tell us whether the parts are stitched correctly, and which way to
  nudge a part that isn't? Three System One models (Cloudflare's Clef Flash and Clef 27B, and TypeSafe's Jev 1.14) got the same images
  and the same questions in seven tests: planted defects, joint close-ups, the frames your reviewer rejected, and three generations of each rig.</p>
  <div class="verdicts">
    <div class="verdict maybe"><span class="q">Spot the real rejects, one frame at a time</span><span class="a">Jev, clearly</span>
      <p>Full-body rejects vs their fixes: AUROC {M["real_single"]["Jev 1.14"]["full_body"]["auroc"]:.2f} for Jev,
      {M["real_single"]["Clef 27B"]["full_body"]["auroc"]:.2f} for 27B and {M["real_single"]["Clef Flash"]["full_body"]["auroc"]:.2f} for Flash.</p></div>
    <div class="verdict maybe"><span class="q">Flag a displaced joint in a close-up</span><span class="a">Jev and 27B, with the master</span>
      <p>On the audited labels: Jev {M["joint_master"]["Jev 1.14"]["audited"]["auroc"]:.2f}, 27B {M["joint_master"]["Clef 27B"]["audited"]["auroc"]:.2f},
      Flash {M["joint_master"]["Clef Flash"]["audited"]["auroc"]:.2f}. Larger shifts are caught more often.</p></div>
    <div class="verdict no"><span class="q">Say which way to move the part</span><span class="a">Not yet, any model</span>
      <p>Direction answers sit near chance in every condition, and Jev's Box edges are as coarse as the shifts. Leave nudges to code.</p></div>
  </div>
  <nav class="toc"><a href="#scoreboard">Scoreboard</a><a href="#t-gt">Ground truth</a><a href="#t-frames">1 Full frame</a><a href="#t-joint">2–3 Joint crops</a><a href="#t-prev">4 Previous render</a><a href="#t-real">5 Real rejects</a><a href="#t-rounds">6 Rig generations</a><a href="#t-box">7 Box</a><a href="#t-cost">Cost</a><a href="#t-next">Next</a></nav>
</header>

<section id="scoreboard"><span class="eyebrow">Scoreboard</span><h2>Every test, every model</h2>
<p class="lede2">Headline number per test; the best model is highlighted. AUROC: 0.5 is chance, 1.0 perfect separation. Click a test for its section.</p>
{scoreboard()}
<div class="models">
  <div class="model" style="--c: var(--m1)"><b>Clef Flash</b><span class="mut">Cloudflare · 9B · $0.038/M tokens · images as data URIs</span></div>
  <div class="model" style="--c: var(--m2)"><b>Clef 27B</b><span class="mut">Cloudflare · 27B · $0.24/M tokens · same contract</span></div>
  <div class="model" style="--c: var(--m3)"><b>Jev 1.14</b><span class="mut">TypeSafe · $0.042/M tokens · images as referenced assets · adds Box</span></div>
</div></section>

{ground_truth_section()}
{frames_section()}
{joint_section()}
{prev_section()}
{real_section()}
{rounds_section()}
{box_section()}
{cost_section()}

<section id="t-next"><span class="eyebrow">What this means</span><h2>Where a model earns a place in the pipeline</h2>
<div class="ideas">
  <div class="idea"><h3>A reject screen before human review</h3><p>Jev, one frame at a time, on full-body frames. It separates real rejects
  from fixes and ranks older builds below approved ones. Calibrate a threshold per character on more rounds, then let it flag frames for review.</p><span class="cost">≈ $0.0001 per frame</span></div>
  <div class="idea"><h3>A joint check with the master beside it</h3><p>Jev or 27B on master + render crops at each joint. Useful for gaps at
  hands and boots. Clean up the approved set's hand joints first, or they read as permanent false alarms.</p><span class="cost">≈ 1.8k tokens per joint</span></div>
  <div class="idea"><h3>Keep nudges in code</h3><p>Direction is at chance for all three models, and two boxes can't resolve 8–24 px. Align
  each part's own mask to the master or the previous render. That's exact.</p><span class="cost">no model cost</span></div>
  <div class="idea"><h3>Use Box to aim, not to measure</h3><p>Box finds the part (IoU about 0.5–0.6; master hand boxes cover your wrist
  and fingertip landmarks {pc(M["box"]["master_hand_landmarks"]["rate"])} of the time). Good for choosing where to crop or what to inspect next.</p><span class="cost">Jev only</span></div>
</div></section>

<footer><span>Raw answers, labels and scripts: <code>experiments/2026-10-12-clef-judge/</code>. No pipeline code was changed.
Every number on this page is computed from the saved result files.</span></footer>
</div>
<script>
(function () {{
  var ts = document.querySelectorAll('.seen-toggle');
  function apply(v) {{ document.body.classList.toggle('seen', v); ts.forEach(function (t) {{ t.checked = v; }}); }}
  var v = false; try {{ v = localStorage.getItem('clef-seen') === '1'; }} catch (e) {{}}
  apply(v);
  ts.forEach(function (t) {{ t.addEventListener('change', function () {{ apply(t.checked); try {{ localStorage.setItem('clef-seen', t.checked ? '1' : '0'); }} catch (e) {{}} }}); }});
}})();
</script>'''
(H / "rig-judge-trial.html").write_text(body)
print("wrote", len(body) // 1024, "KB")

#!/usr/bin/env python3
"""Build the report page (clef-rig-judge.html) from assets.json and the recorded result files."""
import html, json, statistics
from pathlib import Path

H = Path(__file__).parent
A = json.load(open(H / "assets.json"))


def load(p):
    return {r["id"]: r for r in map(json.loads, open(H / p))}


solo, ref = load("data/results_solo_cloudflare_clef-flash.jsonl"), load("data/results_ref_cloudflare_clef-flash.jsonl")
joint, rsolo = load("data/joints/results_joint_cloudflare_clef-flash.jsonl"), load("real/results_solo_cloudflare_clef-flash.jsonl")
pair, pswap = load("real/results_pair_cloudflare_clef-flash.jsonl"), load("real/results_pair_swap_cloudflare_clef-flash.jsonl")
lab = {r["id"]: r for r in map(json.loads, open(H / "data/labels.jsonl"))}
jlab = {r["id"]: r for r in map(json.loads, open(H / "data/joints/labels.jsonl"))}
rlab = {r["id"]: r for r in map(json.loads, open(H / "real/labels.jsonl"))}
esc = html.escape


def bar(p, label="P(defect)", hot=False):
    return (f'<div class="pbar{" hot" if hot else ""}"><span class="plabel">{label}</span>'
            f'<span class="track"><span class="fill" style="width:{p*100:.1f}%"></span><span class="half"></span></span>'
            f'<span class="pval">{p:.2f}</span></div>')


def dist(probs, truth=None):
    rows = "".join(
        f'<div class="drow{" truth" if k == truth else ""}"><span class="dk">{esc(k)}</span><span class="dtrack">'
        f'<span class="dfill" style="width:{v*100:.1f}%"></span></span><span class="dv">{v:.2f}</span></div>'
        for k, v in sorted(probs.items(), key=lambda x: -x[1]))
    return f'<div class="dist">{rows}</div>'


def truth_text(L):
    k = L["kind"]
    if k == "none": return "Clean frame"
    if k == "offset": return f'{L.get("side") or ""} {L["part"]} shifted {L["direction"]} by {L["mag"]} px'.strip().capitalize()
    if k == "layer_order": return f'{L.get("side","")} sleeve drawn over the torso'.strip().capitalize() if L["part"] == "arm" else f'{L["part"].capitalize()} drawn in front'
    if k == "mirrored": return f'{L.get("side","")} hand mirrored'.strip().capitalize()
    return k


def syn_card(k, res=solo):
    L, a = lab[k], res[k]["answers"]
    img = A[k + "__marked"] if k + "__marked" in A else A[k]
    plain = A[k]
    defect = L["defect"]
    return f'''<figure class="spec">
  <div class="plate"><img class="as-marked" src="{img}" alt="{esc(truth_text(L))}, highlighted"><img class="as-seen" src="{plain}" alt="{esc(truth_text(L))}, as the model saw it"></div>
  <figcaption>
    <div class="truth-line"><span class="chip {'bad' if defect else 'ok'}">{'Defect' if defect else 'Clean'}</span>{esc(truth_text(L))}</div>
    {bar(a["defect"]["noul"])}
    <details><summary>Kind and direction answers</summary>
      <p class="mini">kind</p>{dist(a["kind"]["probabilities"], L["kind"])}
      <p class="mini">direction</p>{dist(a["direction"]["probabilities"], L["direction"])}
    </details>
  </figcaption>
</figure>'''


# ---------- aggregates for charts
def by_mag(res, labels, key="defect"):
    g = {}
    for k, r in res.items():
        L = labels[k]
        if L["kind"] in ("offset", "none"):
            g.setdefault(L.get("mag", 0), []).append(r["answers"][key]["noul"])
    return {m: (statistics.mean(v), len(v)) for m, v in sorted(g.items())}


S_SOLO, S_REF, S_JOINT = by_mag(solo, lab), by_mag(ref, lab), by_mag(joint, jlab, "detached")
XS = [0, 3, 8, 16, 24]


def line_chart():
    W, Hh, l, r, t, b = 640, 300, 52, 20, 18, 46
    x = lambda i: l + i * (W - l - r) / (len(XS) - 1)
    y = lambda p: t + (1 - p) * (Hh - t - b)
    g = []
    for p in (0, .25, .5, .75, 1):
        g.append(f'<line x1="{l}" x2="{W-r}" y1="{y(p):.1f}" y2="{y(p):.1f}" class="{"g50" if p == .5 else "gl"}"/>'
                 f'<text x="{l-10}" y="{y(p)+4:.1f}" class="ax" text-anchor="end">{p:.2f}</text>')
    g.append(f'<text x="{W-r}" y="{y(.5)-6:.1f}" class="ax" text-anchor="end">decision threshold 0.5</text>')
    for i, m in enumerate(XS):
        g.append(f'<text x="{x(i):.1f}" y="{Hh-b+20}" class="ax" text-anchor="middle">{"clean" if m == 0 else f"{m} px"}</text>')
    g.append(f'<text x="{(l+W-r)/2}" y="{Hh-6}" class="ax" text-anchor="middle">size of the shift applied to one part</text>')
    series = [("s1", "Full frame", S_SOLO), ("s2", "Frame + master", S_REF), ("s3", "Joint close-up", S_JOINT)]
    for cls, name, s in series:
        pts = [(x(i), y(s[m][0])) for i, m in enumerate(XS) if m in s]
        g.append(f'<polyline class="{cls} ln" points="{" ".join(f"{a:.1f},{b_:.1f}" for a, b_ in pts)}"/>')
        for (a, b_), m in zip(pts, [m for m in XS if m in s]):
            g.append(f'<circle class="{cls} dot" cx="{a:.1f}" cy="{b_:.1f}" r="4.5"><title>{name}, {"clean" if m == 0 else str(m)+" px"}: '
                     f'mean {s[m][0]:.2f} (n={s[m][1]})</title></circle>')
    return f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="Mean probability of defect by shift size for three conditions; all lines stay flat">{"".join(g)}</svg>'


PAIRS = []
for k in pair:
    pa = pair[k]["answers"]["worse"]["probabilities"][pair[k]["truth"]]
    pb = pswap[k]["answers"]["worse"]["probabilities"][pswap[k]["truth"]]
    PAIRS.append((k, (pa + pb) / 2, "shoulders" in k))


def pair_chart():
    W, Hh, l, r = 640, 150, 20, 20
    x = lambda p: l + p * (W - l - r)
    g = [f'<line x1="{x(0)}" x2="{x(1)}" y1="70" y2="70" class="gl"/>',
         f'<line x1="{x(.5)}" x2="{x(.5)}" y1="22" y2="112" class="g50"/>',
         f'<text x="{x(.5)}" y="14" class="ax" text-anchor="middle">coin flip</text>']
    for p in (0, .25, .5, .75, 1):
        g.append(f'<text x="{x(p):.1f}" y="134" class="ax" text-anchor="middle">{p:.2f}</text>')
    for i, (k, p, sh) in enumerate(sorted(PAIRS, key=lambda z: z[1])):
        yy = 50 if sh else 90
        g.append(f'<circle class="{"s2" if sh else "s1"} dot" cx="{x(p):.1f}" cy="{yy}" r="6"><title>{k[5:]}: {p:.2f}</title></circle>')
    g.append(f'<text x="{x(0)}" y="40" class="ax">sleeve over torso (8 pairs)</text>')
    g.append(f'<text x="{x(0)}" y="112" class="ax">full-body before / after (11 pairs)</text>')
    return f'<svg viewBox="0 0 {W} 146" role="img" aria-label="Probability of picking the defective render for each of 19 pairs">{"".join(g)}</svg>'


def real_pair(bad, good):
    pk = bad
    pa = pair[pk]["answers"]["worse"]["probabilities"][pair[pk]["truth"]]
    pb = pswap[pk]["answers"]["worse"]["probabilities"][pswap[pk]["truth"]]
    m = (pa + pb) / 2
    return f'''<figure class="pairfig">
  <div class="pairimgs">
    <div><img src="{A[bad]}" alt="Rejected render"><span class="chip bad">Rejected</span>{bar(rsolo[bad]["answers"]["defect"]["noul"])}</div>
    <div><img src="{A[good]}" alt="Approved fix"><span class="chip ok">Approved fix</span>{bar(rsolo[good]["answers"]["defect"]["noul"])}</div>
  </div>
  <figcaption>Asked "which one has the defect?" in both orders: picked the rejected render with
  <b class="{'good' if m > .5 else 'badtxt'}">{m:.2f}</b> ({pa:.2f} and {pb:.2f}).</figcaption>
</figure>'''


def joint_card(k):
    L, a = jlab[k], joint[k]["answers"]
    return f'''<figure class="jcard"><img src="{A["j_" + k]}" alt="joint crop">
  <figcaption><div class="truth-line"><span class="chip {'bad' if L['defect'] else 'ok'}">{'Defect' if L['defect'] else 'Clean'}</span>
  {esc(f"hand shifted {L['direction']} {L['mag']} px" if L['defect'] else 'hand in its cuff, as drawn')}</div>
  {bar(a["detached"]["noul"], "P(displaced)")}</figcaption></figure>'''


# ---------- round 2: setup-pose joint crops, with vs without the master crop
r2lab = {r["id"]: r for r in map(json.loads, open(H / "jref/labels.jsonl"))}
r2ref, r2no = load("jref/results_jref_cloudflare_clef-flash.jsonl"), load("jref/results_joint_cloudflare_clef-flash.jsonl")
r2sum = json.load(open(H / "jref/summary.json"))
reg = json.load(open(H / "jref/register.json"))


def d4(probs):
    p = {k: v for k, v in probs.items() if k != "none"}; return max(p, key=p.get)


def r2_card(k, note):
    L = r2lab[k]; a, b = r2ref[k]["answers"], r2no[k]["answers"]
    truth = f"{L['slot'].replace('_l','').replace('_r','')} shifted {L['direction']} {L['mag']} px" if L["defect"] else "clean joint"
    return f'''<figure class="r2card">
  <div class="r2imgs"><div><img src="{A["r2_" + k + "__ref"]}" alt="master crop"><span class="mini">Image 1 · master</span></div>
  <div><img src="{A["r2_" + k]}" alt="render crop"><span class="mini">Image 2 · render</span></div></div>
  <figcaption><div class="truth-line"><span class="chip {'bad' if L['defect'] else 'ok'}">{'Defect' if L['defect'] else 'Clean'}</span>{esc(truth)}</div>
  {bar(b["detached"]["noul"], "render only")}{bar(a["detached"]["noul"], "with master")}
  <span class="mini">direction answer (with master): {d4(a["direction"]["probabilities"])}{" ✓" if L["defect"] and d4(a["direction"]["probabilities"]) == L["direction"] else ""}</span>
  <span class="note">{esc(note)}</span></figcaption></figure>'''


def heat():
    from collections import defaultdict
    g, cl = defaultdict(list), defaultdict(list)
    for i, L in r2lab.items():
        b = L["slot"][:-2] if L["slot"][-2:] in ("_l", "_r") else L["slot"]
        v = r2no[i]["answers"]["detached"]["noul"]
        (g[(b, L["direction"])] if L["defect"] and L["mag"] >= 16 else cl[b] if not L["defect"] else []).append(v)
    rows = ""
    for b in ["boot", "hand", "tail", "hips", "head", "hoof", "antler"]:
        c = statistics.mean(cl[b])
        cells = f'<td class="num">{c:.2f}</td>'
        for d in ("up", "down", "left", "right"):
            m = statistics.mean(g[(b, d)]); lift = m - c
            cells += f'<td class="num heat" style="--h:{max(0, min(1, lift / 0.2)):.2f}">{m:.2f}</td>'
        rows += f"<tr><td>{b}</td>{cells}</tr>"
    return rows


regP = [r for r in reg if r["defect"]]
reg_dir = sum((("right" if r["dx"] > 0 else "left") if abs(r["dx"]) > abs(r["dy"]) else ("down" if r["dy"] > 0 else "up")) == r["direction"] for r in regP) / len(regP)

# ---------- round 3: Clef 27B on the same items
def aur(pos, neg): return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def cond_auc(labf, resf, key, m):
    L = {r["id"]: r for r in map(json.loads, open(H / labf))}; R = load(resf.format(m=m))
    pos = [R[i]["answers"][key]["noul"] for i in L if i in R and L[i]["defect"]]
    neg = [R[i]["answers"][key]["noul"] for i in L if i in R and not L[i]["defect"]]
    D = [i for i in L if i in R and L[i]["defect"] and L[i].get("direction") not in (None, "none")]
    dr = sum(d4(R[i]["answers"]["direction"]["probabilities"]) == L[i]["direction"] for i in D) / len(D) if D else None
    return aur(pos, neg), dr


R3 = ""
for name, lf, rf, key in [("Joint crop, render only", "jref/labels.jsonl", "jref/results_joint_cloudflare_{m}.jsonl", "detached"),
                          ("Joint crop + master crop", "jref/labels.jsonl", "jref/results_jref_cloudflare_{m}.jsonl", "detached"),
                          ("Full frame, planted defects", "data/labels.jsonl", "data/results_solo_cloudflare_{m}.jsonl", "defect"),
                          ("Full frame, real reviewed", "real/labels.jsonl", "real/results_solo_cloudflare_{m}.jsonl", "defect")]:
    (a1, d1), (a2, d2) = cond_auc(lf, rf, key, "clef-flash"), cond_auc(lf, rf, key, "clef")
    f = lambda d: f"{d:.0%}" if d is not None else "n/a"
    R3 += f'<tr><td>{name}</td><td class="num">{a1:.2f}</td><td class="num">{a2:.2f}</td><td class="num">{f(d1)}</td><td class="num">{f(d2)}</td></tr>'


def debiased(m):
    pv = "typesafe" if m.startswith("jev") else "cloudflare"
    A_, B_ = load(f"real/results_pair_{pv}_{m}.jsonl"), load(f"real/results_pair_swap_{pv}_{m}.jsonl")
    return {k: (A_[k]["answers"]["worse"]["probabilities"][A_[k]["truth"]] + B_[k]["answers"]["worse"]["probabilities"][B_[k]["truth"]]) / 2 for k in A_ if k in B_}


PF, PC = debiased("clef-flash"), debiased("clef")


def dumbbell():
    ks = sorted(PF, key=lambda k: ("shoulders" in k, PC[k]))
    W, l, r, row = 640, 150, 20, 22; Hh = 40 + row * len(ks)
    x = lambda p: l + (p - 0.3) / 0.7 * (W - l - r)
    g = [f'<line x1="{x(.5):.1f}" x2="{x(.5):.1f}" y1="18" y2="{Hh-10}" class="g50"/>',
         f'<text x="{x(.5):.1f}" y="12" class="ax" text-anchor="middle">coin flip</text>']
    for p in (.3, .5, .7, .9):
        g.append(f'<text x="{x(p):.1f}" y="{Hh}" class="ax" text-anchor="middle">{p:.1f}</text>')
    for i, k in enumerate(ks):
        y = 30 + i * row; nm = k.replace("real_", "").replace("before_after_", "full body · ").replace("shoulders_ab_", "sleeve · ").replace("_r0_c", " #")
        a, b = PF[k], PC[k]
        g.append(f'<text x="{l-10}" y="{y+4}" class="ax" text-anchor="end">{nm}</text>'
                 f'<line x1="{x(a):.1f}" x2="{x(b):.1f}" y1="{y}" y2="{y}" class="gl" style="stroke-width:3"/>'
                 f'<circle class="s1 dot" cx="{x(a):.1f}" cy="{y}" r="5"><title>Flash {a:.2f}</title></circle>'
                 f'<circle class="s3 dot" cx="{x(b):.1f}" cy="{y}" r="5"><title>27B {b:.2f}</title></circle>')
    return f'<svg viewBox="0 0 {W} {Hh+6}" role="img" aria-label="Per-pair probability of picking the rejected render, Flash vs 27B">{"".join(g)}</svg>'


bf = [k for k in PF if "before_after" in k]; sh = [k for k in PF if "shoulders" in k]

# ---------- round 4: Jev 1.14 (TypeSafe), with Box questions
def loadp(p): return load(p)


JV = "jev-1.14.0"
def auc_for(labf, resf, key, filt=lambda L: True):
    L = {r["id"]: r for r in map(json.loads, open(H / labf))}; R = load(resf)
    pos = [R[i]["answers"][key]["noul"] for i in L if i in R and L[i]["defect"] and filt(L[i])]
    neg = [R[i]["answers"][key]["noul"] for i in L if i in R and not L[i]["defect"] and filt(L[i])]
    return aur(pos, neg)


R4 = []
for name, lf, key, files in [
        ("Joint crop, render only", "jref/labels.jsonl", "detached", ["jref/results_joint_cloudflare_clef-flash.jsonl", "jref/results_joint_cloudflare_clef.jsonl", f"jref/results_joint_typesafe_{JV}.jsonl"]),
        ("Joint crop + master crop", "jref/labels.jsonl", "detached", ["jref/results_jref_cloudflare_clef-flash.jsonl", "jref/results_jref_cloudflare_clef.jsonl", f"jref/results_jref_typesafe_{JV}.jsonl"]),
        ("Full frame, planted defects", "data/labels.jsonl", "defect", ["data/results_solo_cloudflare_clef-flash.jsonl", "data/results_solo_cloudflare_clef.jsonl", f"data/results_solo_typesafe_{JV}.jsonl"]),
        ("Real rejected frames, all", "real/labels.jsonl", "defect", ["real/results_solo_cloudflare_clef-flash.jsonl", "real/results_solo_cloudflare_clef.jsonl", f"real/results_solo_typesafe_{JV}.jsonl"]),
        ("Real rejected frames, full body", "real/labels.jsonl", "defect:bf", ["real/results_solo_cloudflare_clef-flash.jsonl", "real/results_solo_cloudflare_clef.jsonl", f"real/results_solo_typesafe_{JV}.jsonl"]),
        ("Real rejected frames, sleeves", "real/labels.jsonl", "defect:sh", ["real/results_solo_cloudflare_clef-flash.jsonl", "real/results_solo_cloudflare_clef.jsonl", f"real/results_solo_typesafe_{JV}.jsonl"])]:
    k, _, sub = key.partition(":")
    f = (lambda L: "before_after" in L["id"]) if sub == "bf" else (lambda L: "shoulders" in L["id"]) if sub == "sh" else (lambda L: True)
    vals = [auc_for(lf, fl, k, f) for fl in files]
    best = max(vals)
    R4.append(f'<tr><td>{name}</td>' + "".join(f'<td class="num{" best" if v == best else ""}">{v:.2f}</td>' for v in vals) + "</tr>")
PJ = debiased(JV)
R4.append('<tr><td>Which of two renders is worse (both orders)</td>' + "".join(
    f'<td class="num">{sum(v > .5 for v in d.values())}/{len(d)}</td>' for d in (PF, PC, PJ)) + "</tr>")
R4.append('<tr><td>…of which full-body pairs</td>' + "".join(
    f'<td class="num{" best" if i == 2 else ""}">{sum(d[k] > .5 for k in bf)}/{len(bf)} · {statistics.mean(d[k] for k in bf):.2f}</td>' for i, d in enumerate((PF, PC, PJ))) + "</tr>")
BS = json.load(open(H / f"jref/box_summary_{JV}.json"))


def rel_rows(rel):
    return "".join(f'<tr><td class="num">{c:.2f}</td><td class="num">{h:.0%}</td><td class="num">{n}</td></tr>' for c, h, n in rel)


def r4_box(k, note):
    L = JG[k]
    return f'''<figure class="r2card">
  <div class="r2imgs"><div><img src="{A["r4m_" + k]}" alt="master crop with boxes"><span class="mini">`master`</span></div>
  <div><img src="{A["r4r_" + k]}" alt="render crop with boxes"><span class="mini">`render`</span></div></div>
  <figcaption><div class="truth-line"><span class="chip bad">Defect</span>{esc(L["slot"].replace("_l","").replace("_r",""))} shifted {L["direction"]} {L["mag"]} px</div>
  {bar(JA[k]["detached"]["noul"], "P(displaced)")}
  <span class="note">{esc(note)}</span></figcaption></figure>'''


JG = {r["id"]: r for r in map(json.loads, open(H / "jref/labels_gt.jsonl"))}
JA = {r["id"]: r["answers"] for r in map(json.loads, open(H / f"jref/results_jref_typesafe_{JV}.jsonl"))}
RJ = {r["id"]: r["answers"]["defect"]["noul"] for r in map(json.loads, open(H / f"real/results_solo_typesafe_{JV}.jsonl"))}

tok = sum(r["usage"]["input_tokens"] for d in (solo, ref, joint, rsolo, pair, pswap, r2ref, r2no) for r in d.values())
calls = sum(len(d) for d in (solo, ref, joint, rsolo, pair, pswap, r2ref, r2no))
lat = statistics.median([r["latency_s"] for d in (solo, ref, joint, rsolo, pair, pswap, r2ref, r2no) for r in d.values()])

tpl = open(H / "page_template.html").read()
fills = {
    "SYN_CARDS": "".join(syn_card(k) for k in ["fox_setup_0.0__clean", "fox_setup_0.0__shift_hand_l_right_24",
                                               "fox_setup_0.0__shift_head_down_24", "moose_setup_0.0__layer_upperarm_l_over_torso",
                                               "moose_setup_0.0__mirror_hand_l", "moose_thumbs_up_0.5__shift_hips_down_16"]),
    "REF_MASTER": A["master_fox"], "REF_FRAME": A["fox_setup_0.0__shift_head_left_24__marked"],
    "REF_FRAME_PLAIN": A["fox_setup_0.0__shift_head_left_24"],
    "REF_BAR": bar(ref["fox_setup_0.0__shift_head_left_24"]["answers"]["defect"]["noul"]),
    "REF_SOLO_BAR": bar(solo["fox_setup_0.0__shift_head_left_24"]["answers"]["defect"]["noul"]) if "fox_setup_0.0__shift_head_left_24" in solo else "",
    "REF_KIND": dist(ref["fox_setup_0.0__shift_head_left_24"]["answers"]["kind"]["probabilities"], "offset"),
    "REF_DIR": dist(ref["fox_setup_0.0__shift_head_left_24"]["answers"]["direction"]["probabilities"], "left"),
    "JOINT_CARDS": "".join(joint_card(k) for k in ["fox_setup_0.0__shift_hand_l_right_24__hand_l", "fox_setup_0.0__clean__hand_r",
                                                   "moose_setup_0.0__shift_hand_l_left_24__hand_l", "fox_idle_1.8__clean__hand_l"]),
    "REAL_PAIRS": real_pair("real_before_after_fox_r0_c0", "real_before_after_fox_r1_c0")
                  + real_pair("real_before_after_moose_r0_c2", "real_before_after_moose_r1_c2")
                  + real_pair("real_shoulders_ab_moose_r0_c1", "real_shoulders_ab_moose_r1_c1"),
    "R2_CARDS": r2_card("fox_shift_hand_l_down_24__hand_l", "Gap opens under the cuff: caught by both, direction right.")
                + r2_card("fox_shift_boot_l_right_24__boot_l", "Boot slides sideways out of the trouser leg: caught only without the master.")
                + r2_card("fox_shift_hand_l_up_24__hand_l", "Hand pushed up into the cuff: the seam hides it, both miss.")
                + r2_card("fox_clean__hand_l", "Clean joint. The rig's hand is drawn differently from the master's."),
    "R2_HEAT": heat(),
    "R2_NO_AUC": f"{r2sum['no reference']['auroc']:.2f}", "R2_REF_AUC": f"{r2sum['with master crop']['auroc']:.2f}",
    "R2_NO_CI": "{:.2f}–{:.2f}".format(*r2sum['no reference']['ci']), "R2_REF_CI": "{:.2f}–{:.2f}".format(*r2sum['with master crop']['ci']),
    "R2_NO_T": f"{r2sum['no reference']['tpr10']:.0%}", "R2_REF_T": f"{r2sum['with master crop']['tpr10']:.0%}",
    "R2_NO_D": f"{r2sum['no reference']['dir']:.0%}", "R2_REF_D": f"{r2sum['with master crop']['dir']:.0%}",
    "R2_REG_D": f"{reg_dir:.0%}",
    "R3_ROWS": R3, "R3_DUMBBELL": dumbbell(),
    "R3_PF": f"{sum(v > .5 for v in PF.values())}/{len(PF)}", "R3_PC": f"{sum(v > .5 for v in PC.values())}/{len(PC)}",
    "R3_BF_F": f"{statistics.mean(PF[k] for k in bf):.2f}", "R3_BF_C": f"{statistics.mean(PC[k] for k in bf):.2f}",
    "R3_SH_F": f"{statistics.mean(PF[k] for k in sh):.2f}", "R3_SH_C": f"{statistics.mean(PC[k] for k in sh):.2f}",
    "R4_ROWS": "".join(R4),
    "R4_BOXES": r4_box("fox_shift_hand_l_right_24__hand_l", "Boxes move right with the hand: offset read correctly.")
                + r4_box("fox_shift_hand_r_left_24__hand_r", "Boxes move left with the hand: offset read correctly.")
                + r4_box("moose_shift_hand_r_down_24__hand_r", "The hand dropped, but the two boxes differ mostly sideways: wrong direction.")
                + r4_box("fox_shift_boot_l_left_24__boot_l", "The master box misses the boot (IoU 0.08), so the offset is meaningless."),
    "R4_FHIT": A["r4f_hit"], "R4_FMISS": A["r4f_miss"],
    "R4_REL_J": rel_rows(BS["loc_joint"]["rel"]), "R4_REL_R": rel_rows(BS["loc_jref"]["rel"]),
    "R4_MIOU": f"{BS['loc_jref']['miou']:.2f}", "R4_HIT": f"{BS['loc_jref']['hit']:.0%}",
    "R4_ECE_J": f"{BS['loc_joint']['ece']:.2f}", "R4_ECE_R": f"{BS['loc_jref']['ece']:.2f}",
    "R4_RHO_J": f"{BS['loc_joint']['rho']:.2f}", "R4_RHO_R": f"{BS['loc_jref']['rho']:.2f}",
    "R4_DIRV": f"{BS['dir_box']['acc_visible']:.0%}", "R4_NV": str(BS['dir_box']['n_visible']),
    "R4_PT": f"{BS['point_solo']['hit']:.0%}",
    "R4_REAL_BF": " · ".join(f"{RJ[k]:.2f}" for k in sorted(RJ) if "before_after" in k and "_r0_" in k),
    "R4_REAL_OK": " · ".join(f"{RJ[k]:.2f}" for k in sorted(RJ) if "before_after" in k and "_r1_" in k),
    "LINE_CHART": line_chart(), "PAIR_CHART": pair_chart(),
    "MASTER_FOX": A["master_fox"], "MASTER_MOOSE": A["master_moose"],
    "CALLS": str(calls), "TOKENS": f"{tok/1000:.0f}k", "NEURONS": f"{tok*3455/1e6/1000:.1f}k", "USD": f"${tok*0.038/1e6:.2f}",
    "LATENCY": f"{lat:.1f} s",
}
for k, v in fills.items():
    tpl = tpl.replace("{{" + k + "}}", v)
assert "{{" not in tpl, tpl[tpl.index("{{"):tpl.index("{{") + 40]
(H / "clef-rig-judge.html").write_text(tpl)
print("wrote", len(tpl) // 1024, "KB")

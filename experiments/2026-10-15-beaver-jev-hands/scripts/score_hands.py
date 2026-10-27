"""Score Jev's hand-direction answers against exact ground truth.

  python3 score_hands.py <set dir> [condition ...]   -> prints a table and writes <set dir>/scores_<condition>.json

Directions: the 8-way argmax (exact bin), the angle of the probability-weighted circular mean (error in degrees),
and 'within 45': the argmax bin centre within 45 deg of the truth. 'clear' items are those whose true angle is at
least 7.5 deg from a bin edge. painted_derived: the anatomy rule applied in code to Jev's own finger/thumb/facing
answers (hands_set.painted_side)."""
import json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BINS = {"right": 0, "up-right": 45, "up": 90, "up-left": 135, "left": 180, "down-left": 225, "down": 270, "down-right": 315}


def adiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def circ_mean(probs):
    x = sum(p * math.cos(math.radians(BINS[k])) for k, p in probs.items())
    y = sum(p * math.sin(math.radians(BINS[k])) for k, p in probs.items())
    return math.degrees(math.atan2(y, x)) % 360, math.hypot(x, y)


def nearest_bin(deg):
    return min(BINS, key=lambda k: adiff(BINS[k], deg))


def painted_side(finger_deg, thumb_deg, facing):
    ccw = ((thumb_deg - finger_deg) % 360) < 180
    return "l" if ccw == (facing == "palm") else "r"


def auroc(pos, neg):
    if not pos or not neg:
        return None
    s = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(s / (len(pos) * len(neg)), 3)


def score(rows):
    out = {"n": len(rows)}
    for q, truth_key in (("finger_dir", "finger_deg"), ("thumb_dir", "thumb_deg")):
        ok = [r for r in rows if q in r["answers"]]
        clear = [r for r in ok if adiff(r[truth_key], BINS[nearest_bin(r[truth_key])]) <= 22.5 - 7.5]
        exact = [r["answers"][q]["choice"] == nearest_bin(r[truth_key]) for r in clear]
        w45 = [adiff(BINS[r["answers"][q]["choice"]], r[truth_key]) <= 45 for r in ok]
        errs = sorted(adiff(circ_mean(r["answers"][q]["probabilities"])[0], r[truth_key]) for r in ok)
        out[q] = {"exact_clear": round(sum(exact) / max(1, len(exact)), 3), "n_clear": len(exact),
                  "within45": round(sum(w45) / max(1, len(w45)), 3),
                  "median_err_deg": round(errs[len(errs) // 2], 1) if errs else None,
                  "p90_err_deg": round(errs[int(len(errs) * 0.9)], 1) if errs else None}
    fac = [r for r in rows if r.get("facing")]
    out["facing"] = {"acc": round(sum(r["answers"]["facing"]["choice"] == r["facing"] for r in fac) / max(1, len(fac)), 3),
                     "auroc": auroc([r["answers"]["facing"]["probabilities"]["palm"] for r in fac if r["facing"] == "palm"],
                                    [r["answers"]["facing"]["probabilities"]["palm"] for r in fac if r["facing"] == "back"]),
                     "n_palm": sum(r["facing"] == "palm" for r in fac), "n_back": sum(r["facing"] == "back" for r in fac)}
    out["gesture"] = {"acc": round(sum(r["answers"]["gesture"]["choice"] == r["variant"] for r in rows) / len(rows), 3)}
    tr = [r for r in rows if r.get("painted") or r.get("side")]

    def truth_side(r):
        if r["set"] == "pieces":
            return r["painted"]
        return r["side"] if not r["planted_mirror"] else ("r" if r["side"] == "l" else "l")
    out["painted_direct"] = round(sum(r["answers"]["painted"]["choice"][0] == truth_side(r) for r in tr) / max(1, len(tr)), 3)
    der = []
    for r in tr:
        a = r["answers"]
        f = circ_mean(a["finger_dir"]["probabilities"])[0]; t = circ_mean(a["thumb_dir"]["probabilities"])[0]
        der.append(painted_side(f, t, a["facing"]["choice"]) == truth_side(r))
    out["painted_derived"] = round(sum(der) / max(1, len(der)), 3)
    # derived with the TRUE facing (isolates the direction answers)
    der2 = [painted_side(circ_mean(r["answers"]["finger_dir"]["probabilities"])[0],
                         circ_mean(r["answers"]["thumb_dir"]["probabilities"])[0], r["facing"]) == truth_side(r)
            for r in tr if r.get("facing")]
    out["painted_derived_true_facing"] = round(sum(der2) / max(1, len(der2)), 3)
    holds = [r for r in rows if r["set"] == "holds"]
    if holds:
        up = lambda r: adiff(r["thumb_deg"], 90) <= 45
        out["thumb_up_auroc"] = auroc([r["answers"]["thumb_up"]["noul"] for r in holds if up(r)],
                                      [r["answers"]["thumb_up"]["noul"] for r in holds if not up(r)])
        out["thumb_up_acc"] = round(sum((r["answers"]["thumb_up"]["noul"] > 0.5) == up(r) for r in holds) / len(holds), 3)
        out["n_thumb_up"] = sum(up(r) for r in holds)
        g = [r for r in holds if r["variant"] != "relaxed" and r["anim"] != "setup"]
        out["mirrored_auroc"] = auroc([r["answers"]["mirrored"]["noul"] for r in g if r["planted_mirror"]],
                                      [r["answers"]["mirrored"]["noul"] for r in g if not r["planted_mirror"]])
        # code rule: mirrored if the anatomy-derived painted side (Jev's finger, thumb, facing) != the slot's side
        flag = lambda r: painted_side(circ_mean(r["answers"]["finger_dir"]["probabilities"])[0],
                                      circ_mean(r["answers"]["thumb_dir"]["probabilities"])[0],
                                      r["answers"]["facing"]["choice"]) != r["side"]
        tp = sum(flag(r) for r in g if r["planted_mirror"]); fp = sum(flag(r) for r in g if not r["planted_mirror"])
        npl = sum(r["planted_mirror"] for r in g)
        out["mirror_rule"] = {"tpr": round(tp / max(1, npl), 3), "fpr": round(fp / max(1, len(g) - npl), 3), "n_planted": npl,
                              "n_clean": len(g) - npl}
        # the same rule with the annotated facing (what the pipeline knows): Jev supplies only the two directions
        flag2 = lambda r: painted_side(circ_mean(r["answers"]["finger_dir"]["probabilities"])[0],
                                       circ_mean(r["answers"]["thumb_dir"]["probabilities"])[0], r["facing"]) != r["side"]
        tp = sum(flag2(r) for r in g if r["planted_mirror"]); fp = sum(flag2(r) for r in g if not r["planted_mirror"])
        out["mirror_rule_annotated_facing"] = {"tpr": round(tp / max(1, npl), 3), "fpr": round(fp / max(1, len(g) - npl), 3)}
        # holds whose thumb is meant to be up (point, thumbs_up, hold_card at their hold) - does thumb_up flag the mirrors?
        h = [r for r in holds if r["anim"] in ("point", "thumbs_up", "hold_card") and r["variant"] != "relaxed"]
        out["gesture_thumb_check"] = {
            "clean_mean_p_up": round(sum(r["answers"]["thumb_up"]["noul"] for r in h if not r["planted_mirror"]) / max(1, sum(not r["planted_mirror"] for r in h)), 3),
            "mirrored_mean_p_up": round(sum(r["answers"]["thumb_up"]["noul"] for r in h if r["planted_mirror"]) / max(1, sum(r["planted_mirror"] for r in h)), 3)}
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    labels = {json.loads(l)["id"]: json.loads(l) for l in open(d / "labels.jsonl")}
    for cond in sys.argv[2:] or ["text"]:
        res = [json.loads(l) for l in open(d / f"results_{cond}.jsonl")]
        rows = [{**labels[r["id"]], "answers": r["answers"]} for r in res if r["id"] in labels and r.get("answers")]
        report = {"all": score(rows)}
        for c in sorted({r["char"] for r in rows}):
            report[c] = score([r for r in rows if r["char"] == c])
        if rows and rows[0]["set"] == "pieces":
            report["unmirrored_upright"] = score([r for r in rows if not r["mirror"] and r["rot"] == 0])
        tok = sum((r.get("usage") or {}).get("input_tokens", 0) for r in res)
        report["tokens"] = tok
        json.dump(report, open(d / f"scores_{cond}.json", "w"), indent=1)
        print(f"== {d.name} / {cond}  ({len(rows)} items, {tok} input tokens)")
        print(json.dumps(report, indent=1))

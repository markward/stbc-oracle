"""Collisions: Galaxy (attacker) flies into a parked Sovereign. Speed at contact, damage to each ship
(shields, hull, subsystems), and the bounce (speeds after)."""
import sys, glob, json, math, re
sys.path.insert(0, ".")
from common import shots, xrows, chunked, sub_names, tap

for path in sys.argv[1:]:
    for s in shots(path):
        r = s["run"]; sp = r["params"]["shot%02d" % s["index"]]
        A = xrows(r, "xm", "A", s["start"], s["end"]); T = xrows(r, "xm", "T", s["start"], s["end"])
        tp = {round(x["t"], 3): x for x in T}
        dist = [(x["t"], math.dist([float(c) for c in x["p"].split(",")], [float(c) for c in tp[round(x["t"], 3)]["p"].split(",")]), float(x["sp"]))
                for x in A if round(x["t"], 3) in tp]
        # contact = largest single-sample drop in the attacker's speed
        drops = [(dist[i][0], dist[i - 1][2] - dist[i][2], dist[i - 1][2], dist[i][1]) for i in range(1, len(dist))]
        t_c, dv, v_in, d_c = max(drops, key=lambda x: x[1]) if drops else (None, 0, 0, 0)
        out = {}
        for tag in "AT":
            n = sub_names(r, tag); c = chunked(r, "xc", tag, "c", s["start"], s["end"]); ts = sorted(c)
            lost = {n[j]: float(c[ts[0]][j]) - float(c[ts[-1]][j]) for j in range(len(n))}
            xh = xrows(r, "xh", tag, s["start"], s["end"])
            shl = sum(float(v) for v in xh[0]["sh"].split(",")) - min(sum(float(v) for v in x["sh"].split(",")) for x in xh)
            out[tag] = (round(shl), {k: round(v) for k, v in lost.items() if v > 1})
        v_after_A = [float(x["sp"]) for x in A if t_c and t_c + 0.3 < x["t"] < t_c + 1.0]
        v_after_T = [float(x["sp"]) for x in T if t_c and t_c + 0.3 < x["t"] < t_c + 1.0]
        evs = [(round(t - (t_c or 0), 2), k, d.get("type"), d.get("dmg")) for t, k, d in tap(r, s["start"], s["end"]) if k in ("H", "DS") and t_c and abs(t - t_c) < 2]
        print(f"{path.split('/')[-1][:-5]}: impact speed {v_in:.2f} GU/s at {d_c:.1f} GU centre distance")
        print(f"   Galaxy (rammer): shields −{out['A'][0]}, losses {out['A'][1]}; speed after {[round(v, 2) for v in v_after_A[:3]]}")
        print(f"   Sovereign (rammed): shields −{out['T'][0]}, losses {out['T'][1]}; speed after {[round(v, 2) for v in v_after_T[:3]]}")
        print(f"   hit events near contact: {evs[:6]}")

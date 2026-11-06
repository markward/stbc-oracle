"""Movement dynamics from the oracle's motion_check flights (one Galaxy, commanded via the same calls the
player's helm uses): turn ramp (t50/t90 of |w|), steady turn rate, stop; for turn-at-speed runs the speed
bleed and drift angle (velocity direction vs nose; nose rebuilt by integrating the yaw rate)."""
import math, re, sys, json
sys.path.insert(0, ".")
from common import shots, xrows

def vec(s): return [float(x) for x in s.split(",")]

def analyse(path, tag="A"):
    out = []
    for s in shots(path):
        spec = s["spec"]
        mv = re.search(r"mv=(\w+)", spec).group(1)
        ipw = float(re.search(r"ipw=([\d.]+)", spec).group(1)); mf = float(re.search(r"mf=([-\d.]+)", spec).group(1))
        ic = float(re.search(r"ic=([\d.]+)", spec).group(1))
        xm = xrows(s["run"], "xm", tag, s["start"], s["end"] - 0.3)
        t0 = xm[0]["t"]
        W = [(x["t"] - t0, math.sqrt(sum(c * c for c in vec(x["w"]))), vec(x["w"]), vec(x["v"]), float(x["sp"])) for x in xm]
        wmax = max(w for _, w, *_ in W)
        res = dict(mv=mv, mf=mf, ipw=ipw, ic=ic, wmax=round(wmax, 4))
        if wmax > 1e-3:
            res["w_t50"] = round(next(t for t, w, *_ in W if w >= 0.5 * wmax), 2)
            res["w_t90"] = round(next(t for t, w, *_ in W if w >= 0.9 * wmax), 2)
            res["w_t99"] = round(next(t for t, w, *_ in W if w >= 0.99 * wmax), 2)
        sp = [x[4] for x in W]
        res["v_end"] = round(sp[-1], 3); res["v_max"] = round(max(sp), 3)
        if mv == "impyaw":
            # nose: start along the initial course; integrate the yaw rate (world z)
            th = None; drift = []
            for i, (t, w, wv, v, spd) in enumerate(W):
                if spd < 0.05:
                    continue
                phi = math.atan2(v[1], v[0])
                if th is None:
                    th = phi; tp = t; continue
                th += wv[2] * (t - tp); tp = t
                d = (th - phi + math.pi) % (2 * math.pi) - math.pi
                drift.append((t, math.degrees(d), spd))
            res["drift_deg_max"] = round(max(abs(d) for _, d, _ in drift), 2) if drift else None
            res["drift_deg_end"] = round(drift[-1][1], 2) if drift else None
            res["v_min_turning"] = round(min(spd for _, _, spd in drift[len(drift)//3:]), 3) if drift else None
        out.append(res)
    return out

if __name__ == "__main__":
    for r in analyse(sys.argv[1]):
        print(r)

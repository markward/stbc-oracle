"""The AI turn controller (ShipClass.TurnTowardLocation, re-issued ~every 0.03 s), the original vs Dauntless.
Original: results_mac/turnto/<ship>_<motion>.json (worker_turn.sh; telemetry xm/xo, point in the boot mark
'turnloc'). Dauntless: scorecard/dauntless_turnto/<ship>_<motion>.json. Per motion: time until the nose is within
30 / 10 / 2 degrees of the point, peak angular speed, overshoot (largest angle after first reaching 2 deg), and the
final up vector's world z (does the controller roll the ship upright?).
usage: python compare_turnto.py"""
import glob, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import aim_reconstruct as AR

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def metrics(samples, pt):
    """samples: [(t, pos, fw, up, w)]"""
    out = {}
    angs = []
    for t, p, fw, up, w in samples:
        d = AR.norm(AR.sub(pt, p))
        a = math.degrees(math.acos(max(-1.0, min(1.0, AR.dot(AR.norm(fw), d)))))
        angs.append((t, a, math.sqrt(AR.dot(w, w)), up))
    t0 = angs[0][0]
    for th in (30, 10, 2):
        out["t<%d" % th] = next((round(t - t0, 2) for t, a, _, _ in angs if a < th), None)
    out["peak w"] = round(max(s for _, _, s, _ in angs), 3)
    t2 = out["t<2"]
    out["overshoot"] = round(max([a for t, a, _, _ in angs if t2 is not None and t - t0 > t2] or [0.0]), 2)
    out["final angle"] = round(angs[-1][1], 2)
    out["final up.z"] = round(angs[-1][3][2], 3)
    return out


def bc(path):
    d = json.load(open(path))
    marks = d.get("boot") or {}
    pt = None
    for k, v in marks.items():
        if k.endswith("turnloc"):
            m = re.search(r"pt=([-\d.]+),([-\d.]+),([-\d.]+)", v)
            if m:
                pt = [float(m.group(i)) for i in (1, 2, 3)]
    rr = d["raw_rows"]
    xm = {round(t, 3): kv for t, kv in AR.telemetry(rr, "xm", "A")}
    xo = {round(t, 3): kv for t, kv in AR.telemetry(rr, "xo", "A")}
    # The command time is on the harness's sample clock ('acted t=', 'first_sample t='), telemetry on game time:
    # anchor the command to the first telemetry row. Samples before it are the idle lead-in.
    acted = None
    first = 0.0
    for k, v in marks.items():
        m2 = re.search(r"t=([\d.]+)", v)
        if m2 and k.endswith("acted"):
            acted = float(m2.group(1))
        elif m2 and k.endswith("first_sample"):
            first = float(m2.group(1))
    times = sorted(set(xm) & set(xo))
    start = times[0] + (acted - first) - 0.001 if acted is not None and times else 0.0
    s = []
    for t in times:
        if t < start:
            continue
        s.append((t, AR.vec(xm[t]["p"]), AR.vec(xo[t]["fw"]), AR.vec(xo[t]["up"]), AR.vec(xm[t]["w"])))
    return s, pt


def dn(path):
    d = json.load(open(path))
    return [(r["t"], r["p"], r["fw"], r["up"], r["w"]) for r in d["rows"]], d["point"]


if __name__ == "__main__":
    for f in sorted(glob.glob(os.path.join(ROOT, "scorecard/dauntless_turnto/*.json"))):
        name = os.path.basename(f)
        g = os.path.join(ROOT, "results_mac/turnto", name)
        md = metrics(*dn(f))
        mb = None
        if os.path.exists(g):
            s, pt = bc(g)
            if s and pt:
                mb = metrics(s, pt)
        print("== %s" % name[:-5])
        for k in md:
            print("   %-12s original %-8s Dauntless %s" % (k, mb.get(k) if mb else "-", md[k]))

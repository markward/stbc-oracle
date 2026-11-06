"""Per-face shield timeline for a duel: per ship and face, time spent below the 60% leak threshold
and at 0, damage the face absorbed, and damage that leaked past it (hull + subsystems), by weapon."""
import sys, json
from collections import defaultdict
sys.path.insert(0, ".")
from common import tap, xrows
FACES = ("front", "rear", "top", "bottom", "left", "right")
def report(path):
    r = json.load(open(path))
    meta = r["meta"]
    # Ship identity: duel runs don't log pointers. Each shield object's per-face maxima (CombatTap S
    # rows) identify its ship; the S row for a hit comes immediately BEFORE that hit's H row, and the
    # H row's ship pointer is then bound to the same tag.
    cls = {"A": r["params"]["attacker"], "T": r["params"]["target"]}
    print("=====", path.split("/")[-1][5:-5])
    fmax = {tag: [float(x) for x in xrows(r, "xh", tag)[0]["sh"].split(",")] for tag in ("A", "T")}
    seen = defaultdict(lambda: [0.0] * 6)
    for t, k, d in tap(r):
        if k == "S":
            i = int(d["face"]); seen[d["sh"]][i] = max(seen[d["sh"]][i], float(d["set"]))
    shtag = {sp: min(("A", "T"), key=lambda tag: sum(abs(v[i] - fmax[tag][i]) for i in range(6))) for sp, v in seen.items()}
    for tag in ("A", "T"):
        xh = xrows(r, "xh", tag)
        if not xh:
            continue
        mx = [float(x) for x in xh[0]["sh"].split(",")]
        below = [0.0] * 6; zero = [0.0] * 6
        for a, b in zip(xh, xh[1:]):
            dt = b["t"] - a["t"]
            for i, v in enumerate(a["sh"].split(",")):
                v = float(v)
                if v < 0.6 * mx[i]: below[i] += dt
                if v <= 0.5: zero[i] += dt
        span = xh[-1]["t"] - xh[0]["t"]
        print(f"  {cls[tag]:10} ({span:.0f}s)  face max / % time below 60% / % time at 0")
        print("     " + "  ".join(f"{FACES[i]} {mx[i]:.0f}/{100*below[i]/span:.0f}%/{100*zero[i]/span:.0f}%" for i in range(6)))
    absorbed = defaultdict(float); leaked = defaultdict(float); nhits = defaultdict(int)
    cur = None; last_s = None; shiptag = {}
    for t, k, d in tap(r):
        if k == "S":
            last_s = (t, d["sh"], int(d["face"]))
        elif k == "H":
            w = "phaser" if d["type"] == "0" else "torpedo"
            if last_s and abs(last_s[0] - t) < 1e-3:
                who = shtag[last_s[1]]; face = FACES[last_s[2]]; shiptag[d["ship"]] = who
            else:
                who = shiptag.get(d["ship"], "?"); face = "no shield event"
            cur = [who, face, w]; last_s = None
            nhits[(who, w)] += 1
        elif k == "W" and cur:
            a, b = (float(x) for x in d["hp"].split("->"))
            leaked[(cur[0], cur[1], cur[2])] += max(0.0, a - b)
    for tag in ("A", "T"):
        rows = sorted(((v, f, w) for (who, f, w), v in leaked.items() if who == tag), reverse=True)
        tot = sum(v for v, _, _ in rows)
        print(f"  damage that got through to {cls[tag]}: {tot:.0f}  hits taken {dict((w, n) for (who, w), n in nhits.items() if who == tag)}")
        print("     " + "; ".join(f"{w} via {f}: {v:.0f}" for v, f, w in rows[:8]))
for p in sys.argv[1:]:
    report(p)

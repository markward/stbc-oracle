"""First contact of each collision run: impact speed (rammer's speed just before), damage to each ship, radius."""
import sys, glob, math
sys.path.insert(0, ".")
from common import shots, tap, xrows
for f in sys.argv[1:]:
    s = shots(f)[0]; r = s["run"]
    pa = r["meta"].get("ptr_attacker", "").upper().lstrip("0X"); pt = r["meta"].get("ptr_target", "").upper().lstrip("0X")
    evs = [(t, d) for t, k, d in tap(r, s["start"], s["end"]) if k == "DS" and float(d["dmg"]) not in (0.0, 600.0)]
    if not evs:
        print(f.split('/')[-1], "no contact"); continue
    t0 = evs[0][0]
    first = [(("Galaxy (rammer)" if d["ship"].upper().lstrip("0") == pa else "Sovereign (rammed)"), float(d["dmg"]), d["r"]) for t, d in evs if abs(t - t0) < 0.02]
    A = xrows(r, "xm", "A", s["start"], t0); v_in = float(A[-2]["sp"]) if len(A) > 1 else None
    T = xrows(r, "xm", "T", s["start"], t0); vt = float(T[-2]["sp"]) if len(T) > 1 else 0
    n = sum(1 for t, d in evs) // 2
    print(f"{f.split('/')[-1][:-5]:18} impact {v_in:.2f} GU/s (target {vt:.2f}) | first contact: {[(w, round(x), rr) for w, x, rr in first]} | contacts in run: {n}")

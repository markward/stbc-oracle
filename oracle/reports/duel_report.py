"""Duel report: outcome, timeline of hull/shields, damage taken per subsystem, weapons used."""
import sys
from collections import defaultdict
from common import xrows, chunked, sub_names, tap
import json
r = json.load(open(sys.argv[1]))
over = [v for k, v in r["boot"].items() if "duel_over" in k]
print("outcome:", over or "time limit", " validation:", r.get("validation") or "OK")
for tag, who in (("A", r["params"]["attacker"] + " (enemy AI)"), ("T", r["params"]["target"] + " (player ship, friendly AI)")):
    names = sub_names(r, tag)
    cond = chunked(r, "xc", tag, "c")
    ts = sorted(cond)
    if not ts:
        continue
    print(f"== {who}")
    hull = [(t, float(cond[t][0])) for t in ts]
    for frac in (0.75, 0.5, 0.25):
        t = next((t for t, v in hull if v <= hull[0][1] * frac), None)
        print(f"   hull at {int(frac*100)}% at t={t - ts[0]:.1f}s" if t else f"   hull never below {int(frac*100)}%")
    first, last = cond[ts[0]], cond[ts[-1]]
    lost = sorted(((float(a) - float(b), names[j] if j < len(names) else j, float(a)) for j, (a, b) in enumerate(zip(first, last))), reverse=True)
    print("   biggest losses:", "; ".join(f"{n} -{l:.0f} ({100*l/m:.0f}%)" for l, n, m in lost[:8] if l > 0))
    xh = xrows(r, "xh", tag)
    if xh:
        print("   shields start", xh[0]["sh"], " end", xh[-1]["sh"])
hits = defaultdict(lambda: [0, 0.0])
for t, k, d in tap(r):
    if k == "H":
        key = ("phaser" if d["type"] == "0" else "torpedo" if d["type"] == "1" else d["type"], d["ship"], d["hull"])
        hits[key][0] += 1; hits[key][1] += float(d["dmg"])
print("hits (weapon, ship hit, reached hull):", {f"{k[0]} on {k[1][-4:]} hull={k[2]}": (v[0], round(v[1])) for k, v in hits.items()})

"""Torpedo reload session: per shot, impacts (time after shot start, point, damage)."""
import sys
from common import shots, tap
for s in shots(sys.argv[1]):
    hits = [(t - s["start"], d) for t, k, d in tap(s["run"], s["start"], s["end"]) if k == "H"]
    tt = s["spec"].split(" tt=")[1].split()[0]
    print(f"shot {s['index']} tt={tt}: {len(hits)} hits " + "; ".join(
        f"{t:.3f}s dmg={float(d['dmg']):.0f} at {d['op']}" for t, d in hits)[:300])

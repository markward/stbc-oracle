"""Shield-face map: for each attacker direction, which target face absorbed the first hits."""
import sys
from collections import defaultdict
from common import shots, tap
NAMES = ["F", "A", "T", "B", "P", "S"]   # front, aft(rear), top, bottom, port, starboard
grid = defaultdict(dict)
for s in shots(sys.argv[1]):
    a = int(float(s["spec"].split(" a=")[1].split()[0])); e = int(float(s["spec"].split(" e=")[1].split()[0]))
    first = {}
    for t, k, d in tap(s["run"], s["start"], s["end"]):
        if k == "S":
            f = int(d["face"]); v = float(d["set"])
            first.setdefault(f, []).append(v)
    drained = [f for f, vals in first.items() if len(vals) > 1 and vals[0] - min(vals) > 5]
    grid[e][a] = "".join(NAMES[f] for f in sorted(drained)) or "-"
print("elev\\az " + " ".join(f"{a:>3}" for a in range(0, 360, 15)))
for e in sorted(grid, reverse=True):
    print(f"{e:+6d}  " + " ".join(f"{grid[e].get(a, ''):>3}" for a in range(0, 360, 15)))

"""Torpedo spread modes: per shot, torpedoes launched in that shot (first seen within the shot window),
launch times, fan angle between launch directions, whether they steered (heading change), hits."""
import math, re, sys
sys.path.insert(0, ".")
from common import shots, tap
def unit(v):
    n = math.hypot(*v) or 1.0
    return [x / n for x in v]
for path in sys.argv[1:]:
    print("=====", path.split("/")[-1])
    for s in shots(path):
        r = s["run"]
        zc = [l for l in r["raw_rows"] if l.startswith("zc %d " % s["index"])]
        name = zc[0].split("name=")[1] if zc else "?"
        a = re.search(r" a=(\S+)", s["spec"]).group(1)
        tr = {}
        for l in r["raw_rows"]:
            if l.startswith("xt1 "):
                d = dict(x.split("=", 1) for x in l.split()[1:] if "=" in x)
                t = float(d["t"])
                if d["par"] == "0" or "err" in l:
                    continue
                tr.setdefault(d["id"], []).append((t, [float(x) for x in d["v"].split(",")]))
        mine = {k: v for k, v in tr.items() if s["start"] - 0.1 <= v[0][0] < s["end"]}
        launches = sorted((v[0][0] - s["start"], unit(v[0][1]), unit(v[-1][1]), v[-1][0] - v[0][0]) for v in mine.values())
        fan = max((math.degrees(math.acos(max(-1, min(1, sum(x * y for x, y in zip(p[1], q[1])))))) for i, p in enumerate(launches) for q in launches[i + 1:]), default=0)
        steer = [math.degrees(math.acos(max(-1, min(1, sum(x * y for x, y in zip(p[1], p[2])))))) for p in launches]
        hits = [(t - s["start"], float(d["dmg"])) for t, k, d in tap(r, s["start"], s["end"]) if k == "H"]
        print(f"  {'ahead ' if a == '0' else 'astern'} {name:7}: {len(launches)} torps at {[round(x[0], 2) for x in launches]} | fan {fan:5.1f} deg | "
              f"heading change in flight {[round(x) for x in steer]} deg | hits {len(hits)} dmg {sum(d for _, d in hits):.0f}")

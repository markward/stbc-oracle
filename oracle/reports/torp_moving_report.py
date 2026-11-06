"""Torpedoes at a moving target: per shot, torpedoes launched, hits, closest approach of each miss."""
import sys, re, math
sys.path.insert(0, ".")
from common import shots, tap, xrows

for path in sys.argv[1:]:
    for s in shots(path):
        r = s["run"]; spec = s["spec"]
        sp = r["params"]["shot%02d" % s["index"]]
        tmv = re.search(r"tmv=([\d.]+)", sp); ttf = re.search(r"ttf=([\d.]+)", sp)
        a = re.search(r"\ba=(\d+)", sp).group(1); rng = re.search(r"rng=(\d+)", sp).group(1); ch = re.search(r"chain=(\d)", sp).group(1)
        tpos = {round(x["t"], 2): [float(c) for c in x["p"].split(",")] for x in xrows(r, "xm", "T", s["start"], s["end"])}
        tsp = [float(x["sp"]) for x in xrows(r, "xm", "T", s["start"] + 2, s["end"])]
        tr = {}
        for l in r["raw_rows"]:
            if l.startswith("xt1 ") and "err" not in l:
                d = dict(x.split("=", 1) for x in l.split()[1:] if "=" in x)
                t = float(d["t"])
                if t <= s["end"]:
                    tr.setdefault(d["id"], []).append((round(t, 2), [float(c) for c in d["p"].split(",")]))
        tr = {k: v for k, v in tr.items() if v[0][0] >= s["start"]}      # launched in this shot only
        hits = [t for t, k, d in tap(r, s["start"], s["end"]) if k == "H" and d["type"] == "1"]
        closest = []
        for tid, pts in tr.items():
            ds = [math.dist(p, tpos[t]) for t, p in pts if t in tpos]
            if ds:
                closest.append(min(ds))
        geo = {"90": "crossing", "0": "flying at shooter", "180": "flying away"}[a]
        mode = {"0": "Single", "1": "Dual", "2": "Quad"}[ch]
        print(f"target {geo:17} throttle {tmv.group(1) if tmv else '0':4} turn {ttf.group(1) if ttf else '0'} | {rng} GU {mode:6} | "
              f"target top speed {max(tsp) if tsp else 0:4.2f} | torpedoes {len(tr)} hits {len(hits)} | closest approach of each (GU): {sorted(round(c, 1) for c in closest)}")

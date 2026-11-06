"""Slider side effects: phaser/torpedo damage vs Weapons control; absorption vs Shields control."""
import re, sys
sys.path.insert(0, ".")
from common import shots, tap, chunked
for s in shots(sys.argv[1]):
    r = s["run"]; spec = r["params"]["shot%02d" % s["index"]] if ("shot%02d" % s["index"]) in r["params"] else ""
    apw = re.search(r"apw=([^,]+)", spec); tpw = re.search(r"tpw=([^,]+)", spec)
    w = re.search(r"w=(\w+)", spec).group(1)
    hits = [d for t, k, d in tap(r, s["start"], s["end"]) if k == "H"]
    hull = [d for d in hits if d["hull"] == "1"]
    S = {}
    for t, k, d in tap(r, s["start"], s["end"]):
        if k == "S":
            S.setdefault(int(d["face"]), []).append(float(d["set"]))
    drain = {f: round(v[0] - min(v), 1) for f, v in S.items() if v[0] - min(v) > 1}
    tot = sum(float(d["dmg"]) for d in hits)
    label = f"Weapons {apw.group(1).split('/')[1].split('+')[0]}" if apw else (f"Shields {tpw.group(1).split('/')[1]}" if tpw else "")
    w_ = chunked(r, "xw", "A", "w", s["start"], s["end"])
    firing = 0.0
    ts = sorted(w_)
    for a, b in zip(ts, ts[1:]):
        if any(x.startswith("e/") and x.endswith("/1") for x in w_[a]):
            firing += b - a
    print(f"shot {s['index']} {w:7} {label:14} hits={len(hits):3} hull-hits={len(hull):3} dmg/hit={tot/len(hits) if hits else 0:7.2f} total={tot:8.1f} "
          f"firing={firing:5.2f}s dmg/firing-s={tot/firing if firing else 0:7.2f} face drain={drain}")

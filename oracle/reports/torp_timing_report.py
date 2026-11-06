"""Natural torpedo timing: per shot, launches and each tube's ready transitions (time after shot start)."""
import re, sys
sys.path.insert(0, ".")
from common import shots, chunked, xrows
for path in sys.argv[1:]:
    print("=====", path.split("/")[-1])
    for s in shots(path):
        r = s["run"]; spec = r["params"].get("shot%02d" % s["index"], "")
        w = chunked(r, "xw", "A", "w", s["start"] - 0.2, s["end"])
        ts = sorted(w)
        tubes = [j for j, x in enumerate(w[ts[0]]) if x.startswith("t/")]
        ev = []
        for a, b in zip(ts, ts[1:]):
            for j in tubes:
                ra, rb = int(w[a][j].split("/")[1]), int(w[b][j].split("/")[1])
                if ra != rb:
                    ev.append((round(b - s["start"], 2), f"tube{tubes.index(j)} {'READY' if rb > ra else 'fired/unloaded'}"))
        st = xrows(r, "xz", "A", s["start"], s["end"])
        am = sorted({d.get("am") for d in st}); ta = st[-1].get("ta") if st else "?"
        print(f"shot {s['index']} [{spec}] ammo seen {am} torps left {ta}")
        ready0 = [int(w[ts[0]][j].split('/')[1]) for j in tubes]
        print(f"   tubes ready at start: {ready0}")
        for t, e in ev:
            print(f"   {t:7.2f}s  {e}")

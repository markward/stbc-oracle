"""Repair session report: per shot, each damaged subsystem's repair rate and timing."""
import sys
from common import shots, chunked, xrows, sub_names
WALK_T = None
for s in shots(sys.argv[1]):
    r = s["run"]
    spec = s["spec"]
    cond = chunked(r, "xc", "T", "c", s["start"], s["end"])
    rep = {d["t"]: d["rep"] for d in xrows(r, "xd", "T", s["start"], s["end"])}
    ts = sorted(cond)
    if len(ts) < 3:
        print(spec[:100], "no data"); continue
    first, last = cond[ts[0]], cond[ts[-1]]
    names = sub_names(r, "T")
    nm = lambda j: names[j] if j < len(names) else f"#{j}"
    print(f"== shot {s['index']}: {spec[spec.find(' a='):][:150]}")
    for j, (a, b) in enumerate(zip(first, last)):
        a, b = float(a), float(b)
        if abs(b - a) < 0.5 and not any(rep.get(t, "")[j:j + 1] == "1" for t in ts):
            continue
        # repair rate while increasing; start/stop times of increase
        series = [(t, float(cond[t][j])) for t in ts]
        inc = [(t0, v0, t1, v1) for (t0, v0), (t1, v1) in zip(series, series[1:]) if v1 > v0 + 1e-6]
        if not inc:
            print(f"   {nm(j):18}: {a:8.1f} -> {b:8.1f}  (no repair; being-repaired flags {sum(1 for t in ts if rep.get(t,'')[j:j+1]=='1')})")
            continue
        t_on, t_off = inc[0][0], inc[-1][2]
        rate = (inc[-1][3] - inc[0][1]) / (t_off - t_on)
        print(f"   {nm(j):18}: {a:8.1f} -> {b:8.1f}  repairing {t_on - s['start']:5.2f}..{t_off - s['start']:5.2f}s  rate {rate:6.2f} HP/s")

"""Power-slider probe report (results_mac/probe_power.json)."""
import json, re, sys
from collections import defaultdict
r = json.load(open(sys.argv[1]))
ps = defaultdict(list); pc = defaultdict(lambda: defaultdict(dict))
for l in r["raw_rows"]:
    p = l.split()
    if p[0] == "ps":
        st, rd = map(int, p[2].split("."))
        d = {"label": p[3]}; d.update(x.split("=", 1) for x in p[4:] if "=" in x)
        ps[(p[1], st)].append((rd, d))
    elif p[0] == "pc":
        st, rd = map(int, p[2].split(".")); pc[(p[1], st)][rd][int(p[3][2:])] = p[4].split(",")
powered = {t: r["meta"].get(f"tele_{t}_powered", "") for t in "AT"}
for tag, name in (("T", "Galaxy"), ("A", "Sovereign")):
    print(f"===== {name}")
    for (t, st), reads in sorted(ps.items()):
        if t != tag: continue
        label = reads[0][1]["label"]
        last = reads[-1][1]
        if label.startswith("pow_"):
            print(f"  {label:28} ms={last['ms']:>6} mw={last['mw']:>7} sr={last['sr']:>6} shon={last['shon']} sh0={last['sh'].split('/')[0]}")
        elif label.startswith("brown"):
            series = [d["ms"] for _, d in reads]
            on = sum(1 for x in series if float(x) > 0)
            print(f"  {label:28} engines powered in {on}/{len(series)} reads (0.5 s apart): {' '.join(series)}")

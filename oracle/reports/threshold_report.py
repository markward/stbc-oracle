"""Threshold probe report: per subsystem, disable point and ship-level effects.
python oracle/reports/threshold_report.py results_mac/probe_threshold.json"""
import json
import re
import sys
from collections import defaultdict

r = json.load(open(sys.argv[1]))
raw = r["raw_rows"]
ps = {}            # (tag, step) -> dict
pc = defaultdict(dict)   # (tag, step) -> {chunk: [vals]}
for l in raw:
    p = l.split()
    if p[0] == "ps":
        tag, (st, rd) = p[1], p[2].split(".")
        d = {"label": p[3]}
        d.update(x.split("=", 1) for x in p[4:] if "=" in x)
        ps[(tag, int(st))] = d
    elif p[0] == "pc":
        tag, (st, rd) = p[1], p[2].split(".")
        k = int(p[3][2:])
        pc[(tag, int(st))][k] = p[4].split(",")
subs = {}
for l in r["raw_rows"]:
    pass
names = {}
for tag, key in (("A", "tele_A_powered"),):
    pass
# subsystem names in walk order come from the step labels thr_<idx>_<name>_c<level>
order = defaultdict(dict)
for (tag, st), d in ps.items():
    m = re.match(r"thr_(\d+)_(.+)_c([\d.]+)$", d["label"])
    if m:
        order[tag][int(m.group(1))] = m.group(2)


def vals(tag, st):
    ch = pc[(tag, st)]
    out = []
    for k in sorted(ch):
        out += ch[k]
    return out


ship = {"A": "attacker", "T": "target"}
for tag in ("T", "A"):
    print(f"===== {ship[tag]} ({r['params'].get('target' if tag == 'T' else 'attacker')})")
    base = None
    steps = sorted(st for (t, st) in ps if t == tag)
    for st in steps:
        d = ps[(tag, st)]
        m = re.match(r"thr_(\d+)_(.+)_c([\d.]+)$", d["label"])
        if not m:
            continue
        idx, nm, lev = int(m.group(1)), m.group(2), float(m.group(3))
        v = vals(tag, st)
        if idx >= len(v):
            continue
        own = v[idx].split("/")          # cond/disabled/canfire/power
        if lev == 1.0 and base is None:
            base = (d, v)
        changed = []
        if base:
            bd, bv = base
            for key in ("ms", "mw", "out", "av", "sr", "shon", "sh", "warp", "dy"):
                if d.get(key) != bd.get(key):
                    changed.append(f"{key}:{bd.get(key)}->{d.get(key)}")
            for j, (a, b) in enumerate(zip(bv, v)):
                if j == idx:
                    continue
                fa, fb = a.split("/"), b.split("/")
                if len(fa) > 2 and len(fb) > 2 and (fa[1] != fb[1] or fa[2] != fb[2]):
                    changed.append(f"{order[tag].get(j, j)}:dis{fa[1]}->{fb[1]},fire{fa[2]}->{fb[2]}")
        print(f"  {nm:22} set {lev:6.3f} -> cond {own[0]:>7} disabled={own[1]} canfire={own[2]:2} {'; '.join(changed)[:160]}")

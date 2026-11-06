"""Compare time-scale runs (results_mac/timescale/*_ts{1,2,4}.json) per GAME second."""
import json
import math
import re
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "results_mac" / "timescale"


def xrows(r, kind, tag):
    out = []
    for l in r["raw_rows"]:
        p = l.split()
        if p[0] == kind and p[1] == tag:
            d = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            d["t"] = float(d["t"])
            out.append(d)
    return out


def v3(s):
    return [float(x) for x in s.split(",")]


def phaser(r):
    hits = [float(re.search(r"dmg=([\d.]+)", l).group(1)) for l in r.get("combat_tap", []) if " H " in l]
    ts = [float(l.split()[0]) for l in r.get("combat_tap", []) if " H " in l]
    if not ts:
        return "no hits"
    span = max(ts) - min(ts)
    return f"hits={len(hits)} total={sum(hits):.0f} over {span:.2f} game-s -> {sum(hits)/span:.1f}/s, per hit {sum(hits)/len(hits):.1f}"


def regen(r):
    rows = xrows(r, "xh", "T")
    pts = [(d["t"], float(d["sh"].split(",")[0])) for d in rows]
    pts = [p for p in pts if p[1] < 7999]
    if len(pts) < 3:
        return "no regen window"
    (t0, a), (t1, b) = pts[len(pts) // 5], pts[-2]
    return f"front face {a:.0f}->{b:.0f} over {t1-t0:.2f} game-s -> {(b-a)/(t1-t0):.2f}/s"


def motion(r, yaw=False):
    rows = xrows(r, "xm", "A")
    if yaw:
        ser = [(d["t"], math.hypot(*v3(d["w"]))) for d in rows]
    else:
        ser = [(d["t"], float(d["sp"])) for d in rows]
    mx = max(v for _, v in ser)
    start = next((t for t, v in ser if v > 0.01 * mx), None)
    t90 = next((t for t, v in ser if v >= 0.9 * mx), None)
    early = [(t, v) for t, v in ser if start is not None and start <= t <= start + 1.0]
    slope = (early[-1][1] - early[0][1]) / (early[-1][0] - early[0][0]) if len(early) > 2 else float("nan")
    return f"max={mx:.4f} t90={t90-start:.2f} game-s initial rate={slope:.4f}/s"


def ticks(r):
    rows = xrows(r, "xm", "A")
    return f"wall {r['elapsed_s']}s"


import sys


def kessok(r):
    rows = [x for x in r["rows"] if "sh" in x]
    d_sh = sum(a - b for a, b in zip(rows[0]["sh"], rows[-1]["sh"]))
    h = rows[0]["h"] - rows[-1]["h"]
    fired = [x for x in rows if any(x.get("fi", []))]
    bank_s = 0.0
    for b in range(len(rows[0]["fi"])):
        f = [x["t"] for x in rows if x["fi"][b]]
        if f:
            bank_s += f[-1] - f[0]
    return f"total={d_sh + h:.0f} hull={h:.0f} bank-seconds={bank_s:.2f} -> {(d_sh + h) / bank_s:.1f}/bank-s"


FUN = {"phaser": phaser, "regen": regen, "impulse": motion, "yaw": lambda r: motion(r, True), "kessok": kessok}
tags = sys.argv[1:] or sorted(p.stem for p in D.glob("*.json"))
for kind in FUN:
    sel = [t for t in tags if t.startswith(kind)]
    if not sel:
        continue
    print(f"== {kind}")
    for t in sel:
        r = json.load(open(D / f"{t}.json"))
        try:
            res = FUN[kind](r)
        except Exception as e:
            res = f"error {e}"
        ls = [x for x in (r.get("lockstep_log") or []) if x.startswith("real=")]
        rate = ""
        if len(ls) > 3:
            a, b = ls[3], ls[-1]
            ra, va = [float(re.search(k + r"=\s*([\d.]+)", a).group(1)) for k in ("real", "virt")]
            rb, vb = [float(re.search(k + r"=\s*([\d.]+)", b).group(1)) for k in ("real", "virt")]
            rate = f" game/real={(vb - va) / (rb - ra):.2f}x"
        print(f"   {t:22} {res}   (wall {r['elapsed_s']}s{rate}, done={r['done']})")

"""Every torpedo's fate, the same way for the original and for Dauntless.

Original: xt1 rows (each projectile in flight: id, ptr, damage, position) + CombatTap HR rows (a hit's
third raw word is the projectile's pointer; pointers are reused, so a hit is matched to the projectile
holding that pointer at that moment). Dauntless: track 'tp' ([id, damage, x, y, z] per sample, recorded
since 2026-10-17) + allhits (a torpedo hit from that launcher within 0.5 s of the projectile vanishing).

Per projectile: launcher (the ship it first appears beside), damage (identifies the type), flight time,
hit or miss, and whether the TARGET ran EvadeTorps at any sample during the flight.

usage: python torp_fates.py --orig <globs> --dn <globs> [--min-dmg 400]
"""
import argparse
import bisect
import collections
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duel_summary as ds  # noqa: E402

RX = re.compile(r"duel_(\w+?)_enemy[\d.]+_vs_(\w+?)_player")


def _orig(path):
    d = ds.load_json(path)
    a, t = RX.search(path).groups()
    rr = d["raw_rows"]
    t0 = float(re.search(r"t0=([\d.]+)", [v for k, v in d["boot"].items() if k.endswith("timers_armed")][0]).group(1))
    pos = {"A": {}, "T": {}}
    ev = {"A": set(), "T": set()}
    tr = {}
    for l in rr:
        p = l.split()
        if p[0] == "xm" and p[1] in "AT" and "p=" in l:
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            pos[p[1]][float(kv["t"])] = [float(x) for x in kv["p"].split(",")]
        elif p[0] == "xa" and "EvadeTorps:" in l:
            ev["T" if p[1] == "Player" else "A"].add(round(float(p[2][2:]), 3))
        elif p[0] == "xt1":
            kv = dict(x.split("=", 1) for x in p[1:] if "=" in x)
            tt = float(kv["t"])
            r = tr.setdefault(kv["id"], {"ptr": ds._norm_ptr(kv["ptr"]), "t0": tt, "t1": tt, "dmg": float(kv["dmg"]),
                                         "p0": [float(x) for x in kv["p"].split(",")]})
            r["t1"] = tt
    hit_ptr_times = collections.defaultdict(list)
    for l in d.get("combat_tap") or []:
        p = l.split()
        if len(p) >= 3 and p[1] == "HR":
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            hit_ptr_times[ds._norm_ptr(kv["raw"].split(",")[2])].append(float(p[0]))
    end = max(pos["A"]) if pos["A"] else 0.0
    ts = sorted(pos["A"])
    out = []
    for i, r in tr.items():
        if r["t1"] >= end - 1.0:
            continue
        k = max(0, bisect.bisect_right(ts, r["t0"]) - 1)
        tk = ts[k]
        da = math.dist(r["p0"], pos["A"][tk]) if tk in pos["A"] else 1e9
        dt_ = math.dist(r["p0"], pos["T"][tk]) if tk in pos["T"] else 1e9
        launcher = "A" if da < dt_ else "T"
        target = "T" if launcher == "A" else "A"
        hit = any(r["t0"] - 0.3 <= h <= r["t1"] + 0.5 for h in hit_ptr_times.get(r["ptr"], ()))
        # xa rows are on the same clock as xm/xt1 (checked 2026-10-17: duels_ai_matrix, duels_ai_speedlog) --
        # no timers_armed offset.
        evaded = any(r["t0"] <= x <= r["t1"] for x in ev[target])
        out.append(dict(cls=a if launcher == "A" else t, dmg=r["dmg"], life=r["t1"] - r["t0"] + 0.25,
                        hit=hit, evaded=evaded))
    return out


def _dn(path):
    g = ds.load_json(path)
    track = g["track"]
    if not track or "tp" not in track[0]:
        return []
    name = {g["attacker_name"]: "A", g["target_name"]: "T"}
    cls = {"A": g["enemy"], "T": g["player"]}
    seen = {}
    for row in track:
        for p in row.get("tp") or []:
            r = seen.setdefault(p[0], {"t0": row["t"], "t1": row["t"], "dmg": p[1], "p0": p[2:5], "row0": row})
            r["t1"] = row["t"]
    evade = {"A": [], "T": []}
    for row in track:
        for k in row.get("beh") or {}:
            who, script = k.split("|")
            if script == "EvadeTorps":
                tag = "A" if who in (g["attacker_name"], "Attacker") else "T"
                evade[tag].append(row["t"])
    # Dauntless logs every projectile hit -- disruptor bolts included -- as "torpedo", with the projectile's script
    # damage. Match a hit to a projectile by (launcher, damage), and let each hit credit ONE projectile (the one whose
    # last sample is nearest in time): a time-only match credited torpedoes with their salvo siblings' and the
    # launcher's bolt hits.
    torp_hits = collections.defaultdict(list)
    for h in g["allhits"]:
        if h[3] == "torpedo" and h[1] in name:
            torp_hits[(name[h[1]], round(float(h[4]), 1))].append(h[0])
    end = track[-1]["t"]
    out = []
    claimed = set()
    for i, r in sorted(seen.items(), key=lambda kv: kv[1]["t1"]):
        if r["t1"] >= end - 1.0:
            continue
        row = r["row0"]
        launcher = "A" if math.dist(r["p0"], row["A"][:3]) < math.dist(r["p0"], row["T"][:3]) else "T"
        target = "T" if launcher == "A" else "A"
        key = (launcher, round(float(r["dmg"]), 1))
        cand = [(abs(h - r["t1"]), k) for k, h in enumerate(torp_hits[key])
                if (key, k) not in claimed and r["t1"] - 0.3 <= h <= r["t1"] + 0.5]
        hit = bool(cand)
        if cand:
            claimed.add((key, min(cand)[1]))
        evaded = any(r["t0"] <= x <= r["t1"] for x in evade[target])
        out.append(dict(cls=cls[launcher], dmg=r["dmg"], life=r["t1"] - r["t0"] + 0.25, hit=hit, evaded=evaded))
    return out


def report(orig_files, dn_files, min_dmg):
    rows = {"orig": [], "dn": []}
    for f in orig_files:
        try:
            rows["orig"] += _orig(f)
        except Exception as e:
            print("skip", f, e, file=sys.stderr)
    for f in dn_files:
        try:
            rows["dn"] += _dn(f)
        except Exception as e:
            print("skip", f, e, file=sys.stderr)
    print("%-11s %-6s | %-28s | %-28s" % ("launcher", "dmg", "original: hit% (n) evading/not", "Dauntless: hit% (n) evading/not"))
    keys = sorted({(r["cls"], r["dmg"]) for s in rows.values() for r in s if r["dmg"] >= min_dmg})
    for c, dm in keys:
        cells = []
        for side in ("orig", "dn"):
            v = [r for r in rows[side] if r["cls"] == c and r["dmg"] == dm]
            ev = [r for r in v if r["evaded"]]
            ne = [r for r in v if not r["evaded"]]
            pct = lambda x: "%3.0f%%" % (100 * sum(r["hit"] for r in x) / len(x)) if x else "  - "
            cells.append("%s (%4d) %s(%d)/%s(%d)" % (pct(v), len(v), pct(ev), len(ev), pct(ne), len(ne)))
        print("%-11s %-6.0f | %-28s | %-28s" % (c, dm, cells[0], cells[1]))
    for side in ("orig", "dn"):
        v = [r for r in rows[side] if r["dmg"] >= min_dmg]
        if v:
            print("%s: torpedoes %d, target evading during flight %.0f%%" % (side, len(v), 100 * sum(r["evaded"] for r in v) / len(v)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", nargs="*", default=[])
    ap.add_argument("--dn", nargs="*", default=[])
    ap.add_argument("--min-dmg", type=float, default=400.0)
    a = ap.parse_args()
    of = sorted(f for g in a.orig for f in glob.glob(g))
    df = sorted(f for g in a.dn for f in glob.glob(g))
    report(of, df, a.min_dmg)

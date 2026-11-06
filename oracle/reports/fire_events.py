"""Torpedo fire decisions as events, from the original game's AI duels (for deriving the firing rule).

For every sample (0.25 s) in which a ship has a loaded torpedo tube, one event:
  t, shooter class, range, the target's angle off each tube's axis at its CURRENT position and at the
  position the SDK's FireScript.PredictTargetLocation predicts (p + v*t + a*t^2/2, t = range / launch
  speed; a = GetAccelerationTG, logged as xac rows), loaded tubes, the behaviours running, and whether
  a tube fired before the next sample (ready count dropped).
The SDK's rule (AI/Preprocessors.py CheckGoodShot): fire when the predicted target is within 10 deg
(cos 0.9848) of ANY tube's direction. This file collects the evidence; firing_rule() summarises it.

usage: python fire_events.py <duel.json ...>      (prints the summary)
"""
import collections
import glob
import json
import math
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
HARDPOINTS = os.path.join(ROOT, "..", "dauntless", "sdk", "Build", "scripts", "ships", "Hardpoints")
PROJECTILES = os.path.join(ROOT, "..", "dauntless", "sdk", "Build", "scripts")
RX = re.compile(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r(\d+)_a(\d+)")
_HP = {}


def hardpoints(cls):
    """{'tubes': [(name, (x, y, z))] in hardpoint order, 'speed': launch speed of ammo slot 0}."""
    if cls in _HP:
        return _HP[cls]
    src = open(os.path.join(HARDPOINTS, cls.lower() + ".py")).read()
    var = dict(re.findall(r'^(\w+) = App\.TorpedoTubeProperty_Create\("([^"]+)"\)', src, re.M))
    dirs = {m.group(1): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
            for m in re.finditer(r"^(\w+)Direction\.SetXYZ\(([-\d.e]+), ([-\d.e]+), ([-\d.e]+)\)", src, re.M)}
    tubes = []
    for v, name in var.items():
        d = dirs.get(v)
        if d:
            n = math.sqrt(sum(x * x for x in d)) or 1.0
            tubes.append((name, tuple(x / n for x in d)))
    speeds = {}
    for slot, script in re.findall(r'SetTorpedoScript\((\d+),\s*"([\w.]+)"\)', src):
        try:
            ps = open(os.path.join(PROJECTILES, *script.split(".")) + ".py").read()
        except OSError:
            continue
        mm = re.search(r"def GetLaunchSpeed\(\):\s*return\s*\(?\s*([\d.]+)", ps)
        if mm:
            speeds[int(slot)] = float(mm.group(1))
    # 'speed' = slot 0 (or the lowest slot present); 'speeds' = every ammo slot, for the current ammo
    speed = speeds.get(0, speeds[min(speeds)] if speeds else None)
    _HP[cls] = {"tubes": tubes, "speed": speed, "speeds": speeds}
    return _HP[cls]


def _v(s):
    return [float(x) for x in s.split(",")]


def _name(path):
    """The capture's name without a .gz suffix: a compressed capture is the same capture."""
    n = os.path.basename(str(path))
    return n[:-3] if n.endswith(".gz") else n


def _kv(parts):
    return dict(x.split("=", 1) for x in parts if "=" in x)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _ang(u, v):
    nu = math.sqrt(sum(x * x for x in u)); nv = math.sqrt(sum(x * x for x in v))
    if nu < 1e-9 or nv < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(u, v)) / (nu * nv)))))


def events(path):
    m = RX.search(os.path.basename(path))
    import duel_summary
    d = duel_summary.load_json(path)
    rr = d.get("raw_rows") or []
    meta = d.get("meta") or {}
    t0 = None
    for k, v in (d.get("boot") or {}).items():
        if k.endswith("timers_armed"):
            t0 = float(re.search(r"t0=([\d.]+)", v).group(1))
    if t0 is None:
        return []
    cls = {"A": m.group(1), "T": m.group(3)}
    S = {tag: collections.defaultdict(dict) for tag in "AT"}
    xw = {tag: collections.defaultdict(dict) for tag in "AT"}
    beh = {tag: collections.defaultdict(set) for tag in "AT"}
    for l in rr:
        p = l.split()
        if len(p) < 3:
            continue
        if p[0] == "xa" and " a=" in l:
            tag = "T" if p[1] == "Player" else "A"
            t = round(float(p[2][2:]) - t0, 3)
            for kv in p[3][2:].split(","):
                if ":" in kv:
                    beh[tag][t].add(kv.split(":")[0])
            continue
        if p[1] not in ("A", "T"):
            continue
        kv = _kv(p[2:])
        if "t" not in kv:
            continue
        t = round(float(kv["t"]) - t0, 3)
        if p[0] == "xm" and "p" in kv:
            S[p[1]][t]["p"], S[p[1]][t]["v"] = _v(kv["p"]), _v(kv["v"])
        elif p[0] == "xo" and "fw" in kv:
            S[p[1]][t]["fw"], S[p[1]][t]["up"] = _v(kv["fw"]), _v(kv["up"])
        elif p[0] == "xac" and "a" in kv:
            S[p[1]][t]["a"] = _v(kv["a"])
        elif p[0] == "xw" and "w" in kv:
            xw[p[1]][t][int(kv.get("k", 0))] = kv["w"]
        elif p[0] == "xz":
            if " dy=1" in l:
                S[p[1]][t]["dying"] = 1
            if "am" in kv:
                try:
                    S[p[1]][t]["am"] = int(kv["am"])
                except ValueError:
                    pass
    out = []
    for tag in "AT":
        o = "T" if tag == "A" else "A"
        hp = hardpoints(cls[tag])
        if not hp["tubes"] or not hp["speed"]:
            continue
        names = (meta.get("tele_%s_emitters" % tag) or "").split(",")
        # The telemetry lists emitters in the game's walk order, which need not be the hardpoint file's
        # (the Akira's file interleaves fore and aft tubes): match tube directions by NAME. The emitter
        # list is cut at 178 characters, so a tube missing from it falls back to hardpoint order.
        by_name = {n.replace(" ", "_"): dv for n, dv in hp["tubes"]}
        tube_dirs = None
        ts = sorted(t for t in S[tag] if t in S[o] and t in xw[tag] and all(k in S[tag][t] for k in ("p", "fw", "up"))
                    and all(k in S[o][t] for k in ("p", "v")))
        prev = None
        for i, t in enumerate(ts):
            if S[tag][t].get("dying") or S[o][t].get("dying"):
                break
            full = ",".join(xw[tag][t][k] for k in sorted(xw[tag][t])).split(",")
            ready = [int(x.split("/")[1]) for x in full if x.startswith("t/")]
            if len(ready) != len(hp["tubes"]):
                continue
            if tube_dirs is None:
                tn = [names[j] for j, x in enumerate(full) if x.startswith("t/") and j < len(names)]
                if len(tn) == len(ready) and all(n in by_name for n in tn):
                    tube_dirs = [by_name[n] for n in tn]
                else:
                    tube_dirs = [dv for _, dv in hp["tubes"]]
            nxt = None
            if i + 1 < len(ts):
                f2 = ",".join(xw[tag][ts[i + 1]][k] for k in sorted(xw[tag][ts[i + 1]])).split(",")
                nxt = [int(x.split("/")[1]) for x in f2 if x.startswith("t/")]
            if sum(ready) == 0 or nxt is None or len(nxt) != len(ready):
                continue
            me, tg = S[tag][t], S[o][t]
            fw, up = me["fw"], me["up"]
            right = _cross(fw, up)
            def body(vec):
                return (sum(a * b for a, b in zip(vec, right)), sum(a * b for a, b in zip(vec, fw)),
                        sum(a * b for a, b in zip(vec, up)))
            rel = [b - a for a, b in zip(me["p"], tg["p"])]
            rng = math.sqrt(sum(x * x for x in rel))
            # flight time from the CURRENT ammo type's launch speed (xz am=), as the SDK's
            # GetWeaponInfo reads pTorp.GetCurrentAmmoType().GetLaunchSpeed()
            am = me.get("am", 0)
            spd = hp["speeds"].get(am, hp["speed"])
            tt = rng / spd
            acc = tg.get("a", [0.0, 0.0, 0.0])
            pred = [tg["p"][k] + tg["v"][k] * tt + 0.5 * acc[k] * tt * tt - me["p"][k] for k in range(3)]
            pred_noacc = [tg["p"][k] + tg["v"][k] * tt - me["p"][k] for k in range(3)]
            bc, bp, bn = body(rel), body(pred), body(pred_noacc)
            per_tube = []
            for j, dvec in enumerate(tube_dirs):
                per_tube.append(dict(loaded=ready[j], fired=max(0, ready[j] - nxt[j]),
                                     cur=_ang(dvec, bc), pred=_ang(dvec, bp), pred_noacc=_ang(dvec, bn)))
            out.append(dict(file=_name(path), shooter=cls[tag], role=tag, t=t, range=rng, ammo=am, speed=spd,
                            tubes=per_tube, beh=sorted(beh[tag].get(t, ())),
                            any_pred=min(x["pred"] for x in per_tube), any_cur=min(x["cur"] for x in per_tube),
                            any_noacc=min(x["pred_noacc"] for x in per_tube),
                            fired=sum(x["fired"] for x in per_tube)))
    return out


def firing_rule(evs, key="any_pred", bins=(0, 2, 4, 6, 8, 10, 12, 15, 20, 30, 45, 90, 180)):
    """P(a launch before the next sample | angle in bin), for the given angle key."""
    rows = []
    for lo, hi in zip(bins, bins[1:]):
        sel = [e for e in evs if lo <= e[key] < hi]
        f = sum(1 for e in sel if e["fired"])
        rows.append((lo, hi, len(sel), f, f / len(sel) if sel else None))
    return rows


if __name__ == "__main__":
    evs = []
    for p in sys.argv[1:]:
        for f in glob.glob(p):
            evs += events(f)
    print("%d events (samples with a loaded tube), %d with a launch" % (len(evs), sum(1 for e in evs if e["fired"])))
    for key in ("any_pred", "any_noacc", "any_cur"):
        print("== P(launch) by %s angle (deg)" % key)
        for lo, hi, n, f, pr in firing_rule(evs, key):
            print("  [%5.1f,%5.1f)  n=%6d  launches=%5d  P=%s" % (lo, hi, n, f, "-" if pr is None else "%.3f" % pr))


def events_dn(path):
    """The same events from a Dauntless duel (scorecard/dauntless_aim_duels.py): the track holds pose
    [x,y,z, fwd, up] and per-tube ready counts 'tr' every 0.25 s; the target's velocity and acceleration
    are differenced from its positions (Dauntless's GetAccelerationTG is the same dv/dt per tick)."""
    import duel_summary
    d = duel_summary.load_json(path)
    if "tube_names" not in d:
        return []
    track = [r for r in d["track"] if r["t"] <= d["t_end"]]
    cls = {"A": d["enemy"], "T": d["player"]}
    who = {"A": {d["attacker_name"], "Attacker"}, "T": {d["target_name"], "Target"}}
    out = []
    for tag in "AT":
        o = "T" if tag == "A" else "A"
        hp = hardpoints(cls[tag])
        tubes_by_name = {n: dv for n, dv in hp["tubes"]}
        names = d["tube_names"].get(tag) or []
        dirs = [tubes_by_name.get(n) for n in names]
        if not names or None in dirs or not hp["speed"]:
            continue
        for i in range(2, len(track) - 1):
            r0, r1, r2, rn = track[i - 2], track[i - 1], track[i], track[i + 1]
            ready, nxt = r2["s" + tag].get("tr"), rn["s" + tag].get("tr")
            if not ready or not nxt or sum(ready) == 0 or len(ready) != len(dirs):
                continue
            dt = r2["t"] - r1["t"]
            if dt <= 0:
                continue
            p0, p1, p2 = r0[o][:3], r1[o][:3], r2[o][:3]
            v = [(b - a) / dt for a, b in zip(p1, p2)]
            v_prev = [(b - a) / dt for a, b in zip(p0, p1)]
            acc = [(b - a) / dt for a, b in zip(v_prev, v)]
            me = r2[tag]
            mp, fw, up = me[:3], me[3:6], me[6:9]
            right = _cross(fw, up)
            def body(vec):
                return (sum(a * b for a, b in zip(vec, right)), sum(a * b for a, b in zip(vec, fw)),
                        sum(a * b for a, b in zip(vec, up)))
            rel = [b - a for a, b in zip(mp, p2)]
            rng = math.sqrt(sum(x * x for x in rel))
            tt = rng / hp["speed"]
            pred = [p2[k] + v[k] * tt + 0.5 * acc[k] * tt * tt - mp[k] for k in range(3)]
            pred_noacc = [p2[k] + v[k] * tt - mp[k] for k in range(3)]
            bc, bp, bn = body(rel), body(pred), body(pred_noacc)
            per_tube = [dict(loaded=ready[j], fired=max(0, ready[j] - nxt[j]), cur=_ang(dv, bc), pred=_ang(dv, bp),
                             pred_noacc=_ang(dv, bn)) for j, dv in enumerate(dirs)]
            behs = sorted({k.split("|")[1] for k in (r2.get("beh") or {}) if k.split("|")[0] in who[tag]})
            out.append(dict(file=_name(path), shooter=cls[tag], role=tag, t=r2["t"], range=rng,
                            tubes=per_tube, beh=behs, any_pred=min(x["pred"] for x in per_tube),
                            any_cur=min(x["cur"] for x in per_tube), any_noacc=min(x["pred_noacc"] for x in per_tube),
                            fired=sum(x["fired"] for x in per_tube)))
    return out

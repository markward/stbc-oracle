"""Does the original's AI choose its target subsystem by the SDK rating?

For every phaser hit aim_reconstruct.py attributes to a chosen subsystem, rebuild
FireScript.RateSubsystemForTargeting (SDK AI/Preprocessors.py:963) for every
candidate on the target at that moment:

    6*critical - 0.0005*max(0, cond - dis%*max) - 3*disabled*DisableFirst(0)
    - 0.0005*cond + 1*hittable + type (weapon/weapon system/shield 5, cloak 4,
    impulse system 3, hull -200)

with conditions from the telemetry (`b` rows: target only; `xb` rows: both
ships), the static facts (critical, disabled %, max, targetable tree) from the
catalogue, and hittable = the measured line-of-sight rule through the target's
mesh from the shooter's real position (energy weapons 0). Candidates are what
ChooseTargetSubsystem builds: targetable subsystems with condition > 0 whose
parents are not targetable.

Reports how often the reconstructed choice is the top-rated candidate, its
rank, and the rating gap when it is not.

usage (needs numpy/trimesh/embreex and Dauntless's _dauntless_host for meshes):
  uv run --with numpy --with trimesh --with embreex python oracle/reports/rating_replay.py <duel.json>...
"""
import json, math, os, re, sys, bisect

sys.path.insert(0, os.path.dirname(__file__))
import aim_reconstruct as AR

DAUNTLESS = os.environ.get("DAUNTLESS_ROOT")     # a built Dauntless checkout (build/python, game/data)
CATALOGUE = os.path.join(os.path.dirname(__file__), "..", "..", "results_mac", "hittable_r20_57_150.json")
TYPE_RATING = (("WeaponSystem", 5.0), ("Weapon", 5.0), ("ShieldClass", 5.0), ("CloakingSubsystem", 4.0),
               ("ImpulseEngineSubsystem", 3.0), ("HullClass", -200.0))


def _mesh(cls):
    if not DAUNTLESS:
        sys.exit("rating_replay.py reads ship meshes through Dauntless: set DAUNTLESS_ROOT to a built checkout")
    sys.path.insert(0, os.path.join(DAUNTLESS, "build", "python"))
    import numpy as np, trimesh
    import _dauntless_host as h
    V_all, F_all, off = [], [], 0
    for d in h.nif_shapes(os.path.join(DAUNTLESS, "game/data/Models/Ships/%s/%s.nif" % (cls, cls))):
        if d.get("hidden"):
            continue
        V = np.array(d["vertices"], dtype=float) * 0.01
        F = np.array(d["triangles"], dtype=int) + off
        V_all.append(V); F_all.append(F); off += len(V)
    return trimesh.Trimesh(np.vstack(V_all), np.vstack(F_all), process=False)


def _hittable(mesh, S, P, R):
    import numpy as np
    o = np.array([S], float); dv = np.array([P], float) - o
    dist = float(np.linalg.norm(dv)); dv /= dist
    locs, ri, _ = mesh.ray.intersects_location(o, dv, multiple_hits=False)
    if len(ri) == 0:
        return 1.0
    first = float(np.linalg.norm(locs[0] - o[0]))
    return 1.0 if abs(dist - first) <= R else 0.0


def static_facts(cat, tag):
    rr = cat["raw_rows"]
    subs = {}
    for l in rr:
        if l.startswith("cs %s " % tag):
            i = int(l.split()[2])
            subs.setdefault(i, {})["name"] = re.search(r"name=(.*?) types=", l).group(1)
            subs[i]["types"] = re.search(r"types=(\S*)", l).group(1).split(",")
            subs[i]["parent"] = int(re.search(r"parent=(-?\d+)", l).group(1))
        if l.startswith("cr %s " % tag) and " ShipSubsystem." in l:
            i = int(l.split()[2]); k, v = l.split(" ShipSubsystem.", 1)[1].split("=", 1)
            subs.setdefault(i, {})[k] = v
    out = {}
    for i, s in subs.items():
        trate = 0.0
        for t, r in TYPE_RATING:
            if t in s["types"]:
                trate = r
                break
        out[s["name"]] = {
            "pos": [float(x) for x in s["GetPosition"].split(",")], "R": float(s["GetRadius"]),
            "max": float(s["GetMaxCondition"]), "dis": float(s["GetDisabledPercentage"]),
            "crit": float(s["IsCritical"]), "targetable": int(s["IsTargetable"]),
            "parent": subs[s["parent"]]["name"] if s["parent"] >= 0 else None,
            "ew": ("EnergyWeapon" in s["types"]), "type": trate}
    return out


def conditions(d, tag, names_target):
    """{t: {name: condition}} for ship `tag`: xc rows (every subsystem, catalogue walk order, chunked by k),
    else xb rows, else (target only) b rows."""
    rr = d["raw_rows"]
    xc = {}
    for l in rr:
        if l.startswith("xc %s " % tag) and " c=" in l:
            p = l.split(); t = float(p[2][2:]); k = int(p[3][2:])
            xc.setdefault(t, {})[k] = [float(x) for x in p[4][2:].split(",")]
    if xc:
        out = {}
        for t, chunks in xc.items():
            flat = []
            for k in sorted(chunks):
                flat += chunks[k]
            out[t] = dict(zip(names_target, flat))
        return out
    meta = d["meta"]
    names = []
    k = 0
    while ("tele_%s_subs%d" % (tag, k)) in meta:
        names += meta["tele_%s_subs%d" % (tag, k)].split(","); k += 1
    series = {}
    if names:
        for l in rr:
            if l.startswith("xb %s " % tag) and " s=" in l:
                p = l.split(); t = float(p[2][2:]); i0 = int(p[3][2:])
                vals = [float(x) for x in p[4][2:].split(",")]
                row = series.setdefault(t, {})
                for j, v in enumerate(vals):
                    if i0 + j < len(names):
                        row[names[i0 + j]] = v
        return series
    if tag != "T":
        return {}
    sub_names = [s.replace(" ", "_") for s in (d.get("subsystems") or names_target)]
    for l in rr:
        if l.startswith("b t="):
            p = l.split(); t = float(p[1][2:]); vals = [float(x) for x in p[2][2:].split(",")]
            series[t] = dict(zip(sub_names, vals))
    return series


def candidates(facts, cond):
    out = []
    for nm, f in facts.items():
        if not f["targetable"] or cond.get(nm, f["max"]) <= 0:
            continue
        p = f["parent"]; ok = True
        while p is not None:
            if facts[p]["targetable"]:
                ok = False
                break
            p = facts[p]["parent"]
        if ok:
            out.append(nm)
    return out


def rate(f, c, hit, disable_first=0):
    to_disable = max(0.0, c - f["dis"] * f["max"])
    disabled = 1.0 if c < f["dis"] * f["max"] else 0.0
    return 6.0 * f["crit"] - 0.0005 * to_disable - 0.0005 * c + hit + f["type"] - 3.0 * disabled * disable_first


def replay(path, cat):
    d = json.load(open(path))
    meta = d["meta"]
    cls = {"A": meta.get("in_attacker"), "T": meta.get("in_target")}
    cat_tag = {"Galaxy": "T", "Sovereign": "A"}
    facts = {t: static_facts(cat, cat_tag[c]) for t, c in cls.items()}
    meshes = {t: _mesh(c) for t, c in cls.items()}
    conds = {t: conditions(d, t, list(facts[t].keys())) for t in ("A", "T")}
    import aim_bank
    D = aim_bank.Duel(path, cat)
    hits = [(r["t"], r["shooter"], r["target"], r["chosen"], r["miss"]) for r in D.best_mapping()
            if r["miss"] < 0.1 and r["margin"] > 0.1]
    xm = {t: AR.telemetry(d["raw_rows"], "xm", t) for t in ("A", "T")}
    xo = {t: AR.telemetry(d["raw_rows"], "xo", t) for t in ("A", "T")}
    # BasicAttack sets DisableBeforeDestroy at difficulty >= 0.7 (g_lFlagThresholds)
    lv = {"A": float(meta.get("in_ai_level") or 1.0), "T": float(meta.get("in_friendly_ai_level") or 1.0)}
    dfirst = {k: (1 if v >= 0.7 else 0) for k, v in lv.items()}
    res = []
    lag = float(os.environ.get("RATING_LAG", "0"))
    for (t, shooter, tgt, chosen, perp) in hits:
        t_hit = t
        t = t - lag
        series = conds[tgt]
        if not series:
            continue
        ts = sorted(series)
        i = bisect.bisect_left(ts, t); i = min(max(i, 0), len(ts) - 1)
        cond = series[ts[i]]
        ms, mt, ot = AR.interp(xm[shooter], t), AR.interp(xm[tgt], t), AR.interp(xo[tgt], t)
        fw, up = AR.norm(AR.vec(ot["fw"])), AR.norm(AR.vec(ot["up"]))
        right = AR.cross(fw, up)
        dw = AR.sub(AR.vec(ms["p"]), AR.vec(mt["p"]))
        S = [AR.dot(dw, right), AR.dot(dw, fw), AR.dot(dw, up)]
        F = facts[tgt]
        ratings = {}
        feats = {}
        for nm in candidates(F, cond):
            f = F[nm]
            hit = 0.0 if f["ew"] else _hittable(meshes[tgt], S, f["pos"], f["R"])
            hit_geo = _hittable(meshes[tgt], S, f["pos"], f["R"])
            c = cond.get(nm, f["max"])
            ratings[nm] = rate(f, c, hit, dfirst[shooter])
            feats[nm] = {"crit": f["crit"], "cond": c, "max": f["max"], "dis": f["dis"], "hit": hit, "hit_geo": hit_geo,
                         "type": f["type"], "ew": f["ew"], "dist": math.sqrt(sum((S[k] - f["pos"][k]) ** 2 for k in range(3)))}
        order = sorted(ratings, key=lambda n: -ratings[n])
        group = chosen.split("+")
        ranks = [order.index(g) + 1 for g in group if g in order]
        rank = min(ranks) if ranks else None
        chosen = [g for g in group if g in order and order.index(g) + 1 == rank][0] if ranks else group[0]
        res.append({"t": t_hit, "lag": lag, "shooter": shooter, "chosen": chosen, "group": group, "feats": feats, "rank": rank, "top": order[:3],
                    "gap": None if rank is None else round(ratings[order[0]] - ratings[chosen], 3),
                    "r_top": [round(ratings[n], 3) for n in order[:3]]})
    return res


if __name__ == "__main__":
    cat = json.load(open(CATALOGUE))
    tot = {}
    for path in [a for a in sys.argv[1:] if a.endswith(".json") and not a.endswith(".aim.json")]:
        res = replay(path, cat)
        json.dump(res, open(path.replace(".json", ".decisions%s.json" % (
            "" if not os.environ.get("RATING_LAG") else "_lag" + os.environ["RATING_LAG"])), "w"))
        print("== %s" % os.path.basename(path))
        for sh in ("A", "T"):
            rs = [r for r in res if r["shooter"] == sh]
            if not rs:
                continue
            top1 = sum(1 for r in rs if r["rank"] == 1)
            top3 = sum(1 for r in rs if r["rank"] is not None and r["rank"] <= 3)
            gaps = sorted(r["gap"] for r in rs if r["gap"] is not None and r["rank"] != 1)
            print("  shooter %s: %d hits  top1 %d (%.0f%%)  top3 %d  median gap when not top %.3f" % (
                sh, len(rs), top1, 100.0 * top1 / len(rs), top3, gaps[len(gaps) // 2] if gaps else 0.0))
            last = None
            for r in rs:
                key = (r["chosen"], tuple(r["top"]))
                if key != last:
                    print("    t=%6.1f chose %-18s rank=%s top=%s %s" % (r["t"], r["chosen"], r["rank"], r["top"], r["r_top"]))
                    last = key
            a = tot.setdefault(sh, [0, 0]); a[0] += top1; a[1] += len(rs)

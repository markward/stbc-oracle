"""Damage dealt per minute, by weapon kind, the original's AI duels vs Dauntless's.

Original: CombatTap H rows (every weapon hit: ship=<target ptr> type=0 phaser / 1 torpedo..., dmg=) in
results_mac/duels*/duel_*.json; the ship pointer is matched to the telemetry tag (A attacker / T target) by which
tag's shield total (xh rows) drops across each shield hit. Dauntless: the recorder's allhits
[t, source, ship, weapon_type, dmg, shields_before, hull_before] in scorecard/dauntless_aim_duels.
Per (enemy, player, level): each SHOOTER's damage per minute of fight, split phaser / torpedo / other.
usage: python compare_damage.py
The last column counts each original hit once (duel_summary.py); the "original" column is kept as it
was and over-counts phaser hits that bleed through (logged twice). matchup_stats.py is the full comparison.
"""
import bisect, collections, glob, json, os, re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RX = re.compile(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)")
KIND = {"0": "phaser"}


def _kind_bc(kv):
    if kv.get("type") == "0":
        return "phaser"
    return "torpedo" if kv.get("type") == "1" else "type" + kv.get("type", "?")


def _kind_dn(w):
    w = (w or "").lower()
    if "phaser" in w or "beam" in w:
        return "phaser"
    if "torp" in w or "projectile" in w:
        return "torpedo"
    return w or "other"


def _shield_series(rr):
    out = {"A": ([], []), "T": ([], [])}
    for l in rr:
        if not l.startswith("xh "):
            continue
        p = l.split()
        t = float(p[2][2:])
        s = sum(float(x) for x in p[3][3:].split(",") if x)
        out[p[1]][0].append(t)
        out[p[1]][1].append(s)
    return out


def _drop(series, t):
    ts, vs = series
    i = bisect.bisect_left(ts, t)
    if i <= 0 or i >= len(ts):
        return 0.0
    return vs[i - 1] - vs[i]


def _drop_bleed_through(hits, tap):
    """The original logs a projectile hit that drains a shield face twice: the shield row and, within ~0.15 s on the
    same ship, a second row for the part that bleeds through -- same weapon (damage / radius ratio), smaller damage.
    Summing both counted those torpedoes twice (a Sovereign's quantum torpedoes read 7,600/min instead of 6,400).
    Keep the larger row of each such pair."""
    rows = []
    for l in tap:
        p = l.split()
        if len(p) < 3 or p[1] != "H":
            continue
        kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
        rows.append((float(p[0]), kv["ship"], kv.get("type"), float(kv.get("dmg", 0)), float(kv.get("rad", 0) or 0)))
    drop = set()
    for i, (t, sh, ty, dm, rad) in enumerate(rows):
        if ty == "0" or dm <= 0 or rad <= 0:
            continue
        for j in range(max(0, i - 6), min(len(rows), i + 7)):
            t2, sh2, ty2, dm2, rad2 = rows[j]
            if (j != i and sh2 == sh and ty2 == ty and abs(t2 - t) < 0.15 and dm2 > dm and rad2 > 0
                    and abs(rad / dm - rad2 / dm2) < 1e-5):
                drop.add(i)
                break
    keep = [r for i, r in enumerate(rows) if i not in drop]
    out = []
    for (t, sh, ty, dm, rad) in keep:
        out.append((t, sh, "phaser" if ty == "0" else ("torpedo" if ty == "1" else "type%s" % ty), dm))
    return out


def bc():
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    mins = collections.defaultdict(float)
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*.json")):
        m = RX.search(os.path.basename(f))
        if not m or "probe" in f:
            continue
        try:
            d = json.load(open(f))
        except Exception:
            continue
        boot = d.get("boot") or {}
        over = [v for k, v in boot.items() if k.endswith("duel_over")]
        if not over:
            continue
        t_end = float(re.search(r"t=([\d.]+)", over[0]).group(1))
        sh = _shield_series(d.get("raw_rows") or [])
        hits = []
        votes = collections.defaultdict(lambda: collections.Counter())
        for l in d.get("combat_tap") or []:
            p = l.split()
            if len(p) < 3 or p[1] != "H":
                continue
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            t, dmg = float(p[0]), float(kv.get("dmg", 0))
            hits.append((t, kv["ship"], _kind_bc(kv), dmg))
            if kv.get("hull") == "0" and dmg > 5:
                da, dt_ = _drop(sh["A"], t + 0.05), _drop(sh["T"], t + 0.05)
                if max(da, dt_) > 1.0:
                    votes[kv["ship"]]["A" if da > dt_ else "T"] += 1
        tag = {ptr: c.most_common(1)[0][0] for ptr, c in votes.items() if c}
        hits = _drop_bleed_through(hits, d.get("combat_tap") or [])
        key = (m.group(1), m.group(3), float(m.group(2)))
        cls = {"A": m.group(1), "T": m.group(3)}
        mins[key] += t_end / 60.0
        for t, ptr, k, dmg in hits:
            if ptr not in tag:
                continue
            shooter = cls["T" if tag[ptr] == "A" else "A"]
            out[key][(shooter, k)] += dmg
    return out, mins


def dauntless():
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    mins = collections.defaultdict(float)
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        key = (d["enemy"], d["player"], float(d["level"]))
        name = {d.get("attacker_name"): d["enemy"], d.get("target_name"): d["player"]}
        mins[key] += float(d["t_end"]) / 60.0
        for t, src, dst, w, dmg, _, _ in d.get("allhits") or []:
            shooter = name.get(src)
            if shooter is None:
                continue
            out[key][(shooter, _kind_dn(w))] += dmg
    return out, mins


def bc_once():
    """The original's damage per (key, (shooter, kind)) with each hit counted ONCE (duel_summary.py:
    a bleed-through hit is re-logged under the same hit ID -- phasers too, which _drop_bleed_through
    above leaves in -- and IDs are reused later). Same minutes as bc()."""
    import duel_summary as ds
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*.json")):
        try:
            s = ds.cached_summary(f)
        except Exception:
            continue
        if not s or not s["ended"] or not s["attribution"]:
            continue
        key = (s["enemy"], s["player"], float(s["level"]))
        for r in s["ships"].values():
            out[key][(r["class"], "phaser")] += r["dealt"]["energy"]["dmg"]
            out[key][(r["class"], "torpedo")] += r["dealt"]["torpedo"]["dmg"]
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    (B, bm), (D, dm) = bc(), dauntless()
    B1 = bc_once()
    for key in sorted(set(B) | set(D)):
        print("== %s (enemy) vs %s AI %.1f   fight-minutes original %.0f, Dauntless %.0f" % (key[0], key[1], key[2],
                                                                                         bm.get(key, 0), dm.get(key, 0)))
        rows = sorted(set(B.get(key, {})) | set(D.get(key, {})))
        for r in rows:
            b = B[key][r] / bm[key] if bm.get(key) else None
            dd = D[key][r] / dm[key] if dm.get(key) else None
            b1 = B1[key][r] / bm[key] if (bm.get(key) and r in B1.get(key, {})) else None
            print("   %-11s %-8s original %8s /min   Dauntless %8s /min   | original, each hit once %8s /min" % (
                r[0], r[1], "%.0f" % b if b is not None else "-", "%.0f" % dd if dd is not None else "-",
                "%.0f" % b1 if b1 is not None else "-"))

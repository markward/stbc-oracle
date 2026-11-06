"""One summary per AI duel, in the same format for the original and for Dauntless.

Original: results_mac/duels*/duel_*.json (run_oracle --duel --ai, OracleTelemetry x* rows + CombatTap).
Dauntless: scorecard/dauntless_aim_duels*/duel_*.json (scorecard/dauntless_aim_duels.py).

summarize(path) -> dict (SCHEMA below); None for a file that is not a finished-or-capped duel.
Every field is per ROLE ("enemy" = the attacker / QuickBattleAI ship, "player" = the target /
QuickBattleFriendlyAI ship). A field a capture cannot supply is None, never a guess, and
"attribution" says how the original's hit log was tied to ships ("ptr" exact, from the
tele_X_ptr meta; "inferred" for captures made before it existed, from the hull's max condition).

Counting rules (each one cost a wrong answer before it was written down):
  - BC's CombatTap logs a hit that bleeds through its shield TWICE under the same hit= ID (an
    H hull=0 row, then an H hull=1 row with the passed amount) -- phasers as well as torpedoes --
    and reuses hit IDs once a projectile is gone. A hit is one ID within HIT_REUSE_S seconds; its
    damage is the first row's.
  - Torpedo launches are decrements of the torpedoes-left count (xz ta= / track ta).
  - Times are seconds since the duel started (BC: game time - t0 of the timers_armed mark;
    Dauntless: the sample clock), and every per-ship series stops at the first death.

usage: python duel_summary.py <duel.json> [...]       (prints the summaries as JSON)
"""
import bisect
import collections
import json
import math
import os
import re
import sys

SCHEMA = 1
HIT_REUSE_S = 0.5
ALIGN_DEG = 10.0             # the SDK FireScript's accurate-torpedo window
CURVE_STEP_S = 15.0
RX = re.compile(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r(\d+)_a(\d+)")
# A human-flown Dauntless fight (DAUNTLESS_COMBAT_RECORD): no range or bearing, the enemy's AI level
# (-1 when the recorder could not read it) and the recording's start time.
RX_HUMAN = re.compile(r"duel_(\w+?)_enemy(-?[\d.]+)_vs_(\w+?)_player_human_(\d{8}-\d{6})")
HULL_MAX = {}                # class -> hull max, filled from captures that log it (inference fallback)


# ---------------------------------------------------------------------------------------- helpers
def _name(path):
    """The capture's name without a .gz suffix: a compressed capture is the same capture."""
    n = os.path.basename(str(path))
    return n[:-3] if n.endswith(".gz") else n


def _kv(parts):
    return dict(x.split("=", 1) for x in parts if "=" in x)


def _v3(s):
    return [float(x) for x in s.split(",")]


def _ang(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    c = sum(x * y for x, y in zip(a, b)) / (na * nb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _median(v):
    v = sorted(v)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def _norm_ptr(p):
    return (p or "").strip().lstrip("0").lower()


def _is_aft(name):
    n = (name or "").lower()
    return "aft" in n or "rear" in n


def _empty_ship(cls):
    return {
        "class": cls,
        "dealt": {"energy": {"hits": 0, "dmg": 0.0}, "torpedo": {"hits": 0, "dmg": 0.0}},
        "taken": {"hits": 0, "dmg": 0.0, "passed": None, "hull": None, "subsystems": None},
        "torpedo": {"launches": 0, "launch_fwd": None, "launch_aft": None,
                    "aligned_loaded_s": None, "launch_aligned": None, "episodes": None, "no_shot": None,
                    "first_shot_med_s": None, "launch_angle_med": None, "launch_range_med": None},
        "behaviour": None,
        "curve": None,
    }


def _torpedo_geometry(series, tube_aft, out):
    """series: [(t, angle of the enemy off the nose, [ready per tube] or None, launched_now)].
    Fills launch side counts and the loaded+aligned conversion figures."""
    have_tubes = all(x[2] is not None for x in series) and series
    if not series:
        return
    angles, ranges = [], []
    for t, a, tr, n, rng in series:
        if n:
            angles += [min(a, 180.0 - a)] * n
            ranges += [rng] * n
    out["launch_angle_med"] = _median(angles)
    out["launch_range_med"] = _median(ranges)
    if not have_tubes:
        return
    fwd = [i for i, aft in enumerate(tube_aft) if not aft]
    aft = [i for i, a_ in enumerate(tube_aft) if a_]
    tot = {"launch_fwd": 0, "launch_aft": 0}
    al_s, al_n, eps, none_, first = 0.0, 0, 0, 0, []
    for side, idx in (("fwd", fwd), ("aft", aft)):
        prev, prev_st, ep = None, False, None
        for t, a, tr, n, rng in series:
            if len(tr) != len(tube_aft):
                prev = None
                continue
            fired = sum(max(0, prev[i] - tr[i]) for i in idx) if prev is not None else 0
            tot["launch_" + side] += fired
            st = sum(tr[i] for i in idx) > 0 and ((a < ALIGN_DEG) if side == "fwd" else (a > 180.0 - ALIGN_DEG))
            if prev is not None and prev_st:
                al_s += series_dt(series)
                al_n += fired
            if st and not prev_st:
                ep = {"t0": t, "shot": None}
            if ep is not None and fired and ep["shot"] is None:
                ep["shot"] = t - ep["t0"]
            if ep is not None and not st and not fired:
                eps += 1
                if ep["shot"] is None:
                    none_ += 1
                else:
                    first.append(ep["shot"])
                ep = None
            prev, prev_st = tr, st
    out.update(tot)
    out["aligned_loaded_s"] = round(al_s, 2)
    out["launch_aligned"] = al_n
    out["episodes"] = eps
    out["no_shot"] = none_
    out["first_shot_med_s"] = _median(first)


def series_dt(series):
    if len(series) < 2:
        return 0.25
    return round((series[-1][0] - series[0][0]) / (len(series) - 1), 4)


def _curve(points, t_end):
    """points: [(t, shields, hull)] -> fractions of the first sample every CURVE_STEP_S."""
    if not points:
        return None
    points = sorted(points)
    ts = [p[0] for p in points]
    s0 = points[0][1] or 1.0
    h0 = points[0][2] or 1.0
    out = {"t": [], "shield": [], "hull": []}
    t = 0.0
    while t <= t_end + 1e-6:
        i = max(0, bisect.bisect_right(ts, t) - 1)
        out["t"].append(t)
        out["shield"].append(round(points[i][1] / s0, 4))
        out["hull"].append(round(points[i][2] / h0, 4))
        t += CURVE_STEP_S
    return out


# --------------------------------------------------------------------------------------- original
def _summarize_orig(d, path, m):
    rr = d.get("raw_rows") or []
    boot = d.get("boot") or {}
    meta = d.get("meta") or {}
    t0 = None
    for k, v in boot.items():
        if k.endswith("timers_armed"):
            mm = re.search(r"t0=([\d.]+)", v)
            t0 = float(mm.group(1)) if mm else None
    over = [v for k, v in boot.items() if k.endswith("duel_over")]
    if t0 is None:
        return None
    if over:
        t_end = float(re.search(r"t=([\d.]+)", over[0]).group(1))
        da = " attacker_dying=1" in over[0]
        dt_ = " target_dying=1" in over[0]
        winner = m["player"] if da and not dt_ else (m["enemy"] if dt_ and not da else None)
        winner_role = "player" if da and not dt_ else ("enemy" if dt_ and not da else None)
        ended = True
    else:
        if not d.get("done"):
            return None
        t_end = float((d.get("params") or {}).get("duration", 600.0))
        winner, ended = None, False
        winner_role = None

    cls = {"A": m["enemy"], "T": m["player"]}
    role = {"A": "enemy", "T": "player"}
    ships = {"enemy": _empty_ship(m["enemy"]), "player": _empty_ship(m["player"])}

    # per-tag time series
    pos, fw, shd, hull0, tr = ({"A": {}, "T": {}} for _ in range(5))
    xw = {"A": collections.defaultdict(dict), "T": collections.defaultdict(dict)}
    ta = {"A": [], "T": []}
    for l in rr:
        p = l.split()
        if len(p) < 3 or not p[0].startswith("x"):
            continue
        kind, tag = p[0], p[1]
        if tag not in ("A", "T"):
            continue
        kv = _kv(p[2:])
        if "t" not in kv:
            continue
        t = float(kv["t"]) - t0
        if kind == "xm" and "p" in kv:
            pos[tag][t] = _v3(kv["p"])
        elif kind == "xo" and "fw" in kv:
            fw[tag][t] = _v3(kv["fw"])
        elif kind == "xh" and "sh" in kv:
            shd[tag][t] = sum(_v3(kv["sh"]))
        elif kind == "xc" and kv.get("k") == "0" and "c" in kv:
            hull0[tag][t] = float(kv["c"].split(",")[0])
        elif kind == "xw" and "w" in kv:
            xw[tag][t][int(kv.get("k", 0))] = kv["w"]
        elif kind == "xz" and "ta" in kv:
            # one count per ammo type: "250", or "150/50" for a two-type ship
            ta[tag].append((t, [int(float(x)) for x in re.split(r"[,/]", kv["ta"]) if x]))
    dying = {}
    for l in rr:
        if l.startswith("xz ") and " dy=1" in l:
            p = l.split()
            tag = p[1]
            t = float(_kv(p[2:])["t"]) - t0
            dying[tag] = min(dying.get(tag, 1e9), t)
    t_cut = min([t_end] + list(dying.values()))

    # torpedo launches + geometry
    names = {tag: (meta.get("tele_%s_emitters" % tag) or "").split(",") for tag in "AT"}
    for tag in "AT":
        o = "T" if tag == "A" else "A"
        out = ships[role[tag]]["torpedo"]
        series, prev = [], None
        tubes_aft = None
        launches_at = {}
        for t, v in ta[tag]:
            if prev is not None and t <= t_cut:
                n = sum(max(0, a - b) for a, b in zip(prev, v))
                out["launches"] += n
                if n:
                    launches_at[t] = n
            prev = v
        for t in sorted(fw[tag]):
            if t > t_cut or t not in pos[tag] or t not in pos[o]:
                continue
            to = [b - a for a, b in zip(pos[tag][t], pos[o][t])]
            ready = None
            if t in xw[tag]:
                full = ",".join(xw[tag][t][k] for k in sorted(xw[tag][t])).split(",")
                ready = [int(x.split("/")[1]) for x in full if x.startswith("t/")]
                if tubes_aft is None:
                    tn = [names[tag][i] for i, x in enumerate(full) if x.startswith("t/") and i < len(names[tag])]
                    tubes_aft = [_is_aft(x) for x in tn] if len(tn) == len(ready) else None
            series.append((t, _ang(fw[tag][t], to), ready if tubes_aft else None, launches_at.get(t, 0),
                           math.sqrt(sum(x * x for x in to))))
        _torpedo_geometry(series, tubes_aft or [], out)

    # behaviour shares (xa rows: ship name 'Player' = the player role)
    grid = sorted(t for t in pos["A"] if t <= t_cut)
    if any(l.startswith("xa ") for l in rr):
        ran = {"A": collections.Counter(), "T": collections.Counter()}
        seen = {"A": collections.defaultdict(set), "T": collections.defaultdict(set)}
        gset = set(round(t, 3) for t in grid)
        for l in rr:
            if l.startswith("xa ") and " a=" in l:
                p = l.split()
                t = round(float(p[2][2:]) - t0, 3)
                if t not in gset:
                    continue
                tag = "T" if p[1] == "Player" else "A"
                for kvp in p[3][2:].split(","):
                    if ":" in kvp:
                        seen[tag][t].add(kvp.split(":")[0])
        for tag in "AT":
            for t, mods in seen[tag].items():
                for x in mods:
                    ran[tag][x] += 1
            ships[role[tag]]["behaviour"] = {k: round(v / len(grid), 4) for k, v in ran[tag].items()} if grid else None

    # curves
    for tag in "AT":
        pts = [(t, shd[tag][t], hull0[tag][t]) for t in shd[tag] if t in hull0[tag] and t <= t_cut]
        ships[role[tag]]["curve"] = _curve(pts, t_cut)

    # hits: attribute ship pointers
    tap = d.get("combat_tap") or []
    ptr_role, attribution = {}, None
    if meta.get("tele_A_ptr") and meta.get("tele_T_ptr") and meta["tele_A_ptr"] != "err":
        ptr_role = {_norm_ptr(meta["tele_A_ptr"]): "enemy", _norm_ptr(meta["tele_T_ptr"]): "player"}
        attribution = "ptr"
    else:
        h0 = {tag: (hull0[tag][min(hull0[tag])] if hull0[tag] else None) for tag in "AT"}
        if h0["A"] is not None and h0["T"] is not None and abs(h0["A"] - h0["T"]) > 1e-3:
            for l in tap:
                p = l.split()
                if len(p) > 2 and p[1] == "W":
                    kv = _kv(p[2:])
                    a = float(kv["hp"].split("->")[0])
                    for tag in "AT":
                        if abs(a - h0[tag]) < 1e-3:
                            ptr_role.setdefault(_norm_ptr(kv["ship"]), role[tag])
            if len(set(ptr_role.values())) == 2:
                attribution = "inferred"
            elif len(ptr_role) == 1:
                # one ship never took hull damage: the other pointer seen in H rows is it
                known = list(ptr_role.items())[0]
                for l in tap:
                    p = l.split()
                    if len(p) > 2 and p[1] == "H":
                        sp = _norm_ptr(_kv(p[2:])["ship"])
                        if sp != known[0]:
                            ptr_role[sp] = "player" if known[1] == "enemy" else "enemy"
                            break
                attribution = "inferred" if len(ptr_role) == 2 else None
    # subsystem names by pointer (new captures)
    sub_name = {}
    for tag in "AT":
        nm, pp = [], []
        k = 0
        while ("tele_%s_sptr%d" % (tag, k)) in meta:
            nm += meta.get("tele_%s_subs%d" % (tag, k), "").split(",")
            pp += meta["tele_%s_sptr%d" % (tag, k)].split(",")
            k += 1
        for n, p_ in zip(nm, pp):
            sub_name[_norm_ptr(p_)] = n
    if attribution:
        other = {"enemy": "player", "player": "enemy"}
        last = {}
        for r in ships.values():
            r["taken"]["passed"] = 0.0
            r["taken"]["hull"] = 0.0
            r["taken"]["subsystems"] = {} if sub_name else None
        hull_ptrs = {}
        for l in tap:
            p = l.split()
            if len(p) < 3 or p[0].startswith("#"):
                continue
            t = float(p[0]) - t0
            if t > t_cut:
                continue
            kv = _kv(p[2:])
            rl = ptr_role.get(_norm_ptr(kv.get("ship")))
            if rl is None:
                continue
            if p[1] == "H":
                hid = kv.get("hit")
                if hid in last and t - last[hid] < HIT_REUSE_S:
                    continue
                last[hid] = t
                w = "torpedo" if kv.get("type") == "1" else "energy"
                dm = float(kv.get("dmg", 0))
                ships[other[rl]]["dealt"][w]["hits"] += 1
                ships[other[rl]]["dealt"][w]["dmg"] += dm
                ships[rl]["taken"]["hits"] += 1
                ships[rl]["taken"]["dmg"] += dm
            elif p[1] == "DS":
                ships[rl]["taken"]["passed"] += float(kv.get("dmg", 0))
            elif p[1] == "W":
                a, b = (float(x) for x in kv["hp"].split("->"))
                sp = _norm_ptr(kv["sub"])
                nm = sub_name.get(sp)
                if nm is None and attribution == "inferred":
                    # the hull is the sub whose first hp equals the ship's hull max
                    if sp not in hull_ptrs:
                        tag = "A" if rl == "enemy" else "T"
                        h0 = hull0[tag][min(hull0[tag])] if hull0[tag] else None
                        hull_ptrs[sp] = h0 is not None and abs(a - h0) < 1e-3
                    nm = "Hull" if hull_ptrs[sp] else None
                if nm == "Hull":
                    ships[rl]["taken"]["hull"] += a - b
                if nm is not None and ships[rl]["taken"]["subsystems"] is not None:
                    ships[rl]["taken"]["subsystems"][nm] = ships[rl]["taken"]["subsystems"].get(nm, 0.0) + (a - b)
    return dict(schema=SCHEMA, source="orig", file=_name(path), enemy=m["enemy"], player=m["player"],
                level=m["level"], angle=m["angle"], winner=winner, winner_role=winner_role, ended=ended,
                t_end=round(t_cut, 3),
                attribution=attribution, ships=ships)


# -------------------------------------------------------------------------------------- Dauntless
def _summarize_dn(d, path, m):
    t_end = float(d["t_end"])
    winner = d.get("winner")
    # role that won: recorded since 2026-10-16 (mirror matches); older files derive it from the class
    winner_role = d.get("winner_role")
    if winner_role is None and winner is not None and d["enemy"] != d["player"]:
        winner_role = "enemy" if winner == d["enemy"] else "player"
    ships = {"enemy": _empty_ship(d["enemy"]), "player": _empty_ship(d["player"])}
    name_role = {d["attacker_name"]: "enemy", d["target_name"]: "player", "Attacker": "enemy", "Target": "player"}
    other = {"enemy": "player", "player": "enemy"}
    track = [r for r in d.get("track") or [] if r["t"] <= t_end + 1e-6]
    tag_role = {"A": "enemy", "T": "player"}

    # hits: allhits (every file) for counts and damage
    for h in d.get("allhits") or []:
        t, src, dst, w, dm = h[0], h[1], h[2], h[3], h[4]
        rs, rd = name_role.get(src), name_role.get(dst)
        if rs is None or rd is None or w not in ("phaser", "torpedo"):
            continue
        k = "torpedo" if w == "torpedo" else "energy"
        ships[rs]["dealt"][k]["hits"] += 1
        ships[rs]["dealt"][k]["dmg"] += dm
        ships[rd]["taken"]["hits"] += 1
        ships[rd]["taken"]["dmg"] += dm
    # per-hit split (files with hitdetail)
    if "hitdetail" in d:
        for r in ships.values():
            r["taken"]["passed"] = 0.0
            r["taken"]["hull"] = 0.0
            r["taken"]["subsystems"] = {}
        for t, src, dst, w, dm, sh0, sh1, lost in d["hitdetail"]:
            rs, rd = name_role.get(src), name_role.get(dst)
            if rs is None or rd is None or w not in ("phaser", "torpedo"):
                continue
            absorbed = sum(a - b for a, b in zip(sh0, sh1)) if sh0 and sh1 else 0.0
            ships[rd]["taken"]["passed"] += max(0.0, dm - absorbed)
            for nm, x in lost.items():
                key = nm.replace(" ", "_")[:13]     # the original's telemetry names are cut to 13
                if nm == "Hull":
                    ships[rd]["taken"]["hull"] += x
                ships[rd]["taken"]["subsystems"][key] = ships[rd]["taken"]["subsystems"].get(key, 0.0) + x

    # torpedoes
    tubes = d.get("tube_names") or {}
    for tag in "AT":
        o = "T" if tag == "A" else "A"
        out = ships[tag_role[tag]]["torpedo"]
        series, prev = [], None
        aft = [_is_aft(x) for x in tubes.get(tag, [])]
        for row in track:
            v = row["s" + tag].get("ta")
            n = sum(max(0, a - b) for a, b in zip(prev, v)) if (prev is not None and v is not None) else 0
            out["launches"] += n
            prev = v
            to = [b - a for a, b in zip(row[tag][:3], row[o][:3])]
            tr = row["s" + tag].get("tr") if aft else None
            series.append((row["t"], _ang(row[tag][3:6], to), tr, n, math.sqrt(sum(x * x for x in to))))
        _torpedo_geometry(series, aft, out)

    # behaviour
    if track and "beh" in track[0]:
        for tag in "AT":
            who = {d["attacker_name"], "Attacker"} if tag == "A" else {d["target_name"], "Target"}
            c = collections.Counter()
            for row in track:
                mods = {k.split("|")[1] for k in row.get("beh", {}) if k.split("|")[0] in who}
                for x in mods:
                    c[x] += 1
            ships[tag_role[tag]]["behaviour"] = {k: round(v / len(track), 4) for k, v in c.items()}

    # curves: per-sample shields/hull (new files) else the allhits before-values as steps
    for tag in "AT":
        pts = [(row["t"], row["s" + tag]["sh"], row["s" + tag]["hu"]) for row in track
               if "sh" in row["s" + tag] and "hu" in row["s" + tag]]
        if not pts:
            nm = {d["attacker_name"], "Attacker"} if tag == "A" else {d["target_name"], "Target"}
            pts = [(h[0], h[5], h[6]) for h in d.get("allhits") or [] if h[2] in nm]
        ships[tag_role[tag]]["curve"] = _curve(pts, t_end)

    return dict(schema=SCHEMA, source="dn", file=_name(path), enemy=d["enemy"], player=d["player"],
                level=float(d["level"]), angle=int(d["angle"]) if d.get("angle") is not None else None, winner=winner, winner_role=winner_role,
                ended=winner is not None,
                t_end=round(t_end, 3), attribution="exact", ships=ships)


# ------------------------------------------------------------------------------------------- api
def load_json(path):
    """A capture, plain or gzip-compressed (<name>.json.gz: how the Mac stores the bulk matrices)."""
    import gzip
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    with open(path) as fh:
        return json.load(fh)


def summarize(path):
    m = RX.search(os.path.basename(path))
    if m:
        meta = {"enemy": m.group(1), "player": m.group(3), "level": float(m.group(2)), "angle": int(m.group(6))}
    else:
        m = RX_HUMAN.search(os.path.basename(path))
        if not m:
            return None
        meta = {"enemy": m.group(1), "player": m.group(3), "level": float(m.group(2)), "angle": None}
    try:
        d = load_json(path)
    except Exception:
        return None
    if "raw_rows" in d:
        if not (d.get("params") or {}).get("duel") and not (d.get("meta") or {}).get("in_duel") == "1":
            return None
        return _summarize_orig(d, path, meta)
    if "allhits" in d and "track" in d:
        return _summarize_dn(d, path, meta)
    return None


CACHE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results_mac", "summary_cache")


def cached_summary(path, cache_dir=None):
    """summarize() with a JSON cache, rebuilt when the capture or this module is newer. The cache
    lives under results_mac/summary_cache/<capture dir>/ -- never beside the captures, where the
    duel_*.json globs of the other reports would pick it up."""
    if cache_dir is None:
        # keyed by the capture folder's full path: the Mac's and the Windows PC's results both live in
        # folders called duels_ai with identical file names
        import hashlib
        parent = os.path.dirname(os.path.abspath(path))
        cache_dir = os.path.join(CACHE_ROOT, "%s-%s" % (os.path.basename(parent),
                                                        hashlib.sha1(parent.encode()).hexdigest()[:8]))
    os.makedirs(cache_dir, exist_ok=True)
    base = os.path.basename(path)
    base = base[:-8] if base.endswith(".json.gz") else base[:-5]
    cpath = os.path.join(cache_dir, base + ".summary.json")
    mine = os.path.getmtime(__file__)
    try:
        if os.path.getmtime(cpath) >= max(os.path.getmtime(path), mine):
            s = json.load(open(cpath))
            if s.get("schema") == SCHEMA:
                return s
    except OSError:
        pass
    s = summarize(path)
    if s is not None:
        try:
            with open(cpath, "w") as fh:
                json.dump(s, fh)
        except OSError:
            pass
    return s


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(summarize(p), indent=1))

"""AI condition scripts, the original vs Dauntless: share of the fight each condition (class + first argument) is TRUE
(status 1), per (ship class, AI level, role). Ownership: a condition belongs to the ship whose AI node was registered
just before it (original: OracleAIProbe xr rows; Dauntless: dauntless_aim_duels cond_nodes, same rule).
usage: python compare_conditions.py"""
import glob, json, os, re, collections

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


BANDS = ((60, 80, "too-close band"), (115, 140, "too-far band"), (155, 175, "close band"), (210, 240, "mid band"),
         (380, 430, "long band"))
SELF = {"Player", "Target", "Attacker"}


def norm(cn, ca, owner):
    """FedAttack/NonFedAttack draw their range bands at random (SDK: Random(lo, hi) = rand(hi - lo) - lo): the
    original replays the same draws every launch, Dauntless draws afresh, so a threshold is keyed by its band; ship
    names become self / opponent."""
    try:
        v = float(ca)
        for lo, hi, nm in BANDS:
            if lo <= v <= hi:
                return "%s(%s)" % (cn, nm)
        return "%s(%g)" % (cn, v)
    except ValueError:
        pass
    if ca and (ca == owner or ca in SELF or re.match(r"^[A-Za-z]+-\d+$", ca)):
        return "%s(%s)" % (cn, "self" if ca == owner else "opponent")
    return "%s(%s)" % (cn, ca)


def _meta(path):
    m = re.search(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)", os.path.basename(path))
    return m.group(1), float(m.group(2)), m.group(3), float(m.group(4)), int(m.group(5))


def bc():
    pool, n = collections.defaultdict(collections.Counter), collections.Counter()
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*.json")):
        enemy, el, player, pl, a = _meta(f)
        rr = json.load(open(f))["raw_rows"]
        owner, reg = "?", []
        for l in rr:
            if l.startswith("xr a "):
                owner = l.split()[4]
            elif l.startswith("xr c "):
                p = l.split(" ", 4)
                reg.append((owner, p[3], p[4] if len(p) > 4 else ""))
        if not reg:
            continue
        dying = min([float(l.split()[2][2:]) for l in rr if l.startswith("xz ") and " dy=1" in l] or [1e9])
        rows = collections.defaultdict(dict)
        for l in rr:
            if l.startswith("xk "):
                p = l.split()
                rows[float(p[1][2:])][int(p[2][2:])] = p[3][2:]
        for t, ch in rows.items():
            if t >= dying:
                continue
            digits = "".join(ch[k] for k in sorted(ch))
            seen = collections.defaultdict(set)
            ow_of = {}
            for i, dg in enumerate(digits):
                if i < len(reg):
                    ow, cn, ca = reg[i]
                    key = (player, pl, "player") if ow == "Player" else (enemy, el, "enemy")
                    seen[key].add((cn, ca, dg == "1"))
                    ow_of[(cn, ca)] = ow
            for key, items in seen.items():
                n[key] += 1
                done = set()
                for cn, ca, tr in items:
                    k = norm(cn, ca, ow_of.get((cn, ca), "?"))
                    if tr and k not in done:
                        pool[key][k] += 1
                        done.add(k)
                    pool[key].setdefault(k, pool[key].get(k, 0))
    return pool, n


def dauntless():
    pool, n = collections.defaultdict(collections.Counter), collections.Counter()
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        if "cond_nodes" not in d:
            continue
        roles = {d["attacker_name"]: (d["enemy"], d["level"], "enemy"), d["target_name"]: (d["player"], d["level"], "player")}
        for row in d["track"]:
            cs = row.get("cond", "")
            seen = collections.defaultdict(set)
            for i, (ow, cn, ca) in enumerate(d["cond_nodes"]):
                if i < len(cs) and ow in roles:
                    seen[roles[ow]].add((norm(cn, ca[:40], ow), cs[i] == "1"))
            for key, items in seen.items():
                n[key] += 1
                done = set()
                for k, tr in items:
                    if tr and k not in done:
                        pool[key][k] += 1
                        done.add(k)
                    pool[key].setdefault(k, pool[key].get(k, 0))
    return pool, n


if __name__ == "__main__":
    B, nb = bc()
    D, nd = dauntless()
    for key in sorted(set(B) | set(D)):
        if not nb[key] or not nd[key]:
            continue
        print("== %s AI %.1f as %s  (original %d samples | Dauntless %d samples)  share of samples TRUE" % (key[0], key[1], key[2], nb[key], nd[key]))
        for k in sorted(set(B[key]) | set(D[key]), key=lambda k: -abs(B[key][k] / nb[key] - D[key][k] / nd[key])):
            b, d = 100.0 * B[key][k] / nb[key], 100.0 * D[key][k] / nd[key]
            if max(b, d) >= 1.0:
                print("   %-58s original %5.1f%%   Dauntless %5.1f%%%s" % (k[:58], b, d, "  <<" if abs(b - d) >= 10 else ""))

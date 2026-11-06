"""The stock AI's decision tree, the original vs Dauntless: share of the fight each named node has focus.

Original: results_mac/duels_ai/*.json (and any duel with the --ai-probe tree rows): `xr a` registry + `xy` focus bits
(+ `xv` IsActive). Dauntless: scorecard/dauntless_aim_duels/*.json `tree_nodes` + per-sample `tree` (focus, active).
A node name can occur more than once in a tree; a name counts as focused in a sample if any node of that name has
focus. Pooled per (ship class, AI level, role); sampled until the first death.
usage: python compare_tree.py [--active] [--min 2.0]
"""
import glob, json, os, re, sys, collections

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _meta(path):
    m = re.search(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)", os.path.basename(path))
    return m.group(1), float(m.group(2)), m.group(3), float(m.group(4)), int(m.group(5))


def bc(use_active=False):
    pool = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    files = sorted(set(glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*.json"))))
    for f in files:
        if any(x in f for x in (".aim", "aimbank", "decisions")):
            continue
        enemy, el, player, pl, a = _meta(f)
        d = json.load(open(f))
        rr = d["raw_rows"]
        reg = collections.defaultdict(list)
        for l in rr:
            if l.startswith("xr a "):
                p = l.split(" ", 5)
                reg[p[4]].append((p[3], p[5] if len(p) > 5 else "?"))
        if not reg:
            continue
        dying = min([float(l.split()[2][2:]) for l in rr if l.startswith("xz ") and " dy=1" in l] or [1e9])
        kind = "xv " if use_active else "xy "
        rows = collections.defaultdict(dict)
        for l in rr:
            if l.startswith(kind):
                p = l.split()
                rows[(p[1], float(p[2][2:]))][int(p[3][2:])] = p[4][2:]
        for (ship, t), chunks in rows.items():
            if t >= dying:
                continue
            bits = "".join(chunks[k] for k in sorted(chunks))
            key = (player, pl, "player") if ship == "Player" else (enemy, el, "enemy")
            names = set()
            for i, b in enumerate(bits):
                if b == "1" and i < len(reg[ship]):
                    names.add("%s %s" % reg[ship][i])
            for nm in names:
                pool[key][nm] += 1
            n[key] += 1
    return pool, n


def dauntless(use_active=False):
    pool = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        if "tree_nodes" not in d:
            continue
        roles = {d["attacker_name"]: (d["enemy"], d["level"], "enemy"), d["target_name"]: (d["player"], d["level"], "player")}
        for row in d["track"]:
            tree = row.get("tree", "")
            per = collections.defaultdict(set)
            for i, (ship, kind, nm) in enumerate(d["tree_nodes"]):
                if 2 * i + 1 < len(tree) and tree[2 * i + (1 if use_active else 0)] == "1":
                    per[ship].add("%s %s" % (kind, nm))
            for ship, key in roles.items():
                for nm in per.get(ship, ()):
                    pool[key][nm] += 1
                n[key] += 1
    return pool, n


if __name__ == "__main__":
    act = "--active" in sys.argv
    mn = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 2.0
    B, nb = bc(act)
    D, nd = dauntless(act)
    for key in sorted(set(B) | set(D)):
        if not nb[key] or not nd[key]:
            continue
        print("== %s AI %.1f as %s  (original %d samples | Dauntless %d samples)  [%s]" % (
            key[0], key[1], key[2], nb[key], nd[key], "IsActive" if act else "HasFocus"))
        names = set(B[key]) | set(D[key])
        rows = []
        for nm in names:
            b = 100.0 * B[key][nm] / nb[key]
            d = 100.0 * D[key][nm] / nd[key]
            if max(b, d) >= mn:
                rows.append((-(max(b, d)), nm, b, d))
        for _, nm, b, d in sorted(rows):
            flag = "  <<" if abs(b - d) >= 10 else ""
            print("   %-48s original %5.1f%%   Dauntless %5.1f%%%s" % (nm[:48], b, d, flag))

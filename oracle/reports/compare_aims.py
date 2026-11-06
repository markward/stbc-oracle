"""Where the AI aims its phasers: the original (reconstructed, aim_bank.py -> *.aimbank.json, unambiguous hits only)
vs Dauntless (exact: the shooter's FireScript choice at each phaser hit, scorecard/dauntless_aim_duels/*.json).

Pooled by (shooter class, AI level); shares of phaser hits by aim category.
usage: python compare_aims.py   (from stbc-oracle)
"""
import glob, json, os, re, collections

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CATS = (("fwd tubes", r"^Forward_Torpedo"), ("aft tubes", r"^Aft_Torpedo"), ("dorsal banks", r"^Dorsal_Phaser"),
        ("ventral banks", r"^Ventral_Phaser"), ("tractors", r"Tractor"), ("shield gen", r"^Shield_Generator"),
        ("warp core", r"^Warp_Core"), ("engines", r"(Impulse|Warp)$|_Impulse$|_Warp$"), ("sensors", r"^Sensor"),
        ("bridge/hull", r"^(Bridge|Hull)$"), ("centre (none)", r"^-$"))


def cat(name):
    if name is None:
        return "?"
    for c, rx in CATS:
        if re.search(rx, name.split("+")[0]):
            return c
    return "other:" + name


def _meta(path):
    m = re.search(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)", os.path.basename(path))
    return m.group(1), float(m.group(2)), m.group(3), float(m.group(4)), int(m.group(5))


def bc():
    pool = collections.defaultdict(collections.Counter)
    n_duels = collections.Counter()
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_aim/*.aimbank.json")):
        enemy, el, player, pl, a = _meta(f)
        cls = {"A": (enemy, el), "T": (player, pl)}
        seen = set()
        for r in json.load(open(f)):
            if r["miss"] < 0.1 and r["margin"] > 0.1:
                key = cls[r["shooter"]]
                pool[key][cat(r["chosen"])] += 1
                seen.add(key)
        for k in seen:
            n_duels[k] += 1
    return pool, n_duels


def dauntless():
    pool = collections.defaultdict(collections.Counter)
    n_duels = collections.Counter()
    for f in glob.glob(os.path.join(ROOT, "scorecard/dauntless_aim_duels/*.json")):
        d = json.load(open(f))
        cls = {d["attacker_name"]: (d["enemy"], d["level"]), d["target_name"]: (d["player"], d["level"])}
        seen = set()
        for h in d["hits"]:
            key = cls.get(h["shooter"])
            if key is None:
                continue
            pool[key][cat(h["aim"])] += 1
            seen.add(key)
        for k in seen:
            n_duels[k] += 1
    return pool, n_duels


def shares(c):
    n = sum(c.values()) or 1
    return {k: 100.0 * v / n for k, v in c.items()}, n


if __name__ == "__main__":
    B, nb = bc()
    D, nd = dauntless()
    cats = [c for c, _ in CATS] + ["?"]
    for key in sorted(set(B) | set(D)):
        sb, b_n = shares(B.get(key, collections.Counter()))
        sd, d_n = shares(D.get(key, collections.Counter()))
        print("== %s AI %.1f shooting  (original: %d aims from %d duels | Dauntless: %d hits from %d duels)" % (
            key[0], key[1], b_n, nb[key], d_n, nd[key]))
        extra = sorted(set(sb) | set(sd))
        for c in cats + [x for x in extra if x not in cats]:
            if c in sb or c in sd:
                print("   %-16s original %5.1f%%   Dauntless %5.1f%%" % (c, sb.get(c, 0.0), sd.get(c, 0.0)))

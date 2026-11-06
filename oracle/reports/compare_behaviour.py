"""Which movement behaviour (PlainAI script) actually RUNS, the original vs Dauntless: share of 0.25 s samples in which
each script's Update ran at least once (original: OracleAIProbe xa rows; Dauntless: dauntless_aim_duels track 'beh').
Pooled per (ship class, AI level, role), up to the first death.  usage: python compare_behaviour.py"""
import glob, json, os, re, collections

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _meta(path):
    m = re.search(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)", os.path.basename(path))
    return m.group(1), float(m.group(2)), m.group(3), float(m.group(4)), int(m.group(5))


def bc():
    pool, n = collections.defaultdict(collections.Counter), collections.Counter()
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*.json")):
        enemy, el, player, pl, a = _meta(f)
        rr = json.load(open(f))["raw_rows"]
        dying = min([float(l.split()[2][2:]) for l in rr if l.startswith("xz ") and " dy=1" in l] or [1e9])
        ts = sorted({round(float(l.split()[2][2:]), 3) for l in rr if l.startswith("xm A ")})
        ts = [t for t in ts if t < dying]
        ran = collections.defaultdict(set)
        for l in rr:
            if l.startswith("xa ") and " a=" in l:
                p = l.split()
                t = round(float(p[2][2:]), 3)
                for kv in p[3][2:].split(","):
                    if ":" in kv:
                        ran[(p[1], t)].add(kv.split(":")[0])
        if not ran:
            continue
        for ship, key in (("Player", (player, pl, "player")), (None, (enemy, el, "enemy"))):
            for t in ts:
                names = set()
                for (sh, tt), mods in ran.items():
                    if tt == t and ((ship and sh == ship) or (not ship and sh != "Player")):
                        names |= mods
                for m in names:
                    pool[key][m] += 1
                n[key] += 1
    return pool, n


def dauntless():
    pool, n = collections.defaultdict(collections.Counter), collections.Counter()
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        roles = {d["attacker_name"]: (d["enemy"], d["level"], "enemy"), d["target_name"]: (d["player"], d["level"], "player")}
        for row in d.get("track", []):
            if "beh" not in row:
                break
            per = collections.defaultdict(set)
            for k in row["beh"]:
                sh, m = k.split("|")
                per[sh].add(m)
            for sh, key in roles.items():
                for m in per.get(sh, ()):
                    pool[key][m] += 1
                n[key] += 1
    return pool, n


if __name__ == "__main__":
    B, nb = bc()
    D, nd = dauntless()
    for key in sorted(set(B) | set(D)):
        if not nb[key] or not nd[key]:
            continue
        print("== %s AI %.1f as %s  (original %d samples | Dauntless %d samples)" % (key[0], key[1], key[2], nb[key], nd[key]))
        for m in sorted(set(B[key]) | set(D[key]), key=lambda m: -max(B[key][m] / nb[key], D[key][m] / nd[key])):
            b, d = 100.0 * B[key][m] / nb[key], 100.0 * D[key][m] / nd[key]
            print("   %-26s original %5.1f%%   Dauntless %5.1f%%%s" % (m, b, d, "  <<" if abs(b - d) >= 10 else ""))

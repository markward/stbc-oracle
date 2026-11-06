"""Who wins, and how fast: the original's AI duels vs Dauntless's, per (attacker, target, AI level).
Original: every results_mac/duels*/duel_*.json with a duel_over boot mark. Dauntless: scorecard/dauntless_aim_duels.
usage: python compare_outcomes.py"""
import glob, json, os, re, collections

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RX = re.compile(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)")


def bc():
    out = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels*/duel_*.json")):
        if any(x in f for x in (".aim", "aimbank", "decisions", "probe")):
            continue
        m = RX.search(os.path.basename(f))
        if not m:
            continue
        try:
            boot = json.load(open(f)).get("boot") or {}
        except Exception:
            continue
        over = [v for k, v in boot.items() if k.endswith("duel_over")]
        if not over:
            out[(m.group(1), m.group(3), float(m.group(2)))].append(("none", 600.0))
            continue
        v = over[0]
        t = float(re.search(r"t=([\d.]+)", v).group(1))
        a = re.search(r"attacker_dying=(\d)", v).group(1) == "1"
        tg = re.search(r"target_dying=(\d)", v).group(1) == "1"
        w = m.group(3) if a and not tg else (m.group(1) if tg and not a else "both")
        out[(m.group(1), m.group(3), float(m.group(2)))].append((w, t))
    return out


def dauntless():
    out = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        out[(d["enemy"], d["player"], float(d["level"]))].append((d.get("winner") or "none", float(d["t_end"])))
    return out


def summary(v):
    wins = collections.Counter(w for w, _ in v)
    ts = sorted(t for w, t in v if w not in ("none",))
    med = ts[len(ts) // 2] if ts else float("nan")
    return "%s  median %.0f s" % (", ".join("%s %d" % kv for kv in wins.most_common()), med)


if __name__ == "__main__":
    B, D = bc(), dauntless()
    for k in sorted(set(B) | set(D)):
        print("%-11s (enemy) vs %-11s AI %.1f | original: %-40s | Dauntless: %s" % (
            k[0], k[1], k[2], summary(B.get(k, [])) if k in B else "-", summary(D.get(k, [])) if k in D else "-"))

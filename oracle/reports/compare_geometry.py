"""AI manoeuvring, the original vs Dauntless: where each ship spends the fight relative to its opponent.

Original: results_mac/duels_aim/*.json telemetry (xm position, xo forward/up). Dauntless:
scorecard/dauntless_aim_duels/*.json `track` (pose of both ships every 0.25 s). Per (ship class, AI level), time
shares of: range band, the opponent's bearing in this ship's frame (is it in front / beside / behind us, above / below),
and the time this ship has the opponent within 30 degrees of its nose. Sampled up to the first death.
usage: python compare_geometry.py   (from stbc-oracle)
"""
import glob, json, math, os, re, collections, sys

sys.path.insert(0, os.path.dirname(__file__))
import aim_reconstruct as AR

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RANGES = ((0, 10), (10, 25), (25, 50), (50, 100), (100, 1e9))


def _meta(path):
    m = re.search(r"duel_(\w+?)_enemy([\d.]+)_vs_(\w+?)_player([\d.]+)_r100_a(\d+)", os.path.basename(path))
    return m.group(1), float(m.group(2)), m.group(3), float(m.group(4)), int(m.group(5))


def rel(p_self, fw, up, p_other):
    """Opponent in this ship's frame: range, azimuth (0 nose, 90 starboard), elevation."""
    fw, up = AR.norm(fw), AR.norm(up)
    right = AR.cross(fw, up)
    d = AR.sub(p_other, p_self)
    x, y, z = AR.dot(d, right), AR.dot(d, fw), AR.dot(d, up)
    r = math.sqrt(x * x + y * y + z * z) or 1e-9
    return r, math.degrees(math.atan2(x, y)) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, z / r))))


def bins(samples):
    """samples: [(range, az, el)] -> dict of time shares (%)."""
    n = len(samples) or 1
    out = collections.OrderedDict()
    for lo, hi in RANGES:
        out["range %g-%s" % (lo, "" if hi > 1e8 else "%g" % hi)] = 100.0 * sum(1 for r, a, e in samples if lo <= r < hi) / n
    sec = lambda a: "front" if a < 45 or a >= 315 else ("behind" if 135 <= a < 225 else "beside")
    for s in ("front", "beside", "behind"):
        out["opponent " + s] = 100.0 * sum(1 for r, a, e in samples if sec(a) == s) / n
    out["opponent above (>20)"] = 100.0 * sum(1 for r, a, e in samples if e > 20) / n
    out["opponent below (<-20)"] = 100.0 * sum(1 for r, a, e in samples if e < -20) / n
    out["opponent in 30deg nose cone"] = 100.0 * sum(1 for r, a, e in samples
                                                     if math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(a)) * math.cos(math.radians(e)))))) < 30) / n
    out["median range"] = sorted(r for r, a, e in samples)[len(samples) // 2] if samples else 0.0
    return out


def bc_samples():
    pool = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_aim/duel_*_a*.json")):
        if any(x in f for x in (".aim", "aimbank", "decisions")):
            continue
        enemy, el, player, pl, a = _meta(f)
        d = json.load(open(f))
        cls = {"A": (enemy, el), "T": (player, pl)}
        xm = {t: AR.telemetry(d["raw_rows"], "xm", t) for t in "AT"}
        xo = {t: AR.telemetry(d["raw_rows"], "xo", t) for t in "AT"}
        dying = min([float(l.split()[2][2:]) for l in d["raw_rows"] if l.startswith("xz ") and " dy=1" in l] or [1e9])
        for tag in "AT":
            o = "T" if tag == "A" else "A"
            om = {round(t, 2): kv for t, kv in xm[o]}
            oo = {round(t, 2): kv for t, kv in xo[tag]}
            for t, kv in xm[tag]:
                if t >= dying:
                    break
                k = round(t, 2)
                if k in om and k in oo:
                    pool[cls[tag]].append(rel(AR.vec(kv["p"]), AR.vec(oo[k]["fw"]), AR.vec(oo[k]["up"]), AR.vec(om[k]["p"])))
    return pool


def dauntless_samples():
    pool = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        if "track" not in d:
            continue
        cls = {"A": (d["enemy"], d["level"]), "T": (d["player"], d["level"])}
        for row in d["track"]:
            for tag in "AT":
                o = "T" if tag == "A" else "A"
                s, other = row[tag], row[o]
                pool[cls[tag]].append(rel(s[0:3], s[3:6], s[6:9], other[0:3]))
    return pool


if __name__ == "__main__":
    B, D = bc_samples(), dauntless_samples()
    for key in sorted(set(B) | set(D)):
        b, d = bins(B.get(key, [])), bins(D.get(key, []))
        print("== %s AI %.1f  (original %d samples | Dauntless %d samples)" % (key[0], key[1], len(B.get(key, [])), len(D.get(key, []))))
        for k in b:
            print("   %-30s original %6.1f   Dauntless %6.1f" % (k, b[k], d[k]))

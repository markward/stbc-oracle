"""Fight geometry split by the movement behaviour running at the time, the original vs Dauntless.
Original: results_mac/duels_ai (xa rows: PlainAI Update counts per 0.25 s; xm/xo poses). Dauntless:
scorecard/dauntless_aim_duels track (beh, poses) or DAUNTLESS_DUELS=<dir>. Per (class, level, behaviour): share of
samples, median range, opponent above/below (|elevation| > 20 deg), opponent in the 30 deg nose cone.
usage: python compare_geometry_by_behaviour.py <class> [level]"""
import collections, glob, json, math, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import aim_reconstruct as AR
import compare_geometry as G

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def bc(cls, lv):
    pool = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, "results_mac/duels_ai/duel_*_a*.json")):
        if "probe" in f:
            continue
        enemy, el, player, pl, a = G._meta(f)
        rr = json.load(open(f))["raw_rows"]
        tags = [t for t, c in (("A", (enemy, el)), ("T", (player, pl))) if c == (cls, lv)]
        if not tags:
            continue
        dying = min([float(l.split()[2][2:]) for l in rr if l.startswith("xz ") and " dy=1" in l] or [1e9])
        xm = {t: {round(tt, 2): kv for tt, kv in AR.telemetry(rr, "xm", t)} for t in "AT"}
        xo = {t: {round(tt, 2): kv for tt, kv in AR.telemetry(rr, "xo", t)} for t in "AT"}
        ran = collections.defaultdict(set)
        for l in rr:
            if l.startswith("xa ") and " a=" in l:
                p = l.split()
                for kv in p[3][2:].split(","):
                    if ":" in kv:
                        ran[("T" if p[1] == "Player" else "A", round(float(p[2][2:]), 2))].add(kv.split(":")[0])
        for tag in tags:
            o = "T" if tag == "A" else "A"
            for t, kv in xm[tag].items():
                if t >= dying or t not in xm[o] or t not in xo[tag]:
                    continue
                g = G.rel(AR.vec(kv["p"]), AR.vec(xo[tag][t]["fw"]), AR.vec(xo[tag][t]["up"]), AR.vec(xm[o][t]["p"]))
                for b in (ran.get((tag, t)) or {"(none)"}):
                    pool[b].append(g)
    return pool


def dauntless(cls, lv):
    pool = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, os.environ.get("DAUNTLESS_DUELS", "scorecard/dauntless_aim_duels") + "/*.json")):
        d = json.load(open(f))
        tags = [t for t, c in (("A", d["enemy"]), ("T", d["player"])) if c == cls and float(d["level"]) == lv]
        names = {"A": d.get("attacker_name"), "T": d.get("target_name")}
        for row in d.get("track") or []:
            for tag in tags:
                o = "T" if tag == "A" else "A"
                s, other = row[tag], row[o]
                g = G.rel(s[0:3], s[3:6], s[6:9], other[0:3])
                bs = {k.split("|")[1] for k in (row.get("beh") or {}) if k.split("|")[0] == names[tag]}
                for b in (bs or {"(none)"}):
                    pool[b].append(g)
    return pool


def stats(v):
    n = len(v)
    if not n:
        return "-"
    rng = sorted(r for r, a, e in v)[n // 2]
    up = 100.0 * sum(1 for r, a, e in v if e > 20) / n
    dn = 100.0 * sum(1 for r, a, e in v if e < -20) / n
    nose = 100.0 * sum(1 for r, a, e in v if math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(a)) * math.cos(math.radians(e)))))) < 30) / n
    return "n %5d  range %5.0f  above %4.0f%%  below %4.0f%%  nose %4.0f%%" % (n, rng, up, dn, nose)


if __name__ == "__main__":
    cls = sys.argv[1]
    lv = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    B, D = bc(cls, lv), dauntless(cls, lv)
    for b in sorted(set(B) | set(D), key=lambda k: -len(B.get(k, []))):
        print("%-24s original %s\n%-24s Dauntless %s" % (b, stats(B.get(b, [])), "", stats(D.get(b, []))))

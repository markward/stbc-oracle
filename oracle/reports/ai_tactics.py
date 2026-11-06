"""AI behaviour in the oracle duels (both AIs at difficulty 0.5): range kept, throttle, phaser/torpedo use,
torpedo type switching, tractor use, targeting. Per ship class, pooled over all duels."""
import sys, json, glob, re, math, collections
sys.path.insert(0, ".")
from common import xrows

def P(s): return [float(x) for x in s.split(",")]

files = sys.argv[1:] or (sorted(glob.glob("../../results_mac/duel_*_enemy_vs_*.json")) + sorted(glob.glob("../../results_mac/duels/*.json")))
stats = collections.defaultdict(lambda: collections.defaultdict(list))
for f in files:
    r = json.load(open(f))
    fl = r["params"].get("friendly_ai_level", -1.0); el = r["params"].get("ai_level", 0.5)
    fl = el if fl is None or float(fl) < 0 else float(fl)
    cls = {"A": f'{r["params"]["attacker"]} AI {float(el):.1f}', "T": f'{r["params"]["target"]} AI {fl:.1f}'}
    pos = {tag: {round(x["t"], 2): P(x["p"]) for x in xrows(r, "xm", tag)} for tag in "AT"}
    for tag in "AT":
        c = cls[tag]
        prev_am, prev_ta = None, None
        for l in r["raw_rows"]:
            if not l.startswith(f"xz {tag} "):
                continue
            kv = dict(x.split("=", 1) for x in l.split()[2:] if "=" in x)
            t = round(float(l.split()[2][2:]), 2)
            if kv.get("dy", "0/0").startswith("1"):
                break
            o = "T" if tag == "A" else "A"
            if t in pos[tag] and t in pos[o]:
                rng = math.dist(pos[tag][t], pos[o][t])
            else:
                continue
            st = stats[c]
            st["range"].append(rng)
            st["imp"].append(float(kv.get("imp", "0")))
            pf = kv.get("pf", "0/0").split("/"); tf = kv.get("tf", "0/0").split("/")
            st["phaser_firing"].append((rng, pf[0] == "1"))
            st["phaser_trying"].append(pf[1] == "1")
            st["ppl"].append(kv.get("ppl"))
            st["tsub"].append(kv.get("tsub"))
            st["tractor"].append(kv.get("tm", "0/0").split("/")[1] == "1")
            am = kv.get("am"); ta = kv.get("ta", "")
            if prev_am is not None and am != prev_am:
                st["switch"].append((t, rng, prev_am, am, ta))
            if prev_ta is not None and ta != prev_ta:
                a0 = [int(x) for x in prev_ta.split("/") if x.lstrip("-").isdigit()]
                a1 = [int(x) for x in ta.split("/") if x.lstrip("-").isdigit()]
                for i, (x0, x1) in enumerate(zip(a0, a1)):
                    if x1 < x0:
                        st["torp_fired"].append((rng, i, x0 - x1))
            prev_am, prev_ta = am, ta

def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))]

for c, st in stats.items():
    R = st["range"]
    print(f"===== {c} AI ({len(R)} samples at 0.25 s ≈ {len(R)/4/60:.0f} min of fighting)")
    print(f"  range kept: median {pct(R, .5):.0f} GU, 10–90% {pct(R, .1):.0f}–{pct(R, .9):.0f}; share of time <60 GU {sum(x < 60 for x in R)/len(R):.0%}, 60–150 {sum(60 <= x < 150 for x in R)/len(R):.0%}, >150 {sum(x >= 150 for x in R)/len(R):.0%}")
    imp = st["imp"]
    print(f"  throttle: median {pct(imp, .5):.2f}, share at ≥0.99 {sum(x >= .99 for x in imp)/len(imp):.0%}, share at 0 {sum(x == 0 for x in imp)/len(imp):.0%}")
    pfr = st["phaser_firing"]
    for lo, hi in ((0, 60), (60, 150), (150, 1e9)):
        sel = [f for r_, f in pfr if lo <= r_ < hi]
        if sel:
            print(f"  phasers firing {sum(sel)/len(sel):.0%} of the time at {lo}–{hi if hi < 1e9 else '∞'} GU ({len(sel)} samples)")
    print(f"  phaser level: {collections.Counter(st['ppl']).most_common()}  (0 Low, 1 Medium, 2 High)")
    print(f"  target subsystem: {collections.Counter(st['tsub']).most_common(4)}")
    print(f"  tractor in use: {sum(st['tractor'])/len(st['tractor']):.1%} of samples")
    tf = st["torp_fired"]
    if tf:
        by = collections.Counter(i for _, i, _ in tf)
        print(f"  torpedoes fired by type (0 photon, 1 quantum): {dict(by)}; launch range median {pct([r_ for r_, _, _ in tf], .5):.0f} GU, 10–90% {pct([r_ for r_, _, _ in tf], .1):.0f}–{pct([r_ for r_, _, _ in tf], .9):.0f}")
    sw = st["switch"]
    if sw:
        print(f"  torpedo type switches: {len(sw)} ({len(sw)/len(files)*2:.1f} per duel side); at range median {pct([x[1] for x in sw], .5):.0f} GU; examples {[(round(x[1]), x[2] + '→' + x[3], x[4]) for x in sw[:6]]}")

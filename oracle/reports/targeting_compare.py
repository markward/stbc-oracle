"""AI targeting, original game vs Dauntless, from what the AI's fire does to the losing Galaxy:
share of each subsystem's HP lost before death, order in which subsystems become disabled, time to the first
disabled weapon. Grouped by the AI level of the ship shooting at the Galaxy (the Sovereign)."""
import sys, json, glob, re, collections, statistics
sys.path.insert(0, ".")
from common import chunked, sub_names

CAT = json.load(open("../../results_mac/catalogue_galaxy_sovereign.json"))
DP = {}
_n = {}
for l in CAT["raw_rows"]:
    p = l.split(" ", 3)
    if p[0] == "cs" and p[1] == "T":
        _n[p[2]] = dict(x.split("=", 1) for x in p[3].split())["name"]
for l in CAT["raw_rows"]:
    p = l.split(" ", 3)
    if p[0] == "cp" and p[1] == "T" and p[3].startswith("SubsystemProperty.GetDisabledPercentage="):
        DP[_n[p[2]]] = float(p[3].split("=")[1])
WEAPON = re.compile(r"Phaser_|Torpedo_|Tractor_")


def summarise(series, names, maxc, dps):
    """series: list of (t, [conditions]) for the Galaxy up to its death."""
    t0 = series[0][0]
    first, last = series[0][1], series[-1][1]
    lost = {n: (first[i] - last[i]) / maxc[i] for i, n in enumerate(names) if maxc[i] > 0 and n != "Hull"}
    order, seen = [], set()
    for t, c in series:
        for i, n in enumerate(names):
            if n in seen or n == "Hull" or maxc[i] <= 0 or dps[i] <= 0:
                continue
            if c[i] < dps[i] * maxc[i]:
                seen.add(n); order.append((round(t - t0, 1), n))
    first_w = next((t for t, n in order if WEAPON.search(n)), None)
    return lost, order, first_w


def bc_cases():
    files = sorted(glob.glob("../../results_mac/duel_*_enemy_vs_*.json")) + sorted(glob.glob("../../results_mac/duels/*.json")) + \
        sorted(glob.glob("../../results_mac/duels_high/*.json"))
    for f in files:
        r = json.load(open(f))
        tag = "A" if r["params"]["attacker"] == "Galaxy" else "T"
        el = float(r["params"].get("ai_level", 0.5))
        fl = r["params"].get("friendly_ai_level", -1.0)
        fl = el if fl is None or float(fl) < 0 else float(fl)
        shooter = fl if tag == "A" else el            # the Sovereign's level
        dy = None
        for l in r["raw_rows"]:
            if l.startswith(f"xz {tag} ") and " dy=1/" in l:
                dy = float(re.search(r"t=([\d.]+)", l).group(1)); break
        nm = sub_names(r, tag); c = chunked(r, "xc", tag, "c"); ts = sorted(c)
        series = [(t, [float(x) for x in c[t]]) for t in ts if dy is None or t < dy - 0.3]
        if len(series) < 10:
            continue
        maxc = series[0][1]
        yield shooter, nm, maxc, [DP.get(n, 0.0) for n in nm], series


def da_cases():
    for f in sorted(glob.glob("../../scorecard/dauntless_duels/*.json")):
        d = json.load(open(f))
        tag = "A" if d["enemy"] == "Galaxy" else "T"
        shooter = d["player_level"] if tag == "A" else d["enemy_level"]
        nm = d["names"][tag]; maxc = d["max"][tag]
        series = [(x["t"], x[tag]) for x in d["samples"]][:-1]
        dps = [DP.get(n, 0.0) for n in nm]       # judge "disabled" by the real thresholds in both games
        yield shooter, nm, maxc, dps, series


def report(cases, label):
    groups = collections.defaultdict(list)
    for shooter, nm, maxc, dps, series in cases:
        groups[shooter].append(summarise(series, nm, maxc, dps))
    out = {}
    for lvl in sorted(groups):
        g = groups[lvl]
        lost = collections.Counter()
        for l, o, fw in g:
            for k, v in l.items():
                lost[k] += v / len(g)
        firsts = collections.Counter(n for l, o, fw in g for (t, n) in o[:3])
        fw = [x for l, o, x in g if x is not None]
        out[lvl] = dict(n=len(g), lost=lost, firsts=firsts, first_w=statistics.median(fw) if fw else None)
        print(f"== {label}, Sovereign AI {lvl}: {len(g)} duels")
        print("   most HP lost: " + ", ".join(f"{k} {100*v:.0f}%" for k, v in lost.most_common(8)))
        print("   among the first 3 disabled: " + ", ".join(f"{k} ×{v}" for k, v in firsts.most_common(8)))
        print(f"   first weapon disabled after (median): {out[lvl]['first_w']} s")
    return out


if __name__ == "__main__":
    bc = report(bc_cases(), "Original game")
    da = report(da_cases(), "Dauntless")
    json.dump({"bc": {str(k): dict(n=v["n"], lost=dict(v["lost"]), firsts=dict(v["firsts"]), first_w=v["first_w"]) for k, v in bc.items()},
               "da": {str(k): dict(n=v["n"], lost=dict(v["lost"]), firsts=dict(v["firsts"]), first_w=v["first_w"]) for k, v in da.items()}},
              open("../../scorecard/targeting_compare.json", "w"))

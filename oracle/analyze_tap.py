"""Reduce CombatTap records: per damage event, impact point, subsystems damaged, and a check of
the footprint rule  hit(sub) <=> |impact - sub.pos| < sub.radius + weapon_radius  (hull always).

    python oracle/analyze_tap.py results_mac/sweep/*.json [--events]
"""
import json
import math
import re
import sys
from pathlib import Path


def load(path):
    r = json.load(open(path))
    subs = [s for s in r["subsystems"] if s.get("ptr")]
    byptr = {s["ptr"].upper().lstrip("0"): s for s in subs}
    events, cur = [], None
    for line in r.get("combat_tap", []):
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        t, kind = float(parts[0]), parts[1]
        kv = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
        if kind == "DS":
            cur = {"t": t, "pos": [float(x) for x in kv["pos"].split(",")], "dmg": float(kv["dmg"]),
                   "r": float(kv["r"]), "hits": {}}
            events.append(cur)
        elif kind == "W" and cur is not None:
            s = byptr.get(kv["sub"].lstrip("0"))
            if s:
                cur["hits"][s["name"]] = float(kv["dmg"])
        elif kind == "ds":
            cur = None
    return r, subs, events


# Subsystems the game marks IsTargetable()==0 (group parents, repair/engineering) are never
# damaged by weapons.  Names come from a catalogue run (OracleCatalogue), per ship class.
CATALOGUE = Path(__file__).resolve().parent.parent / "results_mac" / "catalogue_galaxy_sovereign.json"


def untargetable():
    out = set()
    if CATALOGUE.exists():
        rows = json.load(open(CATALOGUE))["raw_rows"]
        names = {}
        for l in rows:
            p = l.split(" ", 3)
            if p[0] == "cs":
                kv = dict(x.split("=", 1) for x in p[3].split())
                names[(p[1], p[2])] = kv["name"].replace("_", " ")
        for l in rows:
            p = l.split(" ", 3)
            if p[0] == "cp" and p[3] == "SubsystemProperty.IsTargetable=0":
                out.add(names[(p[1], p[2])])
    return out


PARENTS = untargetable()


def check(subs, ev):
    """Predicted vs actual set of damaged subsystems.  Group parents are excluded from the
    prediction and reported if they are ever damaged."""
    pred = set()
    for s in subs:
        if s["name"] in PARENTS:
            continue
        if s["name"] == "Hull":
            pred.add("Hull")
            continue
        if not s.get("pos"):
            continue
        d = math.dist(ev["pos"], s["pos"])
        if d < s["radius"] + ev["r"]:
            pred.add(s["name"])
    act = set(ev["hits"])
    return pred, act


def main(paths, show):
    tot = ok = 0
    for p in paths:
        r, subs, events = load(p)
        name = Path(p).stem
        if not events:
            print(f"{name}: no damage events")
            continue
        pts = sorted({tuple(round(x, 2) for x in e["pos"]) for e in events})
        print(f"{name}: {len(events)} damage events, impact points {pts[:4]}{' ...' if len(pts) > 4 else ''}")
        for e in events:
            pred, act = check(subs, e)
            tot += 1
            ok += pred == act
            if show or pred != act:
                print(f"   t={e['t']:.2f} pos={[round(x, 3) for x in e['pos']]} r={e['r']} dmg={e['dmg']:.1f}")
                print(f"      damaged: {sorted(act)}")
                if pred != act:
                    print(f"      RULE MISMATCH predicted-only={sorted(pred - act)} actual-only={sorted(act - pred)}")
    print(f"rule check: {ok}/{tot} damage events match the sphere-overlap rule")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args, "--events" in sys.argv)

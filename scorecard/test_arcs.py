"""A: firing arcs. The original game's own in-arc answers (catalogue ca rows: PhaserBank.CanHit,
TorpedoTube.IsInArc, tractor CanHit on a 5° sphere at r = 50 in the ship's model frame) replayed through
Dauntless's arc tests, with the ship at the origin and unrotated so model frame = world frame."""
import json
import math

import pytest

from conftest import CATALOGUE

STEP, R = 5, 50.0


def _maps(path=CATALOGUE):
    cat = json.loads(path.read_text())
    tagcls = {"A": cat["params"]["attacker"], "T": cat["params"]["target"]}
    names, maps = {}, {}
    for l in cat["raw_rows"]:
        p = l.split(" ", 3)
        if p[0] == "cs":
            names[(p[1], p[2])] = dict(x.split("=", 1) for x in p[3].split())["name"]
    for l in cat["raw_rows"]:
        p = l.split()
        if p[0] == "ca" and len(p) == 6 and p[4].startswith("e="):
            bits = []
            for ch in p[5]:
                v = int(ch, 16)
                bits += [(v >> q) & 1 for q in range(4)]
            maps.setdefault((tagcls[p[1]], names[(p[1], p[2])], p[3]), {})[int(p[4][2:])] = bits[:360 // STEP]
    return maps


ARCS150 = CATALOGUE.parent / "catalogue_arcs_r150.json"


@pytest.mark.parametrize("radius", [50.0, 150.0])
@pytest.mark.parametrize("cls", ["Galaxy", "Sovereign"])
def test_arcs(oracle, record, cls, radius):
    if radius != 50.0 and not ARCS150.exists():
        pytest.skip("no 150 GU arc capture")
    if not CATALOGUE.exists():
        pytest.skip("no catalogue capture (%s)" % CATALOGUE.name)
    import App
    from engine.appc import weapon_subsystems as W
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=3000.0)
    ship = s.tgt
    emitters = {}
    for g in ("GetPhaserSystem", "GetTorpedoSystem", "GetTractorBeamSystem"):
        ws = getattr(ship, g)()
        for i in range(ws.GetNumWeapons()):
            w = ws.GetWeapon(i)
            emitters[w.GetName().replace(" ", "_")] = w
    totals = {}
    worst = {}
    for (c, name, test), rows in _maps(CATALOGUE if radius == 50.0 else ARCS150).items():
        if c != cls or name not in emitters:
            continue
        w = emitters[name]
        if test == "TorpedoTube.CanHit":
            continue                                   # same map as IsInArc for tubes; avoid double counting
        fn = None
        if test in ("PhaserBank.CanHit", "Tractor.CanHit"):
            fn = lambda p, w=w: w.CanHit(p)
        elif test == "TorpedoTube.IsInArc":
            if hasattr(type(w), "IsInArc"):
                fn = lambda p, w=w: w.IsInArc(p)
            elif hasattr(W, "_in_torpedo_cone"):
                fn = lambda p, w=w: W._in_torpedo_cone(w, ship, p)   # Dauntless's tube fire gate (±30° square cone)
        if fn is None:
            totals.setdefault(test, [0, 0, set()])[2].add(name + " (no in-arc test)")
            continue
        agree = n = 0
        for e, bits in rows.items():
            for j, b in enumerate(bits):
                a = j * STEP
                ce = math.cos(math.radians(e))
                p = App.TGPoint3()
                p.SetXYZ(radius * ce * math.sin(math.radians(a)), radius * ce * math.cos(math.radians(a)), radius * math.sin(math.radians(e)))
                got = 1 if fn(p) else 0
                agree += (got == b)
                n += 1
        t = totals.setdefault(test, [0, 0, set()])
        t[0] += agree
        t[1] += n
        worst.setdefault(test, {})[name] = 100.0 * agree / n
    for test, (agree, n, missing) in sorted(totals.items()):
        kind = {"PhaserBank.CanHit": "phaser banks", "TorpedoTube.IsInArc": "torpedo tubes", "Tractor.CanHit": "tractor projectors"}[test]
        if n == 0:
            record(f"A-{cls}-{kind}-r{int(radius)}", "Arcs", f"{cls} {kind}: in-arc answers vs the original game (r = {radius:.0f})", "game's own map",
                   "no comparable test", "missing", "; ".join(sorted(missing)))
            continue
        pct = 100.0 * agree / n
        record(f"A-{cls}-{kind}-r{int(radius)}", "Arcs", f"{cls} {kind}: in-arc answers vs the original game (5° sphere, r = {radius:.0f} GU)",
               "game's own CanHit/IsInArc map", f"{pct:.1f}% of {n} directions agree",
               "match" if pct >= 99 else "close" if pct >= 95 else "wrong",
               "lowest: " + ", ".join(f"{k} {v:.1f}%" for k, v in sorted(worst[test].items(), key=lambda kv: kv[1])[:3]))

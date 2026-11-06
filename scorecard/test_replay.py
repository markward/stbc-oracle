"""H: replay the original game's recorded hits (CombatTap distributor events: impact point in the target's
model frame, damage, weapon radius) through Dauntless's own combat.apply_hit, and compare which subsystems
took damage, and how much, with what the game recorded."""
import glob
import json
import math
from pathlib import Path

import pytest

from conftest import RESULTS_MAC as ROOT
MAX_EVENTS = 400


def _events(target_cls):
    """(file, t, pos, dmg, r, {subsystem name: damage}) for distributor events on `target_cls`."""
    out = []
    for f in sorted(glob.glob(str(ROOT / "sweep" / "*.json"))) + sorted(glob.glob(str(ROOT / "*.json"))):
        if Path(f).name.startswith(("phaser_range", "low_footprint", "coll_", "collisions")):
            continue   # Low-intensity and collision hits have their own rules and checks (PR2/PR3, C1/C2)
        try:
            r = json.load(open(f))
        except Exception:
            continue
        runs = [p["result"] for p in r["parts"]] if "parts" in r else [r]
        for run in runs:
            if run.get("params", {}).get("target") != target_cls or not run.get("combat_tap"):
                continue
            subs = [s for s in run.get("subsystems", []) if s.get("ptr")]
            byptr = {s["ptr"].upper().lstrip("0"): s["name"] for s in subs}
            tgt_ptr = (run.get("meta", {}).get("ptr_target") or "").upper().replace("0X", "").lstrip("0")
            if not tgt_ptr:
                continue          # duels log hits on both ships without identifying them; skip
            cur = None
            dead = set()        # subsystems at 0 condition in the game right now (C rows track every change, repairs too)
            for line in run["combat_tap"]:
                p = line.split()
                if len(p) < 2 or p[0].startswith("#"):
                    continue
                kind = p[1]
                kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
                if kind == "DS" and float(kv.get("dmg", "0")) <= 0.01:
                    cur = None      # zero-damage beam ticks: the game logs a 0-point hull entry; nothing to compare
                    continue
                if kind == "DS":
                    if tgt_ptr and kv.get("ship", "").upper().lstrip("0") != tgt_ptr:
                        cur = None
                        continue
                    cur = dict(f=Path(f).name, t=float(p[0]), pos=[float(x) for x in kv["pos"].split(",")],
                               dmg=float(kv["dmg"]), r=float(kv["r"]), hits={}, dead=set(dead))
                    out.append(cur)
                elif kind == "C":
                    n = byptr.get(kv.get("sub", "").upper().lstrip("0"))
                    if n and "->" in kv.get("hp", ""):
                        if float(kv["hp"].split("->")[1]) <= 0.0:
                            dead.add(n)
                        else:
                            dead.discard(n)
                    continue
                elif kind == "W" and cur is not None:
                    n = byptr.get(kv["sub"].upper().lstrip("0"))
                    if n:
                        a, b = (float(x) for x in kv["hp"].split("->"))
                        cur["hits"][n] = (float(kv["dmg"]), a - b)
                elif kind == "ds":
                    cur = None
            if len(out) >= MAX_EVENTS:
                return out
    return out


def _walk(ship):
    from engine.appc.combat import _iter_subsystems
    seen = list(_iter_subsystems(ship)) + [ship.GetHull()]
    hull = ship.GetHull()
    seen += [hull.GetChildSubsystem(i) for i in range(hull.GetNumChildSubsystems())]
    return {x.GetName(): x for x in seen}


@pytest.mark.parametrize("cls", ["Galaxy", "Sovereign"])
def test_replay_hits(oracle, record, cls):
    import App
    from engine.appc import combat
    evs = _events(cls)
    if not evs:
        record(f"H1-{cls}", "Damage", f"Replay of the game's recorded hits on the {cls}", "recorded hits", "no events found", "missing")
        return
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=3000.0)
    ship = s.tgt
    rs = ship.GetRepairSubsystem()
    subs = _walk(ship)
    same_set = same_amount = 0
    diffs = {}
    for ev in evs:
        for x in subs.values():
            x.SetCondition(x.GetMaxCondition())
        rs.SetCondition(0.0) if rs is not None else None
        for n in ev.get("dead", ()):
            # Destroyed earlier in the game's run: a destroyed subsystem takes no more damage.
            x = subs.get(n) or subs.get(n.replace("_", " "))
            if x is not None and x is not ship.GetHull():
                x.SetCondition(0.0)
        before = {n: x.GetCondition() for n, x in subs.items()}
        p = App.TGPoint3(); p.SetXYZ(*ev["pos"])
        combat.apply_hit(ship, ev["dmg"], p, s.atk, splash_radius=ev["r"], bypass_shields=True)
        got = {n.replace(" ", "_"): before[n] - x.GetCondition() for n, x in subs.items() if before[n] - x.GetCondition() > 0.01}
        if rs is not None and "Engineering" in got and rs.GetName().replace(" ", "_") == "Engineering":
            pass
        want = {n.replace(" ", "_"): v[0] for n, v in ev["hits"].items()}
        if set(got) == set(want):
            same_set += 1
            if all(abs(got[k] - want[k]) <= 0.01 * max(1.0, want[k]) for k in want):
                same_amount += 1
        else:
            for k in set(want) - set(got):
                diffs[f"game damaged {k}, Dauntless not"] = diffs.get(f"game damaged {k}, Dauntless not", 0) + 1
            for k in set(got) - set(want):
                diffs[f"Dauntless damaged {k}, game not"] = diffs.get(f"Dauntless damaged {k}, game not", 0) + 1
    n = len(evs)
    top = sorted(diffs.items(), key=lambda kv: -kv[1])[:8]
    record(f"H1-{cls}", "Damage", f"Replay of {n} recorded hits on the {cls}: same subsystems damaged",
           "game's recorded subsystems per hit", f"{same_set}/{n} identical sets ({100*same_set/n:.0f}%)",
           "match" if same_set >= 0.99 * n else "close" if same_set >= 0.9 * n else "wrong",
           "; ".join(f"{k} ×{v}" for k, v in top))
    record(f"H2-{cls}", "Damage", f"Replay on the {cls}: same damage amounts (where the set matched)",
           "full hit damage to each", f"{same_amount}/{same_set} identical", "match" if same_amount >= 0.99 * max(1, same_set) else "wrong")

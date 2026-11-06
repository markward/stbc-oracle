"""P2: EVERY numeric property the original game exposes (catalogue: every Get*/Is* of every property class, per
subsystem) compared with the same getter on Dauntless's live subsystem, or on its property object."""
import pytest

from conftest import catalogue, catalogue_runtime

SKIP = {"GetObjType", "GetRefCount", "GetIconNum", "GetIconPositionX", "GetIconPositionY", "GetIndicatorIconNum",
        "GetIndicatorIconPositionX", "GetIndicatorIconPositionY", "IsIconAboveShip", "GetName", "GetPositionTG",
        "GetEngineSound", "GetTextureName", "GetTextureStart", "GetTextureEnd", "GetTextureSpeed", "GetPhaserTextureStart",
        "GetPhaserTextureEnd", "GetLengthTextureTilePerUnit", "GetPerimeterTile", "GetInnerCoreColor", "GetOuterCoreColor",
        "GetInnerShellColor", "GetOuterShellColor", "GetShieldGlowColor", "GetShieldGlowDecay", "GetCoreScale",
        "GetTaperRadius", "GetTaperRatio", "GetTaperMinLength", "GetTaperMaxLength", "GetPhaserWidth", "GetMainRadius",
        "GetTractorBeamWidth", "GetLength", "GetWidth", "GetNumSides", "GetFiringChainString",   # visuals / handles
        "GetArcWidthAngleMin", "GetArcWidthAngleMax", "GetArcHeightAngleMin", "GetArcHeightAngleMax",  # compared as arcs (test_arcs)
        "GetWeaponID", "IsPrimary", "IsDumbfire"}   # identifiers / UI flags with no combat effect
ALIAS = {"IsSingleFire": "GetSingleFire"}


def _walk(ship):
    from engine.appc.combat import _iter_subsystems
    seen = list(_iter_subsystems(ship)) + [ship.GetHull()]
    hull = ship.GetHull()
    seen += [hull.GetChildSubsystem(i) for i in range(hull.GetNumChildSubsystems())]
    return {x.GetName().replace(" ", "_"): x for x in seen}


def _num(v):
    if isinstance(v, (int, float)):
        return [float(v)]
    for attr in ("x", "y", "z"):
        if not hasattr(v, attr):
            break
    else:
        return [float(v.x), float(v.y), float(v.z)]
    if isinstance(v, str):
        try:
            return [float(p) for p in v.split(",")]
        except ValueError:
            return None
    return None


def _live(sub, getter, property_first=True):
    """The catalogue's cp rows are PROPERTY getters: ask the property first (a phaser bank's property position
    is its mount; the live subsystem answers its arc midpoint -- compared separately, test_runtime_values)."""
    objs = (getattr(sub, "GetProperty", lambda: None)(), sub)
    if not property_first:
        objs = (sub,)
    for obj in objs:
        if obj is None:
            continue
        fn = getattr(type(obj), getter, None)
        if fn is None:
            continue
        try:
            return _num(getattr(obj, getter)())
        except TypeError:
            return None
        except Exception:
            return None
    return None


@pytest.mark.parametrize("cls", sorted(catalogue()))
def test_every_property(oracle, record, cls):
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=57.0)
    live = _walk(s.tgt)
    bc = catalogue()[cls]
    by_getter = {}
    for name, props in bc.items():
        sub = live.get(name)
        if sub is None:
            continue
        for getter, val in props.items():
            if getter in SKIP:
                continue
            want = _num(val)
            if want is None:
                continue
            got = _live(sub, getter)
            if got is None and getter in ALIAS:
                got = _live(sub, ALIAS[getter])
            g = by_getter.setdefault(getter, {"n": 0, "bad": [], "absent": 0})
            g["n"] += 1
            if got is None:
                g["absent"] += 1
            elif len(got) != len(want) or any(abs(a - b) > 1e-3 * max(1.0, abs(a)) for a, b in zip(want, got)):
                g["bad"].append(f"{name} {','.join(f'{x:g}' for x in want)}→{','.join(f'{x:g}' for x in got)}")
    for getter, g in sorted(by_getter.items()):
        if g["absent"] == g["n"]:
            verdict, ours = "missing", f"no {getter} on Dauntless's subsystem or its property"
        elif g["bad"]:
            verdict, ours = "wrong", f"{g['n'] - len(g['bad']) - g['absent']}/{g['n']} equal"
        else:
            verdict, ours = "match", f"{g['n'] - g['absent']}/{g['n']} equal" + (f" ({g['absent']} not exposed)" if g["absent"] else "")
        record(f"P2-{cls}-{getter}", "Ship data", f"{cls}: {getter[3:] if getter.startswith('Get') else getter}",
               f"{g['n']} values", ours, verdict, "; ".join(g["bad"][:8]) + (" …" if len(g["bad"]) > 8 else ""))


RUNTIME = ("GetPosition", "GetDamagePoint", "GetRadius", "GetMaxCondition", "GetDisabledPercentage", "IsCritical",
           "IsTargetable")


@pytest.mark.parametrize("cls", sorted(catalogue_runtime()))
def test_runtime_values(oracle, record, cls):
    """P3: what the live subsystem answers in the original (runtime position -- a bank's arc midpoint -- damage
    point, radius, ...) against Dauntless's live subsystem."""
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=57.0)
    live = _walk(s.tgt)
    bc = catalogue_runtime()[cls]
    for getter in RUNTIME:
        n, bad, absent = 0, [], 0
        for name, props in bc.items():
            sub = live.get(name)
            if sub is None or getter not in props:
                continue
            want = _num(props[getter])
            if want is None:
                continue
            n += 1
            got = _live(sub, getter, property_first=False)
            if got is None:
                absent += 1
            elif len(got) != len(want) or any(abs(a - b) > 2e-3 * max(1.0, abs(a)) for a, b in zip(want, got)):
                bad.append(f"{name} {','.join(f'{x:g}' for x in want)}→{','.join(f'{x:.4g}' for x in got)}")
        if not n:
            continue
        verdict = "missing" if absent == n else ("wrong" if bad else "match")
        record(f"P3-{cls}-{getter}", "Ship data", f"{cls}: live subsystem {getter[3:] if getter.startswith('Get') else getter}",
               f"{n} values", f"{n - len(bad) - absent}/{n} equal", verdict, "; ".join(bad[:8]) + (" …" if len(bad) > 8 else ""))

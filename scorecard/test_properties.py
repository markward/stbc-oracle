"""P: every subsystem's live settings in Dauntless vs the original game's catalogue dump."""
import pytest

from conftest import catalogue_for, catalogue

FIELDS = [  # (BC getter, Dauntless getter, label, kind)
    ("GetMaxCondition", "GetMaxCondition", "HP", float),
    ("GetDisabledPercentage", "GetDisabledPercentage", "disable threshold", float),
    ("GetRadius", "GetRadius", "radius (damage footprint)", float),
    ("GetRepairComplexity", "GetRepairComplexity", "repair complexity", float),
    ("IsCritical", "IsCritical", "critical flag", int),
    ("IsTargetable", "IsTargetable", "targetable flag", int),
]


def _walk(ship):
    from engine.appc.combat import _iter_subsystems
    seen = list(_iter_subsystems(ship))
    hull = ship.GetHull()
    seen.append(hull)
    for i in range(hull.GetNumChildSubsystems()):
        seen.append(hull.GetChildSubsystem(i))
    return {x.GetName().replace(" ", "_"): x for x in seen}


@pytest.mark.parametrize("cls", ["Galaxy", "Sovereign"])
def test_subsystem_settings(oracle, record, cls):
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=57.0)
    live = _walk(s.tgt)
    bc = catalogue_for(cls)
    missing = sorted(set(bc) - set(live))
    record(f"P0-{cls}", "Ship data", f"{cls}: subsystems present", f"{len(bc)}", f"{len(bc) - len(missing)}",
           "match" if not missing else "wrong", "missing: " + ", ".join(missing) if missing else "")
    for bget, dget, label, kind in FIELDS:
        bad = []
        for name, props in sorted(bc.items()):
            sub = live.get(name)
            if sub is None or bget not in props:
                continue
            want = kind(float(props[bget]))
            got = kind(getattr(sub, dget)())
            if abs(want - got) > 1e-4:
                bad.append(f"{name} {want:g}→{got:g}")
        n = sum(1 for p in bc.values() if bget in p)
        record(f"P-{cls}-{label.split()[0]}", "Ship data", f"{cls}: {label} of every subsystem",
               f"{n} subsystems as authored", f"{n - len(bad)}/{n} correct",
               "match" if not bad else "wrong", "; ".join(bad[:12]) + (" …" if len(bad) > 12 else ""))

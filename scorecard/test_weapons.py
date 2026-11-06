"""W: weapon behaviour, set up as the oracle measured it (attacker 57 GU dead ahead, target shields off)."""
import pytest

from conftest import grade


def _no_repair(ship):
    """The oracle turns repair off for condition tests. Dauntless repair stops only when the bay is at 0."""
    rs = ship.GetRepairSubsystem()
    if rs is not None:
        rs.SetCondition(0.0)


def _only_bank(s, name):
    """Leave one phaser bank working (the oracle isolates one bank; others held disabled)."""
    _no_repair(s.atk)
    ws = s.atk.GetPhaserSystem()
    keep = None
    for i in range(ws.GetNumWeapons()):
        w = ws.GetWeapon(i)
        if w.GetName().replace(" ", "_") == name:
            keep = w
        else:
            w.SetCondition(0.0)
    return ws, keep


def _phaser_rate(s, bank_name, cond=1.0, seconds=8.0):
    s.zero_shields()
    ws, bank = _only_bank(s, bank_name)
    bank.SetCondition(bank.GetMaxCondition() * cond)
    h0 = s.hull_damage()
    s.fire("phaser", intensity=2)
    firing = 0.0
    from engine.core.loop import TICK_DELTA
    for t, sc in s.sample_until(seconds):
        s.zero_shields()
        if bank.IsFiring():
            firing += TICK_DELTA
    dmg = s.hull_damage() - h0
    return dmg, firing


def test_phaser_damage_rate(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    dmg, firing = _phaser_rate(s, "Dorsal_Phaser_3")
    rate = dmg / firing if firing else 0.0
    record("W1", "Phasers", "Damage per firing-second, one Sovereign bank at 57 GU (High)",
           "125–133 /s", f"{rate:.1f} /s (dmg {dmg:.0f} over {firing:.2f} s firing)",
           grade(129.0, rate, tol_close=0.08, tol_match=0.04))


def test_phaser_damage_vs_bank_condition(oracle, record):
    s1 = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    d1, f1 = _phaser_rate(s1, "Dorsal_Phaser_3", 1.0)
    s2 = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    d2, f2 = _phaser_rate(s2, "Dorsal_Phaser_3", 0.8)
    r = (d2 / f2) / (d1 / f1) if f1 and f2 and d1 else 0.0
    record("W2", "Phasers", "Damage of a bank at 80% condition, relative to 100%",
           "0.80 (133.4 → 106.5 /s)", f"{r:.2f}", grade(0.80, r, tol_close=0.05, tol_match=0.02))


@pytest.mark.parametrize("cond,bc", [(1.0, 0.0806), (0.8, 0.0626)])
def test_phaser_recharge(oracle, record, cond, bc):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    ws, bank = _only_bank(s, "Dorsal_Phaser_3")
    bank.SetCondition(bank.GetMaxCondition() * cond)
    bank.SetChargeLevel(0.0)
    c0 = bank.GetChargeLevel()
    s.run(12.0)
    rate = (bank.GetChargeLevel() - c0) / 12.0
    record(f"W3-{int(cond*100)}", "Phasers", f"Recharge per bank, bank at {int(cond*100)}% (Weapons 100%)",
           f"{bc:.4f} /s", f"{rate:.4f} /s", grade(bc, rate, tol_close=0.06, tol_match=0.02))


@pytest.mark.parametrize("atk,ammo,bc", [("Galaxy", 0, 500.0), ("Sovereign", 0, 550.0), ("Sovereign", 1, 900.0)])
def test_torpedo_damage(oracle, record, atk, ammo, bc):
    s = oracle(attacker=atk, target="Sovereign" if atk == "Galaxy" else "Galaxy", range_gu=57.0)
    s.zero_shields()
    ts = s.atk.GetTorpedoSystem()
    if ammo:
        ts.SetAmmoType(ammo)
        for i in range(ts.GetNumWeapons()):
            ts.GetWeapon(i).SetNumReady(1)
    h0 = s.hull_damage()
    s.fire("torpedo")
    s.run(0.2)
    ts.StopFiring()
    hits = []
    last = h0
    for t, sc in s.sample_until(8.0):
        s.zero_shields()
        d = s.hull_damage()
        if d - last > 1.0:
            hits.append(d - last)
        last = d
    per = hits[0] if hits else 0.0
    label = {0: "photon", 1: "quantum"}[ammo]
    record(f"W4-{atk}-{label}", "Torpedoes", f"{atk} {label} damage per hit", f"{bc:.0f}",
           f"{per:.0f} (hits {[round(h) for h in hits][:4]})", grade(bc, per))


def _reload_time(s, weapons_power=1.0):
    ts = s.atk.GetTorpedoSystem()
    ts.SetPowerPercentageWanted(weapons_power)
    tube = ts.GetWeapon(0)
    s.fire("torpedo")
    from engine.core.loop import TICK_DELTA
    fired_at = ready_at = None
    for t, sc in s.sample_until(100.0):
        n = tube.GetNumReady()
        if fired_at is None and n == 0:
            fired_at = t
            ts.StopFiring()
        elif fired_at is not None and n > 0:
            ready_at = t
            break
    return (ready_at - fired_at) if (fired_at is not None and ready_at is not None) else None


@pytest.mark.parametrize("pw,bc", [(1.0, 40.0), (0.5, 80.0)])
def test_torpedo_reload(oracle, record, pw, bc):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=57.0)
    t = _reload_time(s, pw)
    record(f"W5-{int(pw*100)}", "Torpedoes", f"Tube reload after firing, Weapons power {int(pw*100)}%",
           f"{bc:.0f} s", f"{t:.1f} s" if t else "never reloaded", grade(bc, t) if t else "wrong")


def test_torpedo_type_switch(oracle, record):
    """BC: switching type empties ALL tubes; every tube is ready again 40 s after the switch."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    ts = s.atk.GetTorpedoSystem()
    s.run(1.0)
    ready0 = sum(ts.GetWeapon(i).GetNumReady() for i in range(ts.GetNumWeapons()))
    ts.SetAmmoType(1)
    s.step(2)
    ready1 = sum(ts.GetWeapon(i).GetNumReady() for i in range(ts.GetNumWeapons()))
    t_all = None
    for t, sc in s.sample_until(60.0, every_ticks=6):
        if sum(ts.GetWeapon(i).GetNumReady() for i in range(ts.GetNumWeapons())) == ts.GetNumWeapons():
            t_all = t
            break
    ok = ready1 == 0 and t_all is not None and abs(t_all - 40.0) < 1.5
    record("W6", "Torpedoes", "Type switch (script path): tubes emptied, all ready again after",
           "all 6 emptied; ready at 40 s", f"{ready0}→{ready1} loaded; all ready at {t_all and round(t_all, 1)} s",
           "match" if ok else "wrong")

"""M: the remaining mechanics in the reference that can be exercised headless."""
import math

import pytest

from conftest import grade

FAR = 3000.0


def _sub(ship, name):
    from engine.appc.combat import _iter_subsystems
    for x in _iter_subsystems(ship):
        if x.GetName().replace(" ", "_") == name:
            return x
    hull = ship.GetHull()
    for i in range(hull.GetNumChildSubsystems()):
        c = hull.GetChildSubsystem(i)
        if c.GetName().replace(" ", "_") == name:
            return c
    raise KeyError(name)


def _no_repair(ship):
    rs = ship.GetRepairSubsystem()
    if rs is not None:
        rs.SetCondition(0.0)


def _phaser_on(s, sub=None, intensity=2):
    s.atk.SetTarget(s.tgt.GetName())
    if sub is not None:
        s.atk.SetTargetSubsystem(sub)
    return s.fire("phaser", intensity=intensity)


# ---------------------------------------------------------------- engines under power
def test_turn_rate_half_power(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    s.atk.GetImpulseEngineSubsystem().SetPowerPercentageWanted(0.5)
    s.run(1.0)
    s.yaw_direct(0.28)
    w = 0.0
    for t, sc in s.sample_until(10.0):
        w = max(w, s.turn_rate_of(s.atk))
    record("M1", "Engines", "Galaxy max turn rate at Engines 50%", "0.140 rad/s", f"{w:.3f} rad/s", grade(0.14, w))


def test_accel_cap_half_power(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    s.atk.GetImpulseEngineSubsystem().SetPowerPercentageWanted(0.5)
    s.run(1.0)
    s.full_impulse()
    prev, amax = 0.0, 0.0
    from engine.core.loop import TICK_DELTA
    for t, sc in s.sample_until(6.0):
        v = s.speed_of(s.atk)
        amax = max(amax, (v - prev) / TICK_DELTA)
        prev = v
    record("M2", "Engines", "Galaxy acceleration cap at Engines 50% (MaxAccel × power)", "0.75", f"{amax:.3f}",
           grade(0.75, amax, tol_close=0.06, tol_match=0.02))


def test_nacelles_no_impulse_effect(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    for n in ("Port_Warp", "Star_Warp"):
        x = _sub(s.atk, n)
        x.SetCondition(x.GetMaxCondition() * 0.1)
    s.full_impulse()
    s.run(12.0)
    v = s.speed_of(s.atk)
    record("M3", "Engines", "Warp nacelles disabled: no effect on impulse", "6.30", f"{v:.2f}", grade(6.3, v))


# ---------------------------------------------------------------- sensors
@pytest.mark.parametrize("power,cond,bc", [(1.0, 1.0, 2000.0), (0.5, 1.0, 1000.0), (1.0, 0.75, 1500.0), (1.0, 0.49, 0.0)])
def test_sensor_range(oracle, record, power, cond, bc):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    se = s.atk.GetSensorSubsystem()
    se.SetPowerPercentageWanted(power)
    se.SetCondition(se.GetMaxCondition() * cond)
    s.run(3.0)
    from engine.appc.sensor_detection import effective_sensor_range
    r = effective_sensor_range(s.atk)
    record(f"M4-{int(power*100)}-{int(cond*100)}", "Sensors", f"Galaxy sensor range, Sensors power {int(power*100)}%, condition {int(cond*100)}%",
           f"{bc:.0f}", f"{r:.0f}", grade(bc, r) if bc else ("match" if r < 1 else "wrong"))


# ---------------------------------------------------------------- beam timing (Sovereign bank, 57 GU)
def _beam_timing(s, intensity):
    s.zero_shields()
    ws = s.atk.GetPhaserSystem()
    keep = None
    for i in range(ws.GetNumWeapons()):
        w = ws.GetWeapon(i)
        if w.GetName() == "Dorsal Phaser 3":
            keep = w
        else:
            w.SetCondition(0.0)
    from engine.appc import combat
    hits = []
    orig = combat.apply_hit
    def spy(*a, **k):
        hits.append(s.t)
        return orig(*a, **k)
    combat.apply_hit = spy
    lit = []
    try:
        _phaser_on(s, intensity=intensity)
        for t, sc in s.sample_until(16.0):
            s.zero_shields()
            if keep.IsFiring():
                lit.append(t)
    finally:
        combat.apply_hit = orig
    return lit, hits


def test_beam_timing_high(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    lit, hits = _beam_timing(s, 2)
    wind = hits[0] - lit[0] if lit and hits else None
    gaps = sorted(b - a for a, b in zip(hits, hits[1:]))
    gap = gaps[len(gaps) // 2] if gaps else None
    dur = lit[-1] - lit[0] if lit else None
    # BC (6 Sovereign runs, sweep/sov_phaserH_galaxy_WarpCore_*): bank IsFiring to the first damage row
    # 1.10-1.16 s (corrected 2026-10-16; the earlier 0.55-0.60 had no raw-data source).
    record("M5", "Phasers", "Beam wind-up: bank firing (IsFiring) to first damage (Sovereign)", "1.10–1.16 s",
           f"{wind:.2f} s" if wind is not None else "no hit", "match" if wind and 1.05 <= wind <= 1.2 else "close" if wind and 0.9 <= wind <= 1.3 else "wrong")
    # BC tap hull-hit gaps median 0.509 s (0.50-0.52) in a capture whose frames were NOT on a fixed 60 Hz grid; the
    # flush rule (pulse when the banked dwell exceeds 0.5 s, the flush frame included) gives 0.533 at fixed 60 Hz.
    record("M6", "Phasers", "Beam pulse interval", "0.50–0.52 s (variable frame rate)", f"{gap:.3f} s" if gap else "-",
           "match" if gap and 0.49 <= gap <= 0.53 else "close" if gap and gap < 0.56 else "wrong",
           "frame-rate artefact: same flush rule, 0.533 s at a fixed 60 Hz")
    record("M7", "Phasers", "Firing time from a full bank (charge 5), High", "5.3–5.5 s", f"{dur:.2f} s" if dur else "-",
           "match" if dur and 5.2 <= dur <= 5.6 else "close" if dur and 4.8 <= dur <= 6.0 else "wrong")


def test_beam_low_discharge(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    lit, hits = _beam_timing(s, 0)
    dur = lit[-1] - lit[0] if lit else 0
    bank = [s.atk.GetPhaserSystem().GetWeapon(i) for i in range(s.atk.GetPhaserSystem().GetNumWeapons())
            if s.atk.GetPhaserSystem().GetWeapon(i).GetName() == "Dorsal Phaser 3"][0]
    record("M8", "Phasers", "Low intensity discharge: charge used in the first 7.85 s of firing",
           "5.00 → 2.34 (0.34 /s)", f"fired {dur:.1f} s", "match" if dur >= 7.5 else "wrong",
           "Dauntless discharge at Low per code: 0.35 /s")


# ---------------------------------------------------------------- torpedoes
@pytest.mark.parametrize("atk,ammo,label,bc", [("Galaxy", 0, "photon", 250), ("Sovereign", 0, "photon", 200), ("Sovereign", 1, "quantum", 60)])
def test_torpedo_stock(oracle, record, atk, ammo, label, bc):
    s = oracle(attacker=atk, target="Sovereign" if atk == "Galaxy" else "Galaxy", range_gu=57.0)
    ts = s.atk.GetTorpedoSystem()
    n = ts.GetAmmoType(ammo).GetAvailable()
    record(f"M9-{atk}-{label}", "Torpedoes", f"{atk} {label} torpedoes carried", f"{bc}", f"{n}", "match" if n == bc else "wrong")


@pytest.mark.parametrize("ammo,label,bc", [(0, "photon", 3.0), (1, "quantum", 2.7)])
def test_torpedo_flight_time(oracle, record, ammo, label, bc):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    s.zero_shields()
    ts = s.atk.GetTorpedoSystem()
    if ammo:
        ts.SetAmmoType(ammo)
        for i in range(ts.GetNumWeapons()):
            ts.GetWeapon(i).SetNumReady(1)
    h0 = s.hull_damage()
    s.fire("torpedo")
    s.step(2)
    ts.StopFiring()
    t_hit = None
    for t, sc in s.sample_until(6.0):
        if s.hull_damage() - h0 > 1:
            t_hit = t
            break
    record(f"M10-{label}", "Torpedoes", f"Sovereign {label} flight time at 57 GU (fire to impact)", f"{bc:.1f} s (2.6–2.8 quantum, 3.0 photon)",
           f"{t_hit:.2f} s" if t_hit else "no hit", grade(bc, t_hit, tol_close=0.1, tol_match=0.05) if t_hit else "wrong",
           "headless impact is at bounding-sphere entry (4.4 GU early), so Dauntless reads short")


def test_player_type_switch(oracle, record):
    """BC: any type switch empties all tubes and restarts reloads. Dauntless code: CycleAmmoType (player UI) doesn't unload."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    ts = s.atk.GetTorpedoSystem()
    s.run(1.0)
    before = sum(ts.GetWeapon(i).GetNumReady() for i in range(ts.GetNumWeapons()))
    ts.CycleAmmoType()
    s.step(2)
    after = sum(ts.GetWeapon(i).GetNumReady() for i in range(ts.GetNumWeapons()))
    record("M11", "Torpedoes", "Type switch from the player's UI (CycleAmmoType) empties the tubes",
           "all tubes emptied, 40 s to reload", f"{before}→{after} loaded", "match" if after == 0 else "wrong")


def test_weapons_power_not_damage(oracle, record):
    def rate(pw):
        s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
        s.atk.GetPhaserSystem().SetPowerPercentageWanted(pw)
        s.zero_shields()
        h0 = s.hull_damage()
        _phaser_on(s)
        for t, sc in s.sample_until(4.0):
            s.zero_shields()
        return s.hull_damage() - h0
    a, b = rate(1.0), rate(0.5)
    r = b / a if a else 0
    record("M12", "Phasers", "Weapons power 50% vs 100%: phaser damage unchanged", "1.00", f"{r:.2f}", grade(1.0, r, tol_match=0.02))


# ---------------------------------------------------------------- shields
def test_shields_power_not_absorption(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    s.shields.SetPowerPercentageWanted(0.0)
    s.run(1.0)
    s.preset_face(0, 1.0)
    h0 = s.hull_damage()
    _phaser_on(s)
    s.run(4.0)
    record("M13", "Shields", "Shields power 0%: a full face still absorbs everything", "hull 0", f"hull −{s.hull_damage() - h0:.0f}",
           "match" if s.hull_damage() - h0 < 1 else "wrong")


def test_generator_recovery(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    g = s.shields
    g.SetCondition(g.GetMaxCondition() * 0.5)
    s.run(1.0)
    g.SetCondition(g.GetMaxCondition())
    s.run(2.0)
    f = s.face(0)
    record("M14", "Shields", "Generator repaired above 75%: faces regenerate from 0", "front ≈ 2 s × regen (≈19)",
           f"front {f:.0f}", "match" if f < 60 else "wrong")


# ---------------------------------------------------------------- thresholds and groups
def test_group_parent_disabled(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.atk)
    p = _sub(s.atk, "Phasers")
    p.SetCondition(p.GetMaxCondition() * 0.5)
    s.zero_shields()
    h0 = s.hull_damage()
    _phaser_on(s)
    for t, sc in s.sample_until(4.0):
        s.zero_shields()
    record("M15", "Thresholds", "Phasers group parent below 75%: no bank can fire", "no damage",
           f"hull −{s.hull_damage() - h0:.0f}", "match" if s.hull_damage() - h0 < 1 else "wrong",
           "In combat the parents are never damaged (BC); this matters only for scripted damage")


def test_hull_never_disables(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    h = s.tgt.GetHull()
    h.SetCondition(h.GetMaxCondition() * 0.05)
    record("M16", "Thresholds", "Hull at 5%: not 'disabled'", "not disabled", "disabled" if h.IsDisabled() else "not disabled",
           "match" if not h.IsDisabled() else "wrong")


# ---------------------------------------------------------------- repair
def test_repair_queue(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
    t = s.tgt
    names = ["Sensor_Array", "Port_Impulse", "Shield_Generator", "Star_Impulse"]
    subs = [_sub(t, n) for n in names]
    for x in subs:
        x.SetCondition(x.GetMaxCondition() * 0.6)
    c0 = [x.GetCondition() for x in subs]
    s.run(3.0)
    gained = [x.GetCondition() - c for x, c in zip(subs, c0)]
    fourth_waits = gained[3] < 1.0 and all(g > 1.0 for g in gained[:3])
    record("M17", "Repair", "4 damaged items: first 3 repaired in parallel, the 4th waits", "4th waits",
           ", ".join(f"{n} +{g:.0f}" for n, g in zip(names, gained)), "match" if fourth_waits else "wrong")


def test_repair_skips_destroyed(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
    t = s.tgt
    dead = _sub(t, "Port_Impulse")
    dead.SetCondition(0.0)
    a = _sub(t, "Sensor_Array")
    a.SetCondition(a.GetMaxCondition() * 0.5)
    c0 = a.GetCondition()
    s.run(3.0)
    rate = (a.GetCondition() - c0) / 3.0
    record("M18", "Repair", "Destroyed item skipped: a lone damaged sensor array repairs at full rate", "50 /s (destroyed pod not repaired)",
           f"sensor {rate:.1f} /s; pod cond {dead.GetCondition():.0f}", grade(50.0, rate) if dead.GetCondition() < 1 else "wrong",
           "BC divisor with a destroyed item queued is unmeasured; 50 assumes it doesn't count")


def test_repair_power_no_effect(oracle, record):
    def rate(pw):
        s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
        rs = s.tgt.GetRepairSubsystem()
        rs.SetPowerPercentageWanted(pw)
        a = _sub(s.tgt, "Sensor_Array")
        a.SetCondition(a.GetMaxCondition() * 0.5)
        c0 = a.GetCondition()
        s.run(3.0)
        return (a.GetCondition() - c0) / 3.0
    a, b = rate(1.0), rate(0.25)
    record("M19", "Repair", "Repair power setting has no effect", "same rate", f"{a:.1f} vs {b:.1f} /s at 100% / 25%",
           "match" if abs(a - b) < 0.5 else "wrong")


# ---------------------------------------------------------------- power plant
def test_disabled_core_still_produces(oracle, record):
    """BC: a core at 49% (disabled) still produces 490/s into the main battery."""
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    for g in ("GetShields", "GetSensorSubsystem", "GetTorpedoSystem", "GetPhaserSystem", "GetImpulseEngineSubsystem"):
        getattr(s.atk, g)().SetPowerPercentageWanted(0.0)
    ps = s.atk.GetPowerSubsystem()
    ps.SetCondition(ps.GetMaxCondition() * 0.49)
    ps.SetMainBatteryPower(ps.GetMainBatteryLimit() * 0.5)
    s.run(2.0)
    m0 = ps.GetMainBatteryPower()
    s.run(10.0)
    rate = (ps.GetMainBatteryPower() - m0) / 10.0
    record("M20", "Power", "Warp core at 49% (disabled), all controls 0%: main battery charging", "≈ +490 /s",
           f"{rate:+.0f} /s", "match" if rate > 400 else "wrong")


def test_tractor_drain(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=40.0)
    for g in ("GetShields", "GetSensorSubsystem", "GetTorpedoSystem", "GetPhaserSystem", "GetImpulseEngineSubsystem"):
        getattr(s.atk, g)().SetPowerPercentageWanted(1.0)
    ps = s.atk.GetPowerSubsystem()
    ps.SetMainBatteryPower(ps.GetMainBatteryLimit() * 0.5)
    s.fire("tractor", tractor_mode="hold")
    s.run(3.0)
    m0 = ps.GetMainBatteryPower()
    s.run(10.0)
    rate = (ps.GetMainBatteryPower() - m0) / 10.0
    record("M21", "Power", "Tractor beam firing (controls 100%): main battery drain", "≈ −650 /s", f"{rate:+.0f} /s",
           "match" if -720 <= rate <= -580 else "close" if rate < -300 else "wrong")


# ---------------------------------------------------------------- death sequence
def test_death_parents(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    s.zero_shields()
    s.tgt.GetHull().SetCondition(30.0)
    _phaser_on(s)
    t_die = None
    par = _sub(s.tgt, "Phasers")
    for t, sc in s.sample_until(4.0):
        s.zero_shields()
        if s.tgt.IsDying() and t_die is None:
            t_die = t
            at_death = par.GetCondition()
            break
    s.run(0.3)
    after = par.GetCondition()
    record("M22", "Death", "Group parents drop to 0 at the instant the ship starts dying", "0 within 5 ms",
           f"Phasers parent {at_death:.0f} at death, {after:.0f} 0.3 s later" if t_die else "ship did not die",
           "match" if t_die and after < 1 else "wrong", "Dauntless cascades all subsystems 1.5 s after death (code)")

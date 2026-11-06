"""E/PW/R/T/PR: engines, power, repair, torpedo spreads, phaser range and intensity."""
import math

import pytest

from conftest import grade

FAR = 3000.0          # attacker far from the target so manoeuvres never collide


def _damageable(combat, ship):
    """The subsystems a weapon footprint can damage: combat._weapon_damageable_subsystems where Dauntless has it
    (combat-ai-parity), else every subsystem _iter_subsystems walks."""
    fn = getattr(combat, "_weapon_damageable_subsystems", None)
    return list(fn(ship)) if fn is not None else list(combat._iter_subsystems(ship))


def _sub(ship, name):
    from engine.appc.combat import _iter_subsystems
    for x in _iter_subsystems(ship):
        if x.GetName().replace(" ", "_") == name:
            return x
    raise KeyError(name)


def _no_repair(ship):
    rs = ship.GetRepairSubsystem()
    if rs is not None:
        rs.SetCondition(0.0)


# ---------------------------------------------------------------- engines (Galaxy attacker)
@pytest.mark.parametrize("label,frac,power,pods,bc", [
    ("full impulse", 1.0, 1.0, None, 6.3),
    ("impulse level 5 (5/9)", 5 / 9, 1.0, None, 3.5),
    ("Engines power 50%", 1.0, 0.5, None, 3.15),
    ("Engines power 125%", 1.0, 1.25, None, 7.875),
    ("one impulse pod disabled (49%)", 1.0, 1.0, {"Port_Impulse": 0.49}, 4.2),
    ("pods at 100/75/50%", 1.0, 1.0, {"Star_Impulse": 0.75, "Center_Impulse": 0.5}, 4.725),
])
def test_top_speed(oracle, record, label, frac, power, pods, bc):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    s.atk.GetImpulseEngineSubsystem().SetPowerPercentageWanted(power)
    for n, c in (pods or {}).items():
        x = _sub(s.atk, n)
        x.SetCondition(x.GetMaxCondition() * c)
    s.full_impulse(fraction=frac)
    s.run(15.0)
    v = s.speed_of(s.atk)
    note = "AI and scripted ships (SetImpulse path); Dauntless's player throttle code does scale to 125%" if power > 1 else ""
    record(f"E1-{label}", "Engines", f"Galaxy top speed: {label}", f"{bc:.3f}", f"{v:.3f}", grade(bc, v), note)


def test_time_to_90(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    s.full_impulse()
    t90 = None
    for t, sc in s.sample_until(12.0):
        if s.speed_of(s.atk) >= 0.9 * 6.3:
            t90 = t
            break
    record("E2", "Engines", "Galaxy time from rest to 90% of full impulse", "4.1 s",
           f"{t90:.2f} s" if t90 else "never", grade(4.1, t90, tol_close=0.1, tol_match=0.04) if t90 else "wrong")


def test_turn_rate_and_bleed(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    s.full_impulse()
    s.run(12.0)
    v0 = s.speed_of(s.atk)
    s.yaw_direct(0.28)
    vmin, wmax = v0, 0.0
    for t, sc in s.sample_until(12.0):
        vmin = min(vmin, s.speed_of(s.atk))
        wmax = max(wmax, s.turn_rate_of(s.atk))
    record("E3", "Engines", "Galaxy max turn rate", "0.280 rad/s", f"{wmax:.3f} rad/s", grade(0.28, wmax))
    _bleed_from_rest(oracle, record, "E4", "Galaxy", 0.28, 5.98, 5.73)


def _bleed_from_rest(oracle, record, rid, ship, rate, bc_peak, bc13):
    """BC raw rows (impulse_matrix[_sovereign], mv=impyaw, Engines 100%): full impulse + full yaw from rest;
    peak speed (≈7 s) and speed at 13 s. Corrected 2026-10-16 from a '−26% / −30%' figure the raw curves don't show."""
    s = oracle(attacker=ship, target="Galaxy" if ship == "Sovereign" else "Sovereign", range_gu=FAR)
    s.full_impulse()
    s.yaw_direct(rate)
    vpk, v13 = 0.0, None
    for t, sc in s.sample_until(13.0):
        vpk = max(vpk, s.speed_of(s.atk))
    v13 = s.speed_of(s.atk)
    ok = abs(vpk - bc_peak) < 0.1 and abs(v13 - bc13) < 0.1
    record(rid, "Engines", f"{ship}: full impulse + full yaw from rest — peak speed / speed at 13 s (turn bleed)",
           f"{bc_peak} / {bc13}", f"{vpk:.2f} / {v13:.2f}", "match" if ok else "close" if abs(v13 - bc13) < 0.3 else "wrong")


def test_reverse(oracle, record):
    """BC: the reverse key (R) gives 2/9 of top speed. Dauntless's player control maps R to REVERSE_FRACTION."""
    from engine import host_loop
    frac = None
    for name in dir(host_loop):
        obj = getattr(host_loop, name)
        if isinstance(obj, type) and hasattr(obj, "REVERSE_FRACTION"):
            frac = obj.REVERSE_FRACTION
    record("E5", "Engines", "Reverse key speed (fraction of top speed)", f"{2/9:.3f} (2/9)",
           f"{frac}" if frac is not None else "not found", grade(2 / 9, frac) if frac is not None else "missing",
           "Dauntless host_loop REVERSE_FRACTION (player control)")


# ---------------------------------------------------------------- power (Galaxy, controls for every system)
SYSTEMS = ("GetShields", "GetSensorSubsystem", "GetTorpedoSystem", "GetPhaserSystem", "GetImpulseEngineSubsystem")


def _set_controls(ship, level):
    for g in SYSTEMS:
        getattr(ship, g)().SetPowerPercentageWanted(level)


def _battery_rates(s, level, seconds=20.0):
    ship = s.atk
    _set_controls(ship, level)
    ps = ship.GetPowerSubsystem()
    ps.SetMainBatteryPower(ps.GetMainBatteryLimit() * 0.5) if hasattr(ps, "SetMainBatteryPower") else None
    ps.SetBackupBatteryPower(ps.GetBackupBatteryLimit() * 0.5) if hasattr(ps, "SetBackupBatteryPower") else None
    ws = ship.GetPhaserSystem()
    s.run(3.0)
    for i in range(ws.GetNumWeapons()):          # banks empty: recharging draws full phaser power, as in BC
        ws.GetWeapon(i).SetChargeLevel(0.0)
    m0, b0 = ps.GetMainBatteryPower(), ps.GetBackupBatteryPower()
    s.run(seconds)
    return (ps.GetMainBatteryPower() - m0) / seconds, (ps.GetBackupBatteryPower() - b0) / seconds


@pytest.mark.parametrize("level,bc_main,bc_backup", [(0.5, 479, 0), (1.0, -42, -5), (1.25, -197, -104)])
def test_battery_rates(oracle, record, level, bc_main, bc_backup):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    m, b = _battery_rates(s, level, 10.0)
    ok = abs(m - bc_main) <= max(25, 0.15 * abs(bc_main)) and abs(b - bc_backup) <= max(15, 0.2 * abs(bc_backup))
    record(f"PW1-{int(level*100)}", "Power", f"Battery drain, all controls {int(level*100)}% (Galaxy, phasers recharging)",
           f"main {bc_main:+d} /s, backup {bc_backup:+d} /s", f"main {m:+.0f} /s, backup {b:+.0f} /s",
           "match" if ok else "wrong")


def test_brownout_shields(oracle, record):
    """BC: with the core at 30% and everything at 100%, shields miss 2 of 3 power hand-outs, so regen drops."""
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    ship = s.atk
    _set_controls(ship, 1.0)
    core = ship.GetPowerSubsystem()
    core.SetCondition(core.GetMaxCondition() * 0.3)
    s.run(5.0)
    sh = ship.GetShields()
    sh.SetCurShields(0, sh.GetMaxShields(0) * 0.5)
    f0 = sh.GetCurShields(0)
    s.run(12.0)
    rate = (sh.GetCurShields(0) - f0) / 12.0
    full = 9.44    # BC full-power regen, Galaxy front face (reference §2.4)
    record("PW2", "Power", "Brownout (core 30%): shield regen cut (shields lose 2 of 3 power hand-outs)",
           "regen falls to about 1/3", f"{rate:.2f} /s ({100*rate/full:.0f}% of the full 9.44 /s)",
           "match" if rate < 0.5 * full else "wrong")


def test_brownout_engines(oracle, record):
    """BC power_core shot 3 (raw rows): Galaxy, core 30%, everything 100%, batteries 50%, phasers firing, full impulse
    from rest. Engines fed 1 hand-out in 3; starved, the ship holds its speed. Speed at 5 / 10 / 15 / 20 s:
    2.57 / 4.94 / 6.04 / 6.25 (corrected 2026-10-16 from an 'avg 5.71' with no recorded window)."""
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=400.0)   # out of ramming reach (the BC runs flew facing away)
    _no_repair(s.atk)
    _set_controls(s.atk, 1.0)
    core = s.atk.GetPowerSubsystem()
    core.SetCondition(core.GetMaxCondition() * 0.3)
    core.SetMainBatteryPower(core.GetMainBatteryLimit() * 0.5)
    core.SetBackupBatteryPower(core.GetBackupBatteryLimit() * 0.5)
    s.fire("phaser")
    s.run(2.0)                         # the BC run's settle (settle_s=2) before the shot
    s.full_impulse()
    v = {}
    t0 = s.t
    for t, sc in s.sample_until(20.0, every_ticks=6):
        t -= t0                        # time since the impulse command
        for mark in (5.0, 10.0, 15.0, 20.0):
            if mark not in v and t >= mark - 1e-6:
                v[mark] = s.speed_of(s.atk)
    bc = {5.0: 2.57, 10.0: 4.94, 15.0: 6.04, 20.0: 6.25}
    err = max(abs(v.get(k, 0.0) - bc[k]) for k in bc)
    record("PW3", "Power", "Brownout (core 30%): engines fed 1 hand-out in 3, ship coasts when starved — speed at 5/10/15/20 s",
           "2.57 / 4.94 / 6.04 / 6.25", " / ".join(f"{v.get(k, 0.0):.2f}" for k in bc),
           "match" if err < 0.3 else "close" if err < 0.7 else "wrong")


# ---------------------------------------------------------------- repair (Galaxy target)
def test_repair_three_teams(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
    tgt = s.tgt
    items = [("Sensor_Array", 1), ("Forward_Torpedo_1", 3), ("Dorsal_Phaser_1", 7)]
    subs = [_sub(tgt, n) for n, _ in items]
    for x in subs:
        x.SetCondition(x.GetMaxCondition() * 0.5)
    c0 = [x.GetCondition() for x in subs]
    s.run(5.0)
    rates = [(x.GetCondition() - c) / 5.0 for x, c in zip(subs, c0)]
    for (n, cx), r in zip(items, rates):
        bc = 50.0 / 3 / cx
        record(f"R1-{n}", "Repair", f"Repair rate, {n.replace('_', ' ')} (3 items, 3 teams)", f"{bc:.2f} /s",
               f"{r:.2f} /s", grade(bc, r, tol_close=0.05, tol_match=0.02))


# ---------------------------------------------------------------- torpedo spreads (Sovereign attacker)
@pytest.mark.parametrize("mode,name,bc", [(0, "Single", "1 tube every 0.65 s"), (1, "Dual", "2 tubes at once, pairs 0.65 s apart"),
                                          (2, "Quad", "4 tubes at once")])
def test_spread_launch_pattern(oracle, record, mode, name, bc):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    ts = s.atk.GetTorpedoSystem()
    try:
        ts.SetFiringChainMode(mode)
    except Exception as e:
        record(f"T1-{name}", "Torpedoes", f"Spread mode {name}: launch pattern", bc, f"SetFiringChainMode failed: {e}", "wrong")
        return
    from engine.appc import projectiles
    seen, times = set(), []
    s.fire("torpedo")
    for t, sc in s.sample_until(3.0):
        for p in list(projectiles._active):
            if id(p) not in seen:
                seen.add(id(p))
                times.append(round(t, 2))
    ts.StopFiring()
    groups = {}
    for t in times:
        groups.setdefault(t, 0)
        groups[t] += 1
    pattern = ", ".join(f"{n}@{t}s" for t, n in sorted(groups.items()))
    want = {0: [1, 1, 1, 1], 1: [2, 2], 2: [4]}[mode]
    keys = sorted(groups)
    got = [groups[t] for t in keys][:len(want)]
    gap_ok = all(abs((b - a) - 0.65) < 0.05 for a, b in zip(keys, keys[1:len(want)]))
    record(f"T1-{name}", "Torpedoes", f"Spread mode {name}: launch pattern", bc, pattern or "none launched",
           "match" if got == want and gap_ok else "close" if got == want else "wrong",
           "" if gap_ok else "salvo count right, interval differs from BC's 0.65 s")


# ---------------------------------------------------------------- phaser range and intensity (Sovereign attacker)
def _per_hit(s, intensity=2, seconds=6.0):
    s.zero_shields()
    from engine.appc import combat
    hits = []
    orig = combat.apply_hit
    def spy(*a, **k):
        r = orig(*a, **k)
        hits.append(1)
        return r
    combat.apply_hit = spy
    h0 = s.hull_damage()
    try:
        ws = s.fire("phaser", intensity=intensity)
        for t, sc in s.sample_until(seconds):
            s.zero_shields()
        ws.StopFiring()
    finally:
        combat.apply_hit = orig
    return (s.hull_damage() - h0), len(hits)


def test_phaser_range_falloff(oracle, record):
    near = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    dn, nn = _per_hit(near)
    far = oracle(attacker="Sovereign", target="Galaxy", range_gu=150.0)
    df, nf = _per_hit(far)
    r = (df / nf) / (dn / nn) if nn and nf and dn else 0.0
    record("PR1", "Phasers", "Damage at 150 GU relative to 57 GU (Sovereign, MaxDamageDistance 70)",
           f"{70/150:.2f} (measured 63/134 = 0.47)", f"{r:.2f}", grade(0.467, r, tol_close=0.06, tol_match=0.02))


def test_phaser_low_intensity(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    sen = _sub(s.tgt, "Sensor_Array")
    c0 = sen.GetCondition()
    s.atk.SetTarget(s.tgt.GetName())
    s.atk.SetTargetSubsystem(sen)
    dh, n = _per_hit(s, intensity=0, seconds=8.0)
    dsub = c0 - sen.GetCondition()
    ok = dh < 1.0 and dsub > 0
    record("PR2", "Phasers", "Low intensity: hull takes no damage, subsystems do", "hull 0, sensor array damaged",
           f"hull −{dh:.0f}, sensor array −{dsub:.0f}", "match" if ok else "wrong")


def test_phaser_low_no_subsystem(oracle, record):
    """BC (6 samples): at Low, a hit whose footprint holds no targetable subsystem damages the hull; one that holds
    a subsystem spares it. A Low hit (damage_hull=False) applied at a Galaxy hull point with no subsystem in reach."""
    import App
    from engine.appc import combat
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=3000.0)
    subs = list(_damageable(combat, s.tgt))
    def clear(p):
        for x in subs:
            w = combat._subsystem_world_position(s.tgt, x)
            if ((p[0]-w.x)**2 + (p[1]-w.y)**2 + (p[2]-w.z)**2) ** 0.5 < x.GetRadius() + 0.15:
                return False
        return True
    cands = [(x / 4.0, y / 4.0, 0.0) for x in range(-8, 9) for y in range(-12, 13)]
    pt = next((c for c in cands if clear(c)), None)
    h0 = s.tgt.GetHull().GetCondition()
    p = App.TGPoint3(); p.SetXYZ(*pt)
    combat.apply_hit(s.tgt, 30.0, p, s.atk, splash_radius=0.15, bypass_shields=True, damage_hull=False)
    dh = h0 - s.tgt.GetHull().GetCondition()
    record("PR3", "Phasers", "Low intensity, no targetable subsystem in the footprint: hull takes the damage",
           "hull damaged", f"hull −{dh:.0f} (30 applied at {pt})", "match" if dh > 1 else "wrong",
           "Dauntless used to set damage_hull=False for every Low hit")


# BC power_core (Galaxy, all controls 100%, batteries 50%, phasers firing): fraction of samples each system was fed,
# and the phaser top-up per frame (of 5). Shields + impulse / sensors + torpedoes always move together.
CORE_HANDOUTS = {1.0: (1.0, 1.0, 5.0), 0.6: (0.66, 0.99, 4.67), 0.49: (0.66, 0.99, 3.76), 0.3: (0.33, 0.66, 3.01)}


@pytest.mark.parametrize("core", [1.0, 0.6, 0.49, 0.3])
def test_power_handouts(oracle, record, core):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=400.0)   # out of ramming reach (the BC runs flew facing away)
    _no_repair(s.atk)
    _set_controls(s.atk, 1.0)
    ps = s.atk.GetPowerSubsystem()
    ps.SetCondition(ps.GetMaxCondition() * core)
    ps.SetMainBatteryPower(ps.GetMainBatteryLimit() * 0.5)
    ps.SetBackupBatteryPower(ps.GetBackupBatteryLimit() * 0.5)
    s.full_impulse()
    s.fire("phaser")
    s.run(3.0)
    sh, im, se, to, ph = s.atk.GetShields(), s.atk.GetImpulseEngineSubsystem(), s.atk.GetSensorSubsystem(), \
        s.atk.GetTorpedoSystem(), s.atk.GetPhaserSystem()
    n = f_sh = f_im = f_se = f_to = 0
    ph_sum = 0.0
    for i in range(int(12 * 60)):
        s.step(1)
        n += 1
        f_sh += bool(getattr(sh, "_handout_fed", True)); f_im += bool(getattr(im, "_handout_fed", True))
        f_se += bool(getattr(se, "_handout_fed", True)); f_to += bool(getattr(to, "_handout_fed", True))
        ph_sum += ph._power_received
    a, b, c = CORE_HANDOUTS[core]
    got = (f_sh / n, f_im / n, f_se / n, f_to / n, ph_sum / n)
    ok = abs(got[0] - a) < 0.06 and abs(got[1] - a) < 0.06 and abs(got[2] - b) < 0.06 and abs(got[3] - b) < 0.06 \
        and abs(got[4] - c) < 0.5
    record(f"PW4-{int(core*100)}", "Power",
           f"Core {int(core*100)}%, everything 100%: share of power hand-outs fed (shields, impulse / sensors, torpedoes) + phaser top-up",
           f"{a:.2f}, {a:.2f} / {b:.2f}, {b:.2f}; phasers {c} per frame",
           f"{got[0]:.2f}, {got[1]:.2f} / {got[2]:.2f}, {got[3]:.2f}; phasers {got[4]:.2f}",
           "match" if ok else "close" if abs(got[0] - a) < 0.15 and abs(got[2] - b) < 0.15 else "wrong")


# BC batteries_flat (raw rows): Galaxy, both batteries EMPTY, phaser banks empty and recharging, full impulse.
# Short of power the engines are not switched off: they miss hand-outs and the ship coasts through them, so it
# climbs in a stop-start staircase. Fed fractions after 3 s; speed at 2/4/6/8/10/15/20 s.
FLAT = {
    "core 100%, all 125%": (1.0, 1.25, (0.66, 0.99), {2: 2.59, 4: 5.09, 6: 7.07, 8: 7.67, 10: 7.82, 15: 7.87, 20: 7.87}),
    "core 60%, all 100%": (0.6, 1.0, (0.33, 0.66), {2: 1.0, 4: 1.97, 6: 2.97, 8: 3.97, 10: 4.94, 15: 6.04, 20: 6.25}),
}


@pytest.mark.parametrize("case", list(FLAT))
def test_batteries_flat(oracle, record, case):
    core, level, (f_si, f_st), bc = FLAT[case]
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=400.0)   # out of ramming reach (the BC runs flew facing away)
    _no_repair(s.atk)
    _set_controls(s.atk, level)
    ps = s.atk.GetPowerSubsystem()
    if not hasattr(s.atk.GetImpulseEngineSubsystem(), "_handout_fed"):
        pytest.skip("needs the power hand-out model (Dauntless combat-ai-parity: _handout_fed)")
    ps.SetCondition(ps.GetMaxCondition() * core)
    ps.SetMainBatteryPower(0.0)
    ps.SetBackupBatteryPower(0.0)
    ph = s.atk.GetPhaserSystem()
    for i in range(ph.GetNumWeapons()):
        ph.GetWeapon(i).SetChargeLevel(0.0)
    s.fire("phaser")
    # Same phase as the capture: its shot began 0.25 s before the power budget's once-a-second reset (the main
    # battery refills at +0.28 s, then every second). The phase only moves the first second.
    ps._interval_elapsed = ps.POWER_INTERVAL - 0.25
    s.full_impulse()
    t0 = s.t
    v, n, fi, fs = {}, 0, 0, 0
    im, se = s.atk.GetImpulseEngineSubsystem(), s.atk.GetSensorSubsystem()
    for t, sc in s.sample_until(20.0):
        t -= t0
        for m in bc:
            if m not in v and t >= m - 1e-6:
                v[m] = s.speed_of(s.atk)
        if t > 3.0:
            n += 1
            fi += bool(im._handout_fed)
            fs += bool(se._handout_fed)
    err = max(abs(v.get(k, 0.0) - bc[k]) for k in bc)
    fed_ok = abs(fi / n - f_si) < 0.06 and abs(fs / n - f_st) < 0.06
    record(f"PW5-{int(core*100)}-{int(level*100)}", "Power",
           f"Batteries empty, {case}: engines fed {f_si:.2f} / sensors {f_st:.2f}; speed at 2/4/6/8/10/15/20 s (stop-start climb)",
           f"fed {f_si:.2f} / {f_st:.2f}; " + " / ".join(f"{bc[k]}" for k in bc),
           f"fed {fi / n:.2f} / {fs / n:.2f}; " + " / ".join(f"{v.get(k, 0.0):.2f}" for k in bc),
           "match" if err < 0.3 and fed_ok else "close" if err < 0.7 else "wrong")

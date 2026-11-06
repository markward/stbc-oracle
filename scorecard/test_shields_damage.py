"""S/D: shields, thresholds, damage distribution, death."""
import pytest

from conftest import grade


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


@pytest.mark.parametrize("pw,bc", [(1.0, 9.44), (0.5, 4.72)])
def test_shield_regen_vs_power(oracle, record, pw, bc):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    s.shields.SetPowerPercentageWanted(pw)
    s.run(2.0)
    s.preset_face(0, 0.5)
    f0 = s.face(0)
    s.run(40.0)                        # long window: regen steps every 0.5 s
    rate = (s.face(0) - f0) / 40.0
    record(f"S1-{int(pw*100)}", "Shields", f"Galaxy front-face regen at Shields power {int(pw*100)}%",
           f"{bc:.2f} /s", f"{rate:.2f} /s", grade(bc, rate, tol_close=0.06, tol_match=0.02))


@pytest.mark.parametrize("frac", [0.7, 0.35, 0.05])
def test_shield_leak_ramp(oracle, record, frac):
    """One 550 photon into the Galaxy front face preset to `frac`."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    s.preset_face(0, frac)
    h0 = s.hull_damage()
    ts = s.atk.GetTorpedoSystem()
    s.fire("torpedo")
    s.step(3)
    ts.StopFiring()
    hits = []
    last = h0
    for t, sc in s.sample_until(6.0):
        d = s.hull_damage()
        if d - last > 0.5:
            hits.append(d - last)
        last = d
    f = frac
    b = 0.0 if f >= 0.6 else 1.0 if f <= 0.1 else 0.6 * (1 - 2 * (f - 0.1))
    bc = 550.0 * b
    got = hits[0] if hits else 0.0
    record(f"S2-{int(frac*100)}", "Shields", f"Damage leaking through a face at {int(frac*100)}% (550 photon)",
           f"{bc:.0f}", f"{got:.0f}", grade(bc, got) if bc else ("match" if got < 1 else "wrong"))


def test_generator_loss(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    g = s.shields
    g.SetCondition(g.GetMaxCondition() * 0.749)
    s.run(1.0)
    zero = all(v < 1.0 for v in s.faces())
    record("S3", "Shields", "Shield generator below 75%: all faces drop to 0", "all 6 faces 0",
           f"faces {[round(v) for v in s.faces()]}", "match" if zero else "wrong")


@pytest.mark.parametrize("name,dp", [("Shield_Generator", 0.75), ("Sensor_Array", 0.5), ("Dorsal_Phaser_1", 0.75),
                                     ("Forward_Torpedo_1", 0.75), ("Warp_Core", 0.5)])
def test_disable_threshold(oracle, record, name, dp):
    """BC: disabled iff condition < threshold (strict). At exactly the threshold it still works."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    x = _sub(s.tgt, name)
    x.SetCondition(x.GetMaxCondition() * dp)
    at = x.IsDisabled()
    x.SetCondition(x.GetMaxCondition() * (dp - 0.002))
    below = x.IsDisabled()
    x.SetCondition(x.GetMaxCondition() * 0.30)
    at30 = x.IsDisabled()
    ok = (not at) and below
    record(f"S4-{name}", "Thresholds", f"Galaxy {name.replace('_', ' ')}: disabled below {int(dp*100)}%",
           f"works at {int(dp*100)}%, disabled at {dp*100-0.2:.1f}%",
           f"at {int(dp*100)}%: {'disabled' if at else 'works'}; at {dp*100-0.2:.1f}%: {'disabled' if below else 'works'}; at 30%: {'disabled' if at30 else 'works'}",
           "match" if ok else "wrong")


def _phaser_at(s, sub, seconds=4.0):
    """Headless, a torpedo lands where it enters the bounding sphere (4.4 GU out), so subsystem tests use
    phasers: Dauntless aims them at the locked subsystem's exact centre (hull centre when sub is None)."""
    s.atk.SetTarget(s.tgt.GetName())
    if sub is not None:
        s.atk.SetTargetSubsystem(sub)
    ws = s.fire("phaser", intensity=2)
    for t, sc in s.sample_until(seconds):
        s.zero_shields()
    ws.StopFiring()
    s.run(0.6)


def test_overflow(oracle, record):
    """BC (reference §1.3): damage beyond a destroyed subsystem's HP is re-applied as a new hit at the same point,
    damage = excess, radius x excess/damage (900 quantum destroying 3 subsystems -> +685.33 on the hull).
    Exact form here: one 550 hit centred on a sensor array preset to 100 HP, shields bypassed:
    hull 550 + 450 (overflow) = 1000; sensor destroyed."""
    import App
    from engine.appc import combat
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=3000.0)
    _no_repair(s.tgt)
    sen = _sub(s.tgt, "Sensor_Array")
    for x in _damageable(combat, s.tgt):
        x.SetCondition(x.GetMaxCondition())
    sen.SetCondition(100.0)
    h0 = s.tgt.GetHull().GetCondition()
    p = sen.GetWorldLocation() if hasattr(sen, "GetWorldLocation") else sen.GetPosition()
    pt = App.TGPoint3(); pt.SetXYZ(p.x, p.y, p.z)
    combat.apply_hit(s.tgt, 550.0, pt, s.atk, splash_radius=0.13, bypass_shields=True)
    dh = h0 - s.tgt.GetHull().GetCondition()
    record("D1", "Damage", "Overflow: a 550 hit destroying a 100-HP sensor array re-applies the 450 excess",
           "hull −1000 (550 + 450), sensor 0", f"hull −{dh:.0f}, sensor {sen.GetCondition():.0f}",
           grade(1000.0, dh, tol_match=0.01) if sen.GetCondition() < 1 else "wrong")


def test_untargetable_parents(oracle, record):
    """BC: group parents and Engineering are never damaged. Phasers at the hull centre sit right on the
    Galaxy's Phasers parent (0,0,0, r 0.4) and near others."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    s.zero_shields()
    names = ["Phasers", "Torpedoes", "Tractors", "Impulse_Engines", "Warp_Engines", "Engineering"]
    before = {n: _sub(s.tgt, n).GetCondition() for n in names}
    h0 = s.hull_damage()
    _phaser_at(s, None, 6.0)
    hit = [f"{n} −{before[n] - _sub(s.tgt, n).GetCondition():.0f}" for n in names
           if before[n] - _sub(s.tgt, n).GetCondition() > 0.5]
    record("D2", "Damage", "Untargetable subsystems (group parents, Engineering) take no weapon damage",
           "never damaged", ("damaged: " + ", ".join(hit)) if hit else "never damaged",
           "match" if not hit else "wrong", f"phasers at hull centre, hull −{s.hull_damage() - h0:.0f}")


def test_bridge_splash(oracle, record):
    """BC: the Bridge (hull child, targetable, r 0.5) is damaged by hits inside its footprint."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    s.zero_shields()
    br = _sub(s.tgt, "Bridge")
    c0 = br.GetCondition(); h0 = s.hull_damage()
    _phaser_at(s, br, 4.0)
    d = c0 - br.GetCondition(); dh = s.hull_damage() - h0
    record("D3", "Damage", "Phaser fire on the Bridge damages it (same as the hull)", f"Bridge −{dh:.0f}",
           f"Bridge −{d:.0f}", grade(dh, d) if dh else "wrong")


@pytest.mark.parametrize("name", ["Hull", "Warp_Core"])
def test_death_by_critical(oracle, record, name):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    _no_repair(s.tgt)
    s.zero_shields()
    x = s.tgt.GetHull() if name == "Hull" else _sub(s.tgt, name)
    x.SetCondition(30.0)
    _phaser_at(s, None if name == "Hull" else x, 3.0)
    dying = bool(s.tgt.IsDying())
    record(f"D4-{name}", "Death", f"Destroying the {name.replace('_', ' ')} kills the ship", "ship dies",
           f"IsDying={dying}; {name} cond {x.GetCondition():.0f}", "match" if dying else "wrong")

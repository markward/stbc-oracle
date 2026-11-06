"""M2: remaining reference items: face strengths, Sovereign regen and engines, partial-damage effects,
damaged-core power, torpedo spread fan."""
import math

import pytest

from conftest import grade
from test_more import _sub, _no_repair, FAR


@pytest.mark.parametrize("cls,bc", [("Galaxy", [8000, 4000, 4000, 4000, 4000, 4000]),
                                    ("Sovereign", [11000, 5500, 11000, 11000, 5500, 5500])])
def test_face_strengths(oracle, record, cls, bc):
    s = oracle(attacker="Sovereign" if cls == "Galaxy" else "Galaxy", target=cls, range_gu=FAR)
    got = [s.face_max(i) for i in range(6)]
    record(f"M30-{cls}", "Shields", f"{cls} shield face strengths (front, rear, top, bottom, left, right)",
           "/".join(str(v) for v in bc), "/".join(f"{v:.0f}" for v in got), "match" if got == bc else "wrong")


def test_sovereign_regen(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    s.run(2.0)
    s.preset_face(1, 0.5)
    f0 = s.face(1)
    s.run(40.0)                        # long window: regen steps every 0.5 s
    rate = (s.face(1) - f0) / 40.0
    record("M31", "Shields", "Sovereign face regen (rear face, Shields 100%)", "10.10 /s", f"{rate:.2f} /s", grade(10.1, rate, tol_close=0.06, tol_match=0.02),
           "BC delivers about 0.84 × the authored ShieldChargePerSecond (Galaxy 11 → 9.26, Sovereign 12 → 10.10)")


def test_generator_80_regen(oracle, record):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
    _no_repair(s.tgt)
    g = s.shields
    g.SetCondition(g.GetMaxCondition() * 0.8)
    s.run(2.0)
    s.preset_face(0, 0.5)
    f0 = s.face(0)
    s.run(40.0)                        # long window: regen steps every 0.5 s
    rate = (s.face(0) - f0) / 40.0
    record("M32", "Shields", "Generator at 80%: regen unchanged (full rate)", "same as at 100%", f"{rate:.2f} /s",
           "match" if rate > 9 else "wrong", "compare with S1: Dauntless 100% rate 11.37")


def test_tube_80_reload(oracle, record):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=57.0)
    _no_repair(s.atk)
    ts = s.atk.GetTorpedoSystem()
    tube = ts.GetWeapon(0)
    tube.SetCondition(tube.GetMaxCondition() * 0.8)
    s.fire("torpedo")
    fired = ready = None
    for t, sc in s.sample_until(60.0):
        n = tube.GetNumReady()
        if fired is None and n == 0:
            fired = t
            ts.StopFiring()
        elif fired is not None and n > 0:
            ready = t
            break
    dt = (ready - fired) if fired is not None and ready is not None else None
    record("M33", "Torpedoes", "Tube at 80% condition: reload time", "40 s", f"{dt:.1f} s" if dt else "never", grade(40.0, dt) if dt else "wrong")


@pytest.mark.parametrize("what,bc", [("top speed", 7.5), ("turn rate", 0.30), ("speed lost turning", 0.30)])
def test_sovereign_engines(oracle, record, what, bc):
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=FAR)
    s.full_impulse()
    s.run(12.0)
    v0 = s.speed_of(s.atk)
    if what == "top speed":
        record("M34-speed", "Engines", "Sovereign top speed", "7.50", f"{v0:.2f}", grade(bc, v0))
        return
    s.yaw_direct(0.30)
    vmin, w = v0, 0.0
    for t, sc in s.sample_until(12.0):
        vmin = min(vmin, s.speed_of(s.atk)); w = max(w, s.turn_rate_of(s.atk))
    if what == "turn rate":
        record("M34-turn", "Engines", "Sovereign max turn rate", "0.300 rad/s", f"{w:.3f} rad/s", grade(bc, w))
    else:
        from test_engines_power import _bleed_from_rest
        _bleed_from_rest(oracle, record, "M34-bleed", "Sovereign", 0.30, 6.63, 5.90)


def test_damaged_core_rates(oracle, record):
    """BC (power_core): Galaxy core 60%, all controls 100%, batteries 50%: main −118 /s, backup −118 /s, engines powered 2/3 of the time."""
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    _no_repair(s.atk)
    for g in ("GetShields", "GetSensorSubsystem", "GetTorpedoSystem", "GetPhaserSystem", "GetImpulseEngineSubsystem"):
        getattr(s.atk, g)().SetPowerPercentageWanted(1.0)
    ps = s.atk.GetPowerSubsystem()
    ps.SetCondition(ps.GetMaxCondition() * 0.6)
    ps.SetMainBatteryPower(ps.GetMainBatteryLimit() * 0.5)
    ps.SetBackupBatteryPower(ps.GetBackupBatteryLimit() * 0.5)
    s.full_impulse()
    s.run(3.0)
    m0, b0 = ps.GetMainBatteryPower(), ps.GetBackupBatteryPower()
    s.run(20.0)
    m, b = (ps.GetMainBatteryPower() - m0) / 20.0, (ps.GetBackupBatteryPower() - b0) / 20.0
    ok = abs(m + 118) < 30 and abs(b + 118) < 30
    record("M35", "Power", "Core 60%, everything at 100%: battery drain", "main −118 /s, backup −118 /s",
           f"main {m:+.0f} /s, backup {b:+.0f} /s", "match" if ok else "wrong")


def test_spread_fan(oracle, record):
    """BC: Dual/Quad torpedoes leave on a 3.8° fan and steer back toward the target."""
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=57.0)
    ts = s.atk.GetTorpedoSystem()
    ts.SetFiringChainMode(2)
    from engine.appc import projectiles
    s.fire("torpedo")
    vs = []
    for _ in range(6):                 # the launch tick: guidance starts pulling the fan in on the next one
        s.step(1)
        if len(projectiles._active) >= 2:
            break
    ts.StopFiring()
    for p in list(projectiles._active):
        v = p.GetVelocityTG()      # Dauntless torpedoes implement GetVelocityTG; GetVelocity is an unimplemented stub
        if v is not None:
            n = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
            vs.append((v.x / n, v.y / n, v.z / n))
    fan = max((math.degrees(math.acos(max(-1, min(1, sum(a * b for a, b in zip(p, q)))))) for i, p in enumerate(vs) for q in vs[i + 1:]), default=0.0)
    record("M36", "Torpedoes", "Quad spread: angle between torpedo launch directions", "3.8°",
           f"{fan:.1f}° ({len(vs)} torpedoes, launch tick)",
           "match" if abs(fan - 3.8) < 0.5 else "close" if abs(fan - 3.8) < 1.5 else "wrong")

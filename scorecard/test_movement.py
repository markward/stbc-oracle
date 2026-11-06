"""MV: how the ship moves. The original game's flights (motion_check, impulse_matrix: Galaxy, power 100%)
against Dauntless through BOTH of its control paths:
  - "AI/script": SetImpulse + SetTargetAngularVelocityDirect, integrated by engine/appc/ship_motion.py
  - "helm": the player's keyboard control, host_loop._PlayerControl.apply(), driven by a stand-in keyboard
BC's own player keyboard path (TacticalInterfaceHandlers) calls SetTargetAngularVelocityFraction, which the
oracle used for its turn runs; Dauntless does not implement that call."""
import math

import pytest

from conftest import grade

FAR = 5000.0
DT = 1.0 / 60.0

# Real game, Galaxy, Engines 100% (motion_check / impulse_matrix)
BC = dict(turn_t50=1.15, turn_t90=2.75, turn_t99=5.05, turn_max=0.28,
          acc_t90={1: 2.28, 5: 2.78, 9: 4.10}, acc_t50={1: 0.73, 5: 1.18, 9: 2.10},
          stop_9_0=6.40, rev_9_m2=7.25,   # raw impulse_matrix rows, settle = within 1% of 6.3 (corrected from 10.80 / 8.75)
          bleed9=(5.98, 4.41), drift_half=15.9)


class _Keyboard:
    """Duck-typed host for _PlayerControl.apply(): held keys and one-frame presses."""
    class _Keys:
        pass

    def __init__(self):
        self.keys = self._Keys()
        for i in range(10):
            setattr(self.keys, f"KEY_{i}", 48 + i)
        for n, c in (("KEY_R", 82), ("KEY_W", 87), ("KEY_S", 83), ("KEY_A", 65), ("KEY_D", 68), ("KEY_Q", 81),
                     ("KEY_E", 69), ("KEY_LEFT_SHIFT", 340), ("KEY_RIGHT_SHIFT", 344), ("KEY_LEFT_CONTROL", 341),
                     ("KEY_RIGHT_CONTROL", 345), ("KEY_LEFT_ALT", 342), ("KEY_RIGHT_ALT", 346),
                     ("KEY_LEFT_SUPER", 343), ("KEY_RIGHT_SUPER", 347)):
            setattr(self.keys, n, c)
        self.held, self.pressed = set(), set()

    def key_state(self, code):
        return code in self.held

    def key_pressed(self, code):
        return code in self.pressed


class Pilot:
    """One control path flying the scene's attacker (a Galaxy)."""
    def __init__(self, s, path):
        self.s, self.path, self.ship = s, path, s.atk
        if path == "helm":
            from engine.host_loop import _PlayerControl
            self.pc = _PlayerControl()
            self.kb = _Keyboard()

    def throttle(self, level):
        if self.path == "helm":
            code = self.kb.keys.KEY_R if level == -2 else getattr(self.kb.keys, f"KEY_{level}")
            if level == 0:
                code = self.pc._input_map.code("full_stop")
            self.kb.pressed.add(code)
        else:
            self.s.full_impulse(fraction=(-2.0 / 9.0) if level == -2 else level / 9.0)

    def turn(self, axis, on=True):
        if self.path == "helm":
            code = self.pc._input_map.code({"yaw": "yaw_right", "pitch": "pitch_up", "roll": "roll_left"}[axis])
            (self.kb.held.add if on else self.kb.held.discard)(code)
        else:
            import App
            v = App.TGPoint3()
            rate = 0.28 if on else 0.0
            v.SetXYZ(rate if axis == "pitch" else 0.0, rate if axis == "roll" else 0.0, rate if axis == "yaw" else 0.0)
            self.ship.SetTargetAngularVelocityDirect(v)

    def tick(self, n=1):
        for _ in range(n):
            if self.path == "helm":
                self.pc.apply(self.ship, DT, self.kb)
                self.kb.pressed.clear()
            self.s.step(1)

    def speed(self):
        v = self.ship.GetVelocity()
        return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)

    def turn_rate(self):
        if self.path == "helm":
            return max(abs(self.pc._current_yaw_rate), abs(self.pc._current_pitch_rate), abs(self.pc._current_roll_rate))
        return self.s.turn_rate_of(self.ship)

    def drift_deg(self):
        v = self.ship.GetVelocity()
        f = self.ship.GetWorldRotation().GetCol(1)
        n = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
        if n < 1e-6:
            return 0.0
        c = (v.x * f.x + v.y * f.y + v.z * f.z) / n
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))


PATHS = ["AI/script", "helm"]


def _pilot(oracle, path):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=FAR)
    return Pilot(s, "helm" if path == "helm" else "ai")


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("axis", ["yaw", "pitch", "roll"])
def test_turn_ramp(oracle, record, path, axis):
    p = _pilot(oracle, path)
    p.turn(axis)
    w, t = [], 0.0
    for i in range(int(8 / DT)):
        p.tick()
        t += DT
        w.append((t, p.turn_rate()))
    wmax = max(x for _, x in w)
    t50 = next(t for t, x in w if x >= 0.5 * 0.28)
    t90 = next(t for t, x in w if x >= 0.9 * 0.28)
    t99 = next((t for t, x in w if x >= 0.99 * 0.28), None)
    tag = path.split("/")[0]
    record(f"MV1-{tag}-{axis}", "Movement", f"{path}: {axis} from rest — time to 50 / 90 / 99% of the turn rate",
           f"{BC['turn_t50']} / {BC['turn_t90']} / {BC['turn_t99']} s (max 0.28)",
           f"{t50:.2f} / {t90:.2f} / {t99:.2f} s (max {wmax:.3f})" if t99 else f"{t50:.2f} / {t90:.2f} / never (max {wmax:.3f})",
           "match" if abs(t90 - BC["turn_t90"]) < 0.15 and t99 and abs(t99 - BC["turn_t99"]) < 0.3 else
           "close" if abs(t90 - BC["turn_t90"]) < 0.5 else "wrong",
           "BC eases in (S-curve with a long tail); Dauntless ramps linearly at MaxAngularAccel" if t99 and t99 < 3 else "")


@pytest.mark.parametrize("path", PATHS)
def test_turn_stop(oracle, record, path):
    p = _pilot(oracle, path)
    p.turn("yaw")
    p.tick(int(8 / DT))
    p.turn("yaw", on=False)
    t, t_stop = 0.0, None
    for i in range(int(8 / DT)):
        p.tick()
        t += DT
        if p.turn_rate() <= 0.01 * 0.28 and t_stop is None:
            t_stop = t
    record(f"MV2-{path.split('/')[0]}", "Movement", f"{path}: stop turning — time from full yaw to 1% of the rate",
           "5.1 s (half 1.18 s, 10% 2.8 s), same on all axes", f"{t_stop:.2f} s" if t_stop else "never",
           grade(5.1, t_stop, tol_close=0.1, tol_match=0.05) if t_stop else "wrong",
           "BC motion2: the stop mirrors the start")


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("level", [1, 5, 9])
def test_accel_curve(oracle, record, path, level):
    p = _pilot(oracle, path)
    p.throttle(level)
    target = 6.3 * level / 9.0
    sp, t = [], 0.0
    for i in range(int(10 / DT)):
        p.tick()
        t += DT
        sp.append((t, p.speed()))
    t50 = next((t for t, v in sp if v >= 0.5 * target), None)
    t90 = next((t for t, v in sp if v >= 0.9 * target), None)
    ok = t50 and t90 and abs(t50 - BC["acc_t50"][level]) < 0.12 and abs(t90 - BC["acc_t90"][level]) < 0.15
    record(f"MV3-{path.split('/')[0]}-{level}", "Movement", f"{path}: level {level} from rest — time to 50 / 90% speed",
           f"{BC['acc_t50'][level]} / {BC['acc_t90'][level]} s", f"{t50:.2f} / {t90:.2f} s" if t90 else "never",
           "match" if ok else "close" if t90 and abs(t90 - BC["acc_t90"][level]) < 0.4 else "wrong")


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("frm,to,bc", [(9, 0, 6.40), (9, -2, 7.25)])
def test_level_change(oracle, record, path, frm, to, bc):
    p = _pilot(oracle, path)
    p.throttle(frm)
    p.tick(int(12 / DT))
    v0 = p.speed()
    p.throttle(to)
    target = 0.0 if to == 0 else 6.3 * 2 / 9
    t, t99 = 0.0, None
    for i in range(int(16 / DT)):
        p.tick()
        t += DT
        v = p.speed()
        # signed progress along the course change; reverse ends moving backwards at 2/9
        f = p.ship.GetWorldRotation().GetCol(1); vv = p.ship.GetVelocity()
        fwd = vv.x * f.x + vv.y * f.y + vv.z * f.z
        want = 0.0 if to == 0 else -target
        if abs(fwd - want) <= 0.01 * 6.3 and t99 is None:
            t99 = t
    record(f"MV4-{path.split('/')[0]}-{frm}{to}", "Movement", f"{path}: throttle {frm} → {to if to else 'stop'}, time to settle (99%)",
           f"{bc} s", f"{t99:.2f} s" if t99 else "never", grade(bc, t99, tol_close=0.1, tol_match=0.04) if t99 else "wrong")


@pytest.mark.parametrize("path", PATHS)
def test_turn_at_full_speed(oracle, record, path):
    p = _pilot(oracle, path)
    p.throttle(9)
    p.tick(int(12 / DT))
    v0 = p.speed()
    p.turn("yaw")
    vmin, dmax = v0, 0.0
    for i in range(int(10 / DT)):
        p.tick()
        vmin = min(vmin, p.speed())
        dmax = max(dmax, p.drift_deg())
    # (MV5 moved to test_turn_bleed_from_rest: BC's raw curves have no −26% dip; corrected 2026-10-16)
    record(f"MV6-{path.split('/')[0]}", "Movement", f"{path}: full yaw at full impulse — course lags the nose (slide)",
           "22° after 9 s, settling at 32° after about 25 s", f"{dmax:.1f}° max", "match" if dmax > 15 else "close" if dmax > 5 else "wrong")


@pytest.mark.parametrize("path", PATHS)
def test_turn_at_half_speed(oracle, record, path):
    """BC motion_check impyaw mf=0.5: turning from rest at half throttle; drift settles at ≈ 16°."""
    p = _pilot(oracle, path)
    p.throttle(5 if path == "helm" else 0)
    if path != "helm":
        p.s.full_impulse(fraction=0.5)
    p.turn("yaw")
    d = []
    for i in range(int(9 / DT)):
        p.tick()
        d.append(p.drift_deg())
    steady = sum(d[-60:]) / 60
    record(f"MV7-{path.split('/')[0]}", "Movement", f"{path}: yaw from rest at half impulse — steady slide angle",
           f"≈ {BC['drift_half']}°", f"{steady:.1f}°", "match" if abs(steady - 15.9) < 2 else "close" if abs(steady - 15.9) < 6 else "wrong",
           "helm uses level 5 (5/9 = 0.556) vs BC 0.5 throttle" if path == "helm" else "")


# BC raw rows (motion2 / motion_check / impulse_matrix, mv=impyaw, Engines 100%): impulse level + full yaw from rest.
# |v| at 7 s and steady (last second): level 9 5.98 / 5.36, level 6 4.05 / 4.05, level 3 2.03 / 2.02.
BLEED = {9: (5.98, 5.36), 6: (4.05, 4.05), 3: (2.03, 2.02)}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("level", [3, 6, 9])
def test_turn_bleed_from_rest(oracle, record, path, level):
    p = _pilot(oracle, path)
    p.throttle(level)
    p.turn("yaw")
    v7 = vend = None
    n = int((29.0 if level == 9 else 13.0) / DT)
    for i in range(n):
        p.tick()
        if abs((i + 1) * DT - 7.0) < DT / 2:
            v7 = abs(p.speed())
    vend = abs(p.speed())
    b7, bend = BLEED[level]
    ok = abs(v7 - b7) < 0.08 and abs(vend - bend) < 0.08
    record(f"MV5-{path.split('/')[0]}-{level}", "Movement",
           f"{path}: impulse {level} + full yaw from rest — speed at 7 s / steady (speed bleeds in turns)",
           f"{b7} / {bend}", f"{v7:.2f} / {vend:.2f}",
           "match" if ok else "close" if abs(vend - bend) < 0.25 else "wrong")

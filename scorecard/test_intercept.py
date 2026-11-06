"""I: intercept / in-system warp (ShipClass.InSystemWarp, the AI Intercept path and the player's intercept order).
Original game (bible §7.3 + our warp2 runs, Galaxy from 600 GU, stop distance 50):
  entry is a step to exactly 75 GU/s; duration = distance / 75 (7.20 s here); drops out at 54-61 GU from the
  target; exit speed = the ship's MaxSpeed (Galaxy 6.25-6.28), whatever the pre-warp speed; unaffected with
  both nacelles at 49%."""
import math

import pytest

from conftest import grade


def _sub(ship, name):
    from engine.appc.combat import _iter_subsystems
    for x in _iter_subsystems(ship):
        if x.GetName().replace(" ", "_") == name:
            return x
    raise KeyError(name)


def _warp(oracle, pre_level=0, nacelles=None):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=600.0)     # attacker faces the target
    rs = s.atk.GetRepairSubsystem()
    if rs is not None:
        rs.SetCondition(0.0)
    for n in (nacelles or ()):
        x = _sub(s.atk, n)
        x.SetCondition(x.GetMaxCondition() * 0.49)
    if pre_level:
        s.full_impulse(fraction=pre_level / 9.0)
        s.run(8.0)
    v_pre = s.speed_of(s.atk)
    ok = s.atk.InSystemWarp(s.tgt, 50.0)
    samples = []
    for t, sc in s.sample_until(30.0):
        samples.append((t, s.speed_of(s.atk), bool(s.atk.IsDoingInSystemWarp()), s.range_now()))
    warping = [x for x in samples if x[2]]
    if not warping:
        return dict(ok=ok, engaged=False, v_pre=v_pre)
    t0, t1 = warping[0][0], warping[-1][0]
    cruise = max(x[1] for x in warping)
    after = [x for x in samples if x[0] > t1]
    return dict(ok=ok, engaged=True, v_pre=v_pre, cruise=cruise, dur=t1 - t0, drop=warping[-1][3],
                v_exit=after[1][1] if len(after) > 1 else None)


def test_intercept_from_rest(oracle, record):
    r = _warp(oracle)
    if not r["engaged"]:
        record("I1", "Intercept", "In-system warp engages (Galaxy facing the target, 600 GU)", "engages at once",
               f"did not engage (InSystemWarp returned {r['ok']})", "wrong")
        return
    record("I1", "Intercept", "In-system warp cruise speed", "75 GU/s", f"{r['cruise']:.1f} GU/s", grade(75.0, r["cruise"]))
    record("I2", "Intercept", "Time in warp, 600 GU start, stop distance 50", "7.20 s (distance / 75)", f"{r['dur']:.2f} s",
           grade(7.2, r["dur"], tol_close=0.1, tol_match=0.04))
    record("I3", "Intercept", "Drop-out distance from the target (asked 50)", "54–61 GU", f"{r['drop']:.1f} GU",
           "match" if 50 <= r["drop"] <= 63 else "close" if 45 <= r["drop"] <= 70 else "wrong")
    record("I4", "Intercept", "Speed just after dropping out (from rest)", "6.25–6.28 (the Galaxy's top impulse speed)",
           f"{r['v_exit']:.2f}" if r["v_exit"] is not None else "-",
           grade(6.27, r["v_exit"], tol_close=0.05, tol_match=0.01) if r["v_exit"] is not None else "wrong")


def test_intercept_keeps_no_pre_warp_speed(oracle, record):
    r = _warp(oracle, pre_level=5)
    if not r["engaged"]:
        record("I5", "Intercept", "Exit speed when entering at impulse 5", "top impulse speed (6.25)", "did not engage", "wrong")
        return
    record("I5", "Intercept", "Exit speed when entering at impulse 5 (3.5 GU/s)", "top impulse speed (≈6.25): pre-warp speed not kept",
           f"{r['v_exit']:.2f}" if r["v_exit"] is not None else "-",
           grade(6.27, r["v_exit"], tol_close=0.05, tol_match=0.01) if r["v_exit"] is not None else "wrong")


def test_intercept_damaged_nacelles(oracle, record):
    r = _warp(oracle, nacelles=("Port_Warp", "Star_Warp"))
    record("I6", "Intercept", "In-system warp still engages with both nacelles at 49% (disabled)", "still warps",
           f"warps (at {r['cruise']:.0f} GU/s; speed graded in I1)" if r["engaged"] else "refuses to warp",
           "match" if r["engaged"] else "wrong",
           "the Helm's own warp button checks the Warp_Engines group; this is the InSystemWarp call itself")

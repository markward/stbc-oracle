"""Dauntless's AI turn controller, for comparison with the original (results_mac/turnto, worker_turn.sh):
ShipClass.TurnTowardLocation on a fixed point 100 GU away at (azimuth, elevation) in the ship's own frame at act
time, re-issued every ~0.03 s as the oracle's OnSample does; optional full impulse ("s"). Writes
scorecard/dauntless_turnto/<ship>_<motion>.json with t, forward, up and angular velocity per sample.
Run from the dauntless repo:
  SCORECARD_APPEND=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p tests.conftest -p tests.oracle.conftest \\
      --rootdir=. -p no:cacheprovider -q ../stbc-oracle/scorecard/dauntless_turnto.py
"""
import json
import math
from pathlib import Path

import pytest

OUT = Path(__file__).resolve().parent / "dauntless_turnto"
MOTIONS = ["turnloc90_0", "turnloc180_0", "turnloc45_0", "turnloc0_60", "turnloc0_-60", "turnloc135_45",
           "turnloc90_0s", "turnloc180_0s"]


@pytest.mark.parametrize("motion", MOTIONS)
def test_record_turnto(oracle, motion):
    OUT.mkdir(exist_ok=True)
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=3000.0)
    App = s.App
    from engine import host_loop
    for ship in (s.atk, s.tgt):
        ship.SetRadius(0.0)
        host_loop._seed_ship_radius(ship, 400.0, 400.0)
    spec = motion[7:]
    moving = spec.endswith("s")
    spec = spec[:-1] if moving else spec
    az, el = (math.radians(float(x)) for x in spec.split("_"))
    ship = s.atk
    R = ship.GetWorldRotation()
    body = App.TGPoint3(); body.SetXYZ(100.0 * math.cos(el) * math.sin(az), 100.0 * math.cos(el) * math.cos(az),
                                       100.0 * math.sin(el))
    body.MultMatrixLeft(R)
    loc = ship.GetWorldLocation()
    pt = App.TGPoint3(); pt.SetXYZ(loc.x + body.x, loc.y + body.y, loc.z + body.z)
    if moving:
        ship.SetImpulse(1.0, App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    rows = []
    for t, sc in s.sample_until(20.0, every_ticks=2):
        ship.TurnTowardLocation(pt)
        R = ship.GetWorldRotation()
        f, u = R.GetCol(1), R.GetCol(2)
        w = ship.GetAngularVelocityTG()
        p = ship.GetWorldLocation()
        rows.append(dict(t=round(t, 3), fw=[f.x, f.y, f.z], up=[u.x, u.y, u.z], w=[w.x, w.y, w.z], p=[p.x, p.y, p.z]))
    (OUT / f"Galaxy_{motion}.json").write_text(json.dumps(dict(motion=motion, point=[pt.x, pt.y, pt.z], rows=rows)))

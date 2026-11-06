"""TM: torpedoes against a moving target. Sovereign fires single photons (4 forward tubes) at a Galaxy 100 GU away.
Original game (torp_moving sessions): parked 4/4; flying away at full impulse 4/4; flying at the shooter 4/5 (150 GU);
crossing at half impulse 0/8; crossing at full impulse 0/5. Headless Dauntless registers a torpedo hit where it
enters the target's bounding sphere (radius 4.4 GU), which is more generous than the real hull."""
import math

import pytest

CASES = {  # name: (target heading in world XY, throttle fraction, BC hits / torpedoes)
    "parked": ((1, 0), 0.0, "4/4"),
    "crossing, half impulse": ((1, 0), 0.5, "0/8"),
    "crossing, full impulse": ((1, 0), 1.0, "0/5"),
    "flying away, full impulse": ((0, -1), 1.0, "4/4"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_torpedo_vs_moving(oracle, record, case):
    import App
    (hx, hy), thr, bc = CASES[case]
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=100.0)
    f = App.TGPoint3(); f.SetXYZ(float(hx), float(hy), 0.0)
    u = App.TGPoint3(); u.SetXYZ(0.0, 0.0, 1.0)
    s.tgt.AlignToVectors(f, u); s.tgt.UpdateNodeOnly()
    s.zero_shields()
    if thr:
        s.tgt.SetImpulse(thr, App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
        s.run(6.0)                                   # the target is at speed before the salvo, as in the oracle
    from engine.appc import projectiles
    seen = set()
    h0 = s.tgt.GetHull().GetMaxCondition() - s.tgt.GetHull().GetCondition()
    s.fire("torpedo")
    t_fire = s.t
    hits, last = 0, h0
    for t, sc in s.sample_until(20.0):
        s.zero_shields()
        for p in list(projectiles._active):
            seen.add(id(p))
        d = s.tgt.GetHull().GetMaxCondition() - s.tgt.GetHull().GetCondition()
        if d - last > 100:
            hits += int(round((d - last) / 550.0))
        last = d
        if t - t_fire > 2.5:                      # one salvo of 4 (the scene clock includes the run-up)
            s.atk.GetTorpedoSystem().StopFiring()
    bc_hits, bc_n = (int(x) for x in bc.split("/"))
    ours = f"{hits}/{len(seen)}"
    same = (hits == 0) == (bc_hits == 0) and (hits > 0) == (bc_hits > 0)
    record(f"TM-{case.split(',')[0].replace(' ', '_')}-{int(thr*100)}", "Torpedoes", f"Torpedoes at a target 100 GU away, {case}: hits / torpedoes",
           bc, ours, "match" if same and abs(hits / max(1, len(seen)) - bc_hits / bc_n) < 0.3 else "close" if same else "wrong")

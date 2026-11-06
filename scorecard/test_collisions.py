"""C: collisions. Galaxy (attacker) flies head-on into a parked Sovereign from 25 GU at the given throttle.
Original game (sessions coll_k*_a0_full, one ram per fresh launch): each contact damages BOTH ships at once,
radius 1.5 GU, shields bypassed; first contact (Sovereign / Galaxy): 2.10 GU/s 2562 / 2218; 4.18 GU/s 4607 / 3922; 6.10 GU/s 6505 / 5504,
i.e. about 490 + 990 v / 490 + 820 v, linear in impact speed; a side impact equals head-on at the same speed."""
import pytest

from conftest import grade

BC = {3: (2.10, 2562.0, 2218.0), 6: (4.18, 4607.0, 3922.0), 9: (6.10, 6505.0, 5504.0)}


def _first_contact(oracle, level):
    s = oracle(attacker="Galaxy", target="Sovereign", range_gu=25.0)
    for sh in (s.atk, s.tgt):
        rs = sh.GetRepairSubsystem()
        if rs is not None:
            rs.SetCondition(0.0)
    s.tgt.SetAI(None, 0, 0) if hasattr(s.tgt, "SetAI") else None
    s.full_impulse(fraction=level / 9.0)
    # BC's figures are the damage AMOUNT each ship was hit with (CombatTap), so record the amount apply_hit receives.
    from engine.appc import combat
    amounts = {}
    orig = combat.apply_hit
    def spy(ship, damage, *a, **k):
        if k.get("weapon_type") == "collision" and ship not in amounts:
            amounts[ship] = float(damage)
        return orig(ship, damage, *a, **k)
    combat.apply_hit = spy
    try:
        return _run_to_contact(s, amounts)
    finally:
        combat.apply_hit = orig


def _run_to_contact(s, amounts):
    ha0, ht0 = s.atk.GetHull().GetCondition(), s.tgt.GetHull().GetCondition()
    sa0 = sum(s.atk.GetShields().GetCurShields(i) for i in range(6))
    st0 = sum(s.tgt.GetShields().GetCurShields(i) for i in range(6))
    v_in = 0.0
    for t, sc in s.sample_until(14.0):
        v = s.speed_of(s.atk)
        dh = (ha0 - s.atk.GetHull().GetCondition()) + (ht0 - s.tgt.GetHull().GetCondition())
        ds = (sa0 - sum(s.atk.GetShields().GetCurShields(i) for i in range(6))) + (st0 - sum(s.tgt.GetShields().GetCurShields(i) for i in range(6)))
        if dh > 1 or ds > 1:
            s.step(2)
            return dict(v_in=v_in, amt_a=amounts.get(s.atk, 0.0), amt_t=amounts.get(s.tgt, 0.0),
                        hull_a=ha0 - s.atk.GetHull().GetCondition(), hull_t=ht0 - s.tgt.GetHull().GetCondition(),
                        sh_a=sa0 - sum(s.atk.GetShields().GetCurShields(i) for i in range(6)),
                        sh_t=st0 - sum(s.tgt.GetShields().GetCurShields(i) for i in range(6)))
        v_in = v
    return None


@pytest.mark.parametrize("level", [3, 6, 9])
def test_collision_damage(oracle, record, level):
    v_bc, sov_bc, gal_bc = BC[level]
    r = _first_contact(oracle, level)
    if r is None:
        record(f"C1-{level}", "Collisions", f"Head-on ram at impulse {level}: first-contact damage", f"Sovereign {sov_bc:.0f} / Galaxy {gal_bc:.0f}",
               "no contact damage within 14 s", "wrong")
        return
    tot_t, tot_a = r["amt_t"], r["amt_a"]
    record(f"C1-{level}", "Collisions", f"Head-on ram at impulse {level} (impact {v_bc} GU/s): first-contact damage, rammed / rammer",
           f"Sovereign {sov_bc:.0f} / Galaxy {gal_bc:.0f}", f"Sovereign {tot_t:.0f} / Galaxy {tot_a:.0f} (impact {r['v_in']:.2f} GU/s)",
           "match" if abs(tot_t - sov_bc) <= 0.05 * sov_bc and abs(tot_a - gal_bc) <= 0.05 * gal_bc else
           "close" if abs(tot_t - sov_bc) <= 0.25 * sov_bc else "wrong",
           "damage amount each ship is hit with (BC CombatTap), first contact")
    record(f"C2-{level}", "Collisions", f"Ram at impulse {level}: shields absorb none of it", "shields untouched, all to hull and subsystems",
           f"shields took {r['sh_t'] + r['sh_a']:.0f} of {tot_t + tot_a:.0f} applied", "match" if r["sh_t"] + r["sh_a"] < 1 else "wrong",
           "headless Dauntless has no shield bubble; with the renderer its collision code lets shields absorb (bypass only when unshielded)")

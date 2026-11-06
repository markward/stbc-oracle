"""X: a whole Galaxy vs Sovereign duel inside Dauntless, both ships flown by the stock AI at 0.5
(BC: the Sovereign won 26/26 in 178-413 s, finishing with 96-100% hull)."""
import os
import time

import pytest



def _duel(oracle, enemy, player, range_gu, limit_s=900.0):
    import importlib
    s = oracle(attacker=enemy, target=player, range_gu=range_gu)
    s.attach_basic_attack(0.5)                       # enemy AI vs the player ship (enemy group)
    mod = importlib.import_module("AI.Compound.BasicAttack")
    friendly_ai = mod.CreateAI(s.tgt, s.mission.GetFriendlyGroup(), Difficulty=0.5)
    s.tgt.SetAI(friendly_ai, 0, 0)                   # the player's ship under friendly AI (QuickBattleFriendlyAI analogue)
    t0 = time.time()
    winner = None
    for t, sc in s.sample_until(limit_s, every_ticks=30):
        if s.atk.IsDying() or s.tgt.IsDying():
            winner = player if s.atk.IsDying() else enemy
            break
    hull = {enemy: s.atk.GetHull().GetCondition() / s.atk.GetHull().GetMaxCondition(),
            player: s.tgt.GetHull().GetCondition() / s.tgt.GetHull().GetMaxCondition()}
    return winner, s.t, hull, time.time() - t0


@pytest.mark.parametrize("rng", [57.0, 100.0, 150.0, 200.0])
@pytest.mark.parametrize("enemy,player", [("Sovereign", "Galaxy"), ("Galaxy", "Sovereign")])
def test_duel(oracle, record, enemy, player, rng):
    winner, t, hull, wall = _duel(oracle, enemy, player, rng)
    ours = (f"{winner} won at {t:.0f} s; hull left Sovereign {100*hull['Sovereign']:.0f}%, Galaxy {100*hull['Galaxy']:.0f}%"
            if winner else f"no result after {t:.0f} s; hull Sovereign {100*hull['Sovereign']:.0f}%, Galaxy {100*hull['Galaxy']:.0f}%")
    verdict = ("match" if winner == "Sovereign" and 150 <= t <= 450 and hull["Sovereign"] >= 0.9
               else "close" if winner == "Sovereign" else "wrong")
    record(f"X1-{enemy}-enemy-{int(rng)}", "Duel", f"AI duel, {enemy} as enemy vs {player} (start {int(rng)} GU)",
           "Sovereign wins in 178–413 s with 96–100% hull", ours, verdict, f"{wall:.0f} s wall time")

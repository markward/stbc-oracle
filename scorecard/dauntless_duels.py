"""Record Dauntless AI-vs-AI duels for the targeting comparison (not a scorecard check by itself).

Writes scorecard/dauntless_duels/<name>.json with, per 0.25 s sample, every subsystem's condition on both ships,
and every change of the AI's chosen target subsystem (AI.Preprocessors.FireScript.ChooseTargetSubsystem wrapped).
Run from the dauntless repo:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p tests.conftest -p tests.oracle.conftest --rootdir=. \\
      -p no:cacheprovider -q ../stbc-oracle/scorecard/dauntless_duels.py
"""
import importlib
import json
from pathlib import Path

import pytest

OUT = Path(__file__).resolve().parent / "dauntless_duels"

CASES = [(e, p, el, fl, rng)
         for (e, p) in (("Sovereign", "Galaxy"), ("Galaxy", "Sovereign"))
         for (el, fl) in ((1.0, 1.0), (1.0, 0.5), (0.5, 0.5))
         for rng in (57.0, 100.0, 150.0)]


def _subs(ship):
    from engine.appc.combat import _iter_subsystems
    out = list(_iter_subsystems(ship)) + [ship.GetHull()]
    hull = ship.GetHull()
    out += [hull.GetChildSubsystem(i) for i in range(hull.GetNumChildSubsystems())]
    return out


@pytest.mark.parametrize("enemy,player,el,fl,rng", CASES)
def test_record_duel(oracle, enemy, player, el, fl, rng):
    OUT.mkdir(exist_ok=True)
    name = f"duel_{enemy}_enemy{el}_vs_{player}_player{fl}_r{int(rng)}"
    s = oracle(attacker=enemy, target=player, range_gu=rng)
    s.attach_basic_attack(el)
    mod = importlib.import_module("AI.Compound.BasicAttack")
    s.tgt.SetAI(mod.CreateAI(s.tgt, s.mission.GetFriendlyGroup(), Difficulty=fl), 0, 0)

    Pre = importlib.import_module("AI.Preprocessors")
    orig = Pre.FireScript.ChooseTargetSubsystem
    choices, last = [], {}

    def wrapped(self, pTarget):
        p = orig(self, pTarget)
        try:
            ship = self.pCodeAI.GetShip().GetName()
            nm = p.GetName().replace(" ", "_") if p else "-"
            key = (ship, id(self))
            if last.get(key) != nm:
                last[key] = nm
                ws = "+".join(w.GetName().replace(" ", "_") for w in getattr(self, "lWeapons", []))
                choices.append(dict(t=round(s.t, 3), ship=ship, ws=ws, sub=nm))
        except Exception:
            pass
        return p

    Pre.FireScript.ChooseTargetSubsystem = wrapped
    try:
        subs = {"A": _subs(s.atk), "T": _subs(s.tgt)}
        names = {k: [x.GetName().replace(" ", "_") for x in v] for k, v in subs.items()}
        maxc = {k: [x.GetMaxCondition() for x in v] for k, v in subs.items()}
        dp = {k: [x.GetDisabledPercentage() for x in v] for k, v in subs.items()}
        samples, winner = [], None
        for t, sc in s.sample_until(900.0, every_ticks=15):
            samples.append(dict(t=round(t, 2), A=[round(x.GetCondition(), 1) for x in subs["A"]],
                                T=[round(x.GetCondition(), 1) for x in subs["T"]]))
            if s.atk.IsDying() or s.tgt.IsDying():
                winner = player if s.atk.IsDying() else enemy
                break
    finally:
        Pre.FireScript.ChooseTargetSubsystem = orig
    (OUT / f"{name}.json").write_text(json.dumps(dict(
        enemy=enemy, player=player, enemy_level=el, player_level=fl, range=rng, winner=winner, t_end=s.t,
        names=names, max=maxc, disabled_pct=dp, samples=samples, choices=choices)))

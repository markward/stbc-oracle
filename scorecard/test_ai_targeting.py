"""AI: which subsystem the stock AI aims at. AI/Preprocessors.py RateSubsystemForTargeting scores each targetable
subsystem (critical +6, weapon / weapon system / shield generator +5, impulse +3, hull -200, hittable +1,
-0.0005 per HP to disable and to destroy). Both games run this same SDK code; what differs is its inputs
(DisabledPercentage, MaxCondition, IsCritical). Ranking for a Galaxy seen from a Sovereign 100 GU ahead,
fresh ship: the original game's values (catalogue) vs Dauntless's live values."""
from conftest import catalogue_for, catalogue

TYPE_RATING = (("CT_WEAPON_SYSTEM", 5.0), ("CT_WEAPON", 5.0), ("CT_SHIELD_SUBSYSTEM", 5.0),
               ("CT_CLOAKING_SUBSYSTEM", 4.0), ("CT_IMPULSE_ENGINE_SUBSYSTEM", 3.0), ("CT_HULL_SUBSYSTEM", -200.0))


def _rating(critical, max_c, dp, cond, hittable, sys_rating):
    to_disable = max(0.0, cond - dp * max_c)
    return critical * 6.0 - 0.0005 * to_disable - 0.0005 * cond + hittable * 1.0 + sys_rating


def test_ai_target_ranking(oracle, record):
    import App
    s = oracle(attacker="Sovereign", target="Galaxy", range_gu=100.0)
    bc = catalogue_for("Galaxy")
    from engine.appc.combat import _iter_subsystems
    rows = []
    for x in list(_iter_subsystems(s.tgt)):
        if not x.IsTargetable():
            continue
        name = x.GetName().replace(" ", "_")
        sysr = 0.0
        for ct, r in TYPE_RATING:
            if x.IsTypeOf(getattr(App, ct)):
                sysr = r
                break
        hit = float(x.IsHittableFromLocation(s.atk.GetWorldLocation()))
        ours = _rating(float(x.IsCritical()), x.GetMaxCondition(), x.GetDisabledPercentage(), x.GetCondition(), hit, sysr)
        p = bc.get(name, {})
        mc = float(p.get("GetMaxCondition", x.GetMaxCondition()))
        theirs = _rating(float(p.get("IsCritical", 0)), mc, float(p.get("GetDisabledPercentage", 0.25)), mc, hit, sysr)
        rows.append((name, theirs, ours))
    top_bc = [n for n, t, o in sorted(rows, key=lambda r: -r[1])[:6]]
    top_da = [n for n, t, o in sorted(rows, key=lambda r: -r[2])[:6]]
    record("AI1", "AI", "AI's top-6 target subsystems on a fresh Galaxy (rating with each game's subsystem values)",
           ", ".join(top_bc), ", ".join(top_da), "match" if top_bc == top_da else "close" if set(top_bc) == set(top_da) else "wrong",
           "same SDK rating code in both; Dauntless's inputs differ where it dropped DisabledPercentage/critical (fix #1)")
    core = [r for r in rows if r[0] == "Warp_Core"]
    if core:
        n, t, o = core[0]
        record("AI2", "AI", "AI's rating of the Galaxy warp core", f"{t:.2f}", f"{o:.2f}", "match" if abs(t - o) < 0.01 else "wrong",
               "critical +6 is lost in Dauntless (warp core not flagged critical)")


def test_ai_targeting_in_duels(record):
    """From oracle/reports/targeting_compare.py (run after recording Dauntless duels with dauntless_duels.py):
    which of the losing Galaxy's subsystems the Sovereign's AI wears down, per AI level."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent / "targeting_compare.json"
    if not p.exists():
        record("AI3", "AI", "AI targeting in duels", "see targeting_compare", "not computed", "missing")
        return
    d = json.loads(p.read_text())
    for lvl in ("0.5", "1.0"):
        if lvl not in d["bc"] or lvl not in d["da"]:
            continue
        def top(side, k=8):
            return [n for n, v in sorted(d[side][lvl]["lost"].items(), key=lambda kv: -kv[1])[:k]]
        bc, da = top("bc"), top("da")
        overlap = len(set(bc) & set(da))
        tubes_bc = sum(1 for n in bc if "Torpedo" in n); tubes_da = sum(1 for n in da if "Torpedo" in n)
        record(f"AI3-{lvl}", "AI", f"AI {lvl}: the 8 most worn-down Galaxy subsystems in duels (torpedo tubes among them)",
               ", ".join(bc) + f" ({tubes_bc} tubes)", ", ".join(da) + f" ({tubes_da} tubes)",
               "match" if overlap >= 6 and tubes_da >= tubes_bc - 1 else "close" if overlap >= 4 else "wrong",
               f"overlap {overlap}/8; original {d['bc'][lvl]['n']} duels, Dauntless {d['da'][lvl]['n']}")

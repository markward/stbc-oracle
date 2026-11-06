"""M: AI duel matchups, the original vs Dauntless, as distributions (oracle/reports/matchup_stats.py).

For every matchup with at least MIN_N duels on both sides (original: results_mac/duels*/duel_*.json;
Dauntless: scorecard/dauntless_aim_duels/duel_*.json, AIM_DUEL_REPEATS for repeats) and every metric
(fight length, winner, damage/hits per minute by weapon, torpedo launches, hit rate, launch conversion,
bleed-through, behaviour shares), one scorecard row:
  wrong  -- the bootstrap 90% interval on (Dauntless - original) excludes 0 and the medians differ > 10%
  close  -- the medians differ > 10% but the interval still includes 0: needs more duels to tell
  match  -- otherwise
The scorecard records; it does not fail on a gap (each gap is a parity item to chase).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "oracle" / "reports"))
import matchup_stats as ms  # noqa: E402

MIN_N = 3


def _report():
    return ms.run(["results_mac/duels*/duel_*.json"], ["scorecard/dauntless_aim_duels/duel_*.json"], MIN_N)


def test_matchups(record):
    rep = _report()
    if not rep:
        pytest.skip("no matchup has %d duels on both sides" % MIN_N)
    for m in rep:
        key = "%s-vs-%s-ai%.1f" % (m["enemy"], m["player"], m["level"])
        for r in m["rows"]:
            scale = max(abs(r["orig"]), abs(r["dn"]), 1e-9)
            # "wrong" needs >= ms.MIN_FLAG_N duels a side; a gap seen on fewer is "close" (suggestive)
            verdict = "wrong" if r["flagged"] else ("close" if abs(r["dn"] - r["orig"]) / scale > ms.REL_TOL else "match")
            record("M." + key + "." + r["metric"], "matchup", r["metric"],
                   "%.4g (n=%d)" % (r["orig"], r["n_orig"]), "%.4g (n=%d)" % (r["dn"], r["n_dn"]), verdict,
                   "90%% diff [%.4g, %.4g]" % (r["lo"], r["hi"]))

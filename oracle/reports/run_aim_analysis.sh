#!/bin/bash
# Firing-bank aim reconstruction + SDK rating replay at lags 0..8 s for the given duel captures.
# usage: DAUNTLESS=<dauntless checkout> oracle/reports/run_aim_analysis.sh results_mac/duels_aim/duel_*.json
cd "$(dirname "$0")/../.." || exit 1
DAUNTLESS=${DAUNTLESS:-$PWD/../dauntless}
PY=$DAUNTLESS/.venv/bin/python
ORACLE=$PWD
files=(); for f in "$@"; do case "$f" in *.aim.json|*.aimbank.json|*decisions*) ;; *.json) files+=("$PWD/$f");; esac; done
$PY oracle/reports/aim_bank.py "${files[@]}"
cd "$DAUNTLESS" || exit 1
for L in 0 0.5 1 1.5 2 3 4 5 6 8; do
  if [ "$L" = 0 ]; then E=""; else E="RATING_LAG=$L"; fi
  env $E uv run -q --with numpy --with trimesh --with embreex python "$ORACLE/oracle/reports/rating_replay.py" "${files[@]}" > /dev/null 2>&1 &
done
wait

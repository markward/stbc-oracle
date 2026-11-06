"""Run the Dauntless side of the duel matrix in N parallel processes (Windows or Mac).

  python harness_win/dn_matrix.py --dauntless C:\\stbc\\dauntless --game C:\\stbc\\master\\bc_clean
         --procs 18 --out dauntless_matrix [--matrix C:\\stbc\\matrix_full.json] [--stub]

Each process runs scorecard/dauntless_aim_duels.py (pytest, with Dauntless's own conftest plugins)
for its share of the ordered pairs, with AIM_DUEL_SKIP_EXISTING=1, so a stopped run resumes. Results:
<stbc-oracle>/scorecard/<out>/duel_*.json, the same names as the original-game matrix. Logs:
<stbc-oracle>/scorecard/<out>_logs/proc<k>.log.

--stub installs harness_win/_dauntless_host.py (pure-Python stand-in for the C++ extension: Python
transform store, hull meshes from hull_shapes.json.gz, renderer calls ignored). Required where the C++
build does not exist; validated on the Mac 2026-10-16 (identical hull meshes for the 14 stock classes;
Galaxy-Keldon duel statistics match native runs).

The Dauntless venv must have pytest + pillow (uv sync --extra dev in the Dauntless folder).
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORACLE = HERE.parent
CORE14 = ["Akira", "Ambassador", "BirdOfPrey", "CardHybrid", "Galaxy", "Galor", "Keldon", "KessokHeavy",
          "KessokLight", "Marauder", "Nebula", "Sovereign", "Vorcha", "Warbird"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dauntless", type=Path, required=True, help="the Dauntless folder (engine/, tests/, sdk/)")
    ap.add_argument("--python", type=Path, help="Dauntless venv python (default <dauntless>/.venv/...)")
    ap.add_argument("--game", type=Path, required=True, help="BC game folder (data/, scripts/)")
    ap.add_argument("--matrix", type=Path, help="same JSON as oracle/batch.py (classes/pairs, levels, angles)")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default="dauntless_matrix")
    ap.add_argument("--stub", action="store_true")
    a = ap.parse_args()

    m = {"classes": CORE14, "both_roles": True, "levels": [1.0], "angles": [0, 30, 60, 90, 120, 150, 180, 210,
                                                                             240, 270, 300, 330]}
    if a.matrix:
        m.update(json.loads(a.matrix.read_text()))
    pairs = [tuple(p) for p in m["pairs"]] if "pairs" in m else list(itertools.combinations(m["classes"], 2))
    if m.get("both_roles", True):
        pairs += [(b, x) for (x, b) in pairs if (b, x) not in pairs]
    py = a.python or (a.dauntless / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    logs = ORACLE / "scorecard" / (a.out + "_logs")
    logs.mkdir(parents=True, exist_ok=True)
    procs = []
    for k in range(a.procs):
        mine = pairs[k::a.procs]
        if not mine:
            continue
        env = dict(os.environ,
                   AIM_DUEL_OUT=a.out, AIM_DUEL_SKIP_EXISTING="1",
                   AIM_DUEL_PAIRS=" ".join("%s:%s" % p for p in mine),
                   AIM_DUEL_LEVELS=" ".join(str(x) for x in m["levels"]),
                   AIM_DUEL_ANGLES=" ".join(str(x) for x in m["angles"]),
                   SCORECARD_APPEND="1", PYTHONDONTWRITEBYTECODE="1",
                   DAUNTLESS_GAME_DIR=str(a.game), DAUNTLESS_SDK_DIR=str(a.dauntless / "sdk"))
        plugins = []
        if a.stub:
            env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get("PYTHONPATH", "")
            plugins = ["-p", "use_stub"]
        cmd = [str(py), "-m", "pytest"] + plugins + ["-p", "tests.conftest", "-p", "tests.oracle.conftest",
               "--rootdir=.", "-p", "no:cacheprovider", "-q", str(ORACLE / "scorecard" / "dauntless_aim_duels.py")]
        fh = open(logs / ("proc%02d.log" % k), "a")
        procs.append((k, subprocess.Popen(cmd, cwd=str(a.dauntless), env=env, stdout=fh, stderr=subprocess.STDOUT), fh))
        print("started proc %d: %d pairs" % (k, len(mine)), flush=True)
        time.sleep(1.0)
    rc = 0
    for k, p, fh in procs:
        r = p.wait()
        fh.close()
        print("proc %d exited %d" % (k, r), flush=True)
        rc = rc or r
    n = len(list((ORACLE / "scorecard" / a.out).glob("duel_*.json")))
    print("done: %d duel files in scorecard/%s" % (n, a.out), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())

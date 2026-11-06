"""Scorecard plumbing: every check records (id, area, what, BC value, Dauntless value, verdict)
to scorecard/results.jsonl. Run from the dauntless repo with its fixtures loaded as plugins:

  cd <your Dauntless checkout>          # stbc-oracle checked out beside it
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p tests.conftest -p tests.oracle.conftest \\
      --rootdir=. -p no:cacheprovider -q ../stbc-oracle/scorecard

Nothing in the dauntless tree is modified. BC values come from the stbc-oracle measurements
(docs/mechanics-reference-galaxy-sovereign.md, provisional until its captures are in docs/results/,
and results_mac/)."""
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results.jsonl"
# The original's captures: results_mac/ beside the scorecard, or ORACLE_RESULTS (raw captures stay out of git,
# so a checkout that is not the one that recorded them points here).
RESULTS_MAC = Path(os.environ.get("ORACLE_RESULTS") or HERE.parent / "results_mac")
CATALOGUE = RESULTS_MAC / "catalogue_galaxy_sovereign.json"


def pytest_sessionstart(session):
    if not os.environ.get("SCORECARD_APPEND"):
        RESULTS.write_text("")


@pytest.fixture
def record():
    """record(id, area, what, bc, ours, verdict, note='') -> verdict in {'match','close','wrong','missing','unmeasured'}."""
    def _rec(cid, area, what, bc, ours, verdict, note=""):
        assert verdict in ("match", "close", "wrong", "missing", "unmeasured")   # unmeasured: BC side not captured yet
        with RESULTS.open("a") as f:
            f.write(json.dumps(dict(id=cid, area=area, what=what, bc=str(bc), ours=str(ours),
                                    verdict=verdict, note=note)) + "\n")
        return verdict
    return _rec


def grade(bc, ours, tol_close=0.05, tol_match=0.01):
    """Relative comparison of two numbers."""
    if bc == 0:
        return "match" if abs(ours) < 1e-6 else "wrong"
    err = abs(ours - bc) / abs(bc)
    return "match" if err <= tol_match else "close" if err <= tol_close else "wrong"


def catalogue_files():
    """Every full property catalogue: results_mac/catalogue_<attacker>_<target>.json (both ships each), the
    Galaxy/Sovereign one first. Arc-only, hittable-only and partial dumps are not property catalogues."""
    files = [CATALOGUE]
    for f in sorted(CATALOGUE.parent.glob("catalogue_*_*.json")):
        if f == CATALOGUE or f.name.startswith(("catalogue_arcs", "catalogue_m2")):
            continue
        files.append(f)
    return files


_CAT_CACHE = {}


def catalogue():
    """{ship class: {subsystem name: {prop: value}}} from the game's own dumps (all pair catalogues merged)."""
    if "all" not in _CAT_CACHE:
        out = {}
        for f in catalogue_files():
            try:
                for cls, subs in _catalogue_one(f).items():
                    out.setdefault(cls, subs)
            except Exception:
                continue
        _CAT_CACHE["all"] = out
    return _CAT_CACHE["all"]


def catalogue_for(cls):
    """catalogue()[cls], skipping the calling test when no capture holds that class (results_mac stays out of git)."""
    cat = catalogue()
    if cls not in cat:
        pytest.skip("no catalogue capture for %s (%s)" % (cls, CATALOGUE.name))
    return cat[cls]


def _catalogue_one(path):
    cat = json.loads(path.read_text())
    p = cat.get("params") or {}
    if not p.get("catalogue") or p.get("arcs_only") or (p.get("hit_radii") not in (None, "none")):
        return {}
    tagcls = {"A": cat["params"]["attacker"], "T": cat["params"]["target"]}
    names, out = {}, {}
    for l in cat["raw_rows"]:
        p = l.split(" ", 3)
        if p[0] == "cs":
            kv = dict(x.split("=", 1) for x in p[3].split())
            names[(p[1], p[2])] = kv["name"]
    for l in cat["raw_rows"]:
        p = l.split(" ", 3)
        if p[0] == "cp" and "=" in p[3] and (p[1], p[2]) in names:
            k, v = p[3].split("=", 1)
            out.setdefault(tagcls[p[1]], {}).setdefault(names[(p[1], p[2])], {})[k.split(".", 1)[1]] = v
    return out


def catalogue_runtime():
    """{ship class: {subsystem name: {getter: value}}} from the RUNTIME subsystem rows (cr ... ShipSubsystem.*):
    what the live subsystem answers (GetPosition = a bank's arc midpoint, GetDamagePoint, ...)."""
    if "rt" not in _CAT_CACHE:
        out = {}
        for f in catalogue_files():
            try:
                cat = json.loads(f.read_text())
                p = cat.get("params") or {}
                if not p.get("catalogue") or p.get("arcs_only") or (p.get("hit_radii") not in (None, "none")):
                    continue
                tagcls = {"A": p["attacker"], "T": p["target"]}
                names, one = {}, {}
                for l in cat["raw_rows"]:
                    q = l.split(" ", 3)
                    if q[0] == "cs":
                        names[(q[1], q[2])] = dict(x.split("=", 1) for x in q[3].split())["name"]
                for l in cat["raw_rows"]:
                    q = l.split(" ", 3)
                    if q[0] == "cr" and q[3].startswith("ShipSubsystem.") and "=" in q[3] and (q[1], q[2]) in names:
                        k, v = q[3].split("=", 1)
                        one.setdefault(tagcls[q[1]], {}).setdefault(names[(q[1], q[2])], {})[k.split(".", 1)[1]] = v
                for cls, subs in one.items():
                    out.setdefault(cls, subs)
            except Exception:
                continue
        _CAT_CACHE["rt"] = out
    return _CAT_CACHE["rt"]

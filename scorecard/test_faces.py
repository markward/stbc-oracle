"""F: shield face selection. The original game's face map (sessions faces_galaxy / faces_sovereign: one
phaser shot from each of 266 directions at 57 GU, the face that took the first shield hit) replayed through
Dauntless's own bubble-entry + face chooser. Headless Dauntless has no renderer hull box, so the box is set
from the game's OWN hull surface samples (catalogue ch rows, ray-cast all round each ship)."""
import json
import math
from pathlib import Path

import pytest

from conftest import CATALOGUE

from conftest import RESULTS_MAC
ROOT = RESULTS_MAC / "sweep"
FACES = ("front", "rear", "top", "bottom", "left", "right")


def _hull_box(cls, catalogue=None):
    cat = json.loads((catalogue or CATALOGUE).read_text())
    tag = "T" if cat["params"]["target"] == cls else "A"
    pts = [[float(v) for v in l.split()[2][2:].split(",")] for l in cat["raw_rows"] if l.startswith(f"ch {tag} ")]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return tuple((a + b) / 2 for a, b in zip(lo, hi)), tuple((b - a) / 2 for a, b in zip(lo, hi)), len(pts)


def _first_faces(session):
    """{(a, e): face index} — first drained face per shot, using the oracle's shot windows."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "oracle" / "reports"))
    from common import shots, tap
    res = {}
    for s in shots(str(ROOT / f"{session}.json")):
        import re
        a = float(re.search(r"\ba=([-\d.]+)", s["spec"]).group(1)); e = float(re.search(r"\be=([-\d.]+)", s["spec"]).group(1))
        first = None
        seen = {}
        for t, k, d in tap(s["run"], s["start"], s["end"]):
            if k == "S":
                f = int(d["face"]); v = float(d["set"])
                seen.setdefault(f, []).append(v)
        drained = [(f, vals) for f, vals in seen.items() if len(vals) > 1 and vals[0] - min(vals) > 5]
        if drained:
            res[(a, e)] = max(drained, key=lambda fv: fv[1][0] - min(fv[1]))[0]
    return res


_SHOOTER = {"Galaxy": "Sovereign", "Sovereign": "Galaxy", "Keldon": "Vorcha", "Akira": "Nebula"}
_CATALOGUE = {"Keldon": "catalogue_vorcha_keldon.json", "Akira": "catalogue_akira_nebula.json"}


@pytest.mark.parametrize("cls,session", [("Galaxy", "faces_galaxy"), ("Sovereign", "faces_sovereign"),
                                         ("Keldon", "faces_keldon"), ("Akira", "faces_akira")])
def test_face_selection(oracle, record, cls, session):
    import App
    from engine.appc import combat
    if not (ROOT / f"{session}.json").exists():
        pytest.skip(f"no {session} capture")
    bc = _first_faces(session)
    cat = ROOT.parent / _CATALOGUE[cls] if cls in _CATALOGUE else None
    centre, half, npts = _hull_box(cls, cat)
    s = oracle(attacker=_SHOOTER[cls], target=cls, range_gu=3000.0)
    ship = s.tgt
    ship._shield_hull_box = (centre, half)
    agree, n, conf = 0, 0, {}
    for (a, e), face in bc.items():
        ar, er = math.radians(a), math.radians(e)
        src = (57 * math.cos(er) * math.sin(ar), 57 * math.cos(er) * math.cos(ar), 57 * math.sin(er))
        o = App.TGPoint3(); o.SetXYZ(*src)
        d = App.TGPoint3(); d.SetXYZ(-src[0] / 57, -src[1] / 57, -src[2] / 57)
        entry = combat.shield_bubble_entry(ship, o, d, 60.0)
        if entry is None:
            continue
        got = combat._shield_face_from_hit_point(ship, entry)
        n += 1
        if got == face:
            agree += 1
        else:
            key = f"{FACES[face]}→{FACES[got]}"
            conf[key] = conf.get(key, 0) + 1
    pct = 100.0 * agree / n if n else 0
    record(f"F1-{cls}", "Shields", f"{cls}: which face takes a shot, over {n} directions (game's face map)",
           "game's own face per direction", f"{agree}/{n} agree ({pct:.0f}%)",
           "match" if pct >= 97 else "close" if pct >= 85 else "wrong",
           "differences (game→Dauntless): " + ", ".join(f"{k} ×{v}" for k, v in sorted(conf.items(), key=lambda kv: -kv[1])[:6])
           + f"; hull box from {npts} game hull samples: centre {tuple(round(c, 2) for c in centre)}, half {tuple(round(h, 2) for h in half)}")

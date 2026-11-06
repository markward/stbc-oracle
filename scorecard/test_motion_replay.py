"""MR: every recorded BC motion flight replayed through Dauntless, compared over the WHOLE curve.

Sources (results_mac/sweep): motion_check, motion2, impulse_matrix (Galaxy), impulse_matrix_sovereign. Each shot is
re-flown with the oracle's own calls (OracleSession._manoeuvre): pods at ic, Engines power ipw,
SetImpulse(|mf|, model forward/backward), SetTargetAngularVelocityFraction(axis * tf), the second throttle /
turn command at t2. At every BC row (0.05 s) the replay is compared on:
  - speed |v|
  - turn rate |w|
  - course heading: how far the velocity direction has swung from its first direction (impyaw only; this is
    what shows the slide, since the nose heading is the integral of w)
Verdict per shot: match when max |dv| <= 0.10 GU/s, max |dw| <= 0.008 rad/s and max |dcourse| <= 3 deg."""
import json
import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
from conftest import RESULTS_MAC
SWEEP = str(RESULTS_MAC / "sweep")
sys.path.insert(0, os.path.join(HERE, "..", "oracle", "reports"))
from common import shots, xrows  # noqa: E402

DT = 1.0 / 60.0
FILES = ["motion_check", "motion2", "motion3", "impulse_matrix", "impulse_matrix_sovereign"]


def _vec(s):
    return [float(x) for x in s.split(",")]


def _spec(s, key, default=None):
    m = re.search(r"\b%s=(\S+)" % key, s)
    return m.group(1) if m else default


def _cases():
    out = []
    for f in FILES:
        path = os.path.join(SWEEP, f + ".json")
        if not os.path.exists(path):
            continue
        meta = json.load(open(path))
        meta = meta["parts"][0]["result"]["meta"] if "parts" in meta else meta["meta"]
        ship = "Sovereign" if "overeign" in meta.get("attacker_name", "") else "Galaxy"
        for s in shots(path):
            mv = _spec(s["spec"], "mv")
            if mv in (None, "none"):
                continue
            out.append(pytest.param(f, ship, s, id=f"{f}-{s['index']:02d}-{mv}"))
    return out


def _bc_series(s):
    """Rows from the command to the oracle's end-of-shot reset (the ship is stilled and moved back before `end`):
    cut at the first physically impossible step -- speed or turn rate jumping more than 0.5 GU/s or 0.05 rad/s, or
    the position moving more than 2 GU, between two 0.05 s rows."""
    xm = xrows(s["run"], "xm", "A", s["start"], s["end"] - 0.3)
    t0 = s["start"]
    out, prev = [], None
    for x in xm:
        v, w, p = _vec(x["v"]), _vec(x["w"]), _vec(x["p"])
        n = lambda q: math.sqrt(sum(c * c for c in q))
        if prev is not None:
            pv, pw, pp = prev
            if abs(n(v) - n(pv)) > 0.5 or abs(n(w) - n(pw)) > 0.05 or n([a - b for a, b in zip(p, pp)]) > 2.0:
                break
            # the oracle's end-of-shot freeze: speed / turn set to exactly 0 from a moving state
            if (n(v) == 0.0 and n(pv) > 0.005) or (n(w) == 0.0 and n(pw) > 0.002):
                break
        out.append((x["t"] - t0, v, w))
        prev = (v, w, p)
    return out


def _course(series):
    """How far the course has swung (deg): the summed angle between successive velocity directions (3-D, so a
    pitch or diagonal turn counts too), from the first row with speed > 0.3."""
    out, prev, acc = [], None, 0.0
    for t, v, *_ in series:
        sp = math.sqrt(sum(c * c for c in v))
        if sp < 0.3:
            out.append(None)
            continue
        u = [c / sp for c in v]
        if prev is not None:
            acc += math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(u, prev)))))
        prev = u
        out.append(math.degrees(acc))
    return out


@pytest.mark.parametrize("fname,ship,shot", _cases())
def test_motion_replay(oracle, record, fname, ship, shot):
    spec = shot["spec"]
    mv, mf, tf = _spec(spec, "mv"), float(_spec(spec, "mf", "1")), float(_spec(spec, "tf", "1"))
    ipw, ic = float(_spec(spec, "ipw", "1")), float(_spec(spec, "ic", "1"))
    mf2, t2, tf2 = _spec(spec, "mf2", "none"), float(_spec(spec, "t2", "0")), _spec(spec, "tf2", "none")
    # tf2 is not in the shot label; the session logged it when the second command fired ("zt <i> t=.. tf2=..")
    for l in shot["run"].get("raw_rows", []):
        if l.startswith("zt %d " % shot["index"]) and "tf2=" in l:
            tf2 = l.split("tf2=")[1].split()[0]
    bc = _bc_series(shot)
    if len(bc) < 10:
        pytest.skip("no rows")

    s = oracle(attacker=ship, target="Galaxy" if ship == "Sovereign" else "Sovereign", range_gu=5000.0)
    App = s.App
    a = s.atk
    try:
        a.GetRepairSubsystem().TurnOff()
    except Exception:
        pass
    e = a.GetImpulseEngineSubsystem()
    e.SetPowerPercentageWanted(ipw)
    for i in range(e.GetNumChildSubsystems()):
        k = e.GetChildSubsystem(i)
        k.SetCondition(k.GetMaxCondition() * ic)

    def throttle(f):
        v = App.TGPoint3_GetModelForward() if f >= 0 else App.TGPoint3_GetModelBackward()
        a.SetImpulse(abs(f), v, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)

    def turn(frac):
        r = 0.70710678
        ax = {"yaw": (0, 0, 1), "impyaw": (0, 0, 1), "pitch": (1, 0, 0), "imppitch": (1, 0, 0),
              "roll": (0, 1, 0), "improll": (0, 1, 0), "yawpitch": (r, 0, r), "impyawpitch": (r, 0, r),
              "yawroll": (0, r, r), "impyawroll": (0, r, r)}.get(mv)
        if ax:
            v = App.TGPoint3()
            v.SetXYZ(ax[0] * frac, ax[1] * frac, ax[2] * frac)
            a.SetTargetAngularVelocityFraction(v)

    if mv.startswith("imp"):
        throttle(mf)
    if mv != "impulse":
        turn(tf)

    ours, t, did2 = [], 0.0, False
    for (tb, _, _) in bc:
        while t < tb - 1e-9:
            if not did2 and t2 > 0 and t >= t2 - 1e-9:
                if mf2 != "none":
                    throttle(float(mf2))
                if tf2 != "none":
                    turn(float(tf2))
                did2 = True
            s.step(1)
            t += DT
        v, w = a.GetVelocity(), a._current_angular_velocity
        ours.append((t, [v.x, v.y, v.z], [w.x, w.y, w.z]))

    dv = max(abs(math.sqrt(sum(c * c for c in vb)) - math.sqrt(sum(c * c for c in vo)))
             for (_, vb, _), (_, vo, _) in zip(bc, ours))
    dw = max(abs(math.sqrt(sum(c * c for c in wb)) - math.sqrt(sum(c * c for c in wo)))
             for (_, _, wb), (_, _, wo) in zip(bc, ours))
    dc = 0.0
    if mv.startswith("imp") and mv != "impulse":
        cb, co = _course(bc), _course(ours)
        dc = max((abs(x - y) for x, y in zip(cb, co) if x is not None and y is not None), default=0.0)
    ok = dv <= 0.10 and dw <= 0.008 and dc <= 3.0
    close = dv <= 0.3 and dw <= 0.02 and dc <= 8.0
    what = (f"{ship} {mv} mf={mf:g}" + (f"→{float(mf2):g}@{t2:g}s" if mf2 != "none" else "")
            + (f" tf={tf:g}" if mv != "impulse" else "") + f" Engines {ipw:g} pods {ic:g}: whole-curve replay")
    record(f"MR-{fname}-{shot['index']:02d}", "Movement", what, "BC curve (0.05 s rows)",
           f"max |Δspeed| {dv:.3f}, max |Δturn| {dw:.4f}" + (f", max |Δcourse| {dc:.1f}°" if mv.startswith("imp") and mv != "impulse" else ""),
           "match" if ok else "close" if close else "wrong")

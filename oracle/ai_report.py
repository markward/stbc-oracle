"""Reduce an --ai capture (docs/results/ai_*.json) to the engagement facts
the bible quotes: reaction time, opening ranges per weapon, closest
approach, pass structure (approach / turn / break-away), speed and turn
envelopes, and damage dealt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def passes(mr: list[dict]) -> list[dict]:
    """Split the range trace into closing / opening legs with their extremes."""
    legs = []
    cur = None
    for a, b in zip(mr, mr[1:]):
        d = b["rng"] - a["rng"]
        kind = "close" if d < -0.01 else ("open" if d > 0.01 else None)
        if kind is None:
            continue
        if cur is None or cur["kind"] != kind:
            if cur is not None and cur["t1"] - cur["t0"] > 1.0:
                legs.append(cur)
            cur = {"kind": kind, "t0": a["t"], "t1": b["t"], "r0": a["rng"], "r1": b["rng"],
                   "vmax": b["sp"]}
        else:
            cur["t1"] = b["t"]
            cur["r1"] = b["rng"]
            cur["vmax"] = max(cur["vmax"], b["sp"])
    if cur is not None and cur["t1"] - cur["t0"] > 1.0:
        legs.append(cur)
    return legs


def report(res: dict) -> dict:
    mr = res["motion_rows"]
    a = res["rows"]
    t_act = res["params"]["fire_at"]
    out: dict = {"name": res.get("name"), "attacker": res["meta"].get("attacker_name"),
                 "ai_level": res["params"].get("ai_level"), "duration": mr[-1]["t"] if mr else None}
    moving = [x for x in mr if x["sp"] > 0.05]
    out["reaction_s"] = round(moving[0]["t"] - t_act, 2) if moving else None
    for tag, name in (("P", "phaser"), ("U", "pulse"), ("T", "torpedo")):
        rs = [x for x in mr if tag in x.get("fire", "")]
        if rs:
            out[f"{name}_first_fire_t"] = round(rs[0]["t"], 2)
            out[f"{name}_open_range"] = round(rs[0]["rng"], 1)
            out[f"{name}_range_min_max"] = (round(min(x["rng"] for x in rs), 1), round(max(x["rng"] for x in rs), 1))
            out[f"{name}_duty"] = round(len(rs) / len(mr), 3)
    out["range_min"] = round(min(x["rng"] for x in mr), 1)
    out["range_max_after_start"] = round(max(x["rng"] for x in moving), 1) if moving else None
    out["speed_max"] = round(max(x["sp"] for x in mr), 3)
    out["angvel_max"] = round(max((sum(v * v for v in x["w"])) ** 0.5 for x in mr), 3)
    out["impulse_limits"] = res["meta"].get("attacker_impulse")
    out["passes"] = [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in leg.items()} for leg in passes(mr)][:12]
    if a:
        first = next(x for x in a if x["t"] >= t_act)
        last = a[-1]
        out["shield_damage"] = [round(x - y) for x, y in zip(first["sh"], last["sh"])]
        out["hull_damage"] = round(first["h"] - last["h"])
        out["attacker_hull_damage"] = round(first.get("ah", 0) - last.get("ah", 0))
    return out


def main(argv=None) -> int:
    files = [Path(x) for x in (argv or sys.argv[1:])]
    if not files:
        files = sorted((Path(__file__).resolve().parents[1] / "docs" / "results").glob("ai_*.json"))
    for f in files:
        print(f"### {f.stem}")
        print(json.dumps(report(json.loads(f.read_text())), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

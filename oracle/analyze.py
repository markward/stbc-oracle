"""Turn docs/oracle/results/*.json into the numbers the behaviour bible quotes.

Every function here is pure and takes one parsed result; ``main`` prints a
report per result file so the bible's tables can be regenerated from the raw
captures rather than re-typed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"


def damage_events(rows: list[dict]) -> list[dict]:
    """Per-sample deltas: shield (sum over faces), hull, face fraction."""
    ev = []
    for a, b in zip(rows, rows[1:]):
        d_sh = [x - y for x, y in zip(a["sh"], b["sh"])]
        d_h = a["h"] - b["h"]
        if any(abs(x) > 0.01 for x in d_sh) or abs(d_h) > 0.01:
            ev.append({"t": b["t"], "d_sh": d_sh, "d_h": d_h, "sh_after": b["sh"], "h_after": b["h"]})
    return ev


def firing_window(rows: list[dict]) -> tuple[float, float, int] | None:
    fired = [r for r in rows if any(r.get("fi", []))]
    if not fired:
        return None
    return fired[0]["t"], fired[-1]["t"], max(sum(r["fi"]) for r in fired)


def weapon_summary(res: dict) -> dict:
    """Baselined at act time (+50 ms): shield presets happen then, so the
    pre-act samples must not count as damage.  Hits are detected from the
    shield/hull deltas, never from the firing flags - torpedo tubes never
    report IsFiring."""
    t_act = res["params"]["fire_at"] + 0.05
    rows = [r for r in res["rows"] if r["t"] >= t_act]
    out: dict = {"name": res.get("name"), "params": res["params"]}
    if not rows:
        return out
    first, last = rows[0], rows[-1]
    ev = damage_events(rows)
    hits = [e for e in ev if sum(e["d_sh"]) + e["d_h"] > 0.5]
    regen = [e for e in ev if sum(e["d_sh"]) < -0.01 and e["d_h"] <= 0.01]
    out["total_shield"] = [round(a - b, 1) for a, b in zip(first["sh"], last["sh"])]
    out["total_hull"] = round(first["h"] - last["h"], 1)
    out["max_faces"] = [float(x) for x in res["meta"].get("target_max_shields", "").split(",") if x]
    fw = firing_window(res["rows"])
    if fw:
        out["fire_on"], out["fire_off"], out["max_emitters"] = fw
        out["windup_s"] = round(hits[0]["t"] - fw[0], 3) if hits else None
    out["first_damage"] = hits[0]["t"] if hits else None
    out["last_damage"] = hits[-1]["t"] if hits else None
    if hits:
        sizes = sorted(round(sum(e["d_sh"]) + e["d_h"], 2) for e in hits)
        out["hit_count"] = len(hits)
        out["hit_size_median"] = sizes[len(sizes) // 2]
        out["hit_size_min"], out["hit_size_max"] = sizes[0], sizes[-1]
        gaps = sorted(round(b["t"] - a["t"], 3) for a, b in zip(hits, hits[1:]))
        out["hit_gap_median"] = gaps[len(gaps) // 2] if gaps else None
        span = (hits[-1]["t"] - hits[0]["t"]) or 1e-9
        out["rate_per_s"] = round((sum(out["total_shield"]) + out["total_hull"]) / span, 1)
        # pass-through: hull share of each hit vs facing fraction at the time
        pt = []
        for e in hits:
            tot = sum(e["d_sh"]) + e["d_h"]
            face = max(range(6), key=lambda i: e["d_sh"][i]) if any(e["d_sh"]) else None
            if face is not None and out["max_faces"]:
                frac = e["sh_after"][face] / out["max_faces"][face]
                pt.append((round(frac, 3), round(e["d_h"] / tot, 3)))
        out["passthrough_by_face_fraction"] = pt
    if regen:
        rg = [(-sum(e["d_sh"]), e["t"]) for e in regen]
        gaps = [b[1] - a[1] for a, b in zip(rg, rg[1:])]
        out["regen_step"] = round(rg[0][0], 2)
        out["regen_period_s"] = round(sorted(gaps)[len(gaps) // 2], 3) if gaps else None
    # subsystem damage
    srows = [r for r in (res.get("sub_rows") or []) if r["t"] >= t_act]
    if srows and res.get("subsystems"):
        d = [a - b for a, b in zip(srows[0]["s"], srows[-1]["s"])]
        out["subsystem_damage"] = {sub["name"]: round(x, 1)
                                   for sub, x in zip(res["subsystems"], d) if abs(x) > 0.05}
    return out


def motion_summary(res: dict) -> dict:
    rows = res.get("motion_rows") or []
    out: dict = {"name": res.get("name"), "params": res["params"]}
    if not rows:
        return out
    t_act = res["params"]["fire_at"]
    moving = [r for r in rows if r["t"] >= t_act]
    sp = [r["sp"] for r in moving]
    out["speed_max"] = round(max(sp), 4)
    out["speed_final"] = round(sp[-1], 4)
    # time to 95% of max speed and mean acceleration over the first second
    target = 0.95 * max(sp)
    out["t_to_95pct"] = round(next((r["t"] - t_act for r in moving if r["sp"] >= target), -1), 3)
    first_s = [r for r in moving if r["t"] - t_act <= 1.0]
    if len(first_s) >= 2:
        out["accel_first_second"] = round((first_s[-1]["sp"] - first_s[0]["sp"]) / (first_s[-1]["t"] - first_s[0]["t"]), 4)
    w = [(sum(x * x for x in r["w"]) ** 0.5) for r in moving]
    out["angvel_max"] = round(max(w), 5)
    out["angvel_final"] = round(w[-1], 5)
    tw = 0.95 * max(w) if max(w) > 0 else 0
    out["t_to_95pct_angvel"] = round(next((r["t"] - t_act for r, ww in zip(moving, w) if ww >= tw), -1), 3) if tw else None
    fw0 = moving[0]["fw"]
    out["heading_change_deg"] = None
    if fw0:
        import math
        fw1 = moving[-1]["fw"]
        dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(fw0, fw1))))
        out["heading_change_deg"] = round(math.degrees(math.acos(dot)), 2)
    out["impulse"] = res["meta"].get("attacker_impulse")
    out["mass"] = res["meta"].get("attacker_mass")
    if "cut" in " ".join(res["boot"].keys()):
        out["cut_marker"] = [v for k, v in res["boot"].items() if k.endswith("cut")]
    return out


def main(argv=None) -> int:
    files = [Path(a) for a in (argv or sys.argv[1:])] or sorted(RESULTS.glob("*.json"))
    for f in files:
        res = json.loads(f.read_text())
        s = motion_summary(res) if res["params"].get("motion", "none") != "none" else weapon_summary(res)
        print(f"### {f.stem}")
        print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

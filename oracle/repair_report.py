"""Reduce the repair_* captures (bible 16): per-subsystem repair rate after the preset.

For each capture: the repair system's stock numbers (meta target_repair), and for
every preset subsystem its condition at the first post-preset sample, at the end,
the mean rate over that span, the discrete step size and the step period.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"


def reduce(path: Path) -> dict:
    r = json.loads(path.read_text())
    names = [s["name"] for s in r["subsystems"]]
    rows = r["sub_rows"]
    hull_rows = r["rows"]
    preset = r["params"].get("sub_preset", "none")
    out = {"name": path.stem, "repair": r["meta"].get("target_repair"), "subs": {}}
    for item in preset.split(";"):
        if "=" not in item:
            continue
        nm = item.split("=")[0].replace("_", " ")
        i = names.index(nm)
        if nm == "Hull":   # row a carries hull at 0.1 resolution; row b rounds to 1
            series = [(x["t"], x["h"]) for x in hull_rows]
        else:
            series = [(x["t"], x["s"][i]) for x in rows]
        mx = r["subsystems"][i]["max"]
        # the preset lands between two samples: start at the first sample below max
        k = next((j for j, (_, v) in enumerate(series) if v < mx * 0.999), None)
        if k is None:
            out["subs"][nm] = {"note": "never below max"}
            continue
        t0, v0 = series[k]
        t1, v1 = series[-1]
        steps = [(t, b - a) for (_, a), (t, b) in zip(series[k:], series[k + 1:]) if b - a > 1e-6]
        out["subs"][nm] = {
            "max": mx, "start": v0, "end": v1, "span_s": round(t1 - t0, 2),
            "rate_per_s": round((v1 - v0) / (t1 - t0), 3) if t1 > t0 else None,
            "steps": len(steps),
            "step_size": round(sorted(d for _, d in steps)[len(steps) // 2], 3) if steps else 0.0,
        }
    rq = r.get("repair_rows") or []
    if rq:
        out["queued_first"] = [names[i] for i, q in enumerate(rq[0]["rq"]) if q == 1]
        out["queued_last"] = [names[i] for i, q in enumerate(rq[-1]["rq"]) if q == 1]
    return out


def main(argv=None) -> int:
    for p in sorted(RESULTS.glob("repair_*.json")):
        print(json.dumps(reduce(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Reduce scene_<mission>.json captures (Oracle/OracleScene.py) to Markdown.

    python oracle/scene_report.py                 # all docs/results/scene_*.json
    python oracle/scene_report.py E3M2 E4M5       # a subset

For each mission: the set the player is in, every ship in it at the first
snapshot, at the snapshot nearest +30 s and at the last one, with what changed
(position, speed, hull, shields, AI, alert, cutscene).  Writes
docs/mission-scenes.md (or prints with --stdout).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "docs" / "results"
OUT = Path(__file__).resolve().parent.parent / "docs" / "mission-scenes.md"

ALERT = {0: "green", 1: "yellow", 2: "red"}


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _nearest(metas, t):
    return min(metas, key=lambda m: abs(m["t"] - t))


def _by_snap(rows):
    out: dict[int, dict[str, dict]] = {}
    for r in rows:
        out.setdefault(r["n"], {})[r.get("name", "?")] = r
    return out


def _ship_line(s, h, s0=None):
    p = s.get("p") or [0, 0, 0]
    fw = s.get("fw") or [0, 0, 0]
    hull = h.get("hull", "-") if h else "-"
    sh = h.get("sh") if h else None
    shm = h.get("shm") if h else None
    if sh and shm:
        frac = [c / m if m else 0.0 for c, m in zip(sh, shm)]
        shtxt = " ".join(f"{f:.2f}" for f in frac)
    else:
        shtxt = "-"
    moved = ""
    if s0 is not None and s0.get("p"):
        d = _dist(p, s0["p"])
        moved = f"{d:.1f}"
    flags = []
    if h:
        if h.get("pl"):
            flags.append("player")
        if h.get("hid"):
            flags.append("hidden")
        if h.get("clk"):
            flags.append("cloaked")
        if h.get("dy"):
            flags.append("dying" if h.get("dy") == 1 else "dead")
    return (f"| {s.get('name', '?')} | `{(s.get('scr') or '-').replace('ships.', '')}` | "
            f"{p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f} | {fw[0]:.2f}, {fw[1]:.2f}, {fw[2]:.2f} | "
            f"{s.get('sp', 0):.2f} | {moved} | {hull} | {shtxt} | "
            f"{ALERT.get(h.get('al'), '-') if h else '-'} | {h.get('ai', '-') if h else '-'} | "
            f"{h.get('tgt', '-') if h else '-'} | {' '.join(flags)} |")


def report(path: Path) -> str:
    d = json.loads(path.read_text())
    name = d.get("name") or path.stem
    mission = (d.get("params") or {}).get("mission", "?")
    metas = d.get("scene_meta_rows") or []
    if not metas:
        return f"## {mission}\n\nno snapshots (`{path.name}`)\n"
    srows = _by_snap(d.get("scene_rows") or [])
    hrows = _by_snap(d.get("scene_health_rows") or [])
    first = metas[0]
    m30 = _nearest(metas, first["t"] + 30.0)
    last = metas[-1]
    lines = [f"## {mission} (`{path.name}`)", ""]
    sets = sorted({m["set"] for m in metas})
    cuts = [m["t"] for m in metas if m.get("cut") == 1]
    lines.append(f"Player set: {', '.join(sets)}; {len(metas)} snapshots {first['t']:.1f}–{last['t']:.1f} s; "
                 f"player `{last.get('player')}`; ships {first['ships']} → {last['ships']}; "
                 f"cutscene mode at {len(cuts)}/{len(metas)} snapshots"
                 + (f" (t {min(cuts):.0f}–{max(cuts):.0f})" if cuts else "") + ".")
    lines.append("")
    hdr = ("| ship | script | position | forward | speed | moved from t0 | hull | shield faces (fraction) | alert | AI | target | flags |\n"
           "|---|---|---|---|---|---|---|---|---|---|---|---|")
    for label, m in (("t = 0", first), ("t ≈ +30 s", m30), (f"t = {last['t']:.0f} s", last)):
        if m is first or m["n"] != first["n"]:
            lines.append(f"### {label} (snapshot {m['n']}, t = {m['t']:.1f} s, set `{m['set']}`, cutscene {m.get('cut')})")
            lines.append("")
            lines.append(hdr)
            ships = srows.get(m["n"], {})
            for nm in sorted(ships, key=lambda k: (not (hrows.get(m["n"], {}).get(k, {}).get("pl")), k)):
                s = ships[nm]
                h = hrows.get(m["n"], {}).get(nm)
                s0 = srows.get(first["n"], {}).get(nm)
                lines.append(_ship_line(s, h, s0 if m is not first else None))
            gone = set(srows.get(first["n"], {})) - set(ships)
            new = set(ships) - set(srows.get(first["n"], {}))
            if gone or new:
                lines.append("")
                if gone:
                    lines.append(f"Gone since t0: {', '.join(sorted(gone))}.")
                if new:
                    lines.append(f"New since t0: {', '.join(sorted(new))}.")
            lines.append("")
    # events: ships appearing/disappearing, hull changes, over all snapshots
    events = []
    prev = None
    for m in metas:
        cur = set(srows.get(m["n"], {}))
        if prev is not None:
            for nm in sorted(cur - prev):
                events.append(f"{m['t']:.0f} s: `{nm}` appears")
            for nm in sorted(prev - cur):
                events.append(f"{m['t']:.0f} s: `{nm}` gone")
        prev = cur
    if events:
        lines.append("Ship comings and goings: " + "; ".join(events) + ".")
        lines.append("")
    return "\n".join(lines)


def main(argv):
    stdout = "--stdout" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    files = sorted(RESULTS.glob("scene_*.json"))
    if wanted:
        files = [f for f in files if any(w in f.name for w in wanted)]
    parts = ["# Mission scenes — what the stock game puts in the player's set",
             "",
             "Generated by `oracle/scene_report.py` from `docs/results/scene_<mission>.json` "
             "(Oracle/OracleScene.py: the mission loaded through the developers' "
             "Test Game override, nothing touched, every ship in the player's set "
             "dumped every 5 s for 90 s). Positions in GU, world axes; shield faces in "
             "hardpoint order front/rear/top/bottom/port/starboard as fractions of max; "
             "\"moved\" is the straight-line distance from the t0 position.",
             ""]
    for f in files:
        parts.append(report(f))
    text = "\n".join(parts)
    if stdout:
        print(text)
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT} ({len(files)} missions)")


if __name__ == "__main__":
    main(sys.argv[1:])

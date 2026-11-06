"""Shared loader for oracle session results (single run or resumed multi-part)."""
import json
import re


def runs(path):
    r = json.load(open(path))
    return [(p["shot_index"], p["result"]) for p in r["parts"]] if "parts" in r else [(r.get("shot_index"), r)]


def shots(path):
    """Yield dicts: index, spec(str), start, end, run(result) for every completed shot."""
    out = []
    for idx_map, r in runs(path):
        local = sorted((int(k.split("_shot")[1]), v) for k, v in r["boot"].items() if re.match(r"\d+_shot\d+$", k))
        for j, v in local:
            g = idx_map[j] if idx_map else j
            out.append({"index": g, "spec": v, "run": r,
                        "start": float(re.search(r"start=([\d.]+)", v).group(1)),
                        "end": float(re.search(r"end=([\d.]+)", v).group(1))})
    return sorted(out, key=lambda s: s["index"])


def xrows(r, kind, tag, t0=-1e9, t1=1e9):
    out = []
    for l in r["raw_rows"]:
        if not l.startswith(kind + " " + tag + " "):
            continue
        p = l.split()
        d = dict(x.split("=", 1) for x in p[2:] if "=" in x)
        d["t"] = float(d["t"])
        if t0 <= d["t"] < t1:
            out.append(d)
    return out


def chunked(r, kind, tag, key, t0=-1e9, t1=1e9):
    """Re-join chunked list rows (xc/xn/xw/xq): {t: [values...]}"""
    acc = {}
    for d in xrows(r, kind, tag, t0, t1):
        acc.setdefault(d["t"], {})[int(d["k"])] = d[key].split(",")
    return {t: sum((ch[k] for k in sorted(ch)), []) for t, ch in sorted(acc.items())}


def tap(r, t0=-1e9, t1=1e9):
    for l in r.get("combat_tap", []):
        p = l.split()
        if len(p) < 2 or p[0].startswith("#"):
            continue
        t = float(p[0])
        if t0 <= t < t1:
            yield t, p[1], dict(x.split("=", 1) for x in p[2:] if "=" in x)


from pathlib import Path
CATALOGUES = [Path(__file__).resolve().parents[2] / "results_mac" / "catalogue_galaxy_sovereign.json"]
_names = None


def sub_names(r, tag):
    """Subsystem names in walk order (telemetry order) for ship tag of run r, from a catalogue
    run of the same ship class (catalogue tags: T = its target class, A = its attacker class)."""
    global _names
    if _names is None:
        _names = {}
        for c in CATALOGUES:
            cr = json.load(open(c))
            for tg, cls in (("T", cr["params"]["target"]), ("A", cr["params"]["attacker"])):
                rows = sorted((int(l.split()[2]), dict(x.split("=", 1) for x in l.split()[3:])["name"])
                              for l in cr["raw_rows"] if l.startswith("cs " + tg + " "))
                _names[cls] = [n for _, n in rows]
    cls = r["params"]["target" if tag == "T" else "attacker"]
    return _names.get(cls, [])


def emitter_names(r, tag):
    """Emitter (phaser/pulse/tube/tractor) names in telemetry order, from the catalogue types."""
    cr = json.load(open(CATALOGUES[0]))
    cls = r["params"]["target" if tag == "T" else "attacker"]
    ctag = "T" if cr["params"]["target"] == cls else "A"
    out = []
    for l in cr["raw_rows"]:
        if l.startswith("cs " + ctag + " "):
            kv = dict(x.split("=", 1) for x in l.split()[3:])
            t = kv["types"].split(",")
            if any(x in t for x in ("PhaserBank", "PulseWeapon", "TorpedoTube", "TractorBeamProjector")):
                out.append((int(l.split()[2]), kv["name"]))
    return [n for _, n in sorted(out)]

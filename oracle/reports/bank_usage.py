"""How each energy weapon (phaser bank, pulse cannon) is used, original vs Dauntless.

Original: xw rows (OracleTelemetry: every emitter's e/<charge>/<firing> per sample, in catalogue order;
names from tele_X_emitters, which is cut at 178 characters, completed from tele_X_subs). Dauntless:
the 'ew' map in each track row's status (scorecard/dauntless_aim_duels.py, since 2026-10-17).

Per (ship class, emitter):
  fire%      share of the fight (before either ship is dying) the emitter is firing
  by range   that share split by the range between the ships (GU)
  start/stop median charge when firing begins / ends
  recharge   median charge gained per second while idle and below full
  drain      median charge lost per second while firing
Per class: mean number of emitters firing at once, while any is.

usage: python bank_usage.py --orig <globs> --dn <globs> [--classes A,B]
"""
import argparse
import collections
import glob
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duel_summary as ds  # noqa: E402

RX = re.compile(r"duel_(\w+?)_enemy[\d.]+_vs_(\w+?)_player")
RANGES = (0, 60, 100, 150, 1e9)


def _orig_names(m, tag, n, known):
    """Emitter names in xw order. tele_X_emitters is cut at 178 chars; the rest come from tele_X_subs
    (13-char names, every subsystem) matched against emitter names known from Dauntless."""
    raw = m.get("tele_%s_emitters" % tag, "")
    names = raw.split(",")
    if len(names) == n and len(raw) < 178:
        return names
    subs, k = [], 0
    while "tele_%s_subs%d" % (tag, k) in m:
        subs += m["tele_%s_subs%d" % (tag, k)].split(",")
        k += 1
    # 13-char names are ambiguous ("Ventral_Phase" x4): hand out each prefix's known names in order,
    # after the complete names tele_X_emitters did carry.
    full = [x for x in names[:-1] if x in known]
    queues = collections.defaultdict(list)
    for x in sorted(known):
        if x not in full:
            queues[x[:13]].append(x)
    seq = [x for x in subs if x in queues or x[:13] in [f[:13] for f in full] or ("Tract" in x and x != "Tractors")]
    out = list(full)
    for x in seq[len(full):]:
        out.append(queues[x].pop(0) if queues.get(x) else x)
    return out[:n] if len(out) >= n else None


def orig_series(path, known):
    """{tag: (class, names, [(t, range, [(charge, firing) or None per emitter])])}"""
    d = ds.load_json(path)
    m = d["meta"]
    a, t = RX.search(path).groups()
    dying = min([float(l.split()[2][2:]) for l in d["raw_rows"] if l.startswith("xz ") and " dy=1" in l] or [1e9])
    pos = {"A": {}, "T": {}}
    w = {"A": collections.defaultdict(dict), "T": collections.defaultdict(dict)}
    for l in d["raw_rows"]:
        p = l.split()
        if p[0] == "xm" and p[1] in "AT" and "p=" in l:
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            pos[p[1]][round(float(kv["t"]), 3)] = [float(x) for x in kv["p"].split(",")]
        elif p[0] == "xw" and p[1] in "AT":
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            w[p[1]][round(float(kv["t"]), 3)][int(kv["k"])] = kv["w"].split(",")
    out = {}
    for tag, cls in (("A", a), ("T", t)):
        rows = []
        for tt in sorted(w[tag]):
            if tt >= dying or tt not in pos["A"] or tt not in pos["T"]:
                continue
            ent = []
            for k in sorted(w[tag][tt]):
                ent += w[tag][tt][k]
            vals = []
            for e in ent:
                if e.startswith("e/"):
                    _, c, f = e.split("/")
                    vals.append((float(c), int(f)))
                else:
                    vals.append(None)
            rows.append((tt, math.dist(pos["A"][tt], pos["T"][tt]), vals))
        if not rows:
            continue
        names = _orig_names(m, tag, len(rows[0][2]), known.get(cls, set()))
        if names is None:
            continue
        out[tag] = (cls, names, rows)
    return out


def dn_series(path):
    g = ds.load_json(path)
    out = {}
    for tag, st, cls in (("A", "sA", g["enemy"]), ("T", "sT", g["player"])):
        rows, names = [], None
        for r in g["track"]:
            if r["t"] > g["t_end"]:
                break
            ew = (r.get(st) or {}).get("ew")
            if not ew:
                continue
            if names is None:
                names = list(ew)
                out.setdefault("_tubes", {})[tag] = [x.replace(" ", "_") for x in (g.get("tube_names") or {}).get(tag, [])]
            rows.append((r["t"], math.dist(r["A"][:3], r["T"][:3]), [tuple(ew[n]) if n in ew else None for n in names]))
        if rows:
            out[tag] = (cls, names, rows)
    return out


def accumulate(acc, lit, cls, names, rows):
    for i, nm in enumerate(names):
        if "Tract" in nm:
            continue
        a = acc[(cls, nm)]
        prev = None
        for (t, rng, vals) in rows:
            v = vals[i] if i < len(vals) else None
            if v is None:
                prev = None
                continue
            c, f = v
            b = next(j for j in range(len(RANGES) - 1) if RANGES[j] <= rng < RANGES[j + 1])
            a["n"] += 1
            a["fire"] += f
            a["rn"][b] += 1
            a["rf"][b] += f
            if prev is not None:
                pt, pc, pf = prev
                dt = t - pt
                if f and not pf:
                    a["start"].append(pc)
                if pf and not f:
                    a["stop"].append(c)
                if dt > 0 and not f and not pf and c > pc and c < a.setdefault("max", 0) - 0.01:
                    a["rech"].append((c - pc) / dt)
                if dt > 0 and f and pf and c < pc:
                    a["drain"].append((pc - c) / dt)
            a["max"] = max(a.get("max", 0), c)
            prev = (t, c, f)
    for (t, rng, vals) in rows:
        k = sum(1 for i, v in enumerate(vals) if v is not None and v[1] and "Tract" not in names[i])
        if k:
            lit[cls].append(k)


def new_acc():
    return collections.defaultdict(lambda: {"n": 0, "fire": 0, "rn": [0] * 4, "rf": [0] * 4,
                                            "start": [], "stop": [], "rech": [], "drain": []})


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", nargs="*", default=[])
    ap.add_argument("--dn", nargs="*", default=[])
    ap.add_argument("--classes", default="")
    a = ap.parse_args()
    want = set(a.classes.split(",")) if a.classes else None
    D, Dl = new_acc(), collections.defaultdict(list)
    known = collections.defaultdict(set)
    for g in a.dn:
        for f in sorted(glob.glob(g)):
            ser = dn_series(f)
            for tag, tubes in ser.pop("_tubes", {}).items():
                known[ser[tag][0] if tag in ser else None].update(tubes)
            for tag, (cls, names, rows) in ser.items():
                known[cls].update(names)
                if want is None or cls in want:
                    accumulate(D, Dl, cls, names, rows)
    O, Ol = new_acc(), collections.defaultdict(list)
    for g in a.orig:
        for f in sorted(glob.glob(g)):
            try:
                ser = orig_series(f, known)
            except Exception as e:
                print("skip", f, e, file=sys.stderr)
                continue
            for tag, (cls, names, rows) in ser.items():
                if want is None or cls in want:
                    accumulate(O, Ol, cls, names, rows)
    hdr = "fire%% [<60 60-100 100-150 150+]   start stop  rech  drain"
    print("%-11s %-20s | original: %s | Dauntless: %s" % ("class", "emitter", hdr, hdr))
    for key in sorted(set(O) | set(D)):
        cells = []
        for acc in (O, D):
            x = acc.get(key)
            if not x or not x["n"]:
                cells.append("%-58s" % "-")
                continue
            br = " ".join("%3.0f" % (100.0 * x["rf"][j] / x["rn"][j]) if x["rn"][j] else "  -" for j in range(4))
            cells.append("%5.1f [%s]  %5.2f %5.2f %5.3f %5.2f" % (
                100.0 * x["fire"] / x["n"], br, med(x["start"]), med(x["stop"]), med(x["rech"]), med(x["drain"])))
        print("%-11s %-20s | %s | %s" % (key[0], key[1][:20], cells[0], cells[1]))
    print()
    for cls in sorted(set(Ol) | set(Dl)):
        o, d = Ol.get(cls, []), Dl.get(cls, [])
        print("%-11s emitters firing at once (while any): original mean %.2f max %s | Dauntless mean %.2f max %s" % (
            cls, sum(o) / len(o) if o else float("nan"), max(o) if o else "-",
            sum(d) / len(d) if d else float("nan"), max(d) if d else "-"))


if __name__ == "__main__":
    main()

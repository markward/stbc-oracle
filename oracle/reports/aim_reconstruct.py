"""Reconstruct the stock AI's chosen target subsystem from its phaser hits.

The AI fires at StartFiring(target, chosenSubsystem.GetPositionTG()), so every phaser hit lies on the line from the
firing ship through the target's hull toward the chosen subsystem's (runtime) position. For each recorded hit
(CombatTap DS, target-model frame), put the shooter into the target's model frame (telemetry xm position + xo
orientation, nearest sample), extend the line past the hit, and pick the subsystem whose position lies closest to it
beyond the hull. The native FireScript exposes its choice nowhere else (OracleAIProbe: py=0, fields never written).

usage: aim_reconstruct.py <duel.json> [<catalogue with cr/cs rows for both ships>]
Prints, per shooter, the chosen-subsystem sequence (run-length) and the share of hits per subsystem; with --json, writes
<duel>.aim.json.
"""
import json, math, re, sys, bisect


def vec(s):
    return [float(x) for x in s.split(",")]


def sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def norm(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def positions(cat, tag):
    """Runtime subsystem positions (model frame) + names for one ship tag of a catalogue run."""
    rr = cat["raw_rows"]
    names, pos = {}, {}
    for l in rr:
        if l.startswith("cs %s " % tag):
            names[int(l.split()[2])] = re.search(r"name=(.*?) types=", l).group(1)
        if l.startswith("cr %s " % tag) and " ShipSubsystem.GetPosition=" in l:
            pos[int(l.split()[2])] = vec(l.split("=")[1])
    return {names[i]: p for i, p in pos.items() if i in names}


def telemetry(rr, kind, tag):
    out = []
    for l in rr:
        if l.startswith("%s %s " % (kind, tag)):
            kv = dict(x.split("=", 1) for x in l.split()[2:] if "=" in x)
            if "t" in kv and ("p" in kv or "fw" in kv):
                out.append((float(kv["t"]), kv))
    out.sort(key=lambda x: x[0])
    return out


def interp(series, t, keys=("p", "fw", "up")):
    """Linear interpolation of vector fields between the bracketing samples (falls back to nearest)."""
    ts = [x[0] for x in series]
    i = bisect.bisect_left(ts, t)
    if i <= 0 or i >= len(series):
        return nearest(series, t)
    (t0, a), (t1, b) = series[i - 1], series[i]
    if t1 - t0 <= 0 or t1 - t0 > 1.0:
        return nearest(series, t)
    w = (t - t0) / (t1 - t0)
    out = dict(a)
    for k in keys:
        if k in a and k in b:
            va, vb = vec(a[k]), vec(b[k])
            out[k] = ",".join("%.6f" % (va[j] + (vb[j] - va[j]) * w) for j in range(3))
    return out


def nearest(series, t):
    ts = [x[0] for x in series]
    i = bisect.bisect_left(ts, t)
    cands = [j for j in (i - 1, i) if 0 <= j < len(series)]
    return min((series[j] for j in cands), key=lambda x: abs(x[0] - t))[1] if cands else None


def reconstruct(duel_path, cat_path):
    d = json.load(open(duel_path))
    cat = json.load(open(cat_path))
    rr = d["raw_rows"]
    meta = d["meta"]
    # which tag is which ship class: the catalogue has T = Galaxy, A = Sovereign (attacker Sovereign, target Galaxy)
    cls = {"T": meta.get("in_target"), "A": meta.get("in_attacker")}
    cat_cls = {"T": cat["meta"].get("in_target"), "A": cat["meta"].get("in_attacker")}
    subpos = {}
    for tag in ("A", "T"):
        src = [k for k, v in cat_cls.items() if v == cls[tag]][0]
        subpos[tag] = positions(cat, src)
    ships = []
    for l in d.get("combat_tap") or []:
        q = l.split()
        if len(q) > 2 and q[1] == "DS":
            sp = dict(x.split("=", 1) for x in q[2:] if "=" in x).get("ship", "").upper().lstrip("0")
            if sp and sp not in ships:
                ships.append(sp)
    pa, pt = (meta.get("ptr_attacker") or "").upper().lstrip("0X"), (meta.get("ptr_target") or "").upper().lstrip("0X")
    if pa and pt:
        mappings = [{pa: "A", pt: "T"}]
    elif len(ships) == 2:
        # duel runs record no ship pointers: try both, keep the one whose lines pass closest to real subsystems
        mappings = [{ships[0]: "A", ships[1]: "T"}, {ships[0]: "T", ships[1]: "A"}]
    else:
        mappings = [{ships[0]: "T"}, {ships[0]: "A"}] if ships else [{}]
    best_hits, best_err = None, None
    for ptr in mappings:
        h = _reconstruct_with(d, rr, ptr, subpos)
        errs = sorted(x[4] for x in h)
        e = errs[len(errs) // 2] if errs else 1e9
        if best_err is None or e < best_err:
            best_hits, best_err = h, e
    return best_hits


def _reconstruct_with(d, rr, ptr, subpos):
    xm = {t: telemetry(rr, "xm", t) for t in ("A", "T")}
    xo = {t: telemetry(rr, "xo", t) for t in ("A", "T")}
    hits = []
    for l in d.get("combat_tap") or []:
        if l.startswith("#"):
            continue
        p = l.split()
        if len(p) < 2 or p[1] != "DS":
            continue
        kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
        if kv.get("r") != "0.1500":          # phaser hits only (torpedoes 0.13/0.14, collisions 1.5)
            continue
        tgt = ptr.get(kv["ship"].upper().lstrip("0"))
        if tgt is None:
            continue
        shooter = "A" if tgt == "T" else "T"
        t = float(p[0])
        ms, mt, ot = nearest(xm[shooter], t), nearest(xm[tgt], t), nearest(xo[tgt], t)
        if not (ms and mt and ot):
            continue
        fw, up = norm(vec(ot["fw"])), norm(vec(ot["up"]))
        right = cross(fw, up)
        dw = sub(vec(ms["p"]), vec(mt["p"]))
        S = [dot(dw, right), dot(dw, fw), dot(dw, up)]       # shooter in target model frame
        H = vec(kv["pos"])
        u = norm(sub(H, S))
        best = None
        for nm, P in subpos[tgt].items():
            if nm in ("Hull", "Phasers", "Torpedoes", "Tractors", "Impulse_Engines", "Warp_Engines"):
                continue
            w = sub(P, S)
            along = dot(w, u)
            th = dot(sub(H, S), u)
            if along < th - 0.6:                # the aim point lies at or beyond the hull hit
                continue
            perp = math.sqrt(max(0.0, dot(w, w) - along * along))
            if best is None or perp < best[0]:
                best = (perp, nm)
        if best is not None:
            hits.append((t, shooter, tgt, best[1], round(best[0], 3)))
    return hits


def summarise(hits):
    out = {}
    for shooter in ("A", "T"):
        seq = [(t, nm, e) for (t, s, g, nm, e) in hits if s == shooter]
        if not seq:
            continue
        runs = []
        for t, nm, e in seq:
            if runs and runs[-1][1] == nm:
                runs[-1][2] += 1
            else:
                runs.append([round(t, 1), nm, 1])
        share = {}
        for _, nm, _ in seq:
            share[nm] = share.get(nm, 0) + 1
        errs = sorted(e for _, _, e in seq)
        out[shooter] = {"hits": len(seq), "runs": runs, "share": share, "median_perp": errs[len(errs) // 2]}
    return out


if __name__ == "__main__":
    duel = sys.argv[1]
    cat = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "results_mac/hittable_r20_57_150.json"
    hits = reconstruct(duel, cat)
    s = summarise(hits)
    for shooter, r in s.items():
        print("shooter %s: %d phaser hits, median miss distance of chosen subsystem from the line %.3f GU" % (
            shooter, r["hits"], r["median_perp"]))
        print("  share:", sorted(r["share"].items(), key=lambda kv: -kv[1]))
        print("  sequence:", " | ".join("%s %s x%d" % tuple(x) for x in r["runs"][:40]))
    if "--json" in sys.argv:
        json.dump({"hits": hits, "summary": s}, open(duel.replace(".json", ".aim.json"), "w"))

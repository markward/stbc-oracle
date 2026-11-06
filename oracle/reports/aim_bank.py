"""Reconstruct the AI's aim point from phaser hits using the FIRING BANK, not the ship centre.

FireScript fires each weapon system at StartFiring(target, chosenSubsystem.GetPositionTG()); a beam is a straight
line from a point on the firing bank's strip to that aim point, and the recorded hit (CombatTap DS, target model
frame) is where that line meets the hull. For each phaser hit: take the banks the telemetry shows firing (xw IsFiring)
at the nearest sample, put every point of each bank's strip ellipse (mount + fwd*Length*cos(a) + right*Width*sin(a)
over its ArcWidth span, right = fwd x up) into the target's frame, and for every candidate subsystem P find the
smallest distance from the hit H to any segment strip-point -> P. The candidate with the smallest distance is the
aim; its margin over the runner-up says how sure that is. Subsystems sharing one position (a ship's forward tubes)
are reported as a group.

usage: python aim_bank.py <duel.json>...   (stdlib only)
"""
import json, math, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import aim_reconstruct as AR

HARDPOINTS = os.environ.get("ORACLE_SDK_HARDPOINTS")       # the SDK's scripts/ships/Hardpoints folder
CATALOGUE = os.path.join(os.path.dirname(__file__), "..", "..", "results_mac", "hittable_r20_57_150.json")
CAT_TAG = {"Galaxy": "T", "Sovereign": "A"}


def _floats(s):
    return [float(x) for x in s.split(",")]


def banks(cls):
    """Energy-weapon emitters in hardpoint order: name -> dict(mount, fwd, up, L, W, a0, a1)."""
    if not HARDPOINTS:
        sys.exit("aim_bank.py reads the SDK hardpoint sources: set ORACLE_SDK_HARDPOINTS to scripts/ships/Hardpoints")
    src = open(os.path.join(HARDPOINTS, cls.lower() + ".py")).read()
    out = []
    for m in re.finditer(r'^(\w+) = App\.(PhaserProperty|TractorBeamProperty|PulseWeaponProperty)_Create\("([^"]+)"\)', src, re.M):
        var, kind, name = m.group(1), m.group(2), m.group(3)
        g = lambda pat: re.search(r"^" + var + pat, src, re.M)
        b = {"name": name.replace(" ", "_"), "kind": kind, "mount": _floats(g(r"\.SetPosition\(([^)]*)\)").group(1))}
        f = re.search(r"^" + var + r"Forward\.SetXYZ\(([^)]*)\)", src, re.M) or re.search(var + r"Forward = App\.TGPoint3\(\)\s*\n\s*" + var + r"Forward\.SetXYZ\(([^)]*)\)", src)
        u = re.search(r"^" + var + r"Up\.SetXYZ\(([^)]*)\)", src, re.M) or re.search(var + r"Up = App\.TGPoint3\(\)\s*\n\s*" + var + r"Up\.SetXYZ\(([^)]*)\)", src)
        b["fwd"] = AR.norm(_floats(f.group(1))); b["up"] = AR.norm(_floats(u.group(1)))
        L = g(r"\.SetLength\(([^)]*)\)"); W = g(r"\.SetWidth\(([^)]*)\)"); A = g(r"\.SetArcWidthAngles\(([^)]*)\)")
        b["L"] = float(L.group(1)) if L else 0.0
        b["W"] = float(W.group(1)) if W else 0.0
        b["a0"], b["a1"] = _floats(A.group(1)) if A else (0.0, 0.0)
        out.append(b)
    return out


def _kind(name):
    for k in ("Forward_Torpedo", "Aft_Torpedo", "Dorsal_Phaser", "Ventral_Phaser", "Tractor"):
        if k in name:
            return k
    return name


def strip_points(b, n=24):
    right = AR.cross(b["fwd"], b["up"])
    pts = []
    for i in range(n + 1):
        a = b["a0"] + (b["a1"] - b["a0"]) * i / float(n)
        c, s = math.cos(a), math.sin(a)
        pts.append([b["mount"][k] + b["fwd"][k] * b["L"] * c + right[k] * b["W"] * s for k in range(3)])
    return pts


def seg_dist(H, E, P):
    d = AR.sub(P, E); w = AR.sub(H, E)
    L2 = AR.dot(d, d) or 1e-12
    t = max(0.0, min(1.0, AR.dot(w, d) / L2))
    q = [E[k] + d[k] * t for k in range(3)]
    r = AR.sub(H, q)
    return math.sqrt(AR.dot(r, r))


def frame(xo_row):
    fw, up = AR.norm(AR.vec(xo_row["fw"])), AR.norm(AR.vec(xo_row["up"]))
    return AR.cross(fw, up), fw, up


def to_world(p_body, pos, fr):
    r, f, u = fr
    return [pos[k] + r[k] * p_body[0] + f[k] * p_body[1] + u[k] * p_body[2] for k in range(3)]


def to_body(p_world, pos, fr):
    d = AR.sub(p_world, pos)
    return [AR.dot(d, fr[0]), AR.dot(d, fr[1]), AR.dot(d, fr[2])]


def firing(rr, tag, t, n_tubes):
    """Indices (into the energy-emitter list) firing at the sample nearest t (xw rows, chunked)."""
    best = None
    rows = {}
    for l in rr:
        if l.startswith("xw %s " % tag):
            p = l.split()
            ts = float(p[2][2:])
            rows.setdefault(ts, {})[int(p[3][2:])] = p[4][2:].split(",")
    if not rows:
        return []
    ts = min(rows, key=lambda x: abs(x - t))
    flat = []
    for k in sorted(rows[ts]):
        flat += rows[ts][k]
    out = []
    ei = 0
    for w in flat:
        if w.startswith("e/"):
            if w.endswith("/1"):
                out.append(ei)
            ei += 1
    return out


class Duel:
    def __init__(self, path, cat):
        self.d = json.load(open(path))
        self.rr = self.d["raw_rows"]
        meta = self.d["meta"]
        self.cls = {"A": meta.get("in_attacker"), "T": meta.get("in_target")}
        self.subpos = {t: AR.positions(cat, CAT_TAG[c]) for t, c in self.cls.items()}
        self.banks = {t: banks(c) for t, c in self.cls.items()}
        self.xm = {t: AR.telemetry(self.rr, "xm", t) for t in ("A", "T")}
        self.xo = {t: AR.telemetry(self.rr, "xo", t) for t in ("A", "T")}
        # xw rows are slow to rescan per hit: index them once
        self.xw = {"A": {}, "T": {}}
        for l in self.rr:
            if l.startswith("xw "):
                p = l.split()
                self.xw[p[1]].setdefault(float(p[2][2:]), {})[int(p[3][2:])] = p[4][2:].split(",")
        self.xw_t = {k: sorted(v) for k, v in self.xw.items()}

    def firing(self, tag, t):
        import bisect
        ts = self.xw_t[tag]
        if not ts:
            return []
        i = bisect.bisect_left(ts, t)
        # the sample at or just BEFORE the hit: a beam that hits at t was firing then
        j = max(0, min(len(ts) - 1, i - 1 if i > 0 and (i == len(ts) or ts[i] > t) else i))
        flat = []
        for k in sorted(self.xw[tag][ts[j]]):
            flat += self.xw[tag][ts[j]][k]
        out, ei = [], 0
        for w in flat:
            if w.startswith("e/"):
                if w.endswith("/1"):
                    out.append(ei)
                ei += 1
        return out

    def ship_tags(self):
        ships = []
        for l in self.d.get("combat_tap") or []:
            q = l.split()
            if len(q) > 2 and q[1] in ("H", "DS"):
                sp = dict(x.split("=", 1) for x in q[2:] if "=" in x).get("ship", "").upper().lstrip("0")
                if sp and sp not in ships:
                    ships.append(sp)
        return ships

    def aims(self, ptr):
        """Every phaser impact (CombatTap H rows: type 0, radius 0.15) -- shield hits (hull=0, point on the shield
        bubble) as well as hull hits (hull=1, the DS point): both lie on the beam from the bank to the aim point."""
        out = []
        for l in self.d.get("combat_tap") or []:
            p = l.split()
            if len(p) < 2 or p[1] != "H":
                continue
            kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
            if kv.get("type") != "0" or kv.get("rad") != "0.1500":
                continue
            kv["pos"] = kv["op"]
            tgt = ptr.get(kv["ship"].upper().lstrip("0"))
            if tgt is None:
                continue
            sh = "A" if tgt == "T" else "T"
            t = float(p[0])
            fire = self.firing(sh, t)
            bl = [self.banks[sh][i] for i in fire if i < len(self.banks[sh]) and self.banks[sh][i]["kind"] == "PhaserProperty"]
            if not bl:
                continue
            ms, mt = AR.interp(self.xm[sh], t), AR.interp(self.xm[tgt], t)
            os_, ot = AR.interp(self.xo[sh], t), AR.interp(self.xo[tgt], t)
            fs, ft = frame(os_), frame(ot)
            ps, pt = AR.vec(ms["p"]), AR.vec(mt["p"])
            E = []
            for b in bl:
                for q in strip_points(b):
                    E.append(to_body(to_world(q, ps, fs), pt, ft))
            H = AR.vec(kv["pos"])
            scores = {}
            for nm, P in self.subpos[tgt].items():
                if nm in ("Phasers", "Torpedoes", "Tractors", "Impulse_Engines", "Warp_Engines"):
                    continue
                key = tuple(round(x, 3) for x in P)
                s = min(seg_dist(H, e, P) for e in E)
                if key not in scores or s < scores[key][0]:
                    scores[key] = (s, [nm])
                elif abs(s - scores[key][0]) < 1e-9:
                    scores[key][1].append(nm)
            order = sorted(scores.values(), key=lambda x: x[0])
            best = order[0]
            # Margin against the best candidate of a DIFFERENT kind: a ship's cluster of tubes (the Sovereign's four
            # forward tubes lie within 0.16 GU) is one aim for this purpose, not four ambiguous ones.
            kind = _kind(best[1][0])
            second = next((o for o in order[1:] if _kind(o[1][0]) != kind), (9e9, []))
            out.append({"t": t, "shooter": sh, "target": tgt, "chosen": "+".join(sorted(best[1])), "hull": kv.get("hull"),
                        "miss": round(best[0], 3), "margin": round(second[0] - best[0], 3),
                        "runner": "+".join(sorted(second[1])), "banks": [b["name"] for b in bl]})
        return out

    def best_mapping(self):
        ships = self.ship_tags()
        if len(ships) == 2:
            maps = [{ships[0]: "A", ships[1]: "T"}, {ships[0]: "T", ships[1]: "A"}]
        else:
            maps = [{ships[0]: "T"}, {ships[0]: "A"}]
        best = None
        for m in maps:
            a = self.aims(m)
            if not a:
                continue
            med = sorted(x["miss"] for x in a)[len(a) // 2]
            if best is None or med < best[0]:
                best = (med, a)
        return best[1] if best else []


if __name__ == "__main__":
    cat = json.load(open(CATALOGUE))
    for path in sys.argv[1:]:
        if not path.endswith(".json") or path.endswith(".aim.json"):
            continue
        D = Duel(path, cat)
        res = D.best_mapping()
        print("== %s" % os.path.basename(path))
        for sh in ("A", "T"):
            rs = [r for r in res if r["shooter"] == sh]
            if not rs:
                continue
            sure = [r for r in rs if r["miss"] < 0.1 and r["margin"] > 0.1]
            share = {}
            for r in sure:
                share[r["chosen"]] = share.get(r["chosen"], 0) + 1
            miss = sorted(r["miss"] for r in rs)
            print("  shooter %s (%s): %d hits, median miss %.3f GU, %d unambiguous (miss<0.1, margin>0.1)" % (
                sh, D.cls[sh], len(rs), miss[len(miss) // 2], len(sure)))
            print("    share:", sorted(share.items(), key=lambda kv: -kv[1]))
            runs = []
            for r in sure:
                if runs and runs[-1][1] == r["chosen"]:
                    runs[-1][2] += 1
                else:
                    runs.append([round(r["t"], 1), r["chosen"], 1])
            print("    sequence:", " | ".join("%s %s x%d" % tuple(x) for x in runs[:50]))
        json.dump(res, open(path.replace(".json", ".aimbank.json"), "w"))

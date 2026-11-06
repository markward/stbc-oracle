"""The AI's speed commands, by behaviour, original vs Dauntless.

Original: xi rows (OracleAIProbe.install_speed: the last SetImpulse/SetSpeed value per ship per 0.25 s
sample, with the PlainAI script that issued it). Dauntless: track 'spd' (scorecard/dauntless_aim_duels.py,
the outermost command only). Per (ship class, behaviour): how many samples carried a command, and the
commanded value's quartiles (SetImpulse = fraction of top speed).

usage: python speed_commands.py --orig <globs> --dn <globs>
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duel_summary as ds  # noqa: E402

RX = re.compile(r"duel_(\w+?)_enemy[\d.]+_vs_(\w+?)_player")


def _orig(path):
    d = ds.load_json(path)
    a, t = RX.search(path).groups()
    dying = min([float(l.split()[2][2:]) for l in d["raw_rows"] if l.startswith("xz ") and " dy=1" in l] or [1e9])
    out = []
    for l in d["raw_rows"]:
        if not l.startswith("xi ") or " k=" not in l:
            continue
        p = l.split()
        kv = dict(x.split("=", 1) for x in p[2:] if "=" in x)
        if float(kv["t"]) >= dying:
            continue
        cls = t if p[1] == "Player" else a
        out.append((cls, kv["s"], kv["k"], float(kv["v"])))
    return out


def _dn(path):
    g = ds.load_json(path)
    out = []
    for r in g["track"]:
        if r["t"] > g["t_end"]:
            break
        for tag, e in (r.get("spd") or {}).items():
            out.append((g["enemy"] if tag == "A" else g["player"], e[2], e[0], float(e[1])))
    return out


def q(v, p):
    v = sorted(v)
    return v[int(p * (len(v) - 1))] if v else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", nargs="*", default=[])
    ap.add_argument("--dn", nargs="*", default=[])
    a = ap.parse_args()
    O = [x for g in a.orig for f in sorted(glob.glob(g)) for x in _orig(f)]
    D = [x for g in a.dn for f in sorted(glob.glob(g)) for x in _dn(f)]
    keys = sorted({(c, s) for c, s, k, v in O + D if k == "I"})
    print("%-11s %-24s | %-36s | %-36s" % ("class", "behaviour", "original: n  impulse p25/p50/p75", "Dauntless: n  impulse p25/p50/p75"))
    for c, s in keys:
        o = [v for cc, ss, k, v in O if cc == c and ss == s and k == "I"]
        d = [v for cc, ss, k, v in D if cc == c and ss == s and k == "I"]
        print("%-11s %-24s | %5d  %5.2f %5.2f %5.2f              | %5d  %5.2f %5.2f %5.2f" % (
            c, s, len(o), q(o, .25), q(o, .5), q(o, .75), len(d), q(d, .25), q(d, .5), q(d, .75)))


if __name__ == "__main__":
    main()

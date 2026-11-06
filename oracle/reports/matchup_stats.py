"""Original vs Dauntless, per matchup, as distributions over duels -- not single numbers.

Each duel is reduced by duel_summary.py (same format for both games). For every matchup
(enemy class, player class, AI level) and every metric below, the per-duel values of each game
are compared by their medians, with a bootstrap 90% interval on (Dauntless - original). A metric
is FLAGGED only when that interval excludes zero AND the medians differ by more than REL_TOL --
so a 4-duel spread like 240-417 s does not read as a gap, and a real one still does.

usage: python matchup_stats.py [--orig GLOB ...] [--dn GLOB ...] [--min-n 3] [--json out.json] [--only Galaxy]
defaults: --orig results_mac/duels*/duel_*.json   --dn scorecard/dauntless_aim_duels/duel_*.json
"""
import argparse
import collections
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duel_summary as ds  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
REL_TOL = 0.10
FDR_Q = 0.10         # Benjamini-Hochberg false discovery rate across EVERY row of a run
PERM = 2000          # permutations for each row's p-value
MIN_FLAG_N = 6       # a bootstrap on fewer duels per side is over-confident: such a gap is "suggestive", not flagged
                     # (measured 2026-10-16: the same 4 Windows setups gave a 65% and an 81% torpedo hit rate
                     # in two modes; 4-vs-4 comparisons flagged gaps that 8 duels per side dissolved)
BOOT = 2000
CI = 0.90


def _rate(x, minutes):
    return None if x is None or minutes <= 0 else x / minutes


def _ratio(a, b):
    return None if a is None or b is None or b <= 0 else a / b


def metrics(s):
    """Per-duel metric values: {name: value or None}."""
    out = {"fight_s": s["t_end"],
           # by ROLE (a mirror match has one class on both sides); summaries without it fall back to the class
           "enemy_wins": (1.0 if s.get("winner_role") == "enemy" else 0.0) if "winner_role" in s
           else (1.0 if s["winner"] == s["enemy"] and s["enemy"] != s["player"] else 0.0),
           "no_winner": 1.0 if not s["winner"] else 0.0}
    mins = s["t_end"] / 60.0
    for role in ("enemy", "player"):
        r = s["ships"][role]
        p = role + "."
        for w in ("energy", "torpedo"):
            out[p + w + "_dmg_per_min"] = _rate(r["dealt"][w]["dmg"], mins)
            out[p + w + "_hits_per_min"] = _rate(r["dealt"][w]["hits"], mins)
        t = r["torpedo"]
        out[p + "torp_launch_per_min"] = _rate(t["launches"], mins)
        out[p + "torp_hit_rate"] = _ratio(r["dealt"]["torpedo"]["hits"], t["launches"])
        out[p + "torp_launch_per_aligned_min"] = _ratio(t["launch_aligned"],
                                                        None if t["aligned_loaded_s"] is None else t["aligned_loaded_s"] / 60.0)
        out[p + "torp_aligned_s_per_min"] = _rate(t["aligned_loaded_s"], mins)
        out[p + "torp_no_shot_share"] = _ratio(t["no_shot"], t["episodes"])
        out[p + "torp_launch_angle_med"] = t["launch_angle_med"]
        tk = r["taken"]
        out[p + "taken_passed_share"] = _ratio(tk["passed"], tk["dmg"])
        out[p + "taken_hull_share"] = _ratio(tk["hull"], tk["dmg"])
        for b, v in (r["behaviour"] or {}).items():
            out[p + "beh." + b] = v
    return out


def _median(v):
    v = sorted(v)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]))


def compare(a, b, rng):
    """a = original values, b = Dauntless values -> (med_a, med_b, lo, hi, flagged)."""
    ma, mb = _median(a), _median(b)
    diffs = []
    for _ in range(BOOT):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in b]
        diffs.append(_median(rb) - _median(ra))
    diffs.sort()
    lo = diffs[int((1 - CI) / 2 * BOOT)]
    hi = diffs[int((1 + CI) / 2 * BOOT) - 1]
    scale = max(abs(ma), abs(mb), 1e-9)
    flagged = (lo > 0 or hi < 0) and abs(mb - ma) / scale > REL_TOL
    return ma, mb, lo, hi, flagged


def perm_p(a, b, rng):
    """Two-sided permutation p-value for |median(b) - median(a)| (labels shuffled PERM times)."""
    obs = abs(_median(b) - _median(a))
    pool = list(a) + list(b)
    na = len(a)
    hit = 0
    for _ in range(PERM):
        rng.shuffle(pool)
        if abs(_median(pool[na:]) - _median(pool[:na])) >= obs - 1e-12:
            hit += 1
    return (hit + 1) / (PERM + 1)


def apply_fdr(report):
    """Benjamini-Hochberg over every row of every matchup: each row gets q, and 'significant' when
    q < FDR_Q and the medians differ by more than REL_TOL. Per-row 90% flags see a few metrics per
    matchup by chance (measured: two Mac-only Galaxy-Keldon sets disagree on 1-4 of ~76 metrics);
    across a whole matrix of matchups the false-discovery-rate control is what keeps them out."""
    rows = [r for m in report for r in m["rows"] if r.get("p") is not None]
    rows.sort(key=lambda r: r["p"])
    n = len(rows)
    q_next = 1.0
    for i in range(n - 1, -1, -1):
        q = min(q_next, rows[i]["p"] * n / (i + 1))
        rows[i]["q"] = q
        q_next = q
    for r in rows:
        scale = max(abs(r["orig"]), abs(r["dn"]), 1e-9)
        r["significant"] = r["q"] < FDR_Q and abs(r["dn"] - r["orig"]) / scale > REL_TOL


def load(globs):
    out = []
    for g in globs:
        files = glob.glob(os.path.join(ROOT, g))
        if g.endswith(".json"):          # the same captures stored compressed (<name>.json.gz)
            files += glob.glob(os.path.join(ROOT, g + ".gz"))
        for f in sorted(files):
            try:
                s = ds.cached_summary(f)
            except Exception as e:          # one bad capture must not hide the rest
                print("skipped %s: %s: %s" % (os.path.relpath(f, ROOT), type(e).__name__, e), file=sys.stderr)
                continue
            if s is not None:
                out.append(s)
    return out


def run(orig_globs, dn_globs, min_n=3, only=None):
    groups = collections.defaultdict(lambda: {"orig": [], "dn": []})
    for side, globs in (("orig", orig_globs), ("dn", dn_globs)):
        for s in load(globs):
            if only and only not in (s["enemy"], s["player"]):
                continue
            groups[(s["enemy"], s["player"], s["level"])][side].append(s)
    rng = random.Random(1)
    report = []
    for key in sorted(groups):
        g = groups[key]
        if len(g["orig"]) < min_n or len(g["dn"]) < min_n:
            continue
        mo = [metrics(s) for s in g["orig"]]
        md = [metrics(s) for s in g["dn"]]
        names = sorted(set().union(*mo, *md))
        rows = []
        for n in names:
            a = [m[n] for m in mo if m.get(n) is not None]
            b = [m[n] for m in md if m.get(n) is not None]
            if len(a) < min_n or len(b) < min_n:
                continue
            ma, mb, lo, hi, fl = compare(a, b, rng)
            small = min(len(a), len(b)) < MIN_FLAG_N
            rows.append(dict(metric=n, n_orig=len(a), n_dn=len(b), orig=ma, dn=mb, lo=lo, hi=hi,
                             flagged=fl and not small, suggestive=fl and small,
                             p=None if small else perm_p(a, b, rng), q=None, significant=False))
        report.append(dict(enemy=key[0], player=key[1], level=key[2], n_orig=len(g["orig"]), n_dn=len(g["dn"]),
                           orig_files=[s["file"] for s in g["orig"]],
                           attribution=dict(collections.Counter(s["attribution"] for s in g["orig"])),
                           rows=rows))
    apply_fdr(report)
    return report


def _fmt(v):
    if v is None:
        return "-"
    return "%.3f" % v if abs(v) < 10 else "%.0f" % v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", nargs="*", default=["results_mac/duels*/duel_*.json"])
    ap.add_argument("--dn", nargs="*", default=["scorecard/dauntless_aim_duels/duel_*.json"])
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--only")
    ap.add_argument("--flagged", action="store_true", help="print flagged metrics only")
    ap.add_argument("--significant", action="store_true", help="print FDR-significant metrics only (##)")
    ap.add_argument("--json")
    a = ap.parse_args()
    rep = run(a.orig, a.dn, a.min_n, a.only)
    for m in rep:
        nfl = sum(r["flagged"] for r in m["rows"])
        nsg = sum(r["suggestive"] for r in m["rows"])
        nsig = sum(r["significant"] for r in m["rows"])
        print("== %s (enemy) vs %s (player), AI %.1f: original %d duels, Dauntless %d; %d significant (FDR q<%.2f), %d flagged, %d suggestive (n < %d)  [hits: %s]" % (
            m["enemy"], m["player"], m["level"], m["n_orig"], m["n_dn"], nsig, FDR_Q, nfl, nsg, MIN_FLAG_N, m["attribution"]))
        for r in m["rows"]:
            if a.significant and not r["significant"]:
                continue
            if a.flagged and not (r["flagged"] or r["suggestive"]):
                continue
            print("  %s %-44s original %9s  Dauntless %9s   diff 90%% [%9s, %9s]  q %5s  n %d/%d" % (
                "##" if r["significant"] else ("!!" if r["flagged"] else ("?!" if r["suggestive"] else "  ")), r["metric"], _fmt(r["orig"]), _fmt(r["dn"]), _fmt(r["lo"]),
                _fmt(r["hi"]), "-" if r.get("q") is None else "%.3f" % r["q"], r["n_orig"], r["n_dn"]))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(rep, fh, indent=1)


if __name__ == "__main__":
    main()

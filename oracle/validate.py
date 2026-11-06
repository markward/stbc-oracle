"""Per-run validation and manifest for oracle results.  validate(result, params) -> list of problems
(empty = valid).  manifest(oracle_dir, params) -> dict recorded in every result."""
import hashlib
import json
import platform
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMBATTAP_HOOKS = 8


def _sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def manifest(oracle_dir, params):
    oracle_dir = Path(oracle_dir)
    try:
        commit = subprocess.run(["git", "-C", str(HERE.parent), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain"],
                                    capture_output=True, text=True).stdout.strip())
    except OSError:
        commit, dirty = None, None
    scripts = {str(p.relative_to(HERE / "scripts")): _sha(p) for p in sorted((HERE / "scripts").rglob("*.py"))}
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "host": platform.node(),
        "oracle_commit": commit, "oracle_dirty": dirty,
        "exe": _sha(oracle_dir / "stbc.exe"),
        "plugins": {p.name: _sha(p) for p in sorted(oracle_dir.glob("*.asi"))} | {"winmm.dll": _sha(oracle_dir / "winmm.dll")},
        "options_cfg": _sha(oracle_dir / "options.cfg"),
        "scripts": scripts,
        "lockstep": params.get("lockstep", 0),
        "params": dict(params),
    }


def validate(result, params):
    probs = []
    if not result.get("done"):
        probs.append("run did not finish (done=0)")
    boot = result.get("boot", {})
    for k, v in boot.items():
        if "error" in k:
            probs.append(f"script error marker {k}={v[:120]}")
    tap = result.get("combat_tap") or []
    ok_hooks = sum(1 for l in tap if l.startswith("# hook") and l.endswith(" ok"))
    if ok_hooks != COMBATTAP_HOOKS:
        probs.append(f"CombatTap hooks ok {ok_hooks}/{COMBATTAP_HOOKS}")
    ls = result.get("lockstep_log") or []
    want = int(params.get("lockstep", 0))
    if not ls or f"mode={want}" not in ls[0]:
        probs.append(f"Lockstep log missing or wrong mode (wanted {want}): {ls[:1]}")
    if want >= 1 and not any("perframe hook ok" in l for l in ls):
        probs.append("Lockstep per-frame hook not installed")
    if want >= 2 and not any("scene hook ok" in l for l in ls):
        probs.append("Lockstep scene hook not installed")
    rows = str(params.get("rows", ""))
    raw = result.get("raw_rows") or []
    if "x" in rows:
        for kind in ("xm", "xe", "xp", "xq", "xc", "xd", "xn", "xh", "xw", "xs", "xz"):
            for tag in ("A", "T"):
                if not any(l.startswith(f"{kind} {tag} ") for l in raw):
                    probs.append(f"telemetry rows {kind} {tag} missing")
        ts = sorted({float(m.group(1)) for l in raw if l.startswith("xm A ")
                     for m in [re.search(r"t=([\d.]+)", l)] if m})
        dt = float(params.get("sample_dt", 0.03))
        if len(ts) > 2:
            gap = max(b - a for a, b in zip(ts, ts[1:]))
            if gap > max(1.0, 10 * dt):
                probs.append(f"telemetry gap {gap:.2f} s")
        errs = [l for l in raw if l.startswith("x") and " err" in l]
        if errs:
            probs.append(f"{len(errs)} telemetry rows with err (e.g. {errs[0][:80]})")
    n = int(params.get("shots", 0) or 0)
    if n:
        done = sum(1 for k in boot if re.match(r"\d+_shot\d+$", k))
        if done != n:
            probs.append(f"session shots completed {done}/{n}")
    return probs

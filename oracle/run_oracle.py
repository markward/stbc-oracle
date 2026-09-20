"""Run one scripted weapon-exchange scenario inside the original stbc.exe.

The "oracle" is an isolated copy of a clean BC install
(``<Documents>/Star Trek Bridge Commander/bc_oracle``) whose ``scripts/`` gets
``tools/oracle/scripts/`` copied over it: a ``Local.py`` startup hook that
boots straight into ``Oracle.OracleGame`` (no movies, no menu), and the
``Oracle`` package that spawns the two ships, fires, samples every tick and
writes ``oracle_out.cfg`` through the engine's own ConfigMapping (the only
file write that works inside stbc.exe).

Two things this driver does that are easy to forget:

* **The game's main loop does not start until its window has focus.**  A
  launch nobody clicks on sits on a black screen forever.  We find the window
  and click into it.
* **The exe must be windowed and run under the same Windows compatibility
  layers the GOG shortcut uses** (``DWM8And16BitMitigation 16BITCOLOR ...``),
  or the 16-bit D3D8 window renders black.  Register them once per exe path
  under ``HKCU\\...\\AppCompatFlags\\Layers``.

Usage::

    python tools/oracle/run_oracle.py --attacker KessokHeavy --target Galaxy \
        --range-gu 57 --intensity 2 --duration 12 --out result.json
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import capture  # noqa: E402  (PrintWindow-based; BitBlt shows the 3D view black)

DEFAULT_ORACLE_DIR = Path.home() / "Documents" / "Star Trek Bridge Commander" / "bc_oracle"
SCRIPTS_SRC = Path(__file__).resolve().parent / "scripts"
WINDOW_TITLE = "Bridge Commander"

IN_CFG = "oracle_in.cfg"
OUT_CFG = "oracle_out.cfg"
BOOT_CFG = "oracle_boot.cfg"


# --- deploy -------------------------------------------------------------------
def deploy_scripts(oracle_dir: Path) -> None:
    """Copy tools/oracle/scripts/* over <oracle>/scripts, dropping stale .pyc."""
    dst = oracle_dir / "scripts"
    for src in SCRIPTS_SRC.rglob("*.py"):
        rel = src.relative_to(SCRIPTS_SRC)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        pyc = target.with_suffix(".pyc")
        if pyc.exists():
            pyc.unlink()


def write_inputs(oracle_dir: Path, params: dict) -> None:
    lines = ["[OracleIn]"]
    for k, v in params.items():
        lines.append(f"{k}={v}")
    (oracle_dir / IN_CFG).write_bytes(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))


def scrub_options(oracle_dir: Path) -> None:
    """The game rewrites options.cfg from its in-memory ConfigMapping, which
    by then holds our Oracle* sections; strip them so no stale marker or
    input leaks into the next run."""
    p = oracle_dir / "options.cfg"
    raw = p.read_bytes()
    out = []
    keep = True
    for line in raw.splitlines(keepends=True):
        if line.startswith(b"["):
            keep = not line.startswith(b"[Oracle")
        if keep:
            out.append(line)
    cleaned = b"".join(out)
    if cleaned != raw:
        p.write_bytes(cleaned)


def check_windowed(oracle_dir: Path) -> None:
    opts = (oracle_dir / "options.cfg").read_bytes()
    if b"Fullscreen Mode|0" not in opts:
        raise SystemExit("options.cfg is not windowed (Fullscreen Mode|0) - refusing to launch")


# --- window focus (the game does not run until it has focus) ------------------
_user32 = ctypes.windll.user32


def _find_window() -> int:
    return _user32.FindWindowW(None, WINDOW_TITLE)


def press_escape() -> None:
    """Skip an opening movie (mainmenu.HandleKeyboardOpening acts on ESC key-up)."""
    _user32.keybd_event(0x1B, 0, 0, 0)
    time.sleep(0.05)
    _user32.keybd_event(0x1B, 0, 2, 0)


def focus_and_click(hwnd: int) -> None:
    _user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    _user32.SetForegroundWindow(hwnd)
    r = wt.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(r))
    x = (r.left + r.right) // 2
    y = (r.top + r.bottom) // 2
    _user32.SetCursorPos(x, y)
    _user32.mouse_event(2, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.06)
    _user32.mouse_event(4, 0, 0, 0, 0)   # LEFTUP


# --- output parsing -----------------------------------------------------------
_ROW_RE = re.compile(r"^r(\d+)=(.*)$")
_META_RE = re.compile(r"^m_(\w+)=(.*)$")


def parse_cfg_section(path: Path, section: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = path.read_bytes().decode("latin-1")
    in_sec = False
    for line in text.splitlines():
        if line.startswith("["):
            in_sec = line.strip() == f"[{section}]"
            continue
        if not in_sec or not line.strip():
            continue
        for sep in ("=", "|", "-"):
            if sep in line:
                k, v = line.split(sep, 1)
                out[k] = v
                break
    return out


def _floats(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x != ""]


def parse_row(line: str) -> dict:
    """One sample line: '<kind> k=v k=v ...' (kinds a/b/c, see OracleMission)."""
    kind, _, rest = line.partition(" ")
    d: dict = {"kind": kind}
    for tok in rest.split(" "):
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        if k in ("t", "h", "sp", "ah", "tsp", "rng"):
            d[k] = float(v)
        elif k == "f":
            d[k] = int(v)
        elif k in ("c", "sh", "s", "p", "v", "w", "fw", "tp"):
            d[k] = _floats(v)
        elif k == "fi":
            d[k] = [int(x) for x in v.split(",") if x != ""]
        elif k in ("tgt", "fire", "set"):
            d[k] = v
        elif k == "isw":
            d[k] = int(v)
    return d


def parse_output(oracle_dir: Path) -> dict:
    """Read oracle_out.cfg (+ oracle_out1.cfg, ... chunks) into rows by kind."""
    first = parse_cfg_section(oracle_dir / OUT_CFG, "OracleOut")
    meta = {k[2:]: v for k, v in first.items() if k.startswith("m_")}
    nchunks = int(first.get("chunks", "1") or 1)
    raw_rows: list[str] = []
    for c in range(nchunks):
        path = oracle_dir / (OUT_CFG if c == 0 else f"oracle_out{c}.cfg")
        sec = parse_cfg_section(path, "OracleOut")
        keys = sorted(k for k in sec if k.startswith("r") and k[1:].isdigit())
        raw_rows.extend(sec[k] for k in keys if sec[k] != "")
    rows = {"a": [], "b": [], "c": []}
    for line in raw_rows:
        d = parse_row(line)
        rows.setdefault(d["kind"], []).append(d)
    subs = [meta[k].split("|") for k in sorted(meta) if k.startswith("sub")]
    boot = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleBoot")
    hook = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleHook")
    return {"meta": meta, "rows": rows["a"], "sub_rows": rows["b"], "motion_rows": rows["c"],
            "subsystems": [{"name": x[0], "max": float(x[1]) if len(x) > 1 and x[1] != "err" else None,
                            "radius": float(x[2]) if len(x) > 2 else None,
                            "pos": _floats(x[3]) if len(x) > 3 else None} for x in subs],
            "done": first.get("done") == "1",
            "boot": dict(sorted(boot.items())), "hook": dict(sorted(hook.items()))}


def summarise(result: dict) -> str:
    rows = result["rows"]
    lines = []
    if rows:
        first, last = rows[0], rows[-1]
        fired = [r for r in rows if any(r.get("fi", []))]
        lines.append(f"rows={len(rows)}  t={first['t']:.2f}..{last['t']:.2f}s  firing rows={len(fired)}")
        d_sh = [a - b for a, b in zip(first["sh"], last["sh"])]
        d_h = first["h"] - last["h"]
        total = sum(d_sh) + d_h
        if fired:
            t_on, t_off = fired[0]["t"], fired[-1]["t"]
            beam_s = max(t_off - t_on, 1e-6)
            lines.append(f"firing {t_on:.2f}..{t_off:.2f}s ({beam_s:.2f}s), "
                         f"max emitters firing={max(sum(r['fi']) for r in fired)}")
            lines.append(f"TOTAL={total:.1f}  =>  {total / beam_s:.1f} per firing-second")
        lines.append(f"shield delta per face={[round(x, 1) for x in d_sh]}  hull delta={d_h:.1f}")
    srows = result.get("sub_rows") or []
    if srows and result.get("subsystems"):
        d = [a - b for a, b in zip(srows[0]["s"], srows[-1]["s"])]
        hit = [(sub["name"], round(x, 1)) for sub, x in zip(result["subsystems"], d) if abs(x) > 0.05]
        lines.append(f"subsystem deltas: {hit if hit else 'none'}")
    mrows = result.get("motion_rows") or []
    if mrows:
        sp = [r["sp"] for r in mrows]
        wmax = max((sum(x * x for x in r["w"]) ** 0.5) for r in mrows)
        lines.append(f"motion: speed {sp[0]:.3f} -> max {max(sp):.3f} (final {sp[-1]:.3f}) GU/s; "
                     f"max |ang vel| {wmax:.4f} rad/s over {len(mrows)} samples")
    return chr(10).join(lines) if lines else "no rows"


# --- main ---------------------------------------------------------------------
def run(oracle_dir: Path, params: dict, timeout_s: float, shot: Path | None,
        shot_at_s: float = 1e9) -> dict:
    scrub_options(oracle_dir)
    check_windowed(oracle_dir)
    deploy_scripts(oracle_dir)
    for p in [oracle_dir / BOOT_CFG] + list(oracle_dir.glob("oracle_out*.cfg")):
        if p.exists():
            p.unlink()
    write_inputs(oracle_dir, params)

    proc = subprocess.Popen([str(oracle_dir / "stbc.exe")], cwd=str(oracle_dir))
    t0 = time.time()
    focused = 0
    done = False
    shot_taken = False
    try:
        while time.time() - t0 < timeout_s:
            time.sleep(0.5)
            if proc.poll() is not None:
                break
            if focused < 4 and time.time() - t0 >= 2 + 3 * focused:
                hwnd = _find_window()
                if hwnd:
                    focus_and_click(hwnd)
                focused += 1
            # Skip the opening movies until the hook reports the menu is up.
            hook = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleHook")
            if focused >= 1 and not any(k.endswith("menu_ready") for k in hook):
                if _find_window() == _user32.GetForegroundWindow():
                    press_escape()
            sec = parse_cfg_section(oracle_dir / OUT_CFG, "OracleOut")
            if shot is not None and time.time() - t0 >= shot_at_s and not shot_taken:
                shot_taken = capture(shot)
            if sec.get("done") == "1":
                done = True
                break
    finally:
        if shot is not None and not shot_taken:
            capture(shot)
        if proc.poll() is None:
            # Give ET_QUIT a moment, then kill: the process is disposable.
            for _ in range(10):
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()
    result = parse_output(oracle_dir)
    tree = oracle_dir / "AITree.txt"
    if tree.exists():
        try:
            result["ai_tree_log"] = tree.read_text(errors="replace")
            tree.unlink()
        except OSError:
            pass
    result["elapsed_s"] = round(time.time() - t0, 1)
    result["params"] = params
    result["timed_out"] = not done
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--oracle-dir", type=Path,
                    default=Path(os.environ.get("DAUNTLESS_ORACLE_DIR", DEFAULT_ORACLE_DIR)))
    ap.add_argument("--attacker", default="KessokHeavy")
    ap.add_argument("--target", default="Galaxy")
    ap.add_argument("--weapon", default="phaser", choices=["phaser", "pulse", "torpedo", "tractor", "none"])
    ap.add_argument("--torp-type", type=int, default=-1)
    ap.add_argument("--pulse-power", type=int, default=-1)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--target-alert", default="red", choices=["red", "yellow", "green"])
    ap.add_argument("--tractor-mode", default="hold", choices=["hold", "tow", "pull", "push"])
    ap.add_argument("--shield-power", type=float, default=-1.0, help="target shield generator power wanted")
    ap.add_argument("--gen-frac", type=float, default=-1.0, help="target shield generator condition fraction")
    ap.add_argument("--ai", action="store_true", help="leave the Quick Battle AI driving the attacker")
    ap.add_argument("--ai-level", type=float, default=0.5, help="BasicAttack difficulty 0.0/0.5/1.0")
    ap.add_argument("--ai-log", action="store_true", help="(non-functional: ArtificialIntelligence_LogAITree stalls the game even when armed at boot)")
    ap.add_argument("--target-motion", default="none", choices=["none", "impulse", "yaw", "warp"])
    ap.add_argument("--target-fire", action="store_true", help="player ship shoots back at act time")
    ap.add_argument("--warp-stop-gu", type=float, default=50.0)
    ap.add_argument("--warp-time", type=float, default=5.0)
    ap.add_argument("--motion", default="none", choices=["none", "impulse", "impulse125", "impulse200", "impulse_power125", "warp", "warp_moving", "warpset", "warpset_moving", "coast", "yaw", "pitch", "roll", "yawdirect"])
    ap.add_argument("--range-gu", type=float, default=57.0)
    ap.add_argument("--angle-deg", type=float, default=0.0, help="attacker bearing: 0 ahead, 90 starboard, 180 astern")
    ap.add_argument("--elev-deg", type=float, default=0.0, help="+ above (dorsal), - below")
    ap.add_argument("--shield-face", type=int, default=-1, help="preset this face (0-5) to --shield-frac of max")
    ap.add_argument("--shield-frac", type=float, default=1.0)
    ap.add_argument("--shields-off", action="store_true", help="zero every face at act time")
    ap.add_argument("--rows", default="abc", help="row kinds to sample: a weapon, b subsystems, c motion")
    ap.add_argument("--intensity", type=int, default=2, help="0=LOW 1=MED 2=HIGH")
    ap.add_argument("--charge", type=float, default=-1.0, help="-1 = leave at max")
    ap.add_argument("--power-wanted", type=float, default=-1.0)
    ap.add_argument("--settle-s", type=float, default=2.0)
    ap.add_argument("--fire-at", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--sample-dt", type=float, default=0.03)
    ap.add_argument("--keep-target-weapons", action="store_true")
    ap.add_argument("--timeout", type=float, default=150.0)
    ap.add_argument("--out", type=Path, help="write the parsed result as JSON here")
    ap.add_argument("--shot", type=Path, help="PNG of the game window (taken at --shot-at seconds, else at the end)")
    ap.add_argument("--shot-at", type=float, default=1e9)
    a = ap.parse_args(argv)

    params = {
        "attacker": a.attacker, "target": a.target, "weapon": a.weapon, "motion": a.motion,
        "range_gu": a.range_gu, "angle_deg": a.angle_deg, "elev_deg": a.elev_deg,
        "intensity": a.intensity, "charge": a.charge, "power_wanted": a.power_wanted,
        "shield_face": a.shield_face, "shield_frac": a.shield_frac,
        "shields_off": 1 if a.shields_off else 0,
        "settle_s": a.settle_s, "fire_at": a.fire_at, "duration": a.duration,
        "sample_dt": a.sample_dt, "disable_target_weapons": 0 if a.keep_target_weapons else 1,
        "rows": a.rows, "torp_type": a.torp_type, "pulse_power": a.pulse_power,
        "time_scale": a.time_scale, "target_alert": a.target_alert, "tractor_mode": a.tractor_mode,
        "shield_power": a.shield_power, "gen_frac": a.gen_frac,
        "ai": 1 if a.ai else 0, "ai_level": a.ai_level, "ai_log": 1 if a.ai_log else 0,
        "target_motion": a.target_motion, "target_fire": 1 if a.target_fire else 0,
        "warp_stop_gu": a.warp_stop_gu, "warp_time": a.warp_time,
    }
    result = run(a.oracle_dir, params, a.timeout, a.shot, a.shot_at)
    print("hook markers:", ", ".join(k[3:] for k in result["hook"]))
    print("boot markers:")
    for k, v in result["boot"].items():
        print(f"  {k} = {v}")
    print(f"done={result['done']} timed_out={result['timed_out']} elapsed={result['elapsed_s']}s")
    for k, v in result["meta"].items():
        print(f"  meta {k} = {v}")
    print(summarise(result))
    if a.out:
        a.out.write_text(json.dumps(result, indent=1))
        print(f"wrote {a.out}")
    return 0 if result["done"] else 1


if __name__ == "__main__":
    sys.exit(main())

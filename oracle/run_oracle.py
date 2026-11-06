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
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# --- platform: Windows (original) or macOS + CrossOver ------------------------
# On the Mac the game runs in its own CrossOver bottle ("BC Oracle", a clean GOG
# install that nothing else uses).  OracleAssist.asi, installed only in that
# bottle, does what the Windows driver did with user32: keeps the game believing
# it is active, posts ESC through the opening movies, and stops the game moving
# or clipping the Mac cursor.  The driver only launches, watches files and kills.
IS_MAC = sys.platform == "darwin"
CX_BIN = Path("/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin")
CX_BOTTLE = os.environ.get("ORACLE_BOTTLE", "BC Oracle")
CX_BOTTLE_DIR = Path.home() / "Library" / "Application Support" / "CrossOver" / "Bottles" / CX_BOTTLE
CX_GAME_WIN = r"C:\GOG Games\Star Trek Bridge Commander"

if IS_MAC:
    def capture(path) -> bool:          # screenshots are optional on the Mac port
        return False
    DEFAULT_ORACLE_DIR = CX_BOTTLE_DIR / "drive_c" / "GOG Games" / "Star Trek Bridge Commander"
else:
    from capture import capture  # noqa: E402  (PrintWindow-based; BitBlt shows the 3D view black)
    DEFAULT_ORACLE_DIR = Path.home() / "Documents" / "Star Trek Bridge Commander" / "bc_oracle"
SCRIPTS_SRC = Path(__file__).resolve().parent / "scripts"
WINDOW_TITLE = "Bridge Commander"

IN_CFG = "oracle_in.cfg"
OUT_CFG = "oracle_out.cfg"
BOOT_CFG = "oracle_boot.cfg"
FREEZE_S = 20.0          # grace beyond the scenario's own length
STALL_FIRST_SAMPLE_S = 90.0   # armed but no first sample this long (real s): the sim clock is not running
STALL_RUNNING_S = 60.0        # sampling started but oracle_boot.cfg unchanged this long (real s); the zz_pulse
                              # heartbeat rewrites it every 16 samples (~4 s of game time, under 5 s of real
                              # time even under Rosetta), so 60 s of silence is a frozen game clock


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


# The SDK's ships/Hardpoints sources (read by --hp-patch). Set ORACLE_SDK_HARDPOINTS; the Windows default is the
# SDK copy beside the oracle install. The Mac has no default.
_SDK_HP = os.environ.get("ORACLE_SDK_HARDPOINTS") or (
    None if IS_MAC else "C:/Users/user/Documents/Star Trek Bridge Commander/sdk/Build/scripts/ships/Hardpoints")
SDK_HARDPOINTS = Path(_SDK_HP) if _SDK_HP else None


def deploy_hp_patch(oracle_dir: Path, spec: str):
    """hp_patch="<hardpoint>:<item>;<item>..." - deploy a patched copy of the SDK
    hardpoint source for one run.  Items: ``<Var>.<Setter>=<value>`` appends
    ``Var.Setter(value)`` after the templates are registered (the registered
    template is the same object); ``pulse.<Setter>=<value>`` does it for every
    ``PulseWeaponProperty_Create`` variable; ``-<Template Name>`` drops that
    template's block from ``LoadPropertySet`` so the ship is built without it.
    Returns a restore() that removes the .py and puts the stock .pyc back."""
    hp, items = spec.split(":", 1)
    if SDK_HARDPOINTS is None or not (SDK_HARDPOINTS / f"{hp}.py").exists():
        raise SystemExit(f"--hp-patch needs the SDK hardpoint source {hp}.py: set ORACLE_SDK_HARDPOINTS to the SDK's"
                         f" scripts/ships/Hardpoints folder (now {SDK_HARDPOINTS})")
    src = (SDK_HARDPOINTS / f"{hp}.py").read_text(encoding="latin-1")
    pulse_vars = re.findall(r"^(\w+) = App\.PulseWeaponProperty_Create\(", src, re.M)
    extra = []
    for item in items.split(";"):
        item = item.strip()
        if not item:
            continue
        if item.startswith("-"):
            name = item[1:]
            pat = (r'\tprop = App\.g_kModelPropertyManager\.FindByName\("' + re.escape(name)
                   + r'", App\.TGModelPropertyManager\.LOCAL_TEMPLATES\)\n\tif \(prop != None\):\n\t\tpObj\.AddToSet\("Scene Root", prop\)\n')
            src, n = re.subn(pat, "", src)
            if n != 1:
                raise SystemExit(f"hp_patch: template {name!r} not found in {hp}.py LoadPropertySet")
            continue
        lhs, val = item.split("=", 1)
        var, setter = lhs.split(".", 1)
        targets = pulse_vars if var == "pulse" else [var]
        for v in targets:
            extra.append(f"{v}.{setter}({val})")
    marker = "def LoadPropertySet(pObj):"
    assert src.count(marker) == 1
    src = src.replace(marker, "# --- oracle hp_patch ---\n" + "\n".join(extra) + "\n# --- end hp_patch ---\n\n" + marker)
    dst_dir = oracle_dir / "scripts" / "ships" / "Hardpoints"
    py, pyc = dst_dir / f"{hp}.py", dst_dir / f"{hp}.pyc"
    backup = pyc.read_bytes() if pyc.exists() else None
    py.write_text(src, encoding="latin-1")
    if pyc.exists():
        pyc.unlink()

    def restore():
        if py.exists():
            py.unlink()
        if pyc.exists():
            pyc.unlink()
        if backup is not None:
            pyc.write_bytes(backup)
    return restore


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
if not IS_MAC:
    import ctypes
    import ctypes.wintypes as wt
    _user32 = ctypes.windll.user32


def _assisted(oracle_dir: Path) -> bool:
    """OracleAssist.asi in the game folder keeps the game believing it is active and posts ESC
    through the movies itself, so the driver must not click or press keys (on Windows that is what
    lets several instances run at once). Always true on the Mac, where the plugin is required."""
    return IS_MAC or (oracle_dir / "OracleAssist.asi").exists()


def check_game_path(oracle_dir: Path) -> None:
    """Windows: warn when options.cfg 'Game Path=' names another folder than this copy. The game may
    then read that install's data instead (a partial install at the default path did this to one
    instance copy); a normal single copy whose Game Path is the install it came from still runs."""
    if IS_MAC:
        return
    try:
        raw = (oracle_dir / "options.cfg").read_bytes().decode("latin-1")
    except OSError:
        return
    m = re.search(r"^Game Path=(.*?)\s*$", raw, re.M)
    if m and Path(m.group(1)).resolve() != oracle_dir.resolve():
        print(f"warning: options.cfg Game Path={m.group(1)} is not this folder {oracle_dir}; the game"
              " may read that install's data (oracle/batch.py setup points instance copies at themselves)",
              flush=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) on Windows sends CTRL_C_EVENT; ask the kernel instead
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wt.DWORD()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                             # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _find_window() -> int:
    if IS_MAC:
        return 0
    return _user32.FindWindowW(None, WINDOW_TITLE)


def press_escape() -> None:
    """Skip an opening movie (mainmenu.HandleKeyboardOpening acts on ESC key-up)."""
    if IS_MAC:
        return                           # OracleAssist.asi posts ESC inside the game
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
        if k in ("t", "h", "sp", "ah", "tsp", "rng", "im", "ip"):
            d[k] = float(v)
        elif k == "f":
            d[k] = int(v)
        elif k in ("c", "sh", "s", "p", "v", "w", "fw", "tp"):
            d[k] = _floats(v)
        elif k in ("fi", "rq"):
            d[k] = [int(x) for x in v.split(",") if x != ""]
        elif k in ("tgt", "fire", "set", "ws", "rs", "cs", "mode", "fr", "cam", "name", "scr", "hull", "ai", "player", "err", "tr", "ad"):
            d[k] = v
        elif k in ("isw", "bv", "tv", "cut", "cin", "pc", "n", "ships", "al", "pl", "hid", "clk", "dy", "tp"):
            d[k] = int(v)
        elif k in ("shm",):
            d[k] = _floats(v)
        elif k == "r":
            d[k] = float(v)
    return d


def _ended_cleanly(oracle_dir: Path) -> bool:
    """The game's own markers: OnEnd ran and the final flush succeeded (ok=1)."""
    boot = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleBoot")
    return any(k.endswith("_on_end") for k in boot) and any(k.endswith("_flushed") and "ok=1" in v for k, v in boot.items())


# Row kinds parse_output turns into "rows", "sub_rows", ...; every other kind is only in "raw_rows".
PARSED_KINDS = ("a", "b", "c", "d", "e", "f", "r", "s", "h", "m")
DOCS_RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"


def for_docs(result: dict) -> dict:
    """The copy of a result that goes under docs/results/ (committed, public): no hostname, no second
    copy of params in the manifest, and raw_rows only for rows that are not already parsed."""
    out = dict(result)
    if isinstance(out.get("manifest"), dict):
        out["manifest"] = {k: v for k, v in out["manifest"].items() if k not in ("host", "params")}
    if "raw_rows" in out:
        keep = []
        for line in out["raw_rows"]:
            if line.split(" ", 1)[0] in PARSED_KINDS:
                try:
                    parse_row(line)
                    continue                # already in rows/sub_rows/...
                except (ValueError, IndexError):
                    pass                    # unparsable: the raw line is its only copy
            keep.append(line)
        out["raw_rows"] = keep
    return out


def write_result(path: Path, result: dict, indent: int | None = 1) -> None:
    """Write a result; under docs/results/ write the for_docs() copy. results_mac/ and results_win/
    (git-ignored) keep everything."""
    path = Path(path)
    if path.resolve().is_relative_to(DOCS_RESULTS):
        result = for_docs(result)
    path.write_text(json.dumps(result, indent=indent))


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
    rows = {k: [] for k in PARSED_KINDS}
    for line in raw_rows:
        kind = line.split(" ", 1)[0]
        if kind not in PARSED_KINDS:
            continue                    # newer row kinds (telemetry, catalogue, probe...) stay raw
        try:
            d = parse_row(line)
        except (ValueError, IndexError):
            continue
        rows.setdefault(d["kind"], []).append(d)
    subs = [meta[k].split("|") for k in sorted(meta) if k.startswith("sub")]
    boot = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleBoot")
    hook = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleHook")
    return {"meta": meta, "raw_rows": raw_rows, "rows": rows["a"], "sub_rows": rows["b"], "motion_rows": rows["c"], "camera_rows": rows["d"], "active_camera_rows": rows["e"],
            "torpedo_rows": rows["f"], "repair_rows": rows["r"], "scene_rows": rows["s"], "scene_health_rows": rows["h"], "scene_meta_rows": rows["m"],
            "subsystems": [{"name": x[0], "max": float(x[1]) if len(x) > 1 and x[1] != "err" else None,
                            "radius": float(x[2]) if len(x) > 2 else None,
                            "pos": _floats(x[3]) if len(x) > 3 else None,
                            "ptr": x[4] if len(x) > 4 else None} for x in subs],
            "done": first.get("done") == "1" or _ended_cleanly(oracle_dir),
            "boot": dict(sorted(boot.items())), "hook": dict(sorted(hook.items()))}


def summarise(result: dict) -> str:
    rows = [r for r in result["rows"] if "t" in r and "sh" in r]
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
    crows = result.get("camera_rows") or []
    if crows:
        segs = []
        for r in crows:
            key = (r.get("rs"), r.get("cs"), r.get("mode"), r.get("bv"), r.get("tv"), r.get("cut"), r.get("cin"))
            if not segs or segs[-1][0] != key:
                segs.append((key, r["t"]))
        desc = "; ".join(f"{t:.2f}s rs={k[0]} cs={k[1]} mode={k[2]} bv={k[3]} tv={k[4]} cut={k[5]} cin={k[6]}" for k, t in segs[:12])
        lines.append(f"camera: {len(crows)} samples, {len(segs)} states: {desc}")
    mrows2 = result.get("scene_meta_rows") or []
    if mrows2:
        first, last = mrows2[0], mrows2[-1]
        lines.append(f"scene: {len(mrows2)} snapshots, t={first['t']:.1f}..{last['t']:.1f}s; first set={first.get('set')} ships={first.get('ships')} player={first.get('player')}; "
                     f"last set={last.get('set')} ships={last.get('ships')} player={last.get('player')} cut={last.get('cut')}")
    erows = result.get("active_camera_rows") or []
    if erows:
        segs = []
        for r in erows:
            key = (r.get("set"), r.get("cam"), r.get("pc"), r.get("mode"))
            if not segs or segs[-1][0] != key:
                segs.append((key, r["t"]))
        desc = "; ".join(f"{t:.2f}s {k[0]}/{k[1]} player={k[2]} mode={k[3]}" for k, t in segs[:12])
        lines.append(f"active camera: {len(segs)} states: {desc}")
    return chr(10).join(lines) if lines else "no rows"


# --- main ---------------------------------------------------------------------
class BottleBusy(RuntimeError):
    pass


def _bottle_lock():
    """One game per CrossOver bottle: two runs in one bottle read each other's oracle_out files
    (happened 2026-10-16). Atomic lock file holding the owner's pid; a dead owner's lock is taken over."""
    lock = Path(__file__).resolve().parent.parent / "results_mac" / "locks" / f"{CX_BOTTLE}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                owner = int(lock.read_text().strip() or 0)
                os.kill(owner, 0)
            except (ValueError, ProcessLookupError, FileNotFoundError):
                lock.unlink(missing_ok=True)      # stale: owner gone
                continue
            except PermissionError:
                pass
            raise BottleBusy(f"bottle '{CX_BOTTLE}' is in use by pid {owner}")
    raise BottleBusy(f"bottle '{CX_BOTTLE}': could not take lock")


def _dir_lock(oracle_dir: Path):
    """Windows: one game per instance folder (several instances run side by side)."""
    lock = oracle_dir / "oracle_instance.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                owner = int(lock.read_text().strip() or 0)
            except (ValueError, FileNotFoundError):
                owner = 0
            if not _pid_alive(owner):
                lock.unlink(missing_ok=True)
                continue
            raise BottleBusy(f"instance '{oracle_dir}' is in use by pid {owner}")
    raise BottleBusy(f"instance '{oracle_dir}': could not take lock")


def run(oracle_dir: Path, params: dict, timeout_s: float, shot: Path | None,
        shot_at_s: float = 1e9, shot_on: str | None = None, shot_count: int = 1,
        shot_every: float = 0.25, shot_delay: float = 0.0) -> dict:
    lock = _bottle_lock() if IS_MAC else (_dir_lock(oracle_dir) if _assisted(oracle_dir) else None)
    try:
        return _run(oracle_dir, params, timeout_s, shot, shot_at_s, shot_on, shot_count, shot_every, shot_delay)
    finally:
        if lock:
            lock.unlink(missing_ok=True)


def _run(oracle_dir: Path, params: dict, timeout_s: float, shot: Path | None,
        shot_at_s: float = 1e9, shot_on: str | None = None, shot_count: int = 1,
        shot_every: float = 0.25, shot_delay: float = 0.0) -> dict:
    """shot_on: take the shots once a boot marker's value contains this text
    (e.g. "fire"), shot_delay seconds later, shot_count of them shot_every
    seconds apart, as <shot>_<k>.png; else one shot at shot_at_s."""
    scrub_options(oracle_dir)
    if not int(params.get("human", 0)):
        # automated runs stay windowed (focus handling, several instances); a human run may be full screen
        check_windowed(oracle_dir)
    check_game_path(oracle_dir)
    assisted = _assisted(oracle_dir)
    if IS_MAC or (oracle_dir / "Lockstep.asi").exists():
        # Lockstep.asi (oracle copies only): 0 rebase only, 1 fixed 1/60 s virtual-clock steps
        mode = int(params.get("lockstep", 0))
        (oracle_dir / "Lockstep.ini").write_text(f"[lockstep]\r\nmode={mode}\r\nhz=60\r\nstep_extra_us=0\r\n")
    import py15_lint                     # in-game Python 1.5 syntax errors freeze the run
    errs = py15_lint.lint([str(x) for x in SCRIPTS_SRC.rglob("*.py")])
    if errs:
        raise SystemExit("in-game scripts fail the Python 1.5 lint:\n" + "\n".join(errs))
    deploy_scripts(oracle_dir)
    for p in [oracle_dir / BOOT_CFG, oracle_dir / "CombatTap.log"] + list(oracle_dir.glob("oracle_out*.cfg")):
        if p.exists():
            p.unlink()
    restore_hp = None
    if params.get("hp_patch", "none") != "none":
        restore_hp = deploy_hp_patch(oracle_dir, params["hp_patch"])
    write_inputs(oracle_dir, params)
    import validate as _validate
    run_manifest = _validate.manifest(oracle_dir, params)

    if IS_MAC:
        log = open(oracle_dir / "oracle_wine.log", "wb")
        proc = subprocess.Popen([str(CX_BIN / "wine"), "--bottle", CX_BOTTLE, "--workdir", CX_GAME_WIN,
                                 "--no-convert", "--wait-children", CX_GAME_WIN + "\\stbc.exe"],
                                stdout=log, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.Popen([str(oracle_dir / "stbc.exe")], cwd=str(oracle_dir))
    t0 = time.time()
    focused = 0
    done = False
    shot_taken = False
    last_boot_mtime, last_boot_change = None, time.time()
    armed_at = None
    seen_first = False      # latched: a torn read of oracle_boot.cfg (the game rewrites it) must not undo it
    try:
        while time.time() - t0 < timeout_s:
            time.sleep(0.5)
            if proc.poll() is not None:
                break
            if not assisted and focused < 4 and time.time() - t0 >= 2 + 3 * focused:
                hwnd = _find_window()
                if hwnd:
                    focus_and_click(hwnd)
                focused += 1
            # Skip the opening movies until the hook reports the menu is up.
            hook = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleHook")
            if not assisted and focused >= 1 and not any(k.endswith("menu_ready") for k in hook):
                if _find_window() == _user32.GetForegroundWindow():
                    press_escape()
            sec = parse_cfg_section(oracle_dir / OUT_CFG, "OracleOut")
            # Freeze detector: an uncaught in-game exception pops the TG debug
            # console and stops the world.  Once the mission has started, if
            # oracle_boot.cfg stops changing for longer than the scenario
            # itself plus FREEZE_S, kill rather than wait for the full timeout.
            boot_path = oracle_dir / BOOT_CFG
            if boot_path.exists():
                m = boot_path.stat().st_mtime
                if m != last_boot_mtime:
                    last_boot_mtime, last_boot_change = m, time.time()
                boot = parse_cfg_section(boot_path, "OracleBoot")
                started = any(k.endswith("timers_armed") for k in boot)
                finished = any(k.endswith("flushed") for k in boot)
                budget = FREEZE_S + float(params.get("duration", 0)) + float(params.get("settle_s", 0)) + float(params.get("fire_at", 0))
                if started and not finished and time.time() - last_boot_change > budget:
                    print("freeze suspected (no progress) - killing", flush=True)
                    break
                # Seen on Windows mode 1 (2026-10-16, inst05): timers armed, the frame loop and the
                # lockstep clock running, but the game clock frozen at t0 - the first sample never
                # fires. Waiting for the 600 s freeze budget or the 1200 s timeout wastes a lane.
                if started and armed_at is None:
                    armed_at = time.time()
                if any(k.endswith("first_sample") for k in boot):
                    seen_first = True
                # Latched (2026-10-16, Windows mode 1, Ambassador>KessokHeavy a180): one read caught the
                # file mid-rewrite without its first_sample key and killed a healthy duel at armed+90 s.
                if (armed_at is not None and not seen_first
                        and time.time() - armed_at > STALL_FIRST_SAMPLE_S):
                    print("stalled: timers armed but no first sample after %.0f s - killing" % STALL_FIRST_SAMPLE_S,
                          flush=True)
                    break
                # Seen on Windows mode 2 (2026-10-16, inst01 Akira>Ambassador a180): sampling started, then
                # the game clock froze at duel t~7.8 s while the frame loop ran on; the 620 s freeze
                # budget above cost the lane ~10 min.
                if (seen_first and not finished
                        and time.time() - last_boot_change > STALL_RUNNING_S):
                    print("stalled: no progress for %.0f s after sampling started - killing" % STALL_RUNNING_S,
                          flush=True)
                    break
            if shot is not None and shot_on is not None and not shot_taken:
                boot_now = parse_cfg_section(oracle_dir / BOOT_CFG, "OracleBoot") if (oracle_dir / BOOT_CFG).exists() else {}
                if any(shot_on in v for v in boot_now.values()):
                    time.sleep(shot_delay)
                    ok = 0
                    for k in range(shot_count):
                        tk = time.time()
                        if capture(shot.with_name(f"{shot.stem}_{k:02d}{shot.suffix}")):
                            ok += 1
                        time.sleep(max(0.0, shot_every - (time.time() - tk)))
                    print(f"shots: {ok}/{shot_count} after marker '{shot_on}'", flush=True)
                    shot_taken = True
            elif shot is not None and time.time() - t0 >= shot_at_s and not shot_taken:
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
        if IS_MAC:
            # Ends every process in the oracle bottle only (bottle-scoped wineserver);
            # the user's own Bridge Commander bottle is a different wineserver.
            env = dict(os.environ, WINEPREFIX=str(CX_BOTTLE_DIR))
            subprocess.run([str(CX_BIN / "wineserver"), "-k"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if restore_hp is not None:
            restore_hp()
    result = parse_output(oracle_dir)
    tree = oracle_dir / "AITree.txt"
    if tree.exists():
        try:
            result["ai_tree_log"] = tree.read_text(errors="replace")
            tree.unlink()
        except OSError:
            pass
    ls = oracle_dir / "Lockstep.log"
    if ls.exists():
        result["lockstep_log"] = ls.read_text(errors="replace").splitlines()
    tap = oracle_dir / "CombatTap.log"
    if tap.exists():
        # Per-hit records from CombatTap.asi (native hooks on the damage pipeline), raw lines.
        result["combat_tap"] = tap.read_text(errors="replace").splitlines()
    result["elapsed_s"] = round(time.time() - t0, 1)
    result["params"] = params
    result["timed_out"] = not done
    result["manifest"] = run_manifest
    result["validation"] = _validate.validate(result, params)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--oracle-dir", type=Path,
                    default=Path(os.environ.get("DAUNTLESS_ORACLE_DIR", DEFAULT_ORACLE_DIR)))
    ap.add_argument("--attacker", default="KessokHeavy")
    ap.add_argument("--target", default="Galaxy")
    ap.add_argument("--weapon", default="phaser", choices=["phaser", "pulse", "torpedo", "tractor", "none", "ammoswitch"])
    ap.add_argument("--torp-type", type=int, default=-1)
    ap.add_argument("--att-dmg", default="none", help="attacker damage pattern 'Sub_Name/frac+...' applied at act time (repair off)")
    ap.add_argument("--human", action="store_true", help="with --duel: a person flies the player ship (no friendly AI, its weapons live)")
    ap.add_argument("--duel", action="store_true", help="both ships fight with stock Quick Battle AI (enemy QuickBattleAI, player QuickBattleFriendlyAI) until one dies")
    ap.add_argument("--probe", default="none", help="instant-read table: engine")
    ap.add_argument("--pin-start", type=float, default=-1.0,
                    help="co-simulation: start the Quick Battle simulation at this game time (s), not when the "
                         "background preload happens to finish; -1 = off (the validated oracle setup)")
    ap.add_argument("--pin-seed", type=int, default=-1,
                    help="co-simulation, with --pin-start: SetRandomSeed(this) at the pinned start; -1 = off")
    ap.add_argument("--lockstep", type=int, default=0, help="Mac: 0 rebase only, 1 fixed-step virtual clock, 2 = 1 + skip scene pass (Lockstep.asi)")
    ap.add_argument("--arc-r", type=float, default=50.0, help="catalogue arc-map radius (GU)")
    ap.add_argument("--ai-probe", action="store_true", help="record every stock FireScript instance live (Oracle.OracleAIProbe): xf rows")
    ap.add_argument("--hit-radii", default="none", help="catalogue: only sweep ShipSubsystem.IsHittableFromLocation at these radii, '+'-separated (e.g. 20+57+150)")
    ap.add_argument("--arcs-only", action="store_true", help="catalogue: arcs only (skip hull points and rays)")
    ap.add_argument("--catalogue", action="store_true", help="inventory + weapon arc maps of both ships (no firing), then quit")
    ap.add_argument("--aim-sub", default="none", help="target subsystem name to aim at ('_' for spaces), as the player's subsystem targeting does")
    ap.add_argument("--pulse-power", type=int, default=-1)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--target-alert", default="red", choices=["red", "yellow", "green"])
    ap.add_argument("--tractor-mode", default="hold", choices=["hold", "tow", "pull", "push"])
    ap.add_argument("--shield-power", type=float, default=-1.0, help="target shield generator power wanted")
    ap.add_argument("--gen-frac", type=float, default=-1.0, help="target shield generator condition fraction")
    ap.add_argument("--ai", action="store_true", help="leave the Quick Battle AI driving the attacker")
    ap.add_argument("--ai-level", type=float, default=0.5, help="BasicAttack difficulty 0.0/0.5/1.0")
    ap.add_argument("--friendly-ai-level", type=float, default=-1.0, help="duel: player-side AI level (-1 = same as --ai-level)")
    ap.add_argument("--ai-log", action="store_true", help="(non-functional: ArtificialIntelligence_LogAITree stalls the game even when armed at boot)")
    ap.add_argument("--target-motion", default="none", choices=["none", "impulse", "yaw", "warp", "warpset", "cinematic", "settarget"])
    ap.add_argument("--sample", default="attacker", choices=["attacker", "target"], help="which ship row c follows")
    ap.add_argument("--mission", default="none", help="stock campaign mission to load instead of Quick Battle (E1M1 .. E8M2); scene rows s/h/m every sample_dt for duration")
    ap.add_argument("--cam-mode", default="none", help="comma list of player-camera steps applied every --cam-step-s from act time: space:<Mode> cin:<Mode> vs:<Dir> settarget fire cinoff")
    ap.add_argument("--cam-step-s", type=float, default=4.0)
    ap.add_argument("--warp-patch", default="none", help="comma list of WarpSequence player-branch camera steps to no-op")
    ap.add_argument("--view", default="bridge", choices=["bridge", "tactical"], help="the player's view once the sim runs")
    ap.add_argument("--target-fire", action="store_true", help="player ship shoots back at act time")
    ap.add_argument("--warp-stop-gu", type=float, default=50.0)
    ap.add_argument("--warp-time", type=float, default=5.0)
    ap.add_argument("--warp-dest", default="Systems.Vesuvi.Vesuvi5", help='destination system module, or "none" to warp out')
    ap.add_argument("--warp-clear", type=float, default=0.0, help="set-to-set warp: move the target this many GU off the streak line first (0 = leave it at the origin)")
    _MOTIONS = ["none", "impulse", "impulse020", "impulse050", "impulse125", "impulse200", "impulse_power125", "impulse020_warpon", "warp", "warp_moving", "warpset", "warpset_moving", "warpset_recmd", "coast", "yaw", "pitch", "roll", "yawdirect"]

    def _motion(v):
        # turnloc<az>_<el>[s]: the AI turn controller (OracleMission._act_motion)
        if v in _MOTIONS or re.match(r"^turnloc-?\d+_-?\d+s?o?$", v):
            return v
        raise argparse.ArgumentTypeError("invalid motion %r" % v)
    ap.add_argument("--motion", default="none", type=_motion)
    ap.add_argument("--range-gu", type=float, default=57.0)
    ap.add_argument("--angle-deg", type=float, default=0.0, help="attacker bearing: 0 ahead, 90 starboard, 180 astern")
    ap.add_argument("--elev-deg", type=float, default=0.0, help="+ above (dorsal), - below")
    ap.add_argument("--shield-face", type=int, default=-1, help="preset this face (0-5) to --shield-frac of max")
    ap.add_argument("--shield-frac", type=float, default=1.0)
    ap.add_argument("--shields-off", action="store_true", help="zero every face at act time")
    ap.add_argument("--rows", default="abc", help="row kinds to sample: a weapon, b subsystems, c motion, d player camera, r repair queue")
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
    ap.add_argument("--shot-on", default=None, help="take shots once a boot marker value contains this text")
    ap.add_argument("--shot-count", type=int, default=1)
    ap.add_argument("--shot-every", type=float, default=0.25)
    ap.add_argument("--shot-delay", type=float, default=0.0)
    ap.add_argument("--difficulty", type=int, default=1, help="Game_SetDifficulty 0/1/2 (easy/medium/hard); Quick Battle's default is 1")
    ap.add_argument("--nebula", default="none", help="hull/shields/radius/dx/dy/dz[/sensor]: MetaNebula around the target at act time")
    ap.add_argument("--ai-patch", default="none", help="with --ai-module: BuilderCreate numbers to stub (N) or pass through (N=pass)")
    ap.add_argument("--face-away", action="store_true", help="place the attacker facing away from the target")
    ap.add_argument("--ai-module", default="none", help="with --ai: replace the Quick Battle AI by <module>.CreateAI (bisection)")
    ap.add_argument("--effects-wrap", action="store_true", help="count calls into Effects.py hit hooks (boot markers fx_*)")
    ap.add_argument("--hp-patch", default="none", help="<hardpoint>:<Var>.<Setter>=<v>;pulse.<Setter>=<v>;-<Template Name> - patched SDK hardpoint deployed for this run only")
    ap.add_argument("--dscale-set", type=float, default=-1.0, help=">=0: PulseWeapon_SetDamageScale on every emitter at act time, if the binding exists")
    ap.add_argument("--vfx-patch", default="none", help="projectile model override: photon:<i>=<v>,<i>=<v> (1-based CreateTorpedoModel args) or pulse:<i>=<v> (CreateDisruptorModel args)")
    ap.add_argument("--sub-preset", default="none", help="Name=frac;Name=frac (\"_\" for spaces): target subsystem condition fractions at act time, set without a hit")
    ap.add_argument("--repair-power", type=float, default=-1.0, help="target RepairSubsystem power wanted at act time")
    ap.add_argument("--repair-enqueue", action="store_true", help="AddToRepairList every --sub-preset subsystem after setting it")
    a = ap.parse_args(argv)

    params = {
        "attacker": a.attacker, "target": a.target, "weapon": a.weapon, "motion": a.motion,
        "range_gu": a.range_gu, "angle_deg": a.angle_deg, "elev_deg": a.elev_deg,
        "intensity": a.intensity, "charge": a.charge, "power_wanted": a.power_wanted,
        "shield_face": a.shield_face, "shield_frac": a.shield_frac,
        "shields_off": 1 if a.shields_off else 0,
        "settle_s": a.settle_s, "fire_at": a.fire_at, "duration": a.duration,
        "sample_dt": a.sample_dt, "disable_target_weapons": 0 if a.keep_target_weapons else 1,
        "rows": a.rows, "torp_type": a.torp_type, "aim_sub": a.aim_sub.replace(" ", "_"), "catalogue": 1 if a.catalogue else 0, "arc_r": a.arc_r, "arcs_only": 1 if a.arcs_only else 0, "hit_radii": a.hit_radii, "ai_probe": 1 if a.ai_probe else 0, "att_dmg": a.att_dmg, "duel": 1 if a.duel else 0, "human": 1 if a.human else 0, "lockstep": a.lockstep, "pin_start": a.pin_start, "pin_seed": a.pin_seed, "probe": a.probe, "pulse_power": a.pulse_power,
        "time_scale": a.time_scale, "target_alert": a.target_alert, "tractor_mode": a.tractor_mode,
        "shield_power": a.shield_power, "gen_frac": a.gen_frac,
        "ai": 1 if a.ai else 0, "ai_level": a.ai_level, "friendly_ai_level": a.friendly_ai_level, "ai_log": 1 if a.ai_log else 0,
        "target_motion": a.target_motion, "target_fire": 1 if a.target_fire else 0, "sample": a.sample, "view": a.view, "warp_patch": a.warp_patch, "mission": a.mission, "cam_mode": a.cam_mode, "cam_step_s": a.cam_step_s, "vfx_patch": a.vfx_patch, "effects_wrap": "1" if a.effects_wrap else "0", "ai_module": a.ai_module, "face_away": "1" if a.face_away else "0", "ai_patch": a.ai_patch, "nebula": a.nebula, "difficulty": a.difficulty, "hp_patch": a.hp_patch, "dscale_set": a.dscale_set,
        "sub_preset": a.sub_preset, "repair_power": a.repair_power, "repair_enqueue": 1 if a.repair_enqueue else 0,
        "warp_stop_gu": a.warp_stop_gu, "warp_time": a.warp_time, "warp_dest": a.warp_dest, "warp_clear": a.warp_clear,
    }
    result = run(a.oracle_dir, params, a.timeout, a.shot, a.shot_at, a.shot_on, a.shot_count, a.shot_every, a.shot_delay)
    print("hook markers:", ", ".join(k[3:] for k in result["hook"]))
    print("boot markers:")
    for k, v in result["boot"].items():
        print(f"  {k} = {v}")
    print(f"done={result['done']} timed_out={result['timed_out']} elapsed={result['elapsed_s']}s")
    print("validation: " + ("OK" if not result["validation"] else "; ".join(result["validation"])))
    for k, v in result["meta"].items():
        print(f"  meta {k} = {v}")
    print(summarise(result))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        write_result(a.out, result)
        print(f"wrote {a.out}")
    return 0 if result["done"] else 1


if __name__ == "__main__":
    sys.exit(main())

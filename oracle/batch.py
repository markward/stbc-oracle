"""Batch AI duels on N game instances at once (Windows; also works with Mac bottles).

  python oracle/batch.py setup --master <clean game folder> --root C:\\stbc\\inst --n 10
  python oracle/batch.py run --root C:\\stbc\\inst --lanes 10 --out results_win/duels_ai [--matrix m.json]
  python oracle/batch.py plan [--matrix m.json] --out results_win/duels_ai       (what would run)

setup: copies the clean game folder to <root>\\inst01..instNN (an existing copy is left alone),
points each copy's options.cfg "Game Path=" at itself and checks it is windowed. Every copy needs
OracleAssist.asi + Lockstep.asi + CombatTap.asi + winmm.dll (the ASI loader): OracleAssist is what
lets instances run unfocused and side by side.
NO compatibility layer by default: measured on Windows 10 (2026-10-16), the README's AppCompat layer
(DWM8And16BitMitigation ...) makes the game's window and DirectInput creation bypass OracleAssist's
hooks -- the window takes focus and the movie-skip ESC is never injected (boot 240 s instead of
4.6 s). Lockstep mode 2 does not draw the scene, so the layer's purpose (a non-black window) does
not apply. --compat-layer registers it per copy under HKCU (per user, no admin) for runs that draw.

run: one thread per lane, each owning one instance folder. Every duel is the exact command of
results_mac/worker_ai.sh (same flags, so results compare 1:1 with the Mac's) writing
<out>/duel_<A>_enemy<L>_vs_<T>_player<L>_r100_a<angle>[_rep<k>].json. A finished duel (output
exists) is skipped, so a stopped batch resumes. A failed duel (no output, timed out, or the
instance's stbc.RPT changed = the game crashed) is retried up to --retries times on any lane,
then listed in <out>/quarantine.jsonl. A lane that fails --lane-failures duels in a row stops.
Lanes start --ramp seconds apart. Every attempt is appended to <out>/ledger.jsonl.

matrix JSON (all keys optional): {"classes": [...] | "pairs": [["Galaxy","Keldon"], ...],
"both_roles": true, "levels": [1.0], "angles": [0, 90, 180, 270], "repeats": 1, "duration": 600,
"timeout": 1200}. Default: the 14 stock combat classes, every unordered pair in both roles,
level 1.0, 4 angles, 1 repeat = 728 duels.
"""
import argparse
import itertools
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE14 = ["Akira", "Ambassador", "BirdOfPrey", "CardHybrid", "Galaxy", "Galor", "Keldon", "KessokHeavy",
          "KessokLight", "Marauder", "Nebula", "Sovereign", "Vorcha", "Warbird"]
DEFAULT = {"classes": CORE14, "both_roles": True, "levels": [1.0], "angles": [0, 90, 180, 270], "repeats": 1,
           "duration": 600, "timeout": 1200}
LAYERS = "~ DWM8And16BitMitigation DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE 16BITCOLOR"
REQUIRED = ("stbc.exe", "winmm.dll", "OracleAssist.asi", "Lockstep.asi", "CombatTap.asi", "options.cfg")


# ------------------------------------------------------------------------------------- setup
def set_game_path(inst: Path) -> None:
    p = inst / "options.cfg"
    raw = p.read_bytes().decode("latin-1")
    line = "Game Path=" + str(inst.resolve())
    if re.search(r"^Game Path=.*$", raw, re.M):
        raw = re.sub(r"^Game Path=.*$", lambda m: line, raw, count=1, flags=re.M)
    else:
        raw = raw.replace("[General Options]", "[General Options]\r\n" + line, 1)
    p.write_bytes(raw.encode("latin-1"))


def register_layers(exe: Path) -> None:
    if os.name != "nt":
        return
    import winreg
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers")
    winreg.SetValueEx(key, str(exe.resolve()), 0, winreg.REG_SZ, LAYERS)
    winreg.CloseKey(key)


def setup(master: Path, root: Path, n: int, compat_layer: bool = False) -> int:
    missing = [f for f in REQUIRED if not (master / f).exists()]
    if missing:
        print("master folder lacks", missing)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        inst = root / ("inst%02d" % i)
        if not inst.exists():
            print("copying", inst, flush=True)
            shutil.copytree(master, inst)
        set_game_path(inst)
        if b"Fullscreen Mode|0" not in (inst / "options.cfg").read_bytes():
            print("WARNING: %s options.cfg is not windowed (Fullscreen Mode|0)" % inst)
        if compat_layer:
            register_layers(inst / "stbc.exe")
        print("ready", inst, flush=True)
    return 0


# -------------------------------------------------------------------------------------- plan
def load_matrix(path):
    m = dict(DEFAULT)
    if path:
        m.update(json.loads(Path(path).read_text()))
    return m


def jobs(m):
    if "pairs" in m:
        pairs = [tuple(p) for p in m["pairs"]]
    else:
        pairs = list(itertools.combinations(m["classes"], 2))
    if m.get("both_roles", True):
        pairs = pairs + [(b, a) for (a, b) in pairs if (b, a) not in pairs]
    out = []
    for k in range(int(m.get("repeats", 1))):
        for (a, t) in pairs:
            for lv in m["levels"]:
                for ang in m["angles"]:
                    out.append(dict(attacker=a, target=t, level=float(lv), angle=int(ang), rep=k))
    return out


def out_name(j):
    return "duel_%s_enemy%s_vs_%s_player%s_r100_a%d%s.json" % (
        j["attacker"], j["level"], j["target"], j["level"], j["angle"], "_rep%d" % j["rep"] if j["rep"] else "")


# --------------------------------------------------------------------------------------- run
class Batch:
    def __init__(self, a, m):
        self.a, self.m = a, m
        self.out = Path(a.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.tries = {}
        self.stats = {"ok": 0, "fail": 0, "quarantined": 0}

    def log(self, rec):
        rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            with open(self.out / "ledger.jsonl", "a") as fh:
                fh.write(json.dumps(rec) + "\n")

    def one(self, inst: Path, j) -> bool:
        out = self.out / out_name(j)
        logf = out.with_suffix(".log")
        rpt = inst / "stbc.RPT"
        before = rpt.stat().st_mtime if rpt.exists() else None
        cmd = [sys.executable, str(HERE / "run_oracle.py"), "--oracle-dir", str(inst),
               "--attacker", j["attacker"], "--target", j["target"], "--duel", "--ai",
               "--ai-level", str(j["level"]), "--friendly-ai-level", str(j["level"]), "--keep-target-weapons",
               "--weapon", "none", "--range-gu", "100", "--angle-deg", str(j["angle"]), "--ai-probe",
               "--rows", "abx", "--sample-dt", "0.25", "--fire-at", "2", "--duration", str(self.m["duration"]),
               "--timeout", str(self.m["timeout"]), "--lockstep", str(self.a.lockstep), "--out", str(out)]
        t0 = time.time()
        with open(logf, "w") as lf:
            rc = subprocess.call(cmd, stdout=lf, stderr=subprocess.STDOUT)
        txt = logf.read_text(errors="replace")
        over = re.search(r"duel_over = (t=\S+ attacker_dying=\d target_dying=\d)", txt)
        crashed = rpt.exists() and (before is None or rpt.stat().st_mtime != before)
        ok = out.exists() and rc == 0 and not crashed and ("timed_out=False" in txt or over is not None)
        if not ok and out.exists():
            out.rename(out.with_suffix(".failed.json"))
        self.log(dict(inst=inst.name, job=out.name, ok=ok, rc=rc, crashed=crashed,
                      duel_over=over.group(1) if over else None, wall_s=round(time.time() - t0, 1)))
        print("%s [%s] %s %s %s" % (time.strftime("%H:%M:%S"), inst.name, out.name,
                                     "ok" if ok else ("CRASH" if crashed else "FAIL"),
                                     over.group(1) if over else ""), flush=True)
        return ok

    def lane(self, inst: Path, delay: float):
        time.sleep(delay)
        streak = 0
        while True:
            try:
                j = self.q.get_nowait()
            except queue.Empty:
                return
            key = out_name(j)
            ok = self.one(inst, j)
            with self.lock:
                if ok:
                    self.stats["ok"] += 1
                    streak = 0
                else:
                    self.stats["fail"] += 1
                    streak += 1
                    self.tries[key] = self.tries.get(key, 0) + 1
                    if self.tries[key] <= self.a.retries:
                        self.q.put(j)
                    else:
                        self.stats["quarantined"] += 1
                        with open(self.out / "quarantine.jsonl", "a") as fh:
                            fh.write(json.dumps(dict(job=key, inst=inst.name)) + "\n")
            if streak >= self.a.lane_failures:
                print("lane %s stopped after %d failures in a row" % (inst.name, streak), flush=True)
                return

    def run(self, insts):
        todo = [j for j in jobs(self.m) if not (self.out / out_name(j)).exists()]
        print("%d duels in the matrix, %d to run, %d lanes" % (len(jobs(self.m)), len(todo), len(insts)), flush=True)
        for j in todo:
            self.q.put(j)
        th = [threading.Thread(target=self.lane, args=(inst, i * self.a.ramp), daemon=True)
              for i, inst in enumerate(insts)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        print("done:", self.stats, flush=True)
        return 0 if self.stats["quarantined"] == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--master", type=Path, required=True)
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--n", type=int, default=10)
    s.add_argument("--compat-layer", action="store_true", help="register the AppCompat layer (breaks OracleAssist's hooks; only for runs that draw)")
    for name in ("run", "plan"):
        r = sub.add_parser(name)
        r.add_argument("--matrix")
        r.add_argument("--out", required=True)
        r.add_argument("--root", type=Path)
        r.add_argument("--lanes", type=int, default=1)
        r.add_argument("--first-lane", type=int, default=1, help="use inst<first>..inst<first+lanes-1>")
        r.add_argument("--ramp", type=float, default=60.0)
        r.add_argument("--retries", type=int, default=2)
        r.add_argument("--lane-failures", type=int, default=3)
        r.add_argument("--lockstep", type=int, default=2)
    a = ap.parse_args(argv)
    if a.cmd == "setup":
        return setup(a.master, a.root, a.n, a.compat_layer)
    m = load_matrix(a.matrix)
    if a.cmd == "plan":
        js = jobs(m)
        done = sum((Path(a.out) / out_name(j)).exists() for j in js)
        print("%d duels, %d done, %d to run" % (len(js), done, len(js) - done))
        for j in js[:10]:
            print("  ", out_name(j))
        return 0
    if a.root is None:
        ap.error("run needs --root")
    insts = [a.root / ("inst%02d" % i) for i in range(a.first_lane, a.first_lane + a.lanes)]
    bad = [str(i) for i in insts if not (i / "stbc.exe").exists()]
    if bad:
        print("missing instances:", bad)
        return 2
    return Batch(a, m).run(insts)


if __name__ == "__main__":
    sys.exit(main())

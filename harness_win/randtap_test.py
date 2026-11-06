"""Can the original game replay a fight exactly from a seed? (co-simulation groundwork)

  python harness_win/randtap_test.py --oracle-dir <instance> --out <dir> --runs A:12345 B:12345 C:777
         [--isolate 004EA435] [--no-sound] [--duration 40] [--attacker Galaxy --target Keldon --angle 0]

Each run: writes <instance>/RandTap.ini (seed, trace=1, isolate), optionally switches the game's sound
off in <instance>/options.cfg (Sound Enabled / Voice Enabled / Music -> 0; the original file is
restored afterwards, also on error), runs one bounded duel with oracle/run_oracle.py (lockstep mode 2),
and keeps <out>/<run>.json, <run>.grn (every GetRandomNumber: rand index, n, result, caller),
<run>.trace (every main-stream rand(): index, caller, value) and <run>.randtap.log.
Then compares every pair of runs: where their GetRandomNumber sequences and main rand() streams first
differ, and whether their sampled state rows (positions, orientation, shields, status) are identical.
The instance must contain RandTap.asi (oracle/native/randtap, built with oracle/native/build.sh); remove it afterwards to return the
instance to the validated oracle setup.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE.parent / "oracle" / "run_oracle.py"


def set_sound(cfg: Path, on: bool) -> bytes:
    raw = cfg.read_bytes()
    out = raw
    for key in (b"Sound Enabled|", b"Voice Enabled|", b"Music|"):
        i = out.find(b"\n" + key)
        if i >= 0:
            j = out.find(b"\r", i + 1 + len(key))
            j = out.find(b"\n", i + 1 + len(key)) if j < 0 else j
            out = out[:i + 1 + len(key)] + (b"1" if on else b"0") + out[j:]
    cfg.write_bytes(out)
    return raw


def grn(path):
    b = path.read_bytes()
    return [struct.unpack_from("<4I", b, i) for i in range(0, len(b) - 15, 16)]


def trace(path):
    b = path.read_bytes()
    return [struct.unpack_from("<IIH", b, i) for i in range(0, len(b) - 9, 10)]


def state_rows(path):
    d = json.loads(path.read_text())
    return [r for r in d.get("raw_rows", []) if r.startswith(("xm", "xo", "xh", "xz"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--runs", nargs="+", required=True, help="NAME:SEED ...")
    ap.add_argument("--isolate", default="")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--attacker", default="Galaxy")
    ap.add_argument("--target", default="Keldon")
    ap.add_argument("--angle", type=int, default=0)
    ap.add_argument("--compare-only", action="store_true")
    ap.add_argument("--pin-start", type=float, default=-1.0, help="start the battle at this game time (run_oracle --pin-start)")
    a = ap.parse_args()
    inst = a.oracle_dir
    a.out.mkdir(parents=True, exist_ok=True)
    if not (inst / "RandTap.asi").exists():
        sys.exit("RandTap.asi is not installed in %s" % inst)
    names = []
    for spec in a.runs:
        name, seed = spec.split(":")
        names.append(name)
        if a.compare_only:
            continue
        (inst / "RandTap.ini").write_text("[randtap]\r\nseed=%s\r\ntrace=1\r\nisolate=%s\r\n" % (seed, a.isolate))
        saved = set_sound(inst / "options.cfg", False) if a.no_sound else None
        try:
            cmd = [sys.executable, str(RUNNER), "--oracle-dir", str(inst), "--attacker", a.attacker, "--target", a.target,
                   "--duel", "--ai", "--ai-level", "1.0", "--friendly-ai-level", "1.0", "--keep-target-weapons",
                   "--weapon", "none", "--range-gu", "100", "--angle-deg", str(a.angle), "--ai-probe", "--rows", "abx",
                   "--sample-dt", "0.25", "--fire-at", "2", "--duration", str(a.duration), "--timeout", "400",
                   "--lockstep", "2", "--pin-start", str(a.pin_start), "--pin-seed", seed if a.pin_start > 0 else "-1",
                   "--out", str(a.out / (name + ".json"))]
            rc = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        finally:
            if saved is not None:
                (inst / "options.cfg").write_bytes(saved)
        for src, dst in (("RandTap.grn", ".grn"), ("RandTap.trace", ".trace"), ("RandTap.log", ".randtap.log")):
            if (inst / src).exists():
                shutil.copy(inst / src, a.out / (name + dst))
        print("run %s seed %s rc=%d" % (name, seed, rc), flush=True)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            x, y = names[i], names[j]
            gx, gy = grn(a.out / (x + ".grn")), grn(a.out / (y + ".grn"))
            n = min(len(gx), len(gy))
            dg = next((k for k in range(n) if gx[k][1:3] != gy[k][1:3]), None)
            tx, ty = trace(a.out / (x + ".trace")), trace(a.out / (y + ".trace"))
            m = min(len(tx), len(ty))
            # a caller outside stbc.exe (0x400000-0x9b6000) is MinHook's trampoline for GetRandomNumber:
            # its address changes every run, so compare it as one symbolic caller
            def ck(r):
                return (r[1] if 0x400000 <= r[1] < 0x9b6000 else 0, r[2])
            dt = next((k for k in range(m) if ck(tx[k]) != ck(ty[k])), None)
            sx, sy = state_rows(a.out / (x + ".json")), state_rows(a.out / (y + ".json"))
            ds = next((k for k in range(min(len(sx), len(sy))) if sx[k] != sy[k]), None)
            # the same rows with the absolute time label removed: identical here but not above means the
            # runs differ only by WHEN the duel was armed (a start-tick shift), not in what happened
            def strip(r):
                return " ".join(w for w in r.split() if not w.startswith("t="))
            dsr = next((k for k in range(min(len(sx), len(sy))) if strip(sx[k]) != strip(sy[k])), None)
            print("%s vs %s: GetRandomNumber %d/%d calls, first diff %s | main rand() %d/%d, first diff %s%s | "
                  "state rows %d/%d, %s" % (
                      x, y, len(gx), len(gy), dg, len(tx), len(ty), dt,
                      "" if dt is None else " (%08x vs %08x)" % (tx[dt][1], ty[dt][1]),
                      len(sx), len(sy), "IDENTICAL" if (ds is None and len(sx) == len(sy)) else
                      "first diff at row %s: %s" % (ds, (sx[ds][:60] if ds is not None else "length"))), flush=True)
            if ds is not None:
                print("    ignoring the time label: %s" % ("IDENTICAL" if dsr is None and len(sx) == len(sy)
                                                         else "first diff at row %s" % dsr), flush=True)


if __name__ == "__main__":
    main()

"""Impulse matrix report: speed vs throttle level/power, ramp times, level changes, turning at speed."""
import math, re, sys
sys.path.insert(0, ".")
from common import shots, xrows
V = lambda s: [float(x) for x in s.split(",")]
def series(r, t0, t1):
    out = []
    for d in xrows(r, "xm", "A", t0, t1):
        v = V(d["v"]); f = 1.0
        out.append((d["t"] - t0, float(d["sp"]), math.hypot(*V(d["w"]))))
    return out
def g(spec, k):
    m = re.search(" " + k + r"=(\S+)", spec); return m.group(1) if m else None
rows = []
for s in shots(sys.argv[1]):
    r = s["run"]; sp = s["spec"]
    ser = series(r, s["start"], s["end"] - 1.1)      # drop the 1 s gap where the ship is stopped for the next shot
    rows.append((s["index"], g(sp, "mv"), float(g(sp, "ipw")), g(sp, "mf"), g(sp, "mf2"), float(g(sp, "t2") or 0), ser))
for pw in (1.0, 0.75, 0.5, 1.25):
    print(f"===== engine power {int(pw*100)}%  (Sovereign max speed 7.5 x power = {7.5*pw:.3f})")
    print("  level  throttle  final speed  (expected)   t to 50%  t to 90%  t to 99%   max accel")
    for idx, mv, p, mf, mf2, t2, ser in rows:
        if p != pw or mv != "impulse" or mf2 != "none":
            continue
        f = float(mf); fin = ser[-1][1]; exp = 7.5 * pw * f
        def tt(frac):
            return next((t for t, v, w in ser if v >= frac * fin), float("nan"))
        acc = max((b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(ser, ser[1:]) if b[0] > a[0])
        print(f"  {round(f*9):>5}  {f:8.4f}  {fin:10.4f}  ({exp:7.4f})  {tt(.5):8.2f}  {tt(.9):8.2f}  {tt(.99):8.2f}  {acc:9.4f}")
    print("  level change (at t=10 s):  from -> to   speed before  after (final)  time to settle (99%)  decel/accel rate")
    for idx, mv, p, mf, mf2, t2, ser in rows:
        if p != pw or mf2 in (None, "none"):
            continue
        before = [v for t, v, w in ser if t < t2]; after = [(t, v) for t, v, w in ser if t >= t2]
        b = before[-1]; fin = after[-1][1]
        target_reached = next((t - t2 for t, v in after if abs(v - fin) <= 0.01 * max(abs(fin), 0.05)), float("nan"))
        rate = max(abs(after[i+1][1] - after[i][1]) / (after[i+1][0] - after[i][0]) for i in range(len(after) - 1))
        fa, fb = round(float(mf) * 9), round(float(mf2) * 9)
        print(f"     {fa:>3} -> {fb:<3}         {b:8.4f}      {fin:8.4f}      {target_reached:6.2f}          {rate:7.4f}")
    print("  turning at speed (yaw full): level  speed before turn  min speed while turning  turn rate")
    for idx, mv, p, mf, mf2, t2, ser in rows:
        if p != pw or mv != "impyaw":
            continue
        mx = max(v for t, v, w in ser); mn = min(v for t, v, w in ser if t > 3); wmax = max(w for t, v, w in ser)
        print(f"        {round(float(mf)*9):>5}  {mx:8.4f}           {mn:8.4f}             {wmax:.4f}")

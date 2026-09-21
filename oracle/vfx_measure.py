"""Measure torpedo sprite layers in TorpCam screenshot bursts (pure-python PNG decode).

Evidence for bible 14.2: core radius, orange halo/flare pixel counts, flare reach
and flare-direction histograms per frame, for docs/results/vfx/<name>_<k>.png
(taken by run_oracle.py --shot-on stopfire --shot-count 12 with --vfx-patch).
"""
import zlib, struct, sys, math, glob, os, json

import pathlib
S = str(pathlib.Path(__file__).resolve().parent.parent / "docs" / "results" / "vfx")   # <name>_<k>.png bursts


def load_png(path):
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8; idat = b""; w = h = 0
    while pos < len(d):
        n = struct.unpack(">I", d[pos:pos+4])[0]; tag = d[pos+4:pos+8]; body = d[pos+8:pos+8+n]; pos += 12 + n
        if tag == b"IHDR": w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT": idat += body
    raw = zlib.decompress(idat); stride = w * 3 + 1
    px = []
    prev = bytearray(w * 3)
    for y in range(h):
        f = raw[y*stride]; row = bytearray(raw[y*stride+1:(y+1)*stride])
        if f == 1:
            for i in range(3, len(row)): row[i] = (row[i] + row[i-3]) & 255
        elif f == 2:
            for i in range(len(row)): row[i] = (row[i] + prev[i]) & 255
        elif f == 3:
            for i in range(len(row)): row[i] = (row[i] + ((row[i-3] if i >= 3 else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(len(row)):
                a = row[i-3] if i >= 3 else 0; b = prev[i]; c = prev[i-3] if i >= 3 else 0
                p = a + b - c; pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 255
        px.append(bytes(row)); prev = row
    return w, h, px


def measure(path):
    w, h, px = load_png(path)
    core = []; orange = []
    for y in range(h):
        row = px[y]
        for x in range(w):
            r, g, b = row[3*x], row[3*x+1], row[3*x+2]
            if r > 230 and g > 200 and b < 170 and r + g > 470:      # yellow-white core
                core.append((x, y))
            elif r > 120 and g < 0.6 * r and b < 0.35 * r and r > g + 40:   # orange glow / flares
                orange.append((x, y))
    if not core:
        return None
    cx = sum(p[0] for p in core) / len(core); cy = sum(p[1] for p in core) / len(core)
    core_r = math.sqrt(len(core) / math.pi)
    # glow = orange within 2.5 core radii + 25 px; flares = the rest
    lim = max(2.5 * core_r, 25) + 30
    glow = [p for p in orange if math.hypot(p[0]-cx, p[1]-cy) <= lim]
    flares = [p for p in orange if math.hypot(p[0]-cx, p[1]-cy) > lim]
    fmax = max((math.hypot(p[0]-cx, p[1]-cy) for p in flares), default=0.0)
    # flare direction histogram (16 bins) for rotation comparison
    bins = [0]*16
    for p in flares:
        a = math.atan2(p[1]-cy, p[0]-cx); bins[int(((a + math.pi) / (2*math.pi)) * 16) % 16] += 1
    return dict(cx=cx, cy=cy, core_px=len(core), core_r=core_r, glow_px=len(glow), flare_px=len(flares), flare_max=fmax, bins=bins)


def run(name):
    files = sorted(glob.glob(os.path.join(S, f"{name}_*.png")))
    out = []
    for f in files:
        m = measure(f)
        out.append(m)
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or ["stock", "core", "flares0", "rot0", "flarelen", "glowbig", "pulse"]
    summary = {}
    for n in names:
        ms = run(n)
        valid = [m for m in ms if m]
        if not valid:
            print(n, "no core found"); continue
        def series(k): return [round(m[k], 1) for m in ms if m]
        # rotation: mean L1 distance between successive normalised flare histograms
        rot = []
        for a, b in zip(valid, valid[1:]):
            sa, sb = sum(a["bins"]) or 1, sum(b["bins"]) or 1
            rot.append(sum(abs(x/sa - y/sb) for x, y in zip(a["bins"], b["bins"])) / 2)
        summary[n] = dict(core_r=series("core_r"), glow_px=series("glow_px"), flare_px=series("flare_px"), flare_max=series("flare_max"),
                          rot_change=[round(x, 2) for x in rot])
        print(f"== {n}: frames={len(valid)}")
        print("   core radius px :", series("core_r"))
        print("   glow px        :", series("glow_px"))
        print("   flare px       :", series("flare_px"))
        print("   flare reach px :", series("flare_max"))
        print("   flare rotation :", [round(x, 2) for x in rot])
    json.dump(summary, open(os.path.join(S, "vfx_summary.json"), "w"), indent=1)

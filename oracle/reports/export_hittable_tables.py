"""Export the original's ShipSubsystem.IsHittableFromLocation maps for ENERGY WEAPONS to Dauntless.

For every subsystem except energy weapons the original's answer is a line of sight through the drawn hull (Dauntless
computes it: engine/appc/hull_line_of_sight.py). Energy weapons -- phaser banks, tractor projectors, pulse weapons --
follow no geometric rule found yet (best candidate 77% over twelve classes; e.g. the Akira's dorsal banks are
hittable from everywhere BELOW, nowhere above), but their answer is range-independent (99.2% of cells identical at 57
and 150 GU), so the measured 10-degree direction map IS the behaviour for the stock ships.

Reads results_mac/ (or ORACLE_RESULTS) hittable_<a>_<t>.json (+ hittable_r20_57_150.json, Galaxy/Sovereign) and writes
bc_hittable_maps.json (and bc_ship_radii.json) into its exports/ folder, or into --out-dir:
  {"grid": {"elev": [-90, 90, 10], "az": [0, 350, 10]}, "radius_gu": 57,
   "ships": {<hardpoint file>: {<subsystem name>: <19 rows x 9 hex digits, elevation -90 first; bit k of digit j =
   azimuth (4j+k)*10 deg, 0 = nose, 90 = starboard>}}}
usage: ORACLE_SDK_HARDPOINTS=<SDK>/scripts/ships/Hardpoints python export_hittable_tables.py [--out-dir DIR]
"""
import argparse, glob, json, os, re, sys

# The captures: results_mac/ beside oracle/, or ORACLE_RESULTS (as the scorecard reads them).
ROOT = os.environ.get("ORACLE_RESULTS") or os.path.join(os.path.dirname(__file__), "..", "..", "results_mac")
OUT_DIR = os.path.join(ROOT, "exports")
SDK_SHIPS = None     # the SDK's scripts/ships: the parent of ORACLE_SDK_HARDPOINTS


def hardpoint_of(cls):
    src = open(os.path.join(SDK_SHIPS, cls + ".py")).read()
    return re.search(r'"HardpointFile"\s*:\s*"([^"]+)"', src).group(1).lower()


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "hittable_*_*.json"))) + [os.path.join(ROOT, "hittable_r20_57_150.json")]
    ships = {}
    sources = []
    for f in files:
        d = json.load(open(f))
        if not d.get("done"):
            continue
        p = d["params"]
        rr = d["raw_rows"]
        for tag, cls in (("A", p["attacker"]), ("T", p["target"])):
            hp = hardpoint_of(cls)
            if hp in ships:
                continue
            names, ew = {}, set()
            for l in rr:
                if l.startswith("cs %s " % tag):
                    i = int(l.split()[2])
                    names[i] = re.search(r"name=(.*?) types=", l).group(1).replace("_", " ")
                    if "EnergyWeapon" in l:
                        ew.add(i)
            rows = {}
            for l in rr:
                if l.startswith("cH %s " % tag) and " r=57" in l:
                    q = l.split()
                    i = int(q[2])
                    if i in ew:
                        rows.setdefault(i, {})[int(q[4][2:])] = q[5][:9]
            table = {}
            for i, r in rows.items():
                if len(r) == 19:
                    table[names[i]] = "".join(r[e] for e in range(-90, 91, 10))
            ships[hp] = table
            sources.append("%s (%s)" % (cls, os.path.basename(f)))
    out = {"grid": {"elev": [-90, 90, 10], "az": [0, 350, 10]}, "radius_gu": 57,
           "source": "stbc.exe ShipSubsystem.IsHittableFromLocation, stbc-oracle catalogue --hit-radii; " + ", ".join(sources),
           "ships": ships}
    path = os.path.join(OUT_DIR, "bc_hittable_maps.json")
    json.dump(out, open(path, "w"), indent=1, sort_keys=True)
    print("wrote %s: %d hardpoints, %d energy weapons" % (path, len(ships), sum(len(v) for v in ships.values())))


def model_of(cls):
    src = open(os.path.join(SDK_SHIPS, cls + ".py")).read()
    return re.search(r'"FilenameHigh"\s*:\s*"([^"]+)"', src).group(1).lower()


def export_radii():
    """ShipClass.GetRadius as the original reports it (catalogue cg rows), keyed by the ship's FilenameHigh (lower
    case): the AI's personal space, intercept and warp-in distances read it. No simple bound of the drawn mesh
    reproduces it (the AABB-corner Dauntless seeds is 8% short on a Galaxy, 33% long on a Kessok Heavy)."""
    radii = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "catalogue_*_*.json"))):
        if os.path.basename(f).startswith(("catalogue_arcs", "catalogue_m2")):
            continue
        d = json.load(open(f))
        p = d["params"]
        for l in d["raw_rows"]:
            if l.startswith("cg ") and "ShipClass.GetRadius=" in l:
                cls = p["attacker"] if l.split()[1] == "A" else p["target"]
                radii.setdefault(model_of(cls), round(float(l.split("=")[1]), 5))
    path = os.path.join(OUT_DIR, "bc_ship_radii.json")
    json.dump({"source": "stbc.exe ShipClass.GetRadius, stbc-oracle catalogues", "radius_gu": radii},
              open(path, "w"), indent=1, sort_keys=True)
    print("wrote %s: %d models" % (path, len(radii)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", default=OUT_DIR, help="where the two JSON files go (default results_mac/exports/)")
    a = ap.parse_args()
    hp = os.environ.get("ORACLE_SDK_HARDPOINTS")
    if not hp:
        sys.exit("set ORACLE_SDK_HARDPOINTS to the SDK's scripts/ships/Hardpoints folder")
    SDK_SHIPS = os.path.dirname(os.path.normpath(hp))
    OUT_DIR = a.out_dir
    os.makedirs(OUT_DIR, exist_ok=True)
    main()
    export_radii()

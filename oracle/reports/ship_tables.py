"""Per-ship subsystem and weapon tables (markdown) from the catalogue capture."""
import json, math, sys
CAT = sys.argv[1] if len(sys.argv) > 1 else "results_mac/catalogue_galaxy_sovereign.json"
cat = json.load(open(CAT))
subs, props = {}, {}
for l in cat["raw_rows"]:
    p = l.split(" ", 3)
    if p[0] == "cs":
        subs[(p[1], int(p[2]))] = dict(x.split("=", 1) for x in p[3].split())
    elif p[0] == "cp" and "=" in p[3]:
        k, v = p[3].split("=", 1)
        props.setdefault((p[1], int(p[2])), {})[k.split(".", 1)[1]] = v
# Measured arc maps (ca rows): per weapon and elevation, a hex bitmap over azimuth 0..355 step 5
# (bit j = azimuth 5*j, 4 bits per hex digit, low bit first). Used for tubes, whose arc is a game test.
arcmap = {}
for l in cat["raw_rows"]:
    p = l.split()
    if p[0] == "ca" and len(p) == 6 and p[4].startswith("e="):
        bits = []
        for ch in p[5]:
            v = int(ch, 16)
            bits += [(v >> q) & 1 for q in range(4)]
        arcmap.setdefault((p[1], int(p[2])), {})[int(p[4][2:])] = bits[:72]
def arc_summary(key):
    m = arcmap.get(key)
    if not m:
        return "-", "-"
    lvl = m.get(0, [])
    az = [((5 * j + 180) % 360) - 180 for j, b in enumerate(lvl) if b]
    if not az:
        return "none at level", "-"
    # contiguous span around the centre of mass (handles wrap at ±180)
    if min(az) == -180 and max(az) >= 175:
        off = [((a % 360) - 180) for a in az]          # offsets from dead astern
        span = f"astern ±{max(abs(min(off)), abs(max(off)))}°"
    else:
        span = f"{min(az)}..{max(az)}°"
    els = sorted(e for e, b in m.items() if any(b))
    return span, f"{els[0]}..{els[-1]}°"
TORP = {"Galaxy": "photon 500", "Sovereign": "photon 550 / quantum 900"}
def f(v, nd=2):
    try:
        x = float(v); return str(int(x)) if x == int(x) else f"{x:.{nd}f}"
    except (TypeError, ValueError):
        return v or "-"
for tag in ("T", "A"):
    cls = cat["params"]["target" if tag == "T" else "attacker"]
    ids = sorted(i for t, i in subs if t == tag)
    print(f"\n#### {cls}: subsystems\n")
    print("| Subsystem | Parent | HP | Disabled below | Repair complexity | Radius | Position (x,y,z) | Targetable | Critical |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i in ids:
        s, pr = subs[(tag, i)], props.get((tag, i), {})
        par = subs.get((tag, int(s["parent"])), {}).get("name", "-")
        dis = pr.get("GetDisabledPercentage")
        print(f"| {s['name']} | {par} | {f(pr.get('GetMaxCondition'))} | {f(float(dis)*100) + '%' if dis else '-'} | "
              f"{f(pr.get('GetRepairComplexity'))} | {f(pr.get('GetRadius'), 3)} | {pr.get('GetPosition', '-')} | "
              f"{pr.get('IsTargetable', '-')} | {pr.get('IsCritical', '-')} |")
    print(f"\n#### {cls}: beam weapons (phasers and tractors)\n")
    print("| Weapon | Type | Max damage | Damage radius | Max charge | Min firing charge | Recharge /s | Arc width | Arc height |")
    print("|---|---|---|---|---|---|---|---|---|")
    tubes = []
    for i in ids:
        s, pr = subs[(tag, i)], props.get((tag, i), {})
        t = s["types"].split(",")
        kind = next((k for k in ("PhaserBank", "TorpedoTube", "PulseWeapon", "TractorBeamProjector") if k in t), None)
        if not kind:
            continue
        if kind == "TorpedoTube":
            aw, ah = arc_summary((tag, i))
            tubes.append(f"| {s['name']} | {TORP.get(cls, '?')} | {pr.get('GetDirection', '-')} | "
                         f"{aw} | {ah} | {f(pr.get('GetMaxReady'))} | {f(pr.get('GetReloadDelay'))} s | {f(pr.get('GetImmediateDelay'))} s | {pr.get('GetGroups', '-')} |")
            continue
        deg = lambda k: f"{math.degrees(float(pr[k])):.0f}"
        arc_w = f"{deg('GetArcWidthAngleMin')}..{deg('GetArcWidthAngleMax')}°" if "GetArcWidthAngleMin" in pr else "-"
        arc_h = f"{deg('GetArcHeightAngleMin')}..{deg('GetArcHeightAngleMax')}°" if "GetArcHeightAngleMin" in pr else "-"
        print(f"| {s['name']} | {kind} | {f(pr.get('GetMaxDamage'))} | {f(pr.get('GetDamageRadiusFactor'), 3)} | "
              f"{f(pr.get('GetMaxCharge'))} | {f(pr.get('GetMinFiringCharge'))} | {f(pr.get('GetRechargeRate'), 3)} | {arc_w} | {arc_h} |")
    print(f"\n#### {cls}: torpedo tubes\n")
    print("Damage, speed and guidance belong to the torpedo type, not the tube; tubes do not charge. "
          "The tube's own DamageRadiusFactor (0.2) is not the hit radius; measured torpedo hits use the torpedo type's radius (about 0.13-0.14). "
          "The firing arc is the game's own in-arc test sampled every 5° (azimuth from dead ahead, positive to starboard).\n")
    print("| Tube | Torpedo damage | Direction | Arc at level | Elevation range | Holds | Reload | Launch delay | Spread group |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in tubes:
        print(row)
    print(f"\n#### {cls}: ship-level systems\n")
    for i in ids:
        s, pr = subs[(tag, i)], props.get((tag, i), {})
        keep = {k: pr[k] for k in ("GetMaxSpeed", "GetMaxAccel", "GetMaxAngularVelocity", "GetMaxAngularAccel", "GetPowerOutput",
                                    "GetMainBatteryLimit", "GetBackupBatteryLimit", "GetMainConduitCapacity", "GetBackupConduitCapacity",
                                    "GetBaseSensorRange", "GetMaxRepairPoints", "GetNumRepairTeams", "GetNormalPowerPerSecond",
                                    "GetFiringChainString", "GetNumAmmoTypes", "GetMaxProbes") if k in pr}
        if keep:
            print(f"- **{s['name']}**: " + ", ".join(f"{k[3:]} {f(v)}" for k, v in keep.items()))

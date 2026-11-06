# OracleCatalogue -- complete inventory and weapon-arc maps of both ships, no firing.  Python 1.5.
#
# Inventory: every subsystem and child of each ship.  Its runtime type is found by trying every
# subsystem cast; its property by trying every property cast.  Then EVERY no-argument Get*/Is*
# method of each matching class (walking base classes) is called and recorded, so nothing depends
# on a hand-picked list.  Rows:
#   cs <ship> <idx> parent=<idx> name=<name> types=<Cast,...> props=<Cast,...>
#   cp <ship> <idx> <Class>.<Getter>=<value>          (property getters)
#   cr <ship> <idx> <Class>.<Getter>=<value>          (runtime object getters)
#   cg <ship> <Class>.<Getter>=<value>                (ship-level property getters)
# Arc maps: for every emitter (phaser bank, pulse weapon, torpedo tube, tractor projector),
# points on a sphere of radius ARC_R around the ship's centre are tested with the game's own
# checks (PhaserBank.CanHit, PulseWeapon.IsInArc/CanHitTarget, TorpedoTube.IsInArc/CanHit,
# TractorBeamProjector via EnergyWeapon/PhaserBank cast).  Rows:
#   ca <ship> <idx> <method> e=<elev deg> <hex bitmask over azimuth 0..355 step ARC_STEP, model frame>
# Hex: nibble j holds azimuth bins 4j..4j+3, least significant bit first.
# Azimuth/elevation are in the SHIP'S MODEL FRAME: az 0 = model +Y (nose), 90 = model +X
# (starboard), elev +90 = model +Z (dorsal).
import App
import string
import Oracle.OracleLog

_log = Oracle.OracleLog
NonSerializedObjects = ("_log",)

ARC_STEP = 5
ARC_R = 50.0
HIT_STEP = 10

SUB_CASTS = ("ShipSubsystem", "PoweredSubsystem", "PowerSubsystem", "Weapon", "WeaponSystem",
             "TorpedoSystem", "TorpedoTube", "ShieldClass", "HullClass", "EnergyWeapon",
             "PhaserSystem", "PhaserBank", "PulseWeapon", "PulseWeaponSystem", "SensorSubsystem",
             "CloakingSubsystem", "RepairSubsystem", "ImpulseEngineSubsystem",
             "WarpEngineSubsystem", "TractorBeamProjector", "TractorBeamSystem")
PROP_CASTS = ("SubsystemProperty", "PoweredSubsystemProperty", "WeaponSystemProperty",
              "WeaponProperty", "EnergyWeaponProperty", "PhaserProperty", "PulseWeaponProperty",
              "TractorBeamProperty", "TorpedoTubeProperty", "TorpedoSystemProperty",
              "ShieldProperty", "HullProperty", "SensorProperty", "CloakingSubsystemProperty",
              "RepairSubsystemProperty", "PowerProperty", "ImpulseEngineProperty",
              "WarpEngineProperty", "EngineProperty", "PositionOrientationProperty")
# Getters never called: need arguments in practice, return UI/sound/texture data, or are known
# to be unsafe without context.
SKIP = ("GetPropertySet", "GetPropertyList", "GetNextSubsystemMatch", "GetChildSubsystem",
        "GetObjID", "GetTargetID", "GetParentShip", "GetParentSubsystem", "GetProperty",
        "GetContainingSet", "GetNode", "GetSoundFromSet", "GetFireLoopSound", "GetFireSound",
        "GetFireStartSound", "GetMainBatteryWatcher", "GetBackupBatteryWatcher",
        "GetCombinedPercentageWatcher", "GetMaxShieldsWatcher")

def _fmt(v):
    t = type(v)
    if t == type(1.0):
        return "%.6g" % v
    if t == type(1) or t == type(""):
        return str(v)
    if v is None:
        return "None"
    try:
        return "%.6g,%.6g,%.6g" % (v.x, v.y, v.z)
    except:
        pass
    try:
        return "<%s>" % v.__class__.__name__
    except:
        return "<obj>"

def _methods(cls, out):
    """All Get*/Is* attribute names of cls and its bases (Python 1.5: dir() is not inherited)."""
    for k in dir(cls):
        if (k[:3] == "Get" or k[:2] == "Is") and k not in SKIP and not out.has_key(k):
            out[k] = 1
    try:
        for b in cls.__bases__:
            _methods(b, out)
    except:
        pass

def _dump(kind, ship, idx, obj, clsname):
    names = {}
    try:
        _methods(getattr(App, clsname), names)
    except:
        return
    keys = names.keys()
    keys.sort()
    for k in keys:
        try:
            v = getattr(obj, k)()
        except:
            continue            # needs arguments, or not valid here
        if idx is None:
            _log.row("c%s %s %s.%s=%s" % (kind, ship, clsname, k, _fmt(v)))
        else:
            _log.row("c%s %s %d %s.%s=%s" % (kind, ship, idx, clsname, k, _fmt(v)))

def _walk(pShip):
    out = []        # (sub, parent index)
    it = pShip.StartGetSubsystemMatch(App.CT_SHIP_SUBSYSTEM)
    while 1:
        pSub = pShip.GetNextSubsystemMatch(it)
        if pSub is None:
            break
        pi = len(out)
        out.append((pSub, -1))
        i = 0
        while i < pSub.GetNumChildSubsystems():
            c = pSub.GetChildSubsystem(i)
            if c is not None:
                out.append((c, pi))
            i = i + 1
    pShip.EndGetSubsystemMatch(it)
    return out

def _types(sub):
    hits = []
    for c in SUB_CASTS:
        try:
            if getattr(App, c + "_Cast")(sub) is not None:
                hits.append(c)
        except:
            pass
    return hits

def _props(prop):
    hits = []
    for c in PROP_CASTS:
        try:
            if getattr(App, c + "_Cast")(prop) is not None:
                hits.append(c)
        except:
            pass
    return hits

def inventory(tag, pShip):
    _log.mark("cat_" + tag, "start " + pShip.GetName())
    try:
        sp = pShip.GetShipProperty()
        _dump("g", tag, None, App.ShipProperty_Cast(sp), "ShipProperty")
    except:
        _log.mark("cat_shipprop_error", _log.exc())
    for k in ("GetRadius", "GetMass", "GetName", "GetWorldLocation"):
        try:
            _log.row("cg %s ShipClass.%s=%s" % (tag, k, _fmt(getattr(pShip, k)())))
        except:
            pass
    subs = _walk(pShip)
    idx = 0
    for (sub, parent) in subs:
        ty = _types(sub)
        prop = None
        pt = []
        try:
            prop = sub.GetProperty()
            pt = _props(prop)
        except:
            pass
        _log.row("cs %s %d parent=%d name=%s types=%s props=%s" % (
            tag, idx, parent, string.replace(sub.GetName(), " ", "_"),
            string.join(ty, ","), string.join(pt, ",")))
        _log.pulse("cat %s %d" % (tag, idx))
        for c in pt:
            try:
                _dump("p", tag, idx, getattr(App, c + "_Cast")(prop), c)
            except:
                _log.mark("cat_prop_error", "%s %d %s %s" % (tag, idx, c, _log.exc()))
        for c in ty:
            try:
                _dump("r", tag, idx, getattr(App, c + "_Cast")(sub), c)
            except:
                _log.mark("cat_rt_error", "%s %d %s %s" % (tag, idx, c, _log.exc()))
        idx = idx + 1
    _log.mark("cat_" + tag + "_done", "subsystems=%d" % idx)
    return subs

HULL_POINTS = 600

def hull_points(tag, pShip):
    """The game's own hull surface samples: ObjectClass.GetLocalRandomPointAndNormalOnModel.
    Rows: ch <ship> p=x,y,z n=x,y,z   (model frame).  Lets impact points be predicted."""
    n = 0
    err = ""
    i = 0
    mode = 0
    while i < HULL_POINTS:
        try:
            pt = None
            nm = None
            if mode == 0:
                try:
                    r = pShip.GetLocalRandomPointAndNormalOnModel()
                    try:
                        pt, nm = r[0], r[1]
                    except:
                        pt = r
                except:
                    mode = 1
            if mode == 1:
                pt = App.TGPoint3()
                nm = App.TGPoint3()
                pShip.GetLocalRandomPointAndNormalOnModel(pt, nm)
            if nm is not None:
                _log.row("ch %s p=%.4f,%.4f,%.4f n=%.4f,%.4f,%.4f" % (tag, pt.x, pt.y, pt.z, nm.x, nm.y, nm.z))
            else:
                _log.row("ch %s p=%.4f,%.4f,%.4f" % (tag, pt.x, pt.y, pt.z))
            n = n + 1
        except:
            err = _log.exc()
            break
        i = i + 1
    err = err + " mode=%d" % mode
    _log.mark("hull_" + tag, "points=%d %s" % (n, err[:120]))

RAY_STEP = 10       # degrees between ray directions
RAY_R = 30.0         # ray start distance from the ship centre (GU)

def rays(tag, pShip, to_world, from_world):
    """Predicted impact points from the game's own collision test: for each direction on a
    RAY_STEP sphere grid (model frame), a ray from RAY_R toward the ship centre; bisect along
    it with ObjectClass.LineCollides to find the first hull surface point (to ~1e-4 GU).
    Rows: cy <ship> az=<deg> el=<deg> hit=x,y,z (model frame) | miss"""
    import math
    n = 0
    for el in range(-90, 91, RAY_STEP):
        _log.pulse("rays %s %d" % (tag, el))
        for az in range(0, 360, RAY_STEP):
            if (el == 90 or el == -90) and az != 0:
                continue
            ce = math.cos(el * math.pi / 180.0)
            sx = RAY_R * ce * math.sin(az * math.pi / 180.0)
            sy = RAY_R * ce * math.cos(az * math.pi / 180.0)
            sz = RAY_R * math.sin(el * math.pi / 180.0)
            a = App.TGPoint3()
            wx, wy, wz = to_world(sx, sy, sz)
            a.SetXYZ(wx, wy, wz)
            c = App.TGPoint3()
            cx, cy_, cz = to_world(0.0, 0.0, 0.0)
            c.SetXYZ(cx, cy_, cz)
            try:
                hitany = pShip.LineCollides(a, c)
            except:
                hitany = -1
                _log.row("cy %s az=%d el=%d err %s" % (tag, az, el, _log.exc()[:60]))
            if hitany == 0:
                _log.row("cy %s az=%d el=%d miss" % (tag, az, el))
            if hitany != 1:
                continue
            try:
                lo = 0.0
                hi = 1.0
                k = 0
                while k < 22:
                    mid = (lo + hi) / 2.0
                    m = App.TGPoint3()
                    m.SetXYZ(wx + (cx - wx) * mid, wy + (cy_ - wy) * mid, wz + (cz - wz) * mid)
                    if pShip.LineCollides(a, m):
                        hi = mid
                    else:
                        lo = mid
                    k = k + 1
                hx, hy, hz = from_world(wx + (cx - wx) * hi, wy + (cy_ - wy) * hi, wz + (cz - wz) * hi)
                _log.row("cy %s az=%d el=%d hit=%.4f,%.4f,%.4f" % (tag, az, el, hx, hy, hz))
                n = n + 1
            except:
                _log.row("cy %s az=%d el=%d err %s" % (tag, az, el, _log.exc()[:60]))
    _log.mark("rays_" + tag, "hits=%d step=%d" % (n, RAY_STEP))

AIM_STEP = 15
AIM_R = 57.0

def _first_hit(pShip, wx, wy, wz, ex, ey, ez):
    """Bisect the segment start->end with LineCollides; world point of first hull contact or None."""
    a = App.TGPoint3()
    a.SetXYZ(wx, wy, wz)
    e = App.TGPoint3()
    e.SetXYZ(ex, ey, ez)
    if not pShip.LineCollides(a, e):
        return None
    lo = 0.0
    hi = 1.0
    k = 0
    while k < 22:
        mid = (lo + hi) / 2.0
        m = App.TGPoint3()
        m.SetXYZ(wx + (ex - wx) * mid, wy + (ey - wy) * mid, wz + (ez - wz) * mid)
        if pShip.LineCollides(a, m):
            hi = mid
        else:
            lo = mid
        k = k + 1
    return (wx + (ex - wx) * hi, wy + (ey - wy) * hi, wz + (ez - wz) * hi)

def rays_aim(tag, pShip, subs, to_world, from_world):
    """Aimed rays: for every TARGETABLE subsystem, from directions on an AIM_STEP grid at AIM_R
    (model frame, centred on the ship), a ray toward that subsystem's position, extended
    through it; first hull contact by bisection.  This is where a shot aimed at the subsystem
    from that direction meets the hull (before bank-offset and projectile-path effects).
    Rows: cz <ship> <idx> az=<deg> el=<deg> hit=x,y,z | miss   (model frame)"""
    import math
    n = 0
    idx = -1
    for (sub, parent) in subs:
        idx = idx + 1
        p = None
        try:
            if sub.IsTargetable():
                p = sub.GetPosition()
        except:
            p = None
        if p is None:
            continue
        _log.pulse("aimrays %s %d" % (tag, idx))
        for el in range(-75, 76, AIM_STEP):
            for az in range(0, 360, AIM_STEP):
                ce = math.cos(el * math.pi / 180.0)
                sx = p.x + AIM_R * ce * math.sin(az * math.pi / 180.0)
                sy = p.y + AIM_R * ce * math.cos(az * math.pi / 180.0)
                sz = p.z + AIM_R * math.sin(el * math.pi / 180.0)
                # end point: through the subsystem to the far side
                ex_, ey_, ez_ = 2 * p.x - sx, 2 * p.y - sy, 2 * p.z - sz
                wx, wy, wz = to_world(sx, sy, sz)
                ex, ey, ez = to_world(ex_, ey_, ez_)
                try:
                    h = _first_hit(pShip, wx, wy, wz, ex, ey, ez)
                except:
                    h = None
                if h is None:
                    _log.row("cz %s %d az=%d el=%d miss" % (tag, idx, az, el))
                else:
                    hx, hy, hz = from_world(h[0], h[1], h[2])
                    _log.row("cz %s %d az=%d el=%d hit=%.4f,%.4f,%.4f" % (tag, idx, az, el, hx, hy, hz))
                    n = n + 1
    _log.mark("aimrays_" + tag, "hits=%d step=%d" % (n, AIM_STEP))

def arcs(tag, pShip, subs, to_world):
    """to_world(mx, my, mz) -> (wx, wy, wz) for this ship's placement."""
    import math
    elevs = range(-90, 91, ARC_STEP)
    azs = range(0, 360, ARC_STEP)
    pts = {}
    for e in elevs:
        row = []
        for a in azs:
            ce = math.cos(e * math.pi / 180.0)
            mx = ARC_R * ce * math.sin(a * math.pi / 180.0)
            my = ARC_R * ce * math.cos(a * math.pi / 180.0)
            mz = ARC_R * math.sin(e * math.pi / 180.0)
            wx, wy, wz = to_world(mx, my, mz)
            k = App.TGPoint3()
            k.SetXYZ(wx, wy, wz)
            row.append(k)
        pts[e] = row
    # Model axes in world space, for the rough-direction rows below (directions, so origin removed).
    ox, oy, oz = to_world(0.0, 0.0, 0.0)
    axes = []
    for (ux, uy, uz) in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        wx, wy, wz = to_world(ux, uy, uz)
        axes.append((wx - ox, wy - oy, wz - oz))
    idx = 0
    n = 0
    for (sub, parent) in subs:
        # cd <ship> <idx> d=<x,y,z>: Weapon.CalculateRoughDirection() in the model frame (the direction
        # PhaserSweep turns toward its target).
        try:
            w = App.Weapon_Cast(sub)
            if w is not None:
                v = w.CalculateRoughDirection()
                d = []
                for (ax, ay, az) in axes:
                    d.append(v.GetX() * ax + v.GetY() * ay + v.GetZ() * az)
                _log.row("cd %s %d d=%.4f,%.4f,%.4f" % (tag, idx, d[0], d[1], d[2]))
        except:
            _log.row("cd %s %d err %s" % (tag, idx, _log.exc()[:80]))
        tests = []
        o = App.PhaserBank_Cast(sub)
        if o is not None:
            tests.append(("PhaserBank.CanHit", o.CanHit))
        o = App.PulseWeapon_Cast(sub)
        if o is not None:
            tests.append(("PulseWeapon.IsInArc", o.IsInArc))
        o = App.TorpedoTube_Cast(sub)
        if o is not None:
            tests.append(("TorpedoTube.IsInArc", o.IsInArc))
            tests.append(("TorpedoTube.CanHit", o.CanHit))
        o = App.TractorBeamProjector_Cast(sub)
        if o is not None:
            p = App.PhaserBank_Cast(sub)
            if p is not None:
                tests.append(("Tractor.CanHit", p.CanHit))
        for (nm, fn) in tests:
            ok = 1
            for e in elevs:
                bits = []
                for k in pts[e]:
                    try:
                        bits.append(fn(k) and 1 or 0)
                    except:
                        ok = 0
                        break
                if not ok:
                    _log.row("ca %s %d %s unsupported %s" % (tag, idx, nm, _log.exc()[:80]))
                    break
                h = ""
                j = 0
                while j < len(bits):
                    v = 0
                    q = 0
                    while q < 4 and j + q < len(bits):
                        v = v + (bits[j + q] << q)
                        q = q + 1
                    h = h + "0123456789abcdef"[v]
                    j = j + 4
                _log.row("ca %s %d %s e=%d %s" % (tag, idx, nm, e, h))
            n = n + 1
        idx = idx + 1
    _log.mark("arcs_" + tag + "_done", "tests=%d step=%d r=%.0f" % (n, ARC_STEP, ARC_R))

def hittable(tag, pShip, subs, to_world, radii):
    """The game's own ShipSubsystem.IsHittableFromLocation(point) for EVERY subsystem (and child),
    from points on spheres of each radius in `radii` around the ship's centre (step HIT_STEP,
    same frame as arcs()).  Rows (each value under 180 chars):
      cH <ship> <idx> r=<r> e=<elev> <hex bitmask over az, as arcs()>     -- when every value is 0 or 1
      cF <ship> <idx> r=<r> e=<elev> a0=<az> <v,v,...>                    -- otherwise, 10 values a row
    Then mark hittable_<tag>_done with the count and the distinct values seen."""
    import math
    elevs = range(-90, 91, HIT_STEP)
    azs = range(0, 360, HIT_STEP)
    seen = {}
    n = 0
    idx = 0
    for (sub, parent) in subs:
        try:
            fn = sub.IsHittableFromLocation
        except:
            _log.row("cF %s %d unsupported" % (tag, idx))
            idx = idx + 1
            continue
        for r in radii:
            for e in elevs:
                vals = []
                ok = 1
                for a in azs:
                    ce = math.cos(e * math.pi / 180.0)
                    mx = r * ce * math.sin(a * math.pi / 180.0)
                    my = r * ce * math.cos(a * math.pi / 180.0)
                    mz = r * math.sin(e * math.pi / 180.0)
                    wx, wy, wz = to_world(mx, my, mz)
                    k = App.TGPoint3()
                    k.SetXYZ(wx, wy, wz)
                    try:
                        v = float(fn(k))
                    except:
                        ok = 0
                        break
                    vals.append(v)
                    seen["%.4f" % v] = 1
                    n = n + 1
                if not ok:
                    _log.row("cF %s %d r=%g e=%d err %s" % (tag, idx, r, e, _log.exc()[:60]))
                    continue
                binary = 1
                for v in vals:
                    if v != 0.0 and v != 1.0:
                        binary = 0
                        break
                if binary:
                    h = ""
                    j = 0
                    while j < len(vals):
                        b = 0
                        q = 0
                        while q < 4 and j + q < len(vals):
                            if vals[j + q] == 1.0:
                                b = b + (1 << q)
                            q = q + 1
                        h = h + "0123456789abcdef"[b]
                        j = j + 4
                    _log.row("cH %s %d r=%g e=%d %s" % (tag, idx, r, e, h))
                else:
                    j = 0
                    while j < len(vals):
                        parts = []
                        for v in vals[j:j + 10]:
                            parts.append("%.3f" % v)
                        _log.row("cF %s %d r=%g e=%d a0=%d %s" % (tag, idx, r, e, azs[j], string.join(parts, ",")))
                        j = j + 10
        idx = idx + 1
    keys = seen.keys()
    keys.sort()
    _log.mark("hittable_" + tag + "_done", "calls=%d step=%d values=%s" % (n, HIT_STEP, string.join(keys[:12], ",")))

# OracleSession -- many shots in one game launch (Mac/CrossOver port).  Python 1.5.
#
# oracle_in.cfg: shots=N and shot00..shotNN, each "key=value,..." with keys
#   a (bearing deg), e (elevation deg), w (phaser|torpedo|pulse), i (phaser intensity 0-2),
#   aim (target subsystem, '_' for spaces, or none), sh (off | full | <face>:<frac>),
#   d (firing seconds), g (gap after firing, seconds), tt (torpedo ammo type, -1 leave),
#   s (settle seconds between placing the ships and firing, like a fresh run's wait),
#   b (attacker bank/tube name, '_' for spaces, or all): only that emitter fires; every other
#     emitter of the system is held DISABLED (condition just under its disabled threshold,
#     never destroyed) for the shot and restored afterwards,
#   mv (none|impulse|yaw|pitch|roll|impyaw|imppitch|improll|yawpitch|yawroll|impyawpitch): attacker manoeuvre
#     (impulse = SetImpulse(mf); yaw/pitch/roll = SetTargetAngularVelocityFraction(axis * tf);
#     imp* = both), mf (throttle fraction), tf (turn fraction), ipw (attacker impulse-engine
#     power wanted), ic (attacker impulse pods condition fraction), fa (1 = attacker faces away),
#   dmg (target damage pattern 'Sub_Name/frac+Other/frac', applied after the restore),
#   rpw (target repair-system power wanted), rc (target repair-system condition fraction),
#   tpw / apw (target / attacker power sliders 'Getter/frac+Getter/frac', Getter one of Shields,
#     PhaserSystem, TorpedoSystem, SensorSubsystem, ImpulseEngineSubsystem, RepairSubsystem,
#     TractorBeamSystem, WarpEngineSubsystem), chg (attacker energy-weapon charge fraction at
#     shot start, -1 leave), tub (attacker torpedo tubes NumReady at shot start, -1 leave),
#   rng (range in GU for this shot; default the session's range_gu),
#   dmg2 / td2 (a second target damage pattern applied td2 seconds after the shot starts, for
#     sequencing: e.g. repair queue order),
#   admg (attacker damage pattern 'Sub_Name/frac+...', applied after the attacker is restored;
#     the attacker's repair is switched off for the shot so the pattern holds),
#   bat (attacker battery fill fraction at shot start, -1 = full as usual: main and backup),
#   nf (1 = do not fire: the weapon system is selected for charge/reload setup and observation only),
#   chain (torpedo spread: TorpedoSystem.SetFiringChainMode(n) before firing; the hardpoint's
#     firing-chain string is "0;Single;123;Dual;53;Quad"; -1 leave),
#   rl (1 = force-reload torpedo tubes at shot start (default); 0 = natural: never touch NumReady,
#     only switch ammo type if tt says so, so reload and type-switch timings are the game's own),
#   mf2 / t2 (second throttle command at t2 seconds after the shot starts; throttles < 0 mean
#     reverse, like the game's R key = -2/9; the game's keys 1..9 = k/9, 0 = stop)
#
# Between shots the target is restored (every subsystem to max condition, shields per 'sh'),
# both ships are re-placed and stilled, both ships' batteries are refilled, the ships settle for
# 's' seconds, then the attacker's weapons are recharged/reloaded and it fires, so each shot
# starts from the same state as a fresh launch without relaunching.  Shot boundaries are written as
# boot markers  shotNN = start=<game time> end=<game time> spec  for joining with CombatTap.log.
import App
import MissionLib
import math
import string
import Oracle.OracleLog

_log = Oracle.OracleLog
NonSerializedObjects = ("_log",)

ET_SHOT = App.UtopiaModule_GetNextEventType()
ET_SHOT_END = App.UtopiaModule_GetNextEventType()
ET_SHOT_FIRE = App.UtopiaModule_GetNextEventType()
ET_THROTTLE2 = App.UtopiaModule_GetNextEventType()
ET_DMG2 = App.UtopiaModule_GetNextEventType()

def OnDmg2(pObject, pEvent):
    d = g_specs[g_i[0]]
    try:
        _damage_target({"dmg": d["dmg2"], "rpw": d["rpw"], "rc": d["rc"]})
        _log.row("zd %d t=%.4f dmg2=%s" % (g_i[0], App.g_kUtopiaModule.GetGameTime(), d["dmg2"]))
    except:
        _log.mark("dmg2_error", _log.exc())

g_specs = []
g_frame = [None]    # attacker placement: (px, py, pz, fx, fy, fz, ux, uy, uz)
g_i = [0]
g_start = [0.0]

def _M():
    import Oracle.OracleMission
    return Oracle.OracleMission

def _parse(s):
    d = {"a": "0", "e": "0", "w": "phaser", "i": "2", "aim": "none", "sh": "off", "d": "10", "g": "3", "tt": "-1", "s": "4", "b": "all",
         "mv": "none", "mf": "1", "tf": "1", "ipw": "1", "ic": "1", "fa": "0",
         "dmg": "none", "rpw": "1", "rc": "1", "tpw": "none", "apw": "none", "chg": "-1", "tub": "-1", "nf": "0", "mf2": "none", "t2": "0", "rl": "1", "chain": "-1", "bat": "-1", "admg": "none", "dmg2": "none", "td2": "0", "rng": "-1", "tf2": "none", "tmv": "none", "ttf": "0", "stock": "none"}
    for kv in string.split(s, ","):
        if string.find(kv, "=") > 0:
            k, v = string.split(kv, "=", 1)
            d[string.strip(k)] = string.strip(v)
    return d

def load(cfg, sec):
    n = 0
    try:
        n = int(cfg.GetStringValue(sec, "shots"))
    except:
        n = 0
    i = 0
    while i < n:
        g_specs.append(_parse(cfg.GetStringValue(sec, "shot%02d" % i)))
        i = i + 1
    return n

def total_seconds():
    t = 0.0
    for d in g_specs:
        t = t + float(d["s"]) + float(d["d"]) + float(d["g"])
    return t

def start(t_first):
    MissionLib.CreateTimer(ET_SHOT, __name__ + ".OnShot", t_first, 0.0, 0.0)

def _place_pair(a_deg, e_deg, face_away=0):
    M = _M()
    a = a_deg * math.pi / 180.0
    e = e_deg * math.pi / 180.0
    r = M.P["range_gu"]
    if g_i[0] < len(g_specs) and float(g_specs[g_i[0]]["rng"]) > 0:
        r = float(g_specs[g_i[0]]["rng"])
    ax = -r * math.cos(e) * math.sin(a)
    ay = -r * math.cos(e) * math.cos(a)
    az = r * math.sin(e)
    n = (ax * ax + ay * ay + az * az) ** 0.5
    fx, fy, fz = -ax / n, -ay / n, -az / n
    if face_away:
        fx, fy, fz = -fx, -fy, -fz
    if abs(fz) > 0.99:
        wx, wy, wz = 0.0, 1.0, 0.0
    else:
        wx, wy, wz = 0.0, 0.0, 1.0
    dd = wx * fx + wy * fy + wz * fz
    ux, uy, uz = wx - dd * fx, wy - dd * fy, wz - dd * fz
    un = (ux * ux + uy * uy + uz * uz) ** 0.5
    M._place(M.g_pTarget, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
    M._place(M.g_pAttacker, ax, ay, az, fx, fy, fz, ux / un, uy / un, uz / un)
    g_frame[0] = (ax, ay, az, fx, fy, fz, ux / un, uy / un, uz / un)
    M._still(M.g_pTarget)
    M._still(M.g_pAttacker)
    pPM = M.g_pSet.GetProximityManager()
    if pPM:
        pPM.UpdateObject(M.g_pTarget)
        pPM.UpdateObject(M.g_pAttacker)

def _stop_attacker():
    M = _M()
    for getter in ("GetPhaserSystem", "GetPulseWeaponSystem", "GetTorpedoSystem"):
        try:
            getattr(M.g_pAttacker, getter)().StopFiring()
        except:
            pass

def _restore_target(sh):
    M = _M()
    for s in M.g_subs:
        try:
            s.SetCondition(s.GetMaxCondition())
        except:
            pass
    if M.P["disable_target_weapons"]:
        M._zero_weapons(M.g_pTarget)
    shields = M.g_pTarget.GetShields()
    if shields is not None:
        f = 0
        while f < 6:
            v = shields.GetMaxShields(f)
            if sh == "off":
                v = 0.0
            shields.SetCurShields(f, v)
            f = f + 1
        if string.find(sh, ":") > 0:
            face, frac = string.split(sh, ":")
            shields.SetCurShields(int(face), shields.GetMaxShields(int(face)) * float(frac))

def _damage_target(d):
    """Apply the shot's damage pattern and repair settings to the target (after the restore)."""
    M = _M()
    try:
        rs = M.g_pTarget.GetRepairSubsystem()
        rs.SetPowerPercentageWanted(float(d["rpw"]))
        rs.SetCondition(rs.GetMaxCondition() * float(d["rc"]))
        rs.TurnOn()
    except:
        _log.mark("repair_set_error", _log.exc())
    if d["dmg"] == "none":
        return
    for item in string.split(d["dmg"], "+"):
        nm, frac = string.split(item, "/")
        nm = string.replace(nm, "_", " ")
        hit = 0
        for x in M.g_subs:
            if x.GetName() == nm:
                x.SetCondition(x.GetMaxCondition() * float(frac))
                hit = 1
        if not hit:
            _log.mark("dmg_missing", nm)

def _sliders(pShip, spec):
    if spec == "none":
        return
    for item in string.split(spec, "+"):
        g, frac = string.split(item, "/")
        try:
            getattr(pShip, "Get" + g)().SetPowerPercentageWanted(float(frac))
        except:
            _log.mark("slider_error", "%s %s" % (item, _log.exc()))

def _start_state(d):
    """Shot-start weapon states (after the reload), for recharge/reload observation."""
    M = _M()
    if float(d["chg"]) >= 0.0:
        for e in M._emitters(M.g_pAttacker):
            try:
                e.SetChargeLevel(e.GetMaxCharge() * float(d["chg"]))
            except:
                pass
    if int(d["tub"]) >= 0:
        ts = M.g_pAttacker.GetTorpedoSystem()
        i = 0
        while i < ts.GetNumChildSubsystems():
            t = App.TorpedoTube_Cast(ts.GetChildSubsystem(i))
            if t is not None:
                t.SetNumReady(int(d["tub"]))
            i = i + 1

def _damage_attacker(d):
    M = _M()
    if d["admg"] == "none":
        return
    import Oracle.OracleTelemetry
    subs = Oracle.OracleTelemetry._walk(M.g_pAttacker)
    for item in string.split(d["admg"], "+"):
        nm, frac = string.split(item, "/")
        nm = string.replace(nm, "_", " ")
        hit = 0
        for x in subs:
            if x.GetName() == nm:
                x.SetCondition(x.GetMaxCondition() * float(frac))
                hit = 1
        if not hit:
            _log.mark("admg_missing", nm)
    try:
        M.g_pAttacker.GetRepairSubsystem().TurnOff()
    except:
        pass

def _prep_attacker(d):
    """Attacker back to full condition and normal power, then the shot's engine settings."""
    M = _M()
    import Oracle.OracleTelemetry
    for x in Oracle.OracleTelemetry._walk(M.g_pAttacker):
        try:
            x.SetCondition(x.GetMaxCondition())
        except:
            pass
        p = App.PoweredSubsystem_Cast(x)
        if p is not None:
            try:
                p.SetPowerPercentageWanted(1.0)
            except:
                pass
    e = M.g_pAttacker.GetImpulseEngineSubsystem()
    e.SetPowerPercentageWanted(float(d["ipw"]))
    i = 0
    while i < e.GetNumChildSubsystems():
        k = e.GetChildSubsystem(i)
        k.SetCondition(k.GetMaxCondition() * float(d["ic"]))
        i = i + 1
    if d["mv"] != "none":
        try:
            M.g_pAttacker.GetRepairSubsystem().TurnOff()     # keep the set condition for the manoeuvre
        except:
            pass

def _throttle(f):
    """The game's own throttle call (TacticalInterfaceHandlers.SetImpulse): negative = reverse."""
    M = _M()
    if f >= 0.0:
        v = App.TGPoint3_GetModelForward()
    else:
        v = App.TGPoint3_GetModelBackward()
        f = -f
    M.g_pAttacker.SetImpulse(f, v, App.ShipClass.DIRECTION_MODEL_SPACE)

def OnThrottle2(pObject, pEvent):
    d = g_specs[g_i[0]]
    try:
        if d["mf2"] != "none":
            _throttle(float(d["mf2"]))
        if d["tf2"] != "none":
            _turn(d["mv"], float(d["tf2"]))
        _log.row("zt %d t=%.4f mf2=%s tf2=%s" % (g_i[0], App.g_kUtopiaModule.GetGameTime(), d["mf2"], d["tf2"]))
    except:
        _log.mark("throttle2_error", _log.exc())

def _manoeuvre(d):
    M = _M()
    mv = d["mv"]
    if mv[:3] == "imp":
        _throttle(float(d["mf"]))
    if d["mf2"] != "none" or d["tf2"] != "none":
        MissionLib.CreateTimer(ET_THROTTLE2, __name__ + ".OnThrottle2",
                               App.g_kUtopiaModule.GetGameTime() + float(d["t2"]), 0.0, 0.0)
    if mv == "impulse":
        return
    _turn(mv, float(d["tf"]))

def _turn(mv, tf):
    """Turn command as the player's keyboard issues it (SetTargetAngularVelocityFraction); tf 0 = stop turning."""
    M = _M()
    ax = None
    if mv in ("yaw", "impyaw"):
        ax = (0.0, 0.0, 1.0)
    elif mv in ("pitch", "imppitch"):
        ax = (1.0, 0.0, 0.0)
    elif mv in ("roll", "improll"):
        ax = (0.0, 1.0, 0.0)
    elif mv in ("yawpitch", "impyawpitch"):
        ax = (0.70710678, 0.0, 0.70710678)      # two keys held: TurnShip unitizes the axis sum
    elif mv in ("yawroll", "impyawroll"):
        ax = (0.0, 0.70710678, 0.70710678)
    if ax is not None:
        v = App.TGPoint3()
        v.SetXYZ(ax[0] * tf, ax[1] * tf, ax[2] * tf)
        M.g_pAttacker.SetTargetAngularVelocityFraction(v)

def _refill_power(pShip):
    try:
        pw = pShip.GetPowerSubsystem()
        pw.SetMainBatteryPower(pw.GetMainBatteryLimit())
        pw.SetBackupBatteryPower(pw.GetBackupBatteryLimit())
    except:
        _log.mark("refill_error", _log.exc())

g_held = []

def _isolate_bank(d):
    """Disable every attacker emitter except d['b'] (weapons with condition below their
    disabled percentage cannot fire); remember them so _release_banks restores them."""
    M = _M()
    if d["b"] == "all":
        return
    want = string.replace(d["b"], "_", " ")
    found = 0
    for e in M._emitters(M.g_pAttacker):
        if e.GetName() == want:
            found = 1
            continue
        try:
            mx = e.GetMaxCondition()
            e.SetCondition(mx * e.GetDisabledPercentage() * 0.9)
            g_held.append(e)
        except:
            _log.mark("isolate_error", _log.exc())
    if not found:
        _log.mark("bank_missing", want)

def _release_banks():
    while len(g_held):
        e = g_held[0]
        del g_held[0]
        try:
            e.SetCondition(e.GetMaxCondition())
        except:
            pass

def _preset_faces(sh):
    """Shield faces only (no conditions): used at fire time, after the settle's regen."""
    M = _M()
    shields = M.g_pTarget.GetShields()
    if shields is None:
        return
    f = 0
    while f < 6:
        v = shields.GetMaxShields(f)
        if sh == "off":
            v = 0.0
        shields.SetCurShields(f, v)
        f = f + 1
    if string.find(sh, ":") > 0:
        face, frac = string.split(sh, ":")
        shields.SetCurShields(int(face), shields.GetMaxShields(int(face)) * float(frac))

def _reload_attacker(d):
    M = _M()
    if d["w"] == "phaser" or d["w"] == "pulse":
        for b in M._emitters(M.g_pAttacker):
            try:
                b.SetChargeLevel(b.GetMaxCharge())
            except:
                pass
    if d["w"] == "torpedo":
        ts = M.g_pAttacker.GetTorpedoSystem()
        tt = int(d["tt"])
        if tt >= 0 and ts.GetAmmoTypeNumber() != tt:
            ts.SetAmmoType(tt)
            _log.row("za %d t=%.4f ammo_switch_to=%d" % (g_i[0], App.g_kUtopiaModule.GetGameTime(), tt))
        if d["rl"] == "0":
            return
        for tube in M._emitters(M.g_pAttacker):
            try:
                tube.SetNumReady(tube.GetMaxReady())
            except:
                _log.mark("reload_error", _log.exc())

def OnShot(pObject, pEvent):
    """Phase 1: stop, place, restore the target, refill power; fire after the settle time."""
    M = _M()
    i = g_i[0]
    if i >= len(g_specs):
        return
    d = g_specs[i]
    try:
        _stop_attacker()
        M.P["weapon"] = d["w"]
        M.P["intensity"] = int(d["i"])
        M.P["aim_sub"] = d["aim"]
        M.P["charge"] = -1.0
        M.P["torp_type"] = int(d["tt"])
        M.g_banks = M._emitters(M.g_pAttacker)
        _place_pair(float(d["a"]), float(d["e"]), int(d["fa"]))
        _restore_target(d["sh"])
        _damage_target(d)
        _prep_attacker(d)
        _damage_attacker(d)
        _target_motion(d)
        _stock(d)
        _sliders(M.g_pTarget, d["tpw"])
        _sliders(M.g_pAttacker, d["apw"])
        _refill_power(M.g_pAttacker)
        _refill_power(M.g_pTarget)
        if float(d["bat"]) >= 0.0:
            pw = M.g_pAttacker.GetPowerSubsystem()
            pw.SetMainBatteryPower(pw.GetMainBatteryLimit() * float(d["bat"]))
            pw.SetBackupBatteryPower(pw.GetBackupBatteryLimit() * float(d["bat"]))
        _isolate_bank(d)
    except:
        _log.mark("shot%02d_prep_error" % i, _log.exc())
    MissionLib.CreateTimer(ET_SHOT_FIRE, __name__ + ".OnShotFire",
                           App.g_kUtopiaModule.GetGameTime() + float(d["s"]), 0.0, 0.0)

def _att_world(mx, my, mz):
    """Attacker model point -> world: X = forward x up, Y = forward, Z = up (the frame
    AlignToVectors builds; checked against the target placement (-x, -y, z))."""
    (px, py, pz, fx, fy, fz, ux, uy, uz) = g_frame[0]
    rx, ry, rz = fy * uz - fz * uy, fz * ux - fx * uz, fx * uy - fy * ux
    return (px + mx * rx + my * fx + mz * ux, py + mx * ry + my * fy + mz * uy, pz + mx * rz + my * fz + mz * uz)

def _predict(i, d):
    """Predicted impact of the isolated bank's shot: the game's own LineCollides, from the
    bank's world position toward the aimed subsystem (extended through it).  Row:
      zp <shot> bank=<name> from=x,y,z(world) aim=x,y,z(target model) hit=x,y,z(target model)|miss"""
    M = _M()
    if d["b"] == "all" or d["aim"] == "none" or g_frame[0] is None:
        return
    import Oracle.OracleCatalogue
    want = string.replace(d["b"], "_", " ")
    bank = None
    for e in M._emitters(M.g_pAttacker):
        if e.GetName() == want:
            bank = e
    tgt = None
    for s in M.g_subs:
        if s.GetName() == string.replace(d["aim"], "_", " "):
            tgt = s
    if bank is None or tgt is None:
        return
    bp = bank.GetPosition()
    bx, by, bz = _att_world(bp.x, bp.y, bp.z)
    tp = tgt.GetPosition()
    tx, ty, tz = -tp.x, -tp.y, tp.z            # target model -> world (target at origin, nose -Y)
    ex, ey, ez = 2 * tx - bx, 2 * ty - by, 2 * tz - bz
    h = None
    try:
        h = Oracle.OracleCatalogue._first_hit(M.g_pTarget, bx, by, bz, ex, ey, ez)
    except:
        _log.mark("predict_error", _log.exc())
    if h is None:
        hs = "miss"
    else:
        hs = "%.4f,%.4f,%.4f" % (-h[0], -h[1], h[2])
    # the same line cast from the far end back toward the bank (exit-side surface)
    r = None
    try:
        r = Oracle.OracleCatalogue._first_hit(M.g_pTarget, ex, ey, ez, bx, by, bz)
    except:
        pass
    if r is None:
        rs = "miss"
    else:
        rs = "%.4f,%.4f,%.4f" % (-r[0], -r[1], r[2])
    _log.row("zp %d bank=%s from=%.3f,%.3f,%.3f aim=%.3f,%.3f,%.3f hit=%s rev=%s" % (
        i, d["b"], bx, by, bz, tp.x, tp.y, tp.z, hs, rs))

def OnShotFire(pObject, pEvent):
    """Phase 2: shields per spec again (regen during the settle), recharge/reload, fire."""
    M = _M()
    i = g_i[0]
    d = g_specs[i]
    try:
        _reload_attacker(d)
        _start_state(d)
        _preset_faces(d["sh"])            # face presets again (regen ran during the settle); conditions untouched
        _predict(i, d)
        g_start[0] = App.g_kUtopiaModule.GetGameTime()
        if d["dmg2"] != "none":
            MissionLib.CreateTimer(ET_DMG2, __name__ + ".OnDmg2", g_start[0] + float(d["td2"]), 0.0, 0.0)
        if d["mv"] != "none":
            _manoeuvre(d)
        if d["chain"] != "-1":
            try:
                ts = M.g_pAttacker.GetTorpedoSystem()
                ts.SetFiringChainMode(int(d["chain"]))
                _log.row("zc %d t=%.4f chain=%d name=%s" % (i, App.g_kUtopiaModule.GetGameTime(),
                         ts.GetFiringChainMode(), str(ts.GetFiringChainName(ts.GetFiringChainMode()))))
            except:
                _log.mark("chain_error", _log.exc())
        if d["w"] != "none" and d["nf"] != "1":
            M._act_weapon()
    except:
        _log.mark("shot%02d_error" % i, _log.exc())
        g_start[0] = App.g_kUtopiaModule.GetGameTime()
    MissionLib.CreateTimer(ET_SHOT_END, __name__ + ".OnShotEnd", g_start[0] + float(d["d"]), 0.0, 0.0)

def _target_motion(d):
    """tmv: target throttle fraction (forward), ttf: target yaw fraction; started at placement so the target
    is already moving when the attacker fires (after the settle)."""
    if d["tmv"] == "none":
        return
    M = _M()
    try:
        M.g_pTarget.SetImpulse(float(d["tmv"]), App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
        if float(d["ttf"]) != 0.0:
            v = App.TGPoint3()
            v.SetXYZ(0.0, 0.0, float(d["ttf"]))
            M.g_pTarget.SetAngularDirectionType(App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
            M.g_pTarget.SetTargetAngularVelocityFraction(v)
        _log.row("zm %d tmv=%s ttf=%s" % (g_i[0], d["tmv"], d["ttf"]))
    except:
        _log.mark("target_motion_error", _log.exc())

def _stock(d):
    """stock: 'type:n' caps the attacker's torpedo stock of that type (TorpedoAmmoType.SetMaxTorpedoes)."""
    if d["stock"] == "none":
        return
    M = _M()
    try:
        ts = M.g_pAttacker.GetTorpedoSystem()
        k, n = string.split(d["stock"], ":")
        at = ts.GetAmmoType(int(k))
        before = ts.GetNumAvailableTorpsToType(int(k))
        at.SetMaxTorpedoes(int(n))
        _log.row("zk %d type=%s max=%s avail_before=%d avail_after=%d" % (g_i[0], k, n, before, ts.GetNumAvailableTorpsToType(int(k))))
    except:
        _log.mark("stock_error", _log.exc())

def OnShotEnd(pObject, pEvent):
    i = g_i[0]
    d = g_specs[i]
    _stop_attacker()
    if d["tmv"] != "none":
        M = _M()
        try:
            M.g_pTarget.SetImpulse(0.0, App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
            v = App.TGPoint3()
            v.SetXYZ(0.0, 0.0, 0.0)
            M.g_pTarget.SetTargetAngularVelocityFraction(v)
        except:
            pass
        M._still(M.g_pTarget)
    if d["mv"] != "none" or d["admg"] != "none":
        M = _M()
        M._still(M.g_pAttacker)
        try:
            M.g_pAttacker.GetRepairSubsystem().TurnOn()
        except:
            pass
    _release_banks()
    now = App.g_kUtopiaModule.GetGameTime()
    _log.flush(0)          # rows on disk BEFORE the shot counts as complete (crash-safe resume)
    _log.mark("shot%02d" % i, "start=%.3f end=%.3f a=%s e=%s w=%s i=%s aim=%s sh=%s tt=%s b=%s mv=%s mf=%s mf2=%s t2=%s tf=%s ipw=%s ic=%s" % (
        g_start[0], now + float(d["g"]), d["a"], d["e"], d["w"], d["i"], d["aim"], d["sh"], d["tt"], d["b"],
        d["mv"], d["mf"], d["mf2"], d["t2"], d["tf"], d["ipw"], d["ic"]))
    g_i[0] = i + 1
    if g_i[0] < len(g_specs):
        MissionLib.CreateTimer(ET_SHOT, __name__ + ".OnShot", now + float(d["g"]), 0.0, 0.0)

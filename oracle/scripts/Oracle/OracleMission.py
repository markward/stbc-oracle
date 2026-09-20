# OracleMission -- scripted scenarios inside the REAL Quick Battle mission.
# Python 1.5 (no closures, no True/False, no "import X as Y", except E, e:).
#
# Inputs  : oracle_in.cfg  [OracleIn]  (written by tools/oracle/run_oracle.py)
# Outputs : oracle_out*.cfg [OracleOut] rows + m_* metadata, done=1
#           oracle_boot.cfg [OracleBoot] progress markers
#
# Riding QuickBattle.QuickBattle (wrapping Initialize and StartSimulation2)
# is the ONLY start path found that does not access-violate on the first
# frame; see tools/oracle/README.md.
#
# Timeline (game time, t0 = takeover + settle_s):
#   t0            sampling begins
#   t0 + fire_at  "act": weapon fires / motion command / shield preset
#   t0 + duration flush + quit
#
# Row types (one line each, per sample):
#   a: t f c=<bank charges> fi=<bank firing> sh=<6 faces> h=<hull>
#   b: t s=<subsystem conditions in meta order>
#   c: t p=<attacker pos> v=<vel> w=<ang vel> fw=<forward> sp=<speed>
import App
import MissionLib
import loadspacehelper
import math
import string
import Oracle.OracleLog
_log = Oracle.OracleLog

_cfg = App.g_kConfigMapping
_SEC = "OracleIn"

# --- inputs -----------------------------------------------------------------
P = {}

def _gets(key, default):
    try:
        v = _cfg.GetStringValue(_SEC, key)
        if v is None or v == "":
            return default
        return v
    except:
        return default

def _getf(key, default):
    try:
        return float(_gets(key, str(default)))
    except:
        return default

def _read_inputs():
    try:
        _cfg.LoadConfigFile("oracle_in.cfg")
    except:
        _log.mark("load_in_error", _log.exc())
    P["attacker"]     = _gets("attacker", "KessokHeavy")
    P["target"]       = _gets("target", "Galaxy")
    P["weapon"]       = _gets("weapon", "phaser")       # phaser|pulse|torpedo|none
    P["motion"]       = _gets("motion", "none")         # none|impulse|yaw|pitch|roll|coast
    P["range_gu"]     = _getf("range_gu", 57.0)
    P["angle_deg"]    = _getf("angle_deg", 0.0)         # attacker bearing around target: 0 front, 90 starboard, 180 aft
    P["elev_deg"]     = _getf("elev_deg", 0.0)          # +up (dorsal), -down
    P["intensity"]    = int(_getf("intensity", 2))      # PhaserSystem PP_LOW/MED/HIGH
    P["charge"]       = _getf("charge", -1.0)           # -1 = leave at max
    P["power_wanted"] = _getf("power_wanted", -1.0)     # -1 = leave default
    P["shield_face"]  = int(_getf("shield_face", -1))   # face to preset (-1 none)
    P["shield_frac"]  = _getf("shield_frac", 1.0)       # preset fraction of max
    P["shields_off"]  = int(_getf("shields_off", 0))    # 1 = zero every face
    P["settle_s"]     = _getf("settle_s", 2.0)
    P["fire_at"]      = _getf("fire_at", 1.0)
    P["duration"]     = _getf("duration", 12.0)
    P["sample_dt"]    = _getf("sample_dt", 0.03)
    P["disable_target_weapons"] = int(_getf("disable_target_weapons", 1))
    P["rows"]         = _gets("rows", "abc")            # which row types to emit
    P["torp_type"]    = int(_getf("torp_type", -1))     # TorpedoSystem.SetAmmoType index (-1 leave)
    P["pulse_power"]  = int(_getf("pulse_power", -1))   # EnergyWeapon.SetPowerSetting on pulse emitters
    P["time_scale"]   = _getf("time_scale", 1.0)        # UtopiaModule.SetTimeScale at takeover
    P["target_alert"] = _gets("target_alert", "red")    # red|yellow|green
    P["tractor_mode"] = _gets("tractor_mode", "hold")   # hold|tow|pull|push
    P["shield_power"] = _getf("shield_power", -1.0)     # target ShieldGenerator.SetPowerPercentageWanted
    P["gen_frac"]     = _getf("gen_frac", -1.0)         # target ShieldGenerator condition fraction
    P["ai"]           = int(_getf("ai", 0))             # 1 = leave the QuickBattle AI on the attacker
    P["ai_level"]     = _getf("ai_level", 0.5)          # BasicAttack Difficulty 0.0 / 0.5 / 1.0
    P["ai_log"]       = int(_getf("ai_log", 0))         # 1 = ArtificialIntelligence_LogAITree("AITree.txt")
    for k in P.keys():
        _log.meta("in_" + k, P[k])

# --- state ------------------------------------------------------------------
g_pSet = None
g_pAttacker = None
g_pTarget = None
g_banks = []          # attacker energy weapons (phaser banks or pulse emitters)
g_subs = []           # target subsystems (top level + children) in meta order
g_t0 = 0.0
g_acted = 0
g_done = 0
g_rows = 0
g_timers = []

# Global counter, NOT Mission_GetNextEventType(): with no mission loaded that
# one hands back the same value every call and all handlers collapse onto it.
ET_SAMPLE = App.UtopiaModule_GetNextEventType()
ET_ACT    = App.UtopiaModule_GetNextEventType()
ET_CUT    = App.UtopiaModule_GetNextEventType()
ET_END    = App.UtopiaModule_GetNextEventType()

# --- helpers ----------------------------------------------------------------
def _place(pShip, x, y, z, fx, fy, fz, ux, uy, uz):
    pShip.SetTranslateXYZ(x, y, z)
    kF = App.TGPoint3(); kF.SetXYZ(fx, fy, fz)
    kU = App.TGPoint3(); kU.SetXYZ(ux, uy, uz)
    pShip.AlignToVectors(kF, kU)
    pShip.UpdateNodeOnly()

def _still(pShip):
    """Kill any motion QuickBattle's spawn left on the hull."""
    try:
        v = App.TGPoint3(); v.SetXYZ(0.0, 0.0, 0.0)
        pShip.SetVelocity(v)
        pShip.SetAngularVelocity(v, App.PhysicsObjectClass.DIRECTION_WORLD_SPACE)
        pShip.SetTargetAngularVelocityDirect(v)
        pShip.SetImpulse(0.0, App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    except:
        _log.mark("still_error", _log.exc())

def _red_alert(pShip):
    _alert(pShip, "red")

def _alert(pShip, level):
    try:
        if level == "green":
            pShip.SetAlertLevel(App.ShipClass.GREEN_ALERT)
        elif level == "yellow":
            pShip.SetAlertLevel(App.ShipClass.YELLOW_ALERT)
        else:
            pShip.SetAlertLevel(App.ShipClass.RED_ALERT)
    except:
        _log.mark("alert_error", _log.exc())

def _weapon_system(pShip):
    w = P["weapon"]
    if w == "phaser":
        return pShip.GetPhaserSystem()
    if w == "pulse":
        return pShip.GetPulseWeaponSystem()
    if w == "torpedo":
        return pShip.GetTorpedoSystem()
    if w == "tractor":
        return pShip.GetTractorBeamSystem()
    return None

def _emitters(pShip):
    """Child weapons of the chosen system, cast so charge/firing are readable."""
    out = []
    ps = _weapon_system(pShip)
    if ps is None:
        return out
    for i in range(ps.GetNumChildSubsystems()):
        raw = ps.GetChildSubsystem(i)
        b = None
        if P["weapon"] == "phaser":
            b = App.PhaserBank_Cast(raw)
        elif P["weapon"] == "pulse":
            b = App.PulseWeapon_Cast(raw)
        elif P["weapon"] == "torpedo":
            b = App.TorpedoTube_Cast(raw)
        elif P["weapon"] == "tractor":
            b = App.EnergyWeapon_Cast(raw)
        if b is not None:
            out.append(b)
    return out

def _all_subsystems(pShip):
    """Top-level subsystems and their children, depth first, like
    MissionLib.GetSubsystemByName walks them."""
    out = []
    it = pShip.StartGetSubsystemMatch(App.CT_SHIP_SUBSYSTEM)
    while 1:
        pSub = pShip.GetNextSubsystemMatch(it)
        if pSub is None:
            break
        out.append(pSub)
        for i in range(pSub.GetNumChildSubsystems()):
            pChild = pSub.GetChildSubsystem(i)
            if pChild is not None:
                out.append(pChild)
    pShip.EndGetSubsystemMatch(it)
    return out

def _zero_weapons(pShip):
    for getter in ("GetPhaserSystem", "GetTorpedoSystem", "GetPulseWeaponSystem"):
        try:
            sys_ = getattr(pShip, getter)()
            if sys_ is not None:
                sys_.SetCondition(0.0)
        except:
            pass

def _fmt_list(vals, fmt):
    s = ""
    for v in vals:
        s = s + (fmt % v) + ","
    return s

def _shields(pShip):
    out = []
    sh = pShip.GetShields()
    if sh is None:
        return out
    for f in range(6):
        out.append(sh.GetCurShields(f))
    return out

def _range():
    a = g_pAttacker.GetWorldLocation(); t = g_pTarget.GetWorldLocation()
    dx = t.x - a.x; dy = t.y - a.y; dz = t.z - a.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5

def _p3(v):
    return "%.3f,%.3f,%.3f" % (v.x, v.y, v.z)

def _record_meta():
    _log.meta("attacker_name", g_pAttacker.GetName())
    _log.meta("target_name", g_pTarget.GetName())
    _log.meta("n_banks", len(g_banks))
    ps = _weapon_system(g_pAttacker)
    if ps is not None:
        for nm in ("GetPowerLevel", "GetPowerPercentage", "GetPowerPercentageWanted", "GetSingleFire"):
            try:
                _log.meta("ws_" + nm[3:], getattr(ps, nm)())
            except:
                pass
    i = 0
    for b in g_banks:
        try:
            if P["weapon"] == "torpedo":
                _log.meta("bank%d" % i, "%s" % b.GetName())
            elif P["weapon"] == "pulse":
                _log.meta("bank%d" % i, "%s md=%.1f mdd=%.1f mc=%.2f dscale=%s pscaled=%s pset=%s" % (
                    b.GetName(), b.GetMaxDamage(), b.GetMaxDamageDistance(), b.GetMaxCharge(),
                    str(b.GetDamageScale()), str(b.GetPowerScaled()), str(b.GetPowerSetting())))
            else:
                _log.meta("bank%d" % i, "%s md=%.1f mdd=%.1f mc=%.2f" % (
                    b.GetName(), b.GetMaxDamage(), b.GetMaxDamageDistance(), b.GetMaxCharge()))
        except:
            _log.meta("bank%d" % i, "err " + _log.exc())
        i = i + 1
    sh = g_pTarget.GetShields()
    if sh is not None:
        mx = []
        for f in range(6):
            mx.append(sh.GetMaxShields(f))
        _log.meta("target_max_shields", _fmt_list(mx, "%.0f"))
    try:
        _log.meta("target_hull_max", g_pTarget.GetHull().GetMaxCondition())
    except:
        pass
    # Subsystem catalogue: name|max|radius|pos, one meta per subsystem.
    i = 0
    for s in g_subs:
        try:
            pos = s.GetPosition()
            _log.meta("sub%02d" % i, "%s|%.0f|%.3f|%s" % (
                s.GetName(), s.GetMaxCondition(), s.GetRadius(), _p3(pos)))
        except:
            _log.meta("sub%02d" % i, "%s|err" % s.GetName())
        i = i + 1
    for (nm, pShip) in (("attacker", g_pAttacker), ("target", g_pTarget)):
        try:
            imp = pShip.GetImpulseEngineSubsystem()
            _log.meta(nm + "_impulse", "maxspeed=%.3f maxaccel=%.3f maxangvel=%.3f maxangaccel=%.3f" % (
                imp.GetMaxSpeed(), imp.GetMaxAccel(), imp.GetMaxAngularVelocity(), imp.GetMaxAngularAccel()))
            _log.meta(nm + "_mass", "%.1f" % pShip.GetMass())
            _log.meta(nm + "_radius", "%.3f" % pShip.GetRadius())
        except:
            _log.meta(nm + "_impulse", "err " + _log.exc())
    try:
        _log.meta("range_actual", "%.3f" % _range())
    except:
        pass

# --- hooks into QuickBattle.QuickBattle ------------------------------------
_orig = {}

def install_hooks():
    import QuickBattle.QuickBattle
    QB = QuickBattle.QuickBattle
    if not _orig.has_key("Initialize"):
        _orig["Initialize"] = QB.Initialize
        _orig["StartSimulation2"] = QB.StartSimulation2
    QB.Initialize = _OracleInitialize
    QB.StartSimulation2 = _OracleStartSimulation2

def _enemy_entry(script, ai_level):
    import QuickBattle.QuickBattle
    QB = QuickBattle.QuickBattle
    kind = QB.g_dShipNameToType[script]
    entry = QB.g_dEnemyShipTypeToDetails[kind][:]
    entry.append(ai_level)
    return entry

def _OracleInitialize(pMission):
    import QuickBattle.QuickBattle
    QB = QuickBattle.QuickBattle
    _log.mark("mission_initialize", "QuickBattle (wrapped)")
    _read_inputs()
    _orig["Initialize"](pMission)
    _log.mark("qb_initialized", "1")
    try:
        QB.g_sPlayerType = P["target"]
        QB.g_kEnemyList = [_enemy_entry(P["attacker"], P["ai_level"])]
        QB.g_kFriendList = []
        pTopWindow = App.TopWindow_GetTopWindow()
        if not pTopWindow.IsBridgeVisible():
            pTopWindow.ForceBridgeVisible()
        QB.StartSimulationAction(None)     # preload -> ET_PRELOAD_DONE -> StartSimulation2
        _log.mark("preload_requested", "1")
    except:
        _log.mark("start_error", _log.exc())

def _OracleStartSimulation2(pObject, pEvent):
    global g_pSet, g_pAttacker, g_pTarget, g_banks, g_subs, g_t0
    _orig["StartSimulation2"](pObject, pEvent)
    _log.mark("qb_simulation_started", "1")
    try:
        g_pTarget = MissionLib.GetPlayer()
        g_pSet = g_pTarget.GetContainingSet()
        g_pAttacker = None
        for pObj in g_pSet.GetClassObjectList(App.CT_SHIP):
            pShip = App.ShipClass_Cast(pObj)
            if pShip is not None and pShip.GetName() != g_pTarget.GetName():
                g_pAttacker = pShip
        if g_pAttacker is None:
            _log.mark("no_attacker", "1")
            return
        if P["ai"]:
            _log.mark("ai_kept", "level=%.2f" % P["ai_level"])
            if P["ai_log"]:
                try:
                    App.ArtificialIntelligence_LogAITree("AITree.txt")
                    _log.mark("ai_log", "AITree.txt")
                except:
                    _log.mark("ai_log_error", _log.exc())
        else:
            g_pAttacker.ClearAI()
            for getter in ("GetPhaserSystem", "GetPulseWeaponSystem", "GetTorpedoSystem"):
                try:
                    getattr(g_pAttacker, getter)().StopFiring()
                except:
                    pass
        # Target at the origin facing -Y.  Attacker on a sphere of radius
        # range_gu at (angle, elev) measured from the target's nose, pointed at
        # the target.  angle 0 -> dead ahead, 90 -> off the target's starboard
        # side, 180 -> astern; elev +90 -> directly above.
        a = P["angle_deg"] * math.pi / 180.0
        e = P["elev_deg"] * math.pi / 180.0
        r = P["range_gu"]
        # target forward is -Y, target starboard is -X (right = forward x up)
        ax = -r * math.cos(e) * math.sin(a)
        ay = -r * math.cos(e) * math.cos(a)
        az = r * math.sin(e)
        n = (ax * ax + ay * ay + az * az) ** 0.5
        fx, fy, fz = -ax / n, -ay / n, -az / n
        # Up must be perpendicular to forward or the engine re-derives the
        # frame and the nose ends up off the target (elev 45 fired only the
        # dorsal pair).  Gram-Schmidt world-up against forward.
        if abs(fz) > 0.99:
            wx, wy, wz = 0.0, 1.0, 0.0
        else:
            wx, wy, wz = 0.0, 0.0, 1.0
        d = wx * fx + wy * fy + wz * fz
        ux, uy, uz = wx - d * fx, wy - d * fy, wz - d * fz
        un = (ux * ux + uy * uy + uz * uz) ** 0.5
        ux, uy, uz = ux / un, uy / un, uz / un
        _place(g_pTarget, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
        _place(g_pAttacker, ax, ay, az, fx, fy, fz, ux, uy, uz)
        _still(g_pTarget)
        if not P["ai"]:
            _still(g_pAttacker)
        pPM = g_pSet.GetProximityManager()
        if pPM:
            pPM.UpdateObject(g_pTarget)
            pPM.UpdateObject(g_pAttacker)
        _red_alert(g_pAttacker)
        if P["target_alert"] != "red":
            _alert(g_pTarget, P["target_alert"])
        if P["disable_target_weapons"]:
            _zero_weapons(g_pTarget)
        if P["shield_power"] >= 0.0 or P["gen_frac"] >= 0.0:
            try:
                gen = g_pTarget.GetShields()
                if P["shield_power"] >= 0.0:
                    gen.SetPowerPercentageWanted(P["shield_power"])
                if P["gen_frac"] >= 0.0:
                    gen.SetCondition(gen.GetMaxCondition() * P["gen_frac"])
                _log.mark("shield_gen", "power=%.2f cond=%.0f" % (gen.GetPowerPercentageWanted(), gen.GetCondition()))
            except:
                _log.mark("shield_gen_error", _log.exc())
        if P["torp_type"] >= 0:
            try:
                g_pAttacker.GetTorpedoSystem().SetAmmoType(P["torp_type"])
                _log.mark("torp_type", "%d -> current %d" % (P["torp_type"], g_pAttacker.GetTorpedoSystem().GetAmmoTypeNumber()))
            except:
                _log.mark("torp_type_error", _log.exc())
        if P["time_scale"] != 1.0:
            try:
                App.g_kUtopiaModule.SetTimeScale(P["time_scale"])
                _log.mark("time_scale", str(P["time_scale"]))
            except:
                _log.mark("time_scale_error", _log.exc())
        g_banks = _emitters(g_pAttacker)
        g_subs = _all_subsystems(g_pTarget)
        _log.mark("placed", "banks=%d subs=%d range=%.2f" % (len(g_banks), len(g_subs), _range()))
        now = App.g_kUtopiaModule.GetGameTime()
        g_t0 = now + P["settle_s"]
        g_timers.append(MissionLib.CreateTimer(ET_SAMPLE, __name__ + ".OnSample", g_t0, P["sample_dt"], -1))
        MissionLib.CreateTimer(ET_ACT, __name__ + ".OnAct", g_t0 + P["fire_at"], 0.0, 0.0)
        MissionLib.CreateTimer(ET_END, __name__ + ".OnEnd", g_t0 + P["duration"] + 0.5, 0.0, 0.0)
        _log.mark("timers_armed", "now=%.3f t0=%.3f" % (now, g_t0))
    except:
        _log.mark("takeover_error", _log.exc())

# --- timer handlers ---------------------------------------------------------
def _preset_shields():
    sh = g_pTarget.GetShields()
    if sh is None:
        return
    if P["shields_off"]:
        for f in range(6):
            sh.SetCurShields(f, 0.0)
    if P["shield_face"] >= 0:
        f = P["shield_face"]
        sh.SetCurShields(f, sh.GetMaxShields(f) * P["shield_frac"])

def _act_weapon():
    ps = _weapon_system(g_pAttacker)
    if ps is None:
        _log.mark("no_weapon_system", P["weapon"])
        return
    if P["weapon"] == "phaser":
        ps.SetPowerLevel(P["intensity"])
    if P["power_wanted"] >= 0.0:
        ps.SetPowerPercentageWanted(P["power_wanted"])
    if P["charge"] >= 0.0 and P["weapon"] != "torpedo":
        for b in g_banks:
            b.SetChargeLevel(P["charge"])
    if P["weapon"] == "pulse" and P["pulse_power"] >= 0:
        for b in g_banks:
            try:
                b.SetPowerSetting(P["pulse_power"])
            except:
                _log.mark("pulse_power_error", _log.exc())
    if P["weapon"] == "tractor":
        modes = {"hold": App.TractorBeamSystem.TBS_HOLD, "tow": App.TractorBeamSystem.TBS_TOW,
                 "pull": App.TractorBeamSystem.TBS_PULL, "push": App.TractorBeamSystem.TBS_PUSH}
        ps.SetMode(modes.get(P["tractor_mode"], App.TractorBeamSystem.TBS_HOLD))
    g_pAttacker.SetTarget(g_pTarget.GetName())   # takes a NAME, not an object
    ps.StartFiring(g_pTarget)

def _act_motion():
    m = P["motion"]
    fwd = App.TGPoint3_GetModelForward()
    if m == "impulse":
        g_pAttacker.SetImpulse(1.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    elif m == "impulse125":
        g_pAttacker.SetImpulse(1.25, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    elif m == "impulse200":
        g_pAttacker.SetImpulse(2.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    elif m == "impulse_power125":
        try:
            g_pAttacker.GetImpulseEngineSubsystem().SetPowerPercentageWanted(1.25)
            _log.mark("impulse_power", str(g_pAttacker.GetImpulseEngineSubsystem().GetPowerPercentageWanted()))
        except:
            _log.mark("impulse_power_error", _log.exc())
        g_pAttacker.SetImpulse(1.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
    elif m == "yawdirect":
        v = App.TGPoint3(); v.SetXYZ(0.0, 0.0, 1.0)
        g_pAttacker.SetTargetAngularVelocityDirect(v)
    elif m == "coast":
        g_pAttacker.SetImpulse(1.0, fwd, App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
        MissionLib.CreateTimer(ET_CUT, __name__ + ".OnCut", g_t0 + P["fire_at"] + P["duration"] * 0.5, 0.0, 0.0)
    elif m in ("yaw", "pitch", "roll"):
        v = App.TGPoint3()
        if m == "yaw":
            v.SetXYZ(0.0, 0.0, 1.0)
        elif m == "pitch":
            v.SetXYZ(1.0, 0.0, 0.0)
        else:
            v.SetXYZ(0.0, 1.0, 0.0)
        try:
            g_pAttacker.SetTargetAngularVelocityFraction(v)
        except:
            _log.mark("angvel_fraction_error", _log.exc())
            try:
                g_pAttacker.SetTargetAngularVelocityFraction(v.x, v.y, v.z)
            except:
                _log.mark("angvel_fraction_error2", _log.exc())

def OnCut(pObject, pEvent):
    try:
        g_pAttacker.SetImpulse(0.0, App.TGPoint3_GetModelForward(), App.PhysicsObjectClass.DIRECTION_MODEL_SPACE)
        _log.mark("cut", "t=%.3f" % (App.g_kUtopiaModule.GetGameTime() - g_t0))
    except:
        _log.mark("cut_error", _log.exc())

def OnAct(pObject, pEvent):
    global g_acted
    if g_acted:
        return
    g_acted = 1
    try:
        _preset_shields()
        if P["weapon"] != "none":
            _act_weapon()
        if P["motion"] != "none":
            _act_motion()
        _record_meta()
        _log.mark("acted", "t=%.3f weapon=%s motion=%s" % (
            App.g_kUtopiaModule.GetGameTime() - g_t0, P["weapon"], P["motion"]))
    except:
        _log.mark("act_error", _log.exc())

def OnSample(pObject, pEvent):
    global g_rows
    if g_done:
        return
    try:
        t = App.g_kUtopiaModule.GetGameTime() - g_t0
        fr = App.g_kSystemWrapper.GetUpdateNumber()
        if string.find(P["rows"], "a") >= 0:
            ch = []; fi = []
            for b in g_banks:
                try:
                    ch.append(b.GetChargeLevel())
                except:
                    ch.append(-1.0)
                fi.append(int(b.IsFiring()))
            hull = g_pTarget.GetHull().GetCondition()
            try:
                ah = g_pAttacker.GetHull().GetCondition()
            except:
                ah = -1.0
            tv = g_pTarget.GetVelocityTG()
            tsp = (tv.x * tv.x + tv.y * tv.y + tv.z * tv.z) ** 0.5
            _log.row("a t=%.4f f=%d c=%s fi=%s sh=%s h=%.1f ah=%.1f tsp=%.4f tp=%s" % (
                t, fr, _fmt_list(ch, "%.3f"), _fmt_list(fi, "%d"),
                _fmt_list(_shields(g_pTarget), "%.1f"), hull, ah, tsp, _p3(g_pTarget.GetWorldLocation())))
        if string.find(P["rows"], "b") >= 0:
            conds = []
            for s in g_subs:
                conds.append(s.GetCondition())
            _log.row("b t=%.4f s=%s" % (t, _fmt_list(conds, "%.0f")))
        if string.find(P["rows"], "c") >= 0:
            v = g_pAttacker.GetVelocityTG()
            w = g_pAttacker.GetAngularVelocityTG()
            f = g_pAttacker.GetWorldForwardTG()
            p = g_pAttacker.GetWorldLocation()
            sp = (v.x * v.x + v.y * v.y + v.z * v.z) ** 0.5
            extra = ""
            if P["ai"]:
                try:
                    tg = g_pAttacker.GetTarget()
                    tn = "-"
                    if tg is not None:
                        tn = string.replace(tg.GetName(), " ", "_")
                    fs = ""
                    for (tag, getter) in (("P", "GetPhaserSystem"), ("U", "GetPulseWeaponSystem"), ("T", "GetTorpedoSystem")):
                        try:
                            ws = getattr(g_pAttacker, getter)()
                            if ws is not None and ws.IsTryingToFire():
                                fs = fs + tag
                        except:
                            pass
                    extra = " rng=%.3f tgt=%s fire=%s" % (_range(), tn, fs or "-")
                except:
                    extra = " rng=%.3f" % _range()
            _log.row("c t=%.4f p=%s v=%s w=%s fw=%s sp=%.4f%s" % (
                t, _p3(p), _p3(v), _p3(w), _p3(f), sp, extra))
        g_rows = g_rows + 1
        if g_rows == 1:
            _log.mark("first_sample", "t=%.3f" % t)
    except:
        _log.mark("sample_error", _log.exc())

def OnEnd(pObject, pEvent):
    global g_done
    if g_done:
        return
    g_done = 1
    for pTimer in g_timers:
        try:
            App.g_kTimerManager.DeleteTimer(pTimer.GetObjID())
        except:
            pass
    _log.mark("on_end", "game=%.3f rows=%d acted=%d" % (App.g_kUtopiaModule.GetGameTime(), g_rows, g_acted))
    try:
        _weapon_system(g_pAttacker).StopFiring()
    except:
        pass
    if P["ai"] and P["ai_log"]:
        try:
            App.ArtificialIntelligence_LogAITree(None)   # flush the tree log
        except:
            pass
    ok = _log.flush(1)
    _log.mark("flushed", "rows=%d ok=%d" % (g_rows, ok))
    try:
        pTopWindow = App.TopWindow_GetTopWindow()
        pOptionsWindow = pTopWindow.FindMainWindow(App.MWT_OPTIONS)
        pQuitEvent = App.TGIntEvent_Create()
        pQuitEvent.SetEventType(App.ET_QUIT)
        pQuitEvent.SetInt(0)
        pQuitEvent.SetDestination(pOptionsWindow)
        App.g_kEventManager.AddEvent(pQuitEvent)
    except:
        _log.mark("quit_error", _log.exc())

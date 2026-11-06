# OracleTelemetry -- full per-sample state of BOTH ships (schema version 1).  Python 1.5.
#
# Enabled when the 'rows' input contains 'x'.  Every sample writes, for ship tag A (attacker)
# and T (target), these rows (lists follow the catalogue subsystem order, see OracleCatalogue):
#   xm <S> t=  p=x,y,z  v=x,y,z  w=x,y,z  sp=<speed>                 motion (world frame)
#   xe <S> t=  ms=<CurMaxSpeed> ma=<CurMaxAccel> mw=<CurMaxAngVel> mwa=<CurMaxAngAccel>
#           on=<impulse IsOn> pw=<wanted%> pr=<received> pp=<power%> pn=<normal%>   impulse engines
#   xp <S> t=  out= mb= bb= av= disp= want= mc= bc= mmc=                power plant
#   xq <S> t= k=<chunk> pw=..;pp=..;pr=..  per powered subsystem: wanted%, power%, received
#   xc <S> t= k=<chunk> c=<conditions>                                 every subsystem condition
#   xd <S> t=  dis=<0/1 per subsystem>  rep=<0/1 being repaired>          disabled + repairing
#   xn <S> t= k=<chunk> rp=<repair points needed>                     per subsystem
#   xh <S> t=  sh=<6 faces>  gen=<on>                                   shields
#   xw <S> t= k=<chunk> ch=<charge>  fi=<firing>  nr=<tube ready>  lf=<tube last fire time>
#   xs <S> t=  sr=<sensor range>
#   xz <S> t=  al=<alert> imp=<impulse setting> ppl=<phaser power level> pf=<phasers firing/trying>
#           tf=<torps firing/trying> am=<ammo type> ta=<torps available per type> tm=<tractor mode/firing>
#           ck=<cloaked/cloaking/decloaking> brk=<any shield breached> wst=<warp state> dy=<dying/dead>
#           tgt=<target name> tsub=<target subsystem name>
#   xt t= n=<torpedoes in the set>  then per torpedo (one row each):
#   xt1 t= ptr=<C++ address> id=<obj id> par=<parent id> dmg=<damage> p=x,y,z v=x,y,z
#       (ptr is matched against CombatTap hit-event words to identify which torpedo hit)
import App
import string
import Oracle.OracleLog

_log = Oracle.OracleLog
NonSerializedObjects = ("_log", "g_ships")

SCHEMA = 1
CHUNK = 12
g_ships = []        # (tag, ship, [subsystems in catalogue order], powered, emitters)

def _walk(pShip):
    out = []
    it = pShip.StartGetSubsystemMatch(App.CT_SHIP_SUBSYSTEM)
    while 1:
        pSub = pShip.GetNextSubsystemMatch(it)
        if pSub is None:
            break
        out.append(pSub)
        i = 0
        while i < pSub.GetNumChildSubsystems():
            c = pSub.GetChildSubsystem(i)
            if c is not None:
                out.append(c)
            i = i + 1
    pShip.EndGetSubsystemMatch(it)
    return out

def setup(pAttacker, pTarget):
    del g_ships[:]
    for (tag, s) in (("A", pAttacker), ("T", pTarget)):
        subs = _walk(s)
        powered = []
        emit = []
        for x in subs:
            p = App.PoweredSubsystem_Cast(x)
            if p is not None:
                powered.append(p)
            for c in ("PhaserBank", "PulseWeapon", "TorpedoTube", "TractorBeamProjector"):
                o = getattr(App, c + "_Cast")(x)
                if o is not None:
                    emit.append((c, o))
                    break
        g_ships.append((tag, s, subs, powered, emit))
        k = 0
        while k < len(subs):
            nm = []
            for x in subs[k:k + 12]:
                try:
                    nm.append(string.replace(x.GetName(), " ", "_")[:13])
                except:
                    nm.append("?")
            _log.meta("tele_%s_subs%d" % (tag, k / 12), string.join(nm, ",")[:178])
            k = k + 12
        # C++ addresses of the ship and of each subsystem (same order as tele_X_subs), so the
        # CombatTap hit log (ship=/sub= pointers) can be attributed exactly instead of inferred.
        try:
            import Oracle.OracleMission
            _log.meta("tele_%s_ptr" % tag, Oracle.OracleMission._swig_ptr(s))
            try:
                _log.meta("tele_%s_radius" % tag, "%.4f" % s.GetRadius())   # ObjectClass.GetRadius (collision/bounds)
            except:
                pass
            k = 0
            while k < len(subs):
                pp = []
                for x in subs[k:k + 12]:
                    pp.append(Oracle.OracleMission._swig_ptr(x))
                _log.meta("tele_%s_sptr%d" % (tag, k / 12), string.join(pp, ",")[:178])
                k = k + 12
        except:
            _log.meta("tele_%s_ptr" % tag, "err")
        names = []
        for x in powered:
            names.append(string.replace(x.GetName(), " ", "_"))
        _log.meta("tele_%s_powered" % tag, string.join(names, ",")[:178])
        names = []
        for (c, o) in emit:
            names.append(string.replace(o.GetName(), " ", "_"))
        _log.meta("tele_%s_emitters" % tag, string.join(names, ",")[:178])
    _log.meta("tele_schema", SCHEMA)

def _f(v):
    return "%.4g" % v

def _p3(v):
    return "%.4f,%.4f,%.4f" % (v.x, v.y, v.z)

def _chunked(kind, tag, t, key, vals):
    i = 0
    k = 0
    while i < len(vals):
        _log.row("%s %s t=%.4f k=%d %s=%s" % (kind, tag, t, k, key, string.join(vals[i:i + CHUNK], ",")))
        i = i + CHUNK
        k = k + 1

def _safe(fn, default="nan"):
    try:
        return fn()
    except:
        return default

def _torpedoes(t):
    try:
        import Oracle.OracleMission
        pSet = Oracle.OracleMission.g_pSet
        lst = pSet.GetClassObjectList(App.CT_TORPEDO)
    except:
        _log.row("xt t=%.4f err" % t)
        return
    _log.row("xt t=%.4f n=%d" % (t, len(lst)))
    for o in lst:
        tp = App.Torpedo_Cast(o)
        if tp is None:
            continue
        try:
            import Oracle.OracleMission
            ptr = Oracle.OracleMission._swig_ptr(tp)
            _log.row("xt1 t=%.4f ptr=%s id=%d par=%d dmg=%s p=%s v=%s" % (
                t, ptr, tp.GetObjID(), tp.GetParentID(), _f(tp.GetDamage()), _p3(tp.GetWorldLocation()),
                _p3(tp.GetVelocityTG())))
        except:
            _log.row("xt1 t=%.4f err %s" % (t, _log.exc()[:60]))

def sample(t):
    _torpedoes(t)
    try:
        import Oracle.OracleAIProbe
        Oracle.OracleAIProbe.sample(_log, t)
    except:
        _log.row("xf t=%.4f err %s" % (t, _log.exc()[:80]))
    for (tag, s, subs, powered, emit) in g_ships:
        try:
            v = s.GetVelocityTG()
            sp = (v.x * v.x + v.y * v.y + v.z * v.z) ** 0.5
            _log.row("xm %s t=%.4f p=%s v=%s w=%s sp=%.4f" % (tag, t, _p3(s.GetWorldLocation()), _p3(v),
                                                         _p3(s.GetAngularVelocityTG()), sp))
        except:
            _log.row("xm %s t=%.4f err" % (tag, t))
        # PhysicsObjectClass.GetAccelerationTG: the 'a' FireScript.PredictTargetLocation
        # passes to GetPredictedPosition (Dauntless returns zero).
        try:
            _log.row("xac %s t=%.4f a=%s" % (tag, t, _p3(s.GetAccelerationTG())))
        except:
            _log.row("xac %s t=%.4f err" % (tag, t))
        try:
            k = 0
            while k < len(subs):
                cs = []
                for x in subs[k:k + 12]:
                    cs.append("%.0f" % x.GetCondition())
                _log.row("xb %s t=%.4f i=%d s=%s" % (tag, t, k, string.join(cs, ",")))
                k = k + 12
        except:
            _log.row("xb %s t=%.4f err" % (tag, t))
        try:
            _log.row("xo %s t=%.4f fw=%s up=%s" % (tag, t, _p3(s.GetWorldForwardTG()), _p3(s.GetWorldUpTG())))
        except:
            _log.row("xo %s t=%.4f err" % (tag, t))
        try:
            e = s.GetImpulseEngineSubsystem()
            _log.row("xe %s t=%.4f ms=%s ma=%s mw=%s mwa=%s on=%d pw=%s pr=%s pp=%s pn=%s" % (
                tag, t, _f(e.GetCurMaxSpeed()), _f(e.GetCurMaxAccel()), _f(e.GetCurMaxAngularVelocity()),
                _f(e.GetCurMaxAngularAccel()), e.IsOn(), _f(e.GetPowerPercentageWanted()),
                _f(e.GetPowerReceived()), _f(e.GetPowerPercentage()), _f(e.GetNormalPowerPercentage())))
        except:
            _log.row("xe %s t=%.4f err" % (tag, t))
        pw = _safe(s.GetPowerSubsystem, None)
        if pw is None:
            _log.row("xp %s t=%.4f err=nopower" % (tag, t))
        else:
            parts = []
            for (k, fn) in (("out", "GetPowerOutput"), ("mb", "GetMainBatteryPower"), ("bb", "GetBackupBatteryPower"),
                            ("av", "GetAvailablePower"), ("disp", "GetPowerDispensed"), ("want", "GetPowerWanted"),
                            ("mc", "GetMainConduitCapacity"), ("bc", "GetBackupConduitCapacity"),
                            ("mmc", "GetMaxMainConduitCapacity"), ("cond", "GetCondition")):
                v = _safe(getattr(pw, fn), None)
                if v is None:
                    parts.append("%s=err" % k)
                else:
                    parts.append("%s=%s" % (k, _f(v)))
            _log.row("xp %s t=%.4f %s" % (tag, t, string.join(parts, " ")))
        vals = []
        for p in powered:
            vals.append("%s/%s/%s/%d" % (_f(_safe(p.GetPowerPercentageWanted, -1)), _f(_safe(p.GetPowerPercentage, -1)),
                                         _f(_safe(p.GetPowerReceived, -1)), _safe(p.IsOn, -1)))
        _chunked("xq", tag, t, "q", vals)
        cond = []
        dis = ""
        rep = ""
        need = []
        rs = _safe(s.GetRepairSubsystem, None)
        for x in subs:
            cond.append("%.1f" % _safe(x.GetCondition, -1))
            dis = dis + str(_safe(x.IsDisabled, 9))
            r = 9
            if rs is not None:
                r = _safe(lambda rs=rs, x=x: rs.IsBeingRepaired(x), 9)
            rep = rep + str(r)
            need.append("%.1f" % _safe(x.GetRepairPointsNeeded, -1))
        _chunked("xc", tag, t, "c", cond)
        _log.row("xd %s t=%.4f dis=%s rep=%s" % (tag, t, dis, rep))
        _chunked("xn", tag, t, "rp", need)
        try:
            sh = s.GetShields()
            faces = []
            f = 0
            while f < 6:
                faces.append("%.1f" % sh.GetCurShields(f))
                f = f + 1
            _log.row("xh %s t=%.4f sh=%s gen=%d" % (tag, t, string.join(faces, ","), sh.IsOn()))
        except:
            _log.row("xh %s t=%.4f err" % (tag, t))
        ws = []
        for (c, o) in emit:
            if c == "TorpedoTube":
                ws.append("t/%d/%.2f" % (_safe(o.GetNumReady, -1), _safe(o.GetLastFireTime, -1)))
            else:
                ws.append("e/%.3f/%d" % (_safe(o.GetChargeLevel, -1), _safe(o.IsFiring, -1)))
        _chunked("xw", tag, t, "w", ws)
        try:
            _log.row("xs %s t=%.4f sr=%s" % (tag, t, _f(s.GetSensorSubsystem().GetSensorRange())))
        except:
            _log.row("xs %s t=%.4f err" % (tag, t))
        _status(tag, s, t)

def _nm(o):
    try:
        if o is None:
            return "-"
        return string.replace(o.GetName(), " ", "_")
    except:
        return "?"

def _status(tag, s, t):
    parts = ["al=%s" % _safe(s.GetAlertLevel, "?"), "imp=%s" % _f(_safe(s.GetImpulse, -1))]
    ph = _safe(s.GetPhaserSystem, None)
    if ph is not None:
        parts.append("ppl=%s" % _safe(ph.GetPowerLevel, "?"))
        parts.append("pf=%s/%s" % (_safe(ph.IsFiring, "?"), _safe(ph.IsTryingToFire, "?")))
    ts = _safe(s.GetTorpedoSystem, None)
    if ts is not None:
        parts.append("tf=%s/%s" % (_safe(ts.IsFiring, "?"), _safe(ts.IsTryingToFire, "?")))
        parts.append("am=%s" % _safe(ts.GetAmmoTypeNumber, "?"))
        av = []
        i = 0
        while i < _safe(ts.GetNumAmmoTypes, 0):
            av.append(str(_safe(lambda ts=ts, i=i: ts.GetNumAvailableTorpsToType(i), "?")))
            i = i + 1
        parts.append("ta=%s" % string.join(av, "/"))
    tr = _safe(s.GetTractorBeamSystem, None)
    if tr is not None:
        parts.append("tm=%s/%s" % (_safe(tr.GetMode, "?"), _safe(tr.IsFiring, "?")))
    ck = _safe(s.GetCloakingSubsystem, None)
    if ck is not None:
        parts.append("ck=%s/%s/%s" % (_safe(ck.IsCloaked, "?"), _safe(ck.IsCloaking, "?"), _safe(ck.IsDecloaking, "?")))
    sh = _safe(s.GetShields, None)
    if sh is not None:
        parts.append("brk=%s" % _safe(sh.IsAnyShieldBreached, "?"))
    we = _safe(s.GetWarpEngineSubsystem, None)
    if we is not None:
        parts.append("wst=%s" % _safe(we.GetWarpState, "?"))
    parts.append("dy=%s/%s" % (_safe(s.IsDying, "?"), _safe(s.IsDead, "?")))
    parts.append("tgt=%s" % _nm(_safe(s.GetTarget, None)))
    parts.append("tsub=%s" % _nm(_safe(s.GetTargetSubsystem, None)))
    _log.row("xz %s t=%.4f %s" % (tag, t, string.join(parts, " ")))

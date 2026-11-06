# OracleProbe -- instant-read tables: set a state, wait for the power system's once-per-second
# update, read what the engine has computed.  No manoeuvres.  Python 1.5.
#
# Input 'probe' = engine.  For each ship (A then T) a list of steps is run; each step resets
# the ship (all subsystems to max condition, power sliders to 1.0, batteries full), applies the
# step's settings, waits WAIT game seconds, then logs one row:
#   pr <ship> <step> <label> | ms= ma= mw= mwa= | ipw= ipr= ipp= ipn= | out= mb= bb= av= disp= |
#      sr= | ecw= (impulse child conditions) | wcc= (warp core condition)
import App
import MissionLib
import string
import Oracle.OracleLog

_log = Oracle.OracleLog
NonSerializedObjects = ("_log", "g_steps")

ET_STEP = App.UtopiaModule_GetNextEventType()
ET_READ = App.UtopiaModule_GetNextEventType()
WAIT = 1.6          # seconds between reads
READS = {"nac": 2, "pods": 2, "imp": 2, "child": 2, "core": 4, "sens": 3, "thr": 1, "pow": 3, "brown": 12}
FIRST = {"thr": 1.2}  # first-read delay per kind (default WAIT)   # reads per step (stability check)
g_steps = []
g_i = [0]
g_r = [0]

def _M():
    import Oracle.OracleMission
    return Oracle.OracleMission

def _impulse_children(s):
    out = []
    e = s.GetImpulseEngineSubsystem()
    i = 0
    while i < e.GetNumChildSubsystems():
        out.append(e.GetChildSubsystem(i))
        i = i + 1
    return out

def _restore(s):
    import Oracle.OracleTelemetry
    for x in Oracle.OracleTelemetry._walk(s):
        try:
            x.SetCondition(x.GetMaxCondition())
        except:
            pass
        p = App.PoweredSubsystem_Cast(x)
        if p is not None:
            try:
                p.SetPowerPercentageWanted(1.0)
                p.TurnOn()
            except:
                pass
    pw = s.GetPowerSubsystem()
    pw.SetMainBatteryPower(pw.GetMainBatteryLimit())
    pw.SetBackupBatteryPower(pw.GetBackupBatteryLimit())
    # repair would raise the conditions we set while we wait: switch it off for the probe
    try:
        s.GetRepairSubsystem().TurnOff()
    except:
        pass

def _caps(tag, s, i, r, label):
    """Full capability snapshot: one 'pc' row per chunk of subsystems + ship-level 'ps' row."""
    import Oracle.OracleTelemetry
    subs = Oracle.OracleTelemetry._walk(s)
    vals = []
    for x in subs:
        cf = "-"
        w = App.Weapon_Cast(x)
        if w is not None:
            try:
                cf = str(w.CanFire())
            except:
                cf = "e"
        pr = "-"
        p = App.PoweredSubsystem_Cast(x)
        if p is not None:
            try:
                pr = "%.4g/%.3g" % (p.GetPowerReceived(), p.GetNormalPowerPercentage())
            except:
                pr = "e"
        try:
            vals.append("%.4g/%d/%s/%s" % (x.GetConditionPercentage(), x.IsDisabled(), cf, pr))
        except:
            vals.append("e")
    k = 0
    j = 0
    while j < len(vals):
        _log.row("pc %s %d.%d k=%d %s" % (tag, i, r, k, string.join(vals[j:j + 10], ",")))
        j = j + 10
        k = k + 1
    e = s.GetImpulseEngineSubsystem()
    w = s.GetPowerSubsystem()
    sh = s.GetShields()
    faces = []
    f = 0
    while f < 6:
        faces.append("%.0f" % sh.GetCurShields(f))
        f = f + 1
    ws = s.GetWarpEngineSubsystem()
    _log.row("ps %s %d.%d %s ms=%s mw=%s out=%s av=%s sr=%s shon=%s sh=%s warp=%s dy=%s" % (
        tag, i, r, label, _g(e, "GetCurMaxSpeed"), _g(e, "GetCurMaxAngularVelocity"), _g(w, "GetPowerOutput"),
        _g(w, "GetAvailablePower"), _g(s.GetSensorSubsystem(), "GetSensorRange"), _g(sh, "IsOn"),
        string.join(faces, "/"), _g(ws, "GetWarpState"), _g(s, "IsDying")))

def build_threshold(attacker, target):
    """Every subsystem of both ships stepped down through its disable threshold to 0 and back.
    Critical subsystems (hull, bridge, warp core...) stop at 1% so the ship survives."""
    import Oracle.OracleTelemetry
    for (tag, s) in (("A", attacker), ("T", target)):
        subs = Oracle.OracleTelemetry._walk(s)
        i = 0
        while i < len(subs):
            x = subs[i]
            try:
                th = x.GetDisabledPercentage()
                crit = x.IsCritical()
            except:
                th = 0.5
                crit = 0
            levels = [1.0, th + 0.02, th + 0.001, th, th - 0.001, th - 0.02, 0.25, 0.01]
            if not crit:
                levels.append(0.0)
            levels = levels + [th + 0.02, 1.0]
            for c in levels:
                if c < 0.0:
                    c = 0.0
                g_steps.append((tag, s, "thr_%d_%s_c%.3f" % (i, string.replace(x.GetName(), " ", "_"), c),
                                ("thr", 1.0, c, i)))
            i = i + 1
    _log.mark("probe_steps", "%d wait=%.1f" % (len(g_steps), WAIT))

POWER_SYSTEMS = ("GetShields", "GetPhaserSystem", "GetTorpedoSystem", "GetSensorSubsystem",
                 "GetImpulseEngineSubsystem", "GetTractorBeamSystem", "GetRepairSubsystem",
                 "GetWarpEngineSubsystem")

def build_power(attacker, target):
    """Each powered system's slider 0..1.25 (others at 1.0), then warp-core brownout series."""
    for (tag, s) in (("A", attacker), ("T", target)):
        n = 0
        for getter in POWER_SYSTEMS:
            for pw in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25):
                g_steps.append((tag, s, "pow_%s_%.2f" % (getter[3:], pw), ("pow", pw, 1.0, n)))
            n = n + 1
        for c in (0.6, 0.5, 0.4, 0.3, 0.2):
            g_steps.append((tag, s, "brown_core%.2f" % c, ("brown", 1.0, c, -1)))
    _log.mark("probe_steps", "%d wait=%.1f" % (len(g_steps), WAIT))

def build_pods(attacker, target):
    """Impulse pod combinations (instant reads): every subset of pods disabled, plus mixed damage."""
    for (tag, s) in (("A", attacker), ("T", target)):
        kids = _impulse_children(s)
        n = len(kids)
        combos = []
        k = 0
        while k < (1 << n):                       # every subset of pods at 0.49 (disabled)
            c = []
            j = 0
            while j < n:
                if k & (1 << j):
                    c.append(0.49)
                else:
                    c.append(1.0)
                j = j + 1
            combos.append(c)
            k = k + 1
        mixed = [[1.0, 0.75, 0.5, 0.25], [0.6, 0.6, 0.6, 0.6], [0.9, 0.7, 0.55, 0.5], [0.51, 1.0, 1.0, 1.0]]
        for m in mixed:
            combos.append(m[:n])
        for c in combos:
            lab = string.join(map(lambda x: "%.2f" % x, c), "_")
            g_steps.append((tag, s, "pods_" + lab, ("pods", 1.0, 0.0, c)))
    _log.mark("probe_steps", "%d" % len(g_steps))

def _warp_children(s):
    out = []
    e = s.GetWarpEngineSubsystem()
    i = 0
    while i < e.GetNumChildSubsystems():
        out.append(e.GetChildSubsystem(i))
        i = i + 1
    return out

def build_nacelles(attacker, target):
    """Warp nacelle combinations: does the warp-engine group (what the Helm warp button checks) go disabled?"""
    for (tag, s) in (("A", attacker), ("T", target)):
        n = len(_warp_children(s))
        combos = []
        for v in (1.0, 0.75, 0.6, 0.51, 0.5, 0.49, 0.3, 0.0):
            combos.append([v] * n)
            if n > 1:
                c = [1.0] * n
                c[0] = v
                combos.append(c)
        for c in combos:
            lab = string.join(map(lambda x: "%.2f" % x, c), "_")
            g_steps.append((tag, s, "nac_" + lab, ("nac", 1.0, 0.0, c)))
    _log.mark("probe_steps", "%d" % len(g_steps))

def build(attacker, target):
    for (tag, s) in (("A", attacker), ("T", target)):
        kids = _impulse_children(s)
        for pw in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25):
            for c in (1.0, 0.75, 0.6, 0.5, 0.4, 0.25, 0.0):
                g_steps.append((tag, s, "imp_pw%.2f_cond%.2f" % (pw, c), ("imp", pw, c, -1)))
        i = 0
        while i < len(kids):
            for c in (0.5, 0.0):
                g_steps.append((tag, s, "imp_child%d_%s_cond%.2f" % (i, string.replace(kids[i].GetName(), " ", "_"), c),
                                ("child", 1.0, c, i)))
            i = i + 1
        for c in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0):
            g_steps.append((tag, s, "core_cond%.2f" % c, ("core", 1.0, c, -1)))
        for spw in (0.0, 0.5, 1.0, 1.25):
            for c in (1.0, 0.75, 0.5, 0.25, 0.0):
                g_steps.append((tag, s, "sens_pw%.2f_cond%.2f" % (spw, c), ("sens", spw, c, -1)))
    _log.mark("probe_steps", "%d wait=%.1f" % (len(g_steps), WAIT))

def start(t):
    MissionLib.CreateTimer(ET_STEP, __name__ + ".OnStep", t, 0.0, 0.0)

def total_seconds():
    t = 2.0
    for st in g_steps:
        k = st[3][0]
        w = WAIT
        if FIRST.has_key(k):
            w = FIRST[k]
        t = t + w + (READS[k] - 1) * WAIT + 0.2
    return t

def OnStep(pObject, pEvent):
    i = g_i[0]
    if i >= len(g_steps):
        _M().OnEnd(pObject, pEvent)
        return
    (tag, s, label, (kind, pw, c, child)) = g_steps[i]
    try:
        _restore(s)
        if kind == "imp":
            e = s.GetImpulseEngineSubsystem()
            e.SetPowerPercentageWanted(pw)
            for k in _impulse_children(s):
                k.SetCondition(k.GetMaxCondition() * c)
        elif kind == "child":
            k = _impulse_children(s)[child]
            k.SetCondition(k.GetMaxCondition() * c)
        elif kind == "core":
            w = s.GetPowerSubsystem()
            w.SetCondition(w.GetMaxCondition() * c)
        elif kind == "pods":
            kids = _impulse_children(s)
            j = 0
            while j < len(kids):
                kids[j].SetCondition(kids[j].GetMaxCondition() * child[j])
                j = j + 1
        elif kind == "nac":
            kids = _warp_children(s)
            j = 0
            while j < len(kids):
                kids[j].SetCondition(kids[j].GetMaxCondition() * child[j])
                j = j + 1
        elif kind == "thr":
            import Oracle.OracleTelemetry
            x = Oracle.OracleTelemetry._walk(s)[child]
            x.SetCondition(x.GetMaxCondition() * c)
        elif kind == "pow":
            getattr(s, POWER_SYSTEMS[child])().SetPowerPercentageWanted(pw)
        elif kind == "brown":
            w = s.GetPowerSubsystem()
            w.SetCondition(w.GetMaxCondition() * c)
        elif kind == "sens":
            se = s.GetSensorSubsystem()
            se.SetPowerPercentageWanted(pw)
            se.SetCondition(se.GetMaxCondition() * c)
    except:
        _log.mark("probe_set_error", "%s %s" % (label, _log.exc()))
    _log.pulse("probe %d %s" % (i, label))
    wait = WAIT
    if FIRST.has_key(kind):
        wait = FIRST[kind]
    MissionLib.CreateTimer(ET_READ, __name__ + ".OnRead", App.g_kUtopiaModule.GetGameTime() + wait, 0.0, 0.0)

def _g(o, fn):
    try:
        return "%.5g" % getattr(o, fn)()
    except:
        return "err"

def OnRead(pObject, pEvent):
    i = g_i[0]
    (tag, s, label, spec) = g_steps[i]
    e = s.GetImpulseEngineSubsystem()
    w = s.GetPowerSubsystem()
    se = s.GetSensorSubsystem()
    kids = []
    for k in _impulse_children(s):
        kids.append(_g(k, "GetConditionPercentage"))
    _log.row("pr %s %d.%d %s ms=%s ma=%s mw=%s mwa=%s ipw=%s ipr=%s ipp=%s ipn=%s" % (
        tag, i, g_r[0], label, _g(e, "GetCurMaxSpeed"), _g(e, "GetCurMaxAccel"), _g(e, "GetCurMaxAngularVelocity"),
        _g(e, "GetCurMaxAngularAccel"), _g(e, "GetPowerPercentageWanted"), _g(e, "GetPowerReceived"),
        _g(e, "GetPowerPercentage"), _g(e, "GetNormalPowerPercentage")))
    _log.row("pr2 %s %d.%d out=%s mb=%s bb=%s av=%s disp=%s wcc=%s sr=%s spp=%s ecw=%s edis=%s" % (
        tag, i, g_r[0], _g(w, "GetPowerOutput"), _g(w, "GetMainBatteryPower"), _g(w, "GetBackupBatteryPower"),
        _g(w, "GetAvailablePower"), _g(w, "GetPowerDispensed"), _g(w, "GetConditionPercentage"),
        _g(se, "GetSensorRange"), _g(se, "GetNormalPowerPercentage"), string.join(kids, "/"), _g(e, "IsDisabled")))
    if spec[0] == "nac":
        we = s.GetWarpEngineSubsystem()
        wk = []
        for k in _warp_children(s):
            wk.append(_g(k, "GetConditionPercentage") + ":" + _g(k, "IsDisabled"))
        _log.row("pw %s %d.%d %s wdis=%s wcond=%s won=%s wpp=%s kids=%s" % (
            tag, i, g_r[0], label, _g(we, "IsDisabled"), _g(we, "GetConditionPercentage"), _g(we, "IsOn"),
            _g(we, "GetPowerPercentage"), string.join(wk, "/")))
    if spec[0] in ("thr", "pow", "brown"):
        _caps(tag, s, i, g_r[0], label)
    g_r[0] = g_r[0] + 1
    if g_r[0] < READS[spec[0]]:
        dt = WAIT
        if spec[0] == "brown":
            dt = 0.5
        MissionLib.CreateTimer(ET_READ, __name__ + ".OnRead", App.g_kUtopiaModule.GetGameTime() + dt, 0.0, 0.0)
        return
    g_r[0] = 0
    g_i[0] = i + 1
    MissionLib.CreateTimer(ET_STEP, __name__ + ".OnStep", App.g_kUtopiaModule.GetGameTime() + 0.2, 0.0, 0.0)

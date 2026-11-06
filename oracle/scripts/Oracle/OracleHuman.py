# OracleHuman -- the player's commands and the combat events of a human-flown duel.  Python 1.5.
#
# Installed by OracleMission when human=1.  Broadcast handlers on the mission log one row per event:
#   xu t=<game time> e=<event name> s=<source name> sp=<source's ship> d=<destination name>
#      v=<int/float payload> tg=<that ship's target> ts=<its target subsystem>
# An INPUT_* event's source is a window, so sp/tg/ts are the player's ship.  The same input event reaches the
# mission twice in one tick; the second, identical (t, type, payload, source) copy is dropped.  TORPEDO_FIRED rows with
# s=- at the duel's first tick are the loadout, not launches.
# Event types: every ET_INPUT_* the SDK defines (keys and buttons the player pressed: fire, target, speed,
# turns, camera, view), plus the combat events below for both ships.
import App
import Oracle.OracleLog

_log = Oracle.OracleLog
NonSerializedObjects = ("_log", "g_names")

COMBAT = ("ET_WEAPON_FIRED", "ET_TORPEDO_FIRED", "ET_PHASER_STARTED_FIRING", "ET_PHASER_STOPPED_FIRING",
          "ET_TRACTOR_BEAM_STARTED_FIRING", "ET_TRACTOR_BEAM_STOPPED_FIRING", "ET_TARGET_WAS_CHANGED",
          "ET_SET_ALERT_LEVEL", "ET_MANEUVER", "ET_SUBSYSTEM_DISABLED", "ET_SUBSYSTEM_OPERATIONAL",
          "ET_SUBSYSTEM_DESTROYED", "ET_CLOAK_BEGINNING", "ET_CLOAK_COMPLETED", "ET_SHIELDS_SET_STATE")
g_names = {}
g_last = [None]      # the previous row's (time, type, payload, source): an input event reaches the mission twice

def _nm(o):
    try:
        if o is None:
            return "-"
        n = o.GetName()
        if n is None or n == "":
            return "?"
        return n
    except:
        return "?"

def _ship_of(o):
    """The ship a source belongs to: itself, or a subsystem's parent ship."""
    try:
        s = App.ShipClass_Cast(o)
        if s:
            return s
    except:
        pass
    try:
        sub = App.ShipSubsystem_Cast(o)
        if sub:
            return sub.GetParentShip()
    except:
        pass
    return None

def _payload(e):
    try:
        ie = App.TGIntEvent_Cast(e)
        if ie:
            return str(ie.GetInt())
    except:
        pass
    try:
        fe = App.TGFloatEvent_Cast(e)
        if fe:
            return "%.4f" % fe.GetFloat()
    except:
        pass
    return "-"

def install(pMission):
    names = []
    d = App.__dict__
    for k in d.keys():
        if k[:9] == "ET_INPUT_":
            names.append(k)
    for k in COMBAT:
        if d.has_key(k):
            names.append(k)
    n = 0
    for k in names:
        try:
            et = d[k]
            if not g_names.has_key(et):
                g_names[et] = k[3:]
                App.g_kEventManager.AddBroadcastPythonFuncHandler(et, pMission, __name__ + ".OnEvent")
                n = n + 1
        except:
            _log.mark("human_handler_error", k + " " + _log.exc())
    _log.mark("human_events", "handlers=%d" % n)

def OnEvent(pObject, pEvent):
    try:
        t = App.g_kUtopiaModule.GetGameTime()
        et = pEvent.GetEventType()
        src = pEvent.GetSource()
        v = _payload(pEvent)
        key = (t, et, v, _nm(src))      # the source keeps two tubes firing in one tick apart
        if g_last[0] == key:
            raise "dup"
        g_last[0] = key
        ship = _ship_of(src)
        name = g_names.get(et, str(et))
        if not ship and name[:6] == "INPUT_":
            # a key/button: its source is a window, not a ship -- the player issued it
            try:
                import MissionLib
                ship = MissionLib.GetPlayer()
            except:
                ship = None
        tg = "-"
        ts = "-"
        if ship:
            try:
                tg = _nm(ship.GetTarget())
                ts = _nm(ship.GetTargetSubsystem())
            except:
                pass
        _log.row("xu t=%.4f e=%s s=%s sp=%s d=%s v=%s tg=%s ts=%s" % (
            t, name, _nm(src), _nm(ship), _nm(pEvent.GetDestination()), v, tg, ts))
    except:
        pass
    try:
        pObject.CallNextHandler(pEvent)
    except:
        pass

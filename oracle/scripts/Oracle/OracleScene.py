# OracleScene -- scene audit for the stock campaign missions.  Python 1.5.
#
# Local.py starts the real game through mainmenu.RunOverrideMission (the
# developers' Test Game path: Options/EpisodeOverride + MissionOverride,
# ET_NEW_GAME "Maelstrom.Maelstrom"), after wrapping the mission module's
# Initialize with _Initialize below.  Nothing in the mission is touched; we
# only arm timers once it exists and dump every ship in the player's set
# every snap_dt seconds for `duration` seconds, then flush and quit.
#
# Row kinds:
#   s n=<snap> t=<mission s> set=<set> name=<ship> scr=<script> p=x,y,z fw=x,y,z sp=<GU/s> w=x,y,z
#   h n=<snap> name=<ship> hull=<cur>/<max> sh=<6 faces cur> shm=<6 faces max> al=<alert> ai=<ai> tgt=<target> pl=<player> hid=<hidden> clk=<cloaked> dy=<dying/dead>
#   m n=<snap> t=<mission s> set=<set> ships=<n> player=<name|-> cut=<cutscene> rs=<rendered set>
import App
import MissionLib
import string
import sys
import Oracle.OracleLog

_log = Oracle.OracleLog

# Missions call MissionLib.SaveGame in Initialize, which pickles every script
# module's globals: keep the module alias and the wrapped function out of it.
NonSerializedObjects = ("_log", "g_orig")

ET_SNAP = App.UtopiaModule_GetNextEventType()
ET_END = App.UtopiaModule_GetNextEventType()

g_orig = [None]
g_name = [""]
g_t0 = [None]
g_snap = [0]
g_done = [0]
g_snap_dt = [5.0]
g_duration = [90.0]
g_err = [0]


def _getf(key, default):
    try:
        return float(App.g_kConfigMapping.GetStringValue("OracleIn", key))
    except:
        return default


def Wrap(sModule):
    """Import the mission module now (the engine's LoadMission will get the
    same object from sys.modules) and wrap its Initialize."""
    try:
        parts = string.split(sModule, ".")
        mod = __import__(sModule, {}, {}, [parts[-1]])
        g_orig[0] = mod.Initialize
        g_name[0] = sModule
        mod.Initialize = _Initialize
        _log.mark("scene_wrapped", sModule)
        return 1
    except:
        _log.mark("scene_wrap_error", _log.exc())
        return 0


def _Initialize(pMission):
    _log.mark("mission_initialize", g_name[0])
    try:
        g_orig[0](pMission)
        _log.mark("mission_initialized", "1")
    except:
        # Do not re-raise: the TG console would freeze the process.
        _log.mark("mission_init_error", _log.exc())
    try:
        g_snap_dt[0] = _getf("sample_dt", 5.0)
        g_duration[0] = _getf("duration", 90.0)
        now = App.g_kUtopiaModule.GetGameTime()
        g_t0[0] = now
        MissionLib.CreateTimer(ET_SNAP, __name__ + ".OnSnap", now + 0.5, g_snap_dt[0], -1)
        MissionLib.CreateTimer(ET_END, __name__ + ".OnEnd", now + g_duration[0] + 0.5, 0.0, 0.0)
        _log.mark("scene_timers_armed", "now=%.3f dt=%.1f dur=%.0f" % (now, g_snap_dt[0], g_duration[0]))
    except:
        _log.mark("scene_arm_error", _log.exc())


def _p3(v):
    return "%.2f,%.2f,%.2f" % (v.x, v.y, v.z)


def _f3(v):
    return "%.3f,%.3f,%.3f" % (v.x, v.y, v.z)


def _nm(s):
    return string.replace(str(s), " ", "_")


def _setname(pSet):
    if pSet is None:
        return "-"
    return _nm(pSet.GetName())


def _ship_rows(n, t, pSet, pShip, pPlayer):
    name = _nm(pShip.GetName())
    try:
        v = pShip.GetVelocityTG()
        w = pShip.GetAngularVelocityTG()
        sp = (v.x * v.x + v.y * v.y + v.z * v.z) ** 0.5
        scr = "-"
        try:
            scr = _nm(pShip.GetScript())
        except:
            pass
        _log.row("s n=%d t=%.2f set=%s name=%s scr=%s p=%s fw=%s sp=%.3f w=%s" % (
            n, t, _setname(pSet), name, scr, _p3(pShip.GetWorldLocation()),
            _f3(pShip.GetWorldForwardTG()), sp, _f3(w)))
    except:
        _log.row("s n=%d t=%.2f name=%s err=%s" % (n, t, name, _nm(_log.exc())[:80]))
    try:
        hull = "-"
        try:
            pHull = pShip.GetHull()
            if pHull is not None:
                hull = "%.0f/%.0f" % (pHull.GetCondition(), pHull.GetMaxCondition())
        except:
            pass
        sh = "-"; shm = "-"
        try:
            pSh = pShip.GetShields()
            if pSh is not None:
                cur = []; mx = []
                f = 0
                while f < 6:
                    cur.append("%.0f" % pSh.GetCurShields(f))
                    mx.append("%.0f" % pSh.GetMaxShields(f))
                    f = f + 1
                sh = string.join(cur, ","); shm = string.join(mx, ",")
        except:
            pass
        al = -1
        try:
            al = pShip.GetAlertLevel()
        except:
            pass
        ai = "-"
        try:
            pAI = pShip.GetAI()
            if pAI is not None:
                ai = _nm(pAI.GetName())
        except:
            ai = "err"
        tgt = "-"
        try:
            pT = pShip.GetTarget()
            if pT is not None:
                tgt = _nm(pT.GetName())
        except:
            pass
        pl = 0
        if pPlayer is not None and pPlayer.GetObjID() == pShip.GetObjID():
            pl = 1
        hid = -1; clk = -1; dy = -1
        try:
            hid = int(pShip.IsHidden())
        except:
            pass
        try:
            clk = int(pShip.IsCloaked())
        except:
            pass
        try:
            dy = int(pShip.IsDying()) + 2 * int(pShip.IsDead())
        except:
            pass
        _log.row("h n=%d name=%s hull=%s sh=%s shm=%s al=%d ai=%s tgt=%s pl=%d hid=%d clk=%d dy=%d" % (
            n, name, hull, sh, shm, al, ai[:24], tgt[:20], pl, hid, clk, dy))
    except:
        _log.row("h n=%d name=%s err=%s" % (n, name, _nm(_log.exc())[:80]))


def OnSnap(pObject, pEvent):
    if g_done[0]:
        return
    try:
        n = g_snap[0]
        g_snap[0] = n + 1
        t = App.g_kUtopiaModule.GetGameTime() - g_t0[0]
        pPlayer = App.Game_GetCurrentPlayer()
        pSet = None
        if pPlayer is not None:
            pSet = pPlayer.GetContainingSet()
        pRS = App.g_kSetManager.GetRenderedSet()
        if pSet is None and pRS is not None and pRS.GetName() != "bridge":
            pSet = pRS
        cut = -1
        try:
            cut = int(App.TopWindow_GetTopWindow().IsCutsceneMode())
        except:
            pass
        ships = []
        if pSet is not None:
            for pObj in pSet.GetClassObjectList(App.CT_SHIP):
                pShip = App.ShipClass_Cast(pObj)
                if pShip is not None:
                    ships.append(pShip)
        pname = "-"
        if pPlayer is not None:
            pname = _nm(pPlayer.GetName())
        _log.row("m n=%d t=%.2f set=%s ships=%d player=%s cut=%d rs=%s" % (
            n, t, _setname(pSet), len(ships), pname, cut, _setname(pRS)))
        for pShip in ships:
            _ship_rows(n, t, pSet, pShip, pPlayer)
        _log.pulse("snap=%d t=%.2f set=%s ships=%d player=%s" % (n, t, _setname(pSet), len(ships), pname))
        if n == 0:
            _log.mark("scene_first_snap", "t=%.2f set=%s ships=%d" % (t, _setname(pSet), len(ships)))
    except:
        if not g_err[0]:
            g_err[0] = 1
            _log.mark("scene_snap_error", _log.exc())


def OnEnd(pObject, pEvent):
    if g_done[0]:
        return
    g_done[0] = 1
    try:
        _log.mark("scene_end", "snaps=%d" % g_snap[0])
        ok = _log.flush(1)
        _log.mark("flushed", "ok=%d" % ok)
    except:
        _log.mark("scene_end_error", _log.exc())
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

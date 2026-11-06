# OracleAIProbe -- see what the stock AI's FireScript chose, live.  Python 1.5.
#
# The engine never exposes an AI tree (containers have AddAI but no getters), and
# PreprocessingAI::SetContainedAI swaps a Python preprocessor for a NATIVE one by looking up the
# bound instance's CLASS NAME ("FireScript" is registered) -- so wrapping methods never sees the
# native choice.  This module replaces AI.Preprocessors.FireScript with a SUBCLASS OF THE SAME
# NAME before any AI is built: the native swap should still happen (same name), every instance is
# kept, and Update is counted so a run shows which body actually ran (py=0 -> native ran).
# Each sample writes one row per instance:
#   xf <i> own=<ship> py=<python Update calls> tgt=<sTarget> sub=<idTargetedSubsystem name|-> lu=<iLastUpdate> nr=<len(dTargetSubsystemRating)> un=<iTargetSubsystemUpdateNum>
import App
import string
import sys
import AI.Preprocessors

NonSerializedObjects = ("_Orig", "_instances", "_plain_orig", "_plain_counts", "_tree_orig", "_tree_nodes", "_tree_conds", "_tree_log")

_Orig = AI.Preprocessors.FireScript
_instances = []


class FireScript(_Orig):
    _oracle_probe = 1

    def __init__(self, *args, **kw):
        apply(_Orig.__init__, (self,) + args, kw)
        self._oracle_py = 0
        _instances.append(self)

    def Update(self, *args):
        self._oracle_py = self._oracle_py + 1
        return apply(_Orig.Update, (self,) + args)


def install(log):
    """Swap the class in before Quick Battle builds its AIs.  Idempotent."""
    try:
        cur = AI.Preprocessors.FireScript
        if hasattr(cur, "_oracle_probe"):
            return
        AI.Preprocessors.FireScript = FireScript
        log.mark("ai_probe", "installed name=%s" % FireScript.__name__)
    except:
        log.mark("ai_probe_error", log.exc())


def _sub_name(sid):
    if sid is None:
        return "-"
    try:
        o = App.TGObject_GetTGObjectPtr(sid)
        s = App.ShipSubsystem_Cast(o)
        if s is None:
            return "?%s" % str(sid)
        return s.GetName()
    except:
        return "err"


def _owner(fs):
    try:
        for w in fs.lWeapons:
            try:
                return w.GetParentShip().GetName()
            except:
                pass
    except:
        pass
    return "-"


def sample(log, t):
    try:
        sample_tree(log, t)
    except:
        log.row("xy t=%.4f err %s" % (t, log.exc()[:80]))
    try:
        sample_plain(log, t)
    except:
        log.row("xa t=%.4f err %s" % (t, log.exc()[:80]))
    try:
        sample_speed(log, t)
    except:
        log.row("xi t=%.4f err %s" % (t, log.exc()[:80]))
    i = 0
    for fs in _instances:
        try:
            d = fs.__dict__
            nr = 0
            if d.has_key("dTargetSubsystemRating"):
                nr = len(fs.dTargetSubsystemRating)
            log.row("xf %d t=%.4f own=%s py=%d tgt=%s sub=%s lu=%s nr=%d un=%s" % (
                i, t, _owner(fs), fs._oracle_py, str(d.get("sTarget", "-"))[:24],
                _sub_name(d.get("idTargetedSubsystem")), str(d.get("iLastUpdate", "-")), nr,
                str(d.get("iTargetSubsystemUpdateNum", "-"))))
        except:
            log.row("xf %d t=%.4f err %s" % (i, t, log.exc()[:80]))
        i = i + 1


# ---------------------------------------------------------------------------------------------------
# PlainAI behaviours: which movement script is running on each ship.  Each module's class Update is
# replaced by a generated wrapper (exec: Python 1.5 has no closures) that counts calls per (ship,
# module); sample() writes the counts since the previous sample:
#   xa <ship> t=<t> a=<Module>:<n>,<Module>:<n>...
PLAIN_MODULES = ("TorpedoRun", "IntelligentCircleObject", "CircleObject", "ManeuverLoop", "Intercept",
                 "StationaryAttack", "FollowObject", "Flee", "PhaserSweep", "TurnToOrientation", "EvadeTorps",
                 "Warp", "MoveToObjectSide", "GoForward", "Stay")
_plain_orig = {}
_plain_counts = {}
# The PlainAI script whose Update is running right now ("-" outside any), so a speed command can be
# attributed to the behaviour that issued it.
_cur = ["-"]
# Speed commands (ShipClass.SetImpulse / SetSpeed), per ship since the last sample:
#   xi <ship> t=<t> k=<I|S> v=<last value> s=<script that issued it> n=<calls>
_speed_orig = {}
_speed_last = {}


def _plain_count(self, name):
    try:
        ship = self.pCodeAI.GetShip().GetName()
    except:
        ship = "?"
    key = (ship, name)
    _plain_counts[key] = _plain_counts.get(key, 0) + 1


def install_plain(log):
    done = []
    for m in PLAIN_MODULES:
        if not _plain_orig.has_key(m):
            try:
                mod = None
                for nm in ("AI.PlainAI." + m, m):
                    if mod is None:
                        try:
                            __import__(nm)
                            mod = sys.modules.get(nm)
                        except:
                            mod = None
                cls = getattr(mod, m)
                _plain_orig[m] = cls.Update
                code = ("def _upd_%s(self, *args):\n    _plain_count(self, '%s')\n    prev = _cur[0]\n    _cur[0] = '%s'\n"
                        "    try:\n        return apply(_plain_orig['%s'], (self,) + args)\n    finally:\n        _cur[0] = prev\n") % (m, m, m, m)
                exec code in globals()
                cls.Update = globals()["_upd_" + m]
                done.append(m)
            except:
                log.mark("ai_probe_plain_err_" + m, log.exc()[:120])
    log.mark("ai_probe_plain", ("%d:" % len(done)) + string.join(done, ",")[:150])


# FireScript wiring: which weapon systems each FireScript was given, and what the engine keeps as the
# preprocessing instance once SetPreprocessingMethod hands it over (the SDK says the Python FireScript
# "is replaced with an optimized version in the code").
_fs_orig = {}
_fs_n = [0]
_fs_log = [None]


def _fs_add(self, pSystem):
    try:
        if not self.__dict__.has_key("_oracle_sys"):
            self.__dict__["_oracle_sys"] = []
        self.__dict__["_oracle_sys"].append(str(pSystem.GetName())[:12])
    except:
        pass
    return _fs_orig["AddWeaponSystem"](self, pSystem)


def _fs_setpp(self, *args):
    r = apply(_fs_orig["SetPreprocessingMethod"], (self,) + args)
    try:
        inst = args[0]
        sysl = "-"
        if hasattr(inst, "__dict__") and inst.__dict__.has_key("_oracle_sys"):
            sysl = string.join(inst.__dict__["_oracle_sys"], "+")
        kept = "?"
        try:
            kept = str(self.GetPreprocessingInstance().__class__.__name__)[:24]
        except:
            kept = "err"
        smart = "-"
        try:
            smart = "%d" % inst.bSmartPhasers
        except:
            pass
        if _fs_n[0] < 60:
            _fs_n[0] = _fs_n[0] + 1
            _fs_log[0].mark("fs%02d" % _fs_n[0], "%s|%s|%s|%s|%s|smart=%s" % (
                str(self.GetShip().GetName())[:14], str(self.GetName())[:20], str(inst.__class__.__name__)[:16], sysl[:60], kept, smart))
    except:
        pass
    return r


def install_firescript(log):
    try:
        import AI.Preprocessors
        if not _fs_orig.has_key("AddWeaponSystem"):
            _fs_orig["AddWeaponSystem"] = AI.Preprocessors.FireScript.AddWeaponSystem
            AI.Preprocessors.FireScript.AddWeaponSystem = _fs_add
            _fs_orig["SetPreprocessingMethod"] = App.PreprocessingAI.SetPreprocessingMethod
            App.PreprocessingAI.SetPreprocessingMethod = _fs_setpp
        _fs_log[0] = log
        log.mark("ai_probe_fs", "1")
    except:
        log.mark("ai_probe_fs_err", log.exc()[:120])


def _speed_note(ship, kind, value):
    try:
        nm = string.replace(ship.GetName(), " ", "_")[:20]
        e = _speed_last.get(nm)
        if e is None:
            _speed_last[nm] = [kind, value, _cur[0], 1]
        else:
            e[0] = kind
            e[1] = value
            e[2] = _cur[0]
            e[3] = e[3] + 1
    except:
        pass


def _set_impulse(self, *args):
    if len(args):
        _speed_note(self, "I", args[0])
    return apply(_speed_orig["SetImpulse"], (self,) + args)


def _set_speed(self, *args):
    if len(args):
        _speed_note(self, "S", args[0])
    return apply(_speed_orig["SetSpeed"], (self,) + args)


def install_speed(log):
    """Wrap ShipClass.SetImpulse / SetSpeed (the AI's speed commands) without changing them."""
    try:
        if not _speed_orig.has_key("SetImpulse"):
            _speed_orig["SetImpulse"] = App.ShipClass.SetImpulse
            _speed_orig["SetSpeed"] = App.ShipClass.SetSpeed
            App.ShipClass.SetImpulse = _set_impulse
            App.ShipClass.SetSpeed = _set_speed
        log.mark("ai_probe_speed", "1")
    except:
        log.mark("ai_probe_speed_err", log.exc()[:120])


def sample_speed(log, t):
    for nm, e in _speed_last.items():
        try:
            log.row("xi %s t=%.4f k=%s v=%.4f s=%s n=%d" % (nm, t, e[0], float(e[1]), e[2], e[3]))
        except:
            pass
    _speed_last.clear()


def sample_plain(log, t):
    ships = {}
    for (ship, name), n in _plain_counts.items():
        if n:
            if not ships.has_key(ship):
                ships[ship] = []
            ships[ship].append("%s:%d" % (name, n))
    for ship, parts in ships.items():
        log.row("xa %s t=%.4f a=%s" % (string.replace(ship, " ", "_")[:20], t, string.join(parts, ",")[:130]))
    for k in _plain_counts.keys():
        _plain_counts[k] = 0


# ---------------------------------------------------------------------------------------------------
# The AI tree itself: every AI node and condition the stock AIs build, captured at creation by
# wrapping the App factories, then polled each sample.
#   xr a <i> <kind> <ship> <name>        registry: AI node i (once, at creation)
#   xr c <i> <module.class> <arg>         registry: condition i (once)
#   xy <ship> t=<t> f=<bits>              HasFocus of that ship's AI nodes, in registry order
#   xk t=<t> i=<first> s=<digits>         GetStatus of conditions i.. (chunks of 150)
TREE_FACTORIES = ("ConditionalAI_Create", "PlainAI_Create", "PriorityListAI_Create", "SequenceAI_Create",
                  "PreprocessingAI_Create", "RandomAI_Create")
_tree_orig = {}
_tree_nodes = []      # (obj, ship name)
_tree_conds = []      # obj
_tree_log = []


def _tree_ai(kind, o, args):
    try:
        nm = "?"
        try:
            nm = string.replace(args[1], " ", "_")
        except:
            pass
        ship = "?"
        try:
            ship = string.replace(args[0].GetName(), " ", "_")
        except:
            pass
        _tree_nodes.append((o, ship))
        _tree_log[0].row("xr a %d %s %s %s" % (len(_tree_nodes) - 1, kind[:-7], ship[:20], nm[:60]))
    except:
        pass


def _tree_cond(o, args):
    try:
        _tree_conds.append(o)
        extra = ""
        if len(args) > 2:
            extra = str(args[2])[:40]
        _tree_log[0].row("xr c %d %s %s" % (len(_tree_conds) - 1, str(args[1])[:40], string.replace(extra, " ", "_")))
    except:
        pass


def install_tree(log):
    _tree_log[:] = [log]
    done = []
    for fn in TREE_FACTORIES:
        if not _tree_orig.has_key(fn) and hasattr(App, fn):
            try:
                _tree_orig[fn] = getattr(App, fn)
                code = "def _tw_%s(*args):\n    o = apply(_tree_orig['%s'], args)\n    _tree_ai('%s', o, args)\n    return o\n" % (fn, fn, fn)
                exec code in globals()
                setattr(App, fn, globals()["_tw_" + fn])
                done.append(fn[:-7])
            except:
                log.mark("ai_probe_tree_err_" + fn, log.exc()[:120])
    if not _tree_orig.has_key("ConditionScript_Create"):
        try:
            _tree_orig["ConditionScript_Create"] = App.ConditionScript_Create
            code = "def _tw_cond(*args):\n    o = apply(_tree_orig['ConditionScript_Create'], args)\n    _tree_cond(o, args)\n    return o\n"
            exec code in globals()
            App.ConditionScript_Create = globals()["_tw_cond"]
            done.append("ConditionScript")
        except:
            log.mark("ai_probe_tree_err_cond", log.exc()[:120])
    log.mark("ai_probe_tree", string.join(done, ",")[:170])


def sample_tree(log, t):
    ships = {}
    order = []
    for (o, ship) in _tree_nodes:
        if not ships.has_key(ship):
            ships[ship] = []
            order.append(ship)
        f = "0"
        try:
            if o.HasFocus():
                f = "1"
        except:
            f = "x"
        a = "0"
        try:
            if o.IsActive():
                a = "1"
        except:
            a = "x"
        ships[ship].append((f, a))
    for ship in order:
        fb = []
        ab = []
        for (f, a) in ships[ship]:
            fb.append(f)
            ab.append(a)
        fbits = string.join(fb, "")
        abits = string.join(ab, "")
        k = 0
        while k < len(fbits):
            log.row("xy %s t=%.4f i=%d f=%s" % (ship[:20], t, k, fbits[k:k + 140]))
            log.row("xv %s t=%.4f i=%d a=%s" % (ship[:20], t, k, abits[k:k + 140]))
            k = k + 140
    st = []
    for o in _tree_conds:
        try:
            st.append(str(o.GetStatus())[:1])
        except:
            st.append("x")
    digits = string.join(st, "")
    k = 0
    while k < len(digits):
        log.row("xk t=%.4f i=%d s=%s" % (t, k, digits[k:k + 150]))
        k = k + 150

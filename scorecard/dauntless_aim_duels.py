"""Dauntless duels for the AI-aim comparison with the original (results_mac/duels_aim, oracle/reports/aim_bank.py).

Same set-ups as results_mac/worker_aim.sh: Galaxy vs Sovereign at 100 GU, both directions, AI levels 1.0/1.0 and
0.5/0.5, attacker bearings 0..315 from the target's nose. Hull line of sight is on headlessly
(DAUNTLESS_HEADLESS_HULL_LOS=1, engine/appc/hull_line_of_sight.py) so IsHittableFromLocation answers as in the game.

Writes scorecard/dauntless_aim_duels/<name>.json: every change of each FireScript's chosen subsystem, and every
phaser hit with the shooter's phaser FireScript choice at that moment ("-" = no subsystem: aimed at the centre).
Run from the dauntless repo (SCORECARD_APPEND=1 keeps the scorecard's results.jsonl):
  SCORECARD_APPEND=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p tests.conftest -p tests.oracle.conftest \\
      --rootdir=. -p no:cacheprovider -q ../stbc-oracle/scorecard/dauntless_aim_duels.py
"""
import importlib
import json
import math
from pathlib import Path

import pytest

import os as _os_out
# AIM_DUEL_OUT=<folder name under scorecard/> writes a separate set (e.g. the full matrix); default unchanged
OUT = Path(__file__).resolve().parent / _os_out.environ.get("AIM_DUEL_OUT", "dauntless_aim_duels")
TREE_FACTORIES = ("ConditionalAI_Create", "PlainAI_Create", "PriorityListAI_Create", "SequenceAI_Create",
                  "PreprocessingAI_Create", "RandomAI_Create")
PLAIN_MODULES = ("TorpedoRun", "IntelligentCircleObject", "CircleObject", "ManeuverLoop", "Intercept",
                 "StationaryAttack", "FollowObject", "Flee", "PhaserSweep", "TurnToOrientation", "EvadeTorps",
                 "Warp", "MoveToObjectSide", "GoForward", "Stay")

import os as _os
_PAIRS = [tuple(x.split(":")) for x in _os.environ.get("AIM_DUEL_PAIRS", "Sovereign:Galaxy Galaxy:Sovereign").split()]
_LEVELS = [float(x) for x in _os.environ.get("AIM_DUEL_LEVELS", "1.0 0.5").split()]
_ANGLES = [int(x) for x in _os.environ.get("AIM_DUEL_ANGLES", "0 45 90 135 180 225 270 315").split()]
# AIM_DUEL_REPEATS=N runs every case N times (the AI makes random choices, so one run per case is
# one sample of a distribution). Repeat 0 keeps the historical file name; repeat k > 0 adds _rep<k>.
_REPEATS = int(_os.environ.get("AIM_DUEL_REPEATS", "1"))
CASES = [(e, p, lv, a, k) for (e, p) in _PAIRS for lv in _LEVELS for a in _ANGLES for k in range(_REPEATS)]


def _place_at_bearing(s, angle_deg, rng=100.0):
    """BC's duel placement (OracleMission: attacker on the target's bearing `angle`, 90 = starboard), in the
    fixture's frame (target at the origin, nose +y, starboard +x)."""
    App = s.App
    a = math.radians(angle_deg)
    x, y = rng * math.sin(a), rng * math.cos(a)
    s.atk.SetTranslateXYZ(x, y, 0.0)
    f = App.TGPoint3(); f.SetXYZ(-x / rng, -y / rng, 0.0)
    u = App.TGPoint3(); u.SetXYZ(0.0, 0.0, 1.0)
    s.atk.AlignToVectors(f, u)
    s.atk.UpdateNodeOnly()


def _tube_names(s):
    """Each ship's torpedo tube names in child order (the order of status()'s 'tr')."""
    out = {}
    for tag, ship in (("A", s.atk), ("T", s.tgt)):
        try:
            ts = ship.GetTorpedoSystem()
            out[tag] = [ts.GetChildSubsystem(i).GetName() for i in range(ts.GetNumChildSubsystems())]
        except Exception:
            out[tag] = []
    return out


def _seed_hull_box(ship, host_loop):
    """The live game caches each ship's hull AABB at realize time (host_loop._cache_shield_hull_box, from the
    renderer's model_aabb) and picks a hit's shield FACE from it; headless there is no renderer, so the face fell
    back to the raw-axis rule and a flat hull's dorsal/ventral hits were billed to front/rear (an Akira's front
    shield read < 70% 82% of a fight vs the original's 11%). Same AABB from the NIF's drawn shapes.
    Needs engine/appc/hull_line_of_sight.py (Dauntless combat-ai-parity); skipped on a Dauntless without it."""
    try:
        from engine.appc import hull_line_of_sight as hl
    except ImportError:
        return
    import _dauntless_host as h
    path = hl._nif_path(ship)
    if not path:
        return
    lo, hi = [1e30] * 3, [-1e30] * 3
    for shp in h.nif_shapes(path):
        if shp.get("hidden"):
            continue
        for v in shp["vertices"]:
            for k in range(3):
                lo[k] = min(lo[k], v[k])
                hi[k] = max(hi[k], v[k])
    if hi[0] < lo[0]:
        return
    host_loop._cache_shield_hull_box(ship, tuple((lo[k] + hi[k]) * 0.5 for k in range(3)),
                                     tuple((hi[k] - lo[k]) * 0.5 for k in range(3)))


@pytest.mark.parametrize("enemy,player,lv,angle,rep", CASES)
def test_record_aim_duel(oracle, monkeypatch, enemy, player, lv, angle, rep):
    monkeypatch.setenv("DAUNTLESS_HEADLESS_HULL_LOS", "1")
    OUT.mkdir(exist_ok=True)
    name = f"duel_{enemy}_enemy{lv}_vs_{player}_player{lv}_r100_a{angle}" + (f"_rep{rep}" if rep else "")
    if _os.environ.get("AIM_DUEL_SKIP_EXISTING") == "1" and (OUT / f"{name}.json").exists():
        pytest.skip("already recorded")
    s = oracle(attacker=enemy, target=player, range_gu=100.0)
    # The live game's radius (host_loop._seed_ship_radius: the original's measured value per stock model),
    # not the fixture's estimate table.
    from engine import host_loop
    for ship in (s.atk, s.tgt):
        ship.SetRadius(0.0)
        host_loop._seed_ship_radius(ship, 400.0, 400.0)
        _seed_hull_box(ship, host_loop)
    _place_at_bearing(s, angle)
    # The AI tree: every node built through the App factories (the original's xr/xy/xv rows).
    import App
    nodes, fac_orig = [], {}
    for fn in TREE_FACTORIES:
        f0 = getattr(App, fn, None)
        if f0 is None:
            continue
        fac_orig[fn] = f0

        def mk(f0=f0, kind=fn[:-7]):
            def w(*args, **kw):
                o = f0(*args, **kw)
                try:
                    nodes.append((o, args[0].GetName(), kind, str(args[1])))
                except Exception:
                    pass
                return o
            return w
        setattr(App, fn, mk())
    # Conditions: owner = the ship of the AI node built just before (the same rule the BC registry is read with).
    conds = []
    c0 = getattr(App, "ConditionScript_Create", None)
    if c0 is not None:
        fac_orig["ConditionScript_Create"] = c0

        def cw(*args, **kw):
            o = c0(*args, **kw)
            try:
                conds.append((o, str(args[1]), str(args[2])[:40] if len(args) > 2 else "", nodes[-1][1] if nodes else "?"))
            except Exception:
                pass
            return o
        App.ConditionScript_Create = cw

    s.attach_basic_attack(lv)              # target weapons live
    mod = importlib.import_module("AI.Compound.BasicAttack")
    # Quick Battle's own keywords (QuickBattle/QuickBattleAI.py, QuickBattleFriendlyAI.py): the original's duels
    # build their AIs this way, and UseCloaking selects CloakAttack for a ship with a cloak.
    # Quick Battle's own AI builders (QuickBattle/QuickBattleAI.py, QuickBattleFriendlyAI.py), exactly as the
    # original's duels build them: a 7 s Wait, AvoidObstacles, then BasicAttack (FollowTargetThroughWarp=1,
    # UseCloaking=1) with a fly-pointlessly fallback. The enemy AI targets QuickBattle's pFriendlies, the friendly
    # AI its pEnemies; the fixture puts the target in the mission's enemy group and the attacker in its friendly
    # group, so they map across.
    QB = importlib.import_module("QuickBattle.QuickBattle")
    monkeypatch.setattr(QB, "pFriendlies", s.mission.GetEnemyGroup(), raising=False)
    monkeypatch.setattr(QB, "pEnemies", s.mission.GetFriendlyGroup(), raising=False)
    monkeypatch.setattr(QB, "g_iCurrentAILevel", lv, raising=False)
    s.atk.SetAI(importlib.import_module("QuickBattle.QuickBattleAI").CreateAI(s.atk), 0, 0)
    s.tgt.SetAI(importlib.import_module("QuickBattle.QuickBattleFriendlyAI").CreateAI(s.tgt), 0, 0)

    # Optional (AIM_DUEL_TRACE_CLOAK=1): who starts/stops each cloak, with a short call stack.
    cloak_calls = []
    if _os.environ.get("AIM_DUEL_TRACE_CLOAK"):
        import traceback
        from engine.appc.subsystems import CloakingSubsystem as _CS
        for _nm in ("StartCloaking", "StopCloaking"):
            def _mk(nm, orig):
                def w(self, *a, **k):
                    try:
                        st = traceback.extract_stack(limit=9)[:-1]
                        cloak_calls.append([round(s.t, 2), nm, " <- ".join("%s:%s" % (f.filename.split("/")[-1], f.name) for f in st[-6:])])
                    except Exception:
                        pass
                    return orig(self, *a, **k)
                return w
            monkeypatch.setattr(_CS, _nm, _mk(_nm, getattr(_CS, _nm)))

    # Optional (AIM_DUEL_TRACE_FS=1): per FireScript node and weapon system, calls to FireSystemAtTarget and passed
    # CheckGoodShot per game second -- the Dauntless twin of CombatTap's FSA rows.
    fs_counts = {}
    # Needs the compiled FireScript node (Dauntless combat-ai-parity).
    if _os.environ.get("AIM_DUEL_TRACE_FS"):
        from engine.appc.optimized_fire_script import CompiledFireScriptMixin as _CFS

        def _fs_key(inst, w):
            try:
                node = inst.pCodeAI
                return "%d|%s|%s|%s" % (int(s.t), node.GetShip().GetName(), node.GetName(), w.GetName().replace(" ", "_"))
            except Exception:
                return None

        def _wrap_fire(orig):
            def w(self, pWeaponSystem, pTarget, pSubsystem):
                k = _fs_key(self, pWeaponSystem)
                if k:
                    fs_counts.setdefault(k, [0, 0])[0] += 1
                return orig(self, pWeaponSystem, pTarget, pSubsystem)
            return w

        def _wrap_good(orig):
            def w(self, pWeaponSystem, pTarget, pSubsystem):
                r = orig(self, pWeaponSystem, pTarget, pSubsystem)
                if r:
                    k = _fs_key(self, pWeaponSystem)
                    if k:
                        fs_counts.setdefault(k, [0, 0])[1] += 1
                return r
            return w
        monkeypatch.setattr(_CFS, "FireSystemAtTarget", _wrap_fire(_CFS.FireSystemAtTarget))
        smart_log = fs_counts.setdefault("_smart", [])

        def _wrap_smart(orig):
            def w(self, pPhaserSystem, pTarget, pSubsystem):
                ok = orig(self, pPhaserSystem, pTarget, pSubsystem)
                try:
                    import math as _m
                    from engine.appc.optimized_fire_script import _dist
                    from engine.appc.combat import _shield_face_from_hit_point
                    aim = (pSubsystem or pTarget).GetWorldLocation()
                    dd = _dist(aim, pPhaserSystem.GetWorldLocation())
                    bank = pPhaserSystem.GetChildSubsystem(0) if pPhaserSystem.GetNumChildSubsystems() > 0 else None
                    R = float(bank.GetMaxDamageDistance()) if bank is not None else 1.0
                    sv, face = 1.0, -1
                    shp = App.ShipClass_Cast(pTarget)
                    shd = shp.GetShields() if shp is not None else None
                    if shd is not None and shd.IsOn() and not shd.IsDisabled():
                        face = _shield_face_from_hit_point(shp, pPhaserSystem.GetWorldLocation())
                        S = float(shd.GetCurShields(face)); avg = 0.2 * sum(float(shd.GetCurShields(i)) for i in range(6) if i != face)
                        if S > avg and S > 0.0:
                            sv = _m.atan(avg / S) / (_m.pi / 2.0)
                    smart_log.append([round(s.t, 2), self.pCodeAI.GetShip().GetName(), round(dd, 1), R, round(sv, 3), face,
                                      round(self.__dict__.get("_ofs_acc", -1), 3), 1 if ok else 0])
                except Exception as e:
                    smart_log.append(["err", repr(e)[:80]])
                return ok
            return w
        import App
        monkeypatch.setattr(_CFS, "_smart_phaser_shot", _wrap_smart(_CFS._smart_phaser_shot))
        # GetPredictedPosition inputs (twin of CombatTap PP rows): one row per caller per 0.25 s.
        pp_log = fs_counts.setdefault("_pp", [])
        pp_next = {}
        from engine.appc.ships import ShipClass as _SC
        import traceback as _tb

        def _wrap_pp(orig):
            def w(self, p, v, a, t):
                try:
                    fr = _tb.extract_stack(limit=3)[0]
                    caller = "%s:%s" % (fr.filename.split("/")[-1], fr.name)
                    if s.t >= pp_next.get(caller, -1.0):
                        pp_next[caller] = s.t + 0.25
                        pp_log.append([round(s.t, 2), caller, self.GetName(), [round(x, 3) for x in (p.x, p.y, p.z)],
                                       [round(x, 4) for x in (v.x, v.y, v.z)], [round(x, 4) for x in (a.x, a.y, a.z)], round(float(t), 3)])
                except Exception:
                    pass
                return orig(self, p, v, a, t)
            return w
        monkeypatch.setattr(_SC, "GetPredictedPosition", _wrap_pp(_SC.GetPredictedPosition))
        _SDKFS = importlib.import_module("AI.Preprocessors").FireScript      # CheckGoodShot is the SDK body
        monkeypatch.setattr(_SDKFS, "CheckGoodShot", _wrap_good(_SDKFS.CheckGoodShot))

    Pre = importlib.import_module("AI.Preprocessors")
    from engine.appc import combat
    orig_choose, orig_hit = Pre.FireScript.ChooseTargetSubsystem, combat.apply_hit
    choices, hits, current = [], [], {}

    def choose(self, pTarget):
        p = orig_choose(self, pTarget)
        try:
            ship = self.pCodeAI.GetShip().GetName()
            ws = "+".join(w.GetName().replace(" ", "_") for w in getattr(self, "lWeapons", []))
            nm = p.GetName().replace(" ", "_") if p else "-"
            if current.get((ship, ws)) != nm:
                choices.append(dict(t=round(s.t, 3), ship=ship, ws=ws, sub=nm))
            current[(ship, ws)] = nm
        except Exception:
            pass
        return p

    allhits = []
    hitdetail = []

    def _all_subsystems(ship):
        out = [ship.GetHull()] if ship.GetHull() is not None else []
        for sub in ship.GetSubsystems():
            if sub is not None and sub is not ship.GetHull():
                out.append(sub)
                try:
                    out.extend(sub.GetChildSubsystem(i) for i in range(sub.GetNumChildSubsystems()))
                except Exception:
                    pass
        return out

    def hit(ship, damage, hit_point, source, **kw):
        try:
            if kw.get("_overflow_depth", 0) == 0:
                sh = ship.GetShields() if hasattr(ship, "GetShields") else None
                before = sum(sh.GetCurrentShields(i) for i in range(6)) if sh is not None else 0.0
                hb = ship.GetHull().GetCondition() if ship.GetHull() is not None else 0.0
                allhits.append([round(s.t, 3), source.GetName() if source is not None else None, ship.GetName(),
                                kw.get("weapon_type"), round(float(damage), 2), round(before, 1), round(hb, 1)])
        except Exception:
            pass
        try:
            if kw.get("weapon_type") == "phaser" and kw.get("_overflow_depth", 0) == 0 and source is not None:
                sn = source.GetName()
                aim = [v for (sh, ws), v in current.items() if sh == sn and "Phasers" in ws]
                hits.append(dict(t=round(s.t, 3), shooter=sn, target=ship.GetName(), aim=aim[0] if aim else None,
                                 dmg=round(float(damage), 2)))
        except Exception:
            pass
        if kw.get("_overflow_depth", 0) != 0:
            return orig_hit(ship, damage, hit_point, source, **kw)
        try:
            subs0 = {sub.GetName(): sub.GetCondition() for sub in _all_subsystems(ship)}
            sh = ship.GetShields() if hasattr(ship, "GetShields") else None
            sh0 = [sh.GetCurrentShields(i) for i in range(6)] if sh is not None else None
        except Exception:
            subs0 = None
        r = orig_hit(ship, damage, hit_point, source, **kw)
        if subs0 is not None:
            try:
                # [t, source, ship, weapon_type, damage, shields per face before, after, {subsystem: damage}]
                # -- the per-hit split BC's CombatTap S/DS/W rows give (hull is the subsystem "Hull").
                sh1 = [sh.GetCurrentShields(i) for i in range(6)] if sh is not None else None
                lost = {}
                for sub in _all_subsystems(ship):
                    d0 = subs0.get(sub.GetName())
                    if d0 is not None and d0 - sub.GetCondition() > 1e-6:
                        lost[sub.GetName()] = round(d0 - sub.GetCondition(), 2)
                hitdetail.append([round(s.t, 3), source.GetName() if source is not None else None, ship.GetName(),
                                  kw.get("weapon_type"), round(float(damage), 2),
                                  [round(x, 1) for x in sh0] if sh0 else None,
                                  [round(x, 1) for x in sh1] if sh1 else None, lost])
            except Exception:
                pass
        return r

    # PlainAI behaviour call counts per ship (the original's xa rows, Oracle/OracleAIProbe.install_plain)
    beh, beh_orig = {}, {}
    # Speed commands by behaviour (the original's xi rows, OracleAIProbe.install_speed): per ship since the
    # last sample, [kind I=SetImpulse / S=SetSpeed, last value, script that issued it, calls]
    cur_script = ["-"]
    speed_last = {}
    from engine.appc.ships import ShipClass as _SC
    speed_orig = {"SetImpulse": _SC.__dict__.get("SetImpulse"), "SetSpeed": _SC.__dict__.get("SetSpeed")}

    speed_depth = [0]

    def _speed_wrap(kind, orig):
        def w(self, *a, **k):
            # record only the OUTERMOST command (Dauntless's SetImpulse calls SetSpeed itself): what the AI asked
            speed_depth[0] += 1
            try:
                if a and speed_depth[0] == 1:
                    e = speed_last.get(self.GetName())
                    if e is None:
                        speed_last[self.GetName()] = [kind, float(a[0]), cur_script[0], 1]
                    else:
                        e[0], e[1], e[2], e[3] = kind, float(a[0]), cur_script[0], e[3] + 1
            except Exception:
                pass
            try:
                return orig(self, *a, **k)
            finally:
                speed_depth[0] -= 1
        return w
    for _nm, _kind in (("SetImpulse", "I"), ("SetSpeed", "S")):
        if speed_orig[_nm] is not None:
            setattr(_SC, _nm, _speed_wrap(_kind, speed_orig[_nm]))
    for m in PLAIN_MODULES:
        try:
            cls = getattr(importlib.import_module("AI.PlainAI." + m), m)
        except Exception:
            continue

        def wrap(orig, m=m):
            def upd(self, *a, **k):
                try:
                    key = (self.pCodeAI.GetShip().GetName(), m)
                    beh[key] = beh.get(key, 0) + 1
                except Exception:
                    pass
                prev = cur_script[0]
                cur_script[0] = m
                try:
                    return orig(self, *a, **k)
                finally:
                    cur_script[0] = prev
            return upd
        beh_orig[cls] = cls.__dict__.get("Update")
        if beh_orig[cls] is not None:
            cls.Update = wrap(beh_orig[cls])

    Pre.FireScript.ChooseTargetSubsystem = choose
    combat.apply_hit = hit
    winner = None
    winner_role = None
    track = []

    def pose(ship):
        p, R = ship.GetWorldLocation(), ship.GetWorldRotation()
        f, u = R.GetCol(1), R.GetCol(2)
        return [round(p.x, 3), round(p.y, 3), round(p.z, 3), round(f.x, 4), round(f.y, 4), round(f.z, 4),
                round(u.x, 4), round(u.y, 4), round(u.z, 4)]
    def status(ship):
        """BC telemetry's xz fields: impulse, phasers firing, torpedo ammo type and torps left per type."""
        out = {}
        try:
            out["imp"] = round(float(ship.GetImpulse()), 3)
        except Exception:
            pass
        try:
            out["pf"] = int(bool(ship.GetPhaserSystem().IsFiring()))
        except Exception:
            pass
        try:
            ts = ship.GetTorpedoSystem()
            out["am"] = ts.GetAmmoTypeNumber()
            out["ta"] = [ts.GetNumAvailableTorpsToType(i) for i in range(ts.GetNumAmmoTypes())]
            # each tube's loaded count, in child order (BC telemetry's xw t/<ready> entries)
            out["tr"] = [ts.GetChildSubsystem(i).GetNumReady() for i in range(ts.GetNumChildSubsystems())]
            # disabled flags (BC telemetry's xd dis= bits for Torpedoes and its tubes): [system, tube...]
            out["td"] = [int(bool(ts.IsDisabled()))] + [int(bool(ts.GetChildSubsystem(i).IsDisabled()))
                                                        for i in range(ts.GetNumChildSubsystems())]
        except Exception:
            pass
        try:
            # batteries (BC telemetry's xp mb= / bb=): main, backup, and their limits
            pw = ship.GetPowerSubsystem()
            if pw is not None:
                out["pw"] = [round(float(pw.GetMainBatteryPower()), 1), round(float(pw.GetBackupBatteryPower()), 1),
                             round(float(pw.GetMainBatteryLimit()), 1), round(float(pw.GetBackupBatteryLimit()), 1),
                             round(float(pw.GetPowerOutput()), 2), round(float(pw.GetAvailablePower()), 2),
                             round(float(pw.GetPowerDispensed()), 2)]
            # per powered subsystem (BC telemetry's xq): wanted %, power % (efficiency), received
            pq = {}
            for sub in ship.GetSubsystems():
                if sub is None or not hasattr(sub, "GetPowerPercentageWanted"):
                    continue
                pq[sub.GetName().replace(" ", "_")] = [round(float(sub.GetPowerPercentageWanted()), 3),
                                                        round(float(sub.GetPowerPercentage()), 3),
                                                        round(float(sub.GetPowerReceived()), 3), int(bool(sub.IsOn()))]
            out["pq"] = pq
        except Exception:
            pass
        try:
            # cloak state (BC telemetry's xz ck=<cloaked>/<cloaking>/<decloaking>)
            ck = ship.GetCloakingSubsystem()
            if ck is not None:
                out["ck"] = [int(bool(ck.IsCloaked())), int(bool(ck.IsCloaking())), int(bool(ck.IsDecloaking()))]
        except Exception:
            pass
        try:
            # each energy emitter's charge and firing flag by name (BC telemetry's xw e/<charge>/<firing>)
            ew = {}
            for sysname in ("GetPhaserSystem", "GetPulseWeaponSystem"):
                ws = getattr(ship, sysname)()
                if ws is None:
                    continue
                for i in range(ws.GetNumChildSubsystems()):
                    o = ws.GetChildSubsystem(i)
                    ew[o.GetName().replace(" ", "_")] = [round(float(o.GetChargeLevel()), 3), int(bool(o.IsFiring()))]
            out["ew"] = ew
        except Exception:
            pass
        try:
            # total shields and hull condition (BC telemetry's xh sh= sum and xc hull)
            sh = ship.GetShields()
            out["sh"] = round(sum(sh.GetCurrentShields(i) for i in range(6)), 1)
            out["hu"] = round(float(ship.GetHull().GetCondition()), 1)
        except Exception:
            pass
        return out
    try:
        for t, sc in s.sample_until(900.0, every_ticks=15):
            fa = []
            for (o, sh, kind, nm) in nodes:
                try:
                    fa.append(("1" if o.HasFocus() else "0") + ("1" if o.IsActive() else "0"))
                except Exception:
                    fa.append("xx")
            cs = []
            for (o, cname, carg, owner) in conds:
                try:
                    cs.append(str(int(o.GetStatus()))[:1])
                except Exception:
                    cs.append("x")
            # projectiles in flight (the original's xt1 rows): [id, damage, x, y, z] -- a torpedo's launcher is
            # the ship it first appears beside, its fate whether it vanished at its lifetime or on a hit
            tp = []
            try:
                from engine.appc import projectiles as _proj
                for _p in list(_proj._active):
                    _w = _p.GetWorldLocation()
                    tp.append([int(_p.GetObjID()), round(float(_p.GetDamage()), 2),
                               round(_w.x, 2), round(_w.y, 2), round(_w.z, 2)])
            except Exception:
                tp = None
            spd = {("A" if n == s.atk.GetName() else "T"): [e[0], round(e[1], 4), e[2], e[3]]
                   for n, e in speed_last.items() if n in (s.atk.GetName(), s.tgt.GetName())}
            speed_last.clear()
            track.append(dict(t=round(s.t, 2), A=pose(s.atk), T=pose(s.tgt), sA=status(s.atk), sT=status(s.tgt), tp=tp, spd=spd,
                              beh={f"{k[0]}|{k[1]}": v for k, v in beh.items() if v}, tree="".join(fa), cond="".join(cs)))
            beh.clear()
            if s.atk.IsDying() or s.tgt.IsDying():
                winner = player if s.atk.IsDying() else enemy
                # which ROLE won: a mirror match (Galaxy vs Galaxy) has the same class on both sides
                winner_role = "player" if s.atk.IsDying() else "enemy"
                break
    finally:
        Pre.FireScript.ChooseTargetSubsystem = orig_choose
        combat.apply_hit = orig_hit
        for _nm in ("SetImpulse", "SetSpeed"):
            if speed_orig[_nm] is not None:
                setattr(_SC, _nm, speed_orig[_nm])
        for cls, up in beh_orig.items():
            if up is not None:
                cls.Update = up
        for fn, f0 in fac_orig.items():
            setattr(App, fn, f0)
        # The fight is over: free both AI trees as a mission end deletes its ships (engine/appc/ai.py
        # destroy_ai_tree) -- else the next duel's same-named ships inherit stale condition registries. A Dauntless
        # without destroy_ai_tree (before combat-ai-parity) keeps the trees, as its own mission ends do.
        try:
            from engine.appc.ai import destroy_ai_tree
        except ImportError:
            destroy_ai_tree = None
        for ship in (s.atk, s.tgt):
            ai = ship.__dict__.get("_ai")
            if ai is not None and destroy_ai_tree is not None:
                destroy_ai_tree(ai)
    (OUT / f"{name}.json").write_text(json.dumps(dict(
        enemy=enemy, player=player, level=lv, angle=angle, winner=winner, winner_role=winner_role, t_end=s.t,
        attacker_name=s.atk.GetName(), target_name=s.tgt.GetName(), choices=choices, hits=hits, track=track,
        allhits=allhits, hitdetail=hitdetail, tube_names=_tube_names(s), cloak_calls=cloak_calls, fs_counts=fs_counts,
        tree_nodes=[(sh, kind, nm) for (o, sh, kind, nm) in nodes],
        cond_nodes=[(owner, cname, carg) for (o, cname, carg, owner) in conds])))

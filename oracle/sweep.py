"""Aim sweeps for the Galaxy-vs-Sovereign study (Mac/CrossOver port).

Each run: attacker (enemy) fires one weapon system at the target (the player ship), aimed at one
target subsystem the way the player's subsystem targeting does, from one bearing, after the
Quick Battle intro cutscene.  CombatTap.asi records every hit (impact point, radius, each
subsystem damaged).  Results go to ../results_mac/sweep/<name>.json; existing ones are skipped.

    python oracle/sweep.py pilot          # warp core, 6 bearings, phaser HIGH + photon
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_oracle  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results_mac" / "sweep"

BEARINGS = {            # name: (angle_deg, elev_deg)
    "front": (0, 0), "stbd": (90, 0), "aft": (180, 0), "port": (270, 0),
    "top": (0, 60), "bottom": (0, -60),
}
WEAPONS = {             # name: extra params
    "phaserH": {"weapon": "phaser", "intensity": 2, "duration": 16.0},
    "photon": {"weapon": "torpedo", "torp_type": 0, "duration": 14.0},
    "quantum": {"weapon": "torpedo", "torp_type": 1, "duration": 14.0},
    "phaserL": {"weapon": "phaser", "intensity": 0, "duration": 16.0},
}


def base(attacker, target):
    return {
        "attacker": attacker, "target": target, "motion": "none", "range_gu": 57.0,
        "angle_deg": 0.0, "elev_deg": 0.0, "intensity": 2, "charge": -1.0, "power_wanted": -1.0,
        "shield_face": -1, "shield_frac": 1.0, "shields_off": 1, "settle_s": 2.0, "fire_at": 8.0,
        "duration": 14.0, "sample_dt": 0.05, "disable_target_weapons": 1, "rows": "ab",
        "torp_type": -1, "aim_sub": "none", "pulse_power": -1, "time_scale": 1.0,
        "target_alert": "red", "tractor_mode": "hold", "shield_power": -1.0, "gen_frac": -1.0,
        "ai": 0, "ai_level": 0.5, "ai_log": 0, "target_motion": "none", "target_fire": 0,
        "sample": "attacker", "view": "bridge", "warp_patch": "none", "mission": "none",
        "cam_mode": "none", "cam_step_s": 4.0, "vfx_patch": "none", "effects_wrap": "0",
        "ai_module": "none", "face_away": "0", "ai_patch": "none", "nebula": "none",
        "difficulty": 1, "hp_patch": "none", "dscale_set": -1.0, "warp_stop_gu": 50.0,
        "warp_time": 5.0, "warp_dest": "Systems.Vesuvi.Vesuvi5", "warp_clear": 0.0,
    }


SESSIONS = {
    # same six phaser shots as the fresh-boot pilot, in one launch (validation of session mode)
    "session_pilot": [dict(a=BEARINGS[b][0], e=BEARINGS[b][1], w="phaser", i=2, aim="Warp_Core", sh="off", d=8, g=3)
                      for b in BEARINGS],
    # angle of fire vs the starboard nacelle: abeam (90) and swung forward/aft, one bank, then torpedoes
    "incidence": [dict(a=a, e=0, w="phaser", i=2, aim="Star_Warp", sh="off", d=6, g=2, s=3, b="Dorsal_Phaser_3")
                  for a in (90, 75, 60, 45, 30, 15, 105, 120, 135, 150, 165)]
               + [dict(a=a, e=0, w="torpedo", i=2, aim="Star_Warp", sh="off", d=6, g=4, s=3, tt=-1)
                  for a in (90, 60, 30, 120, 150)],
    # same angles with full shields: which face takes the shot as the angle swings
    "incidence_shields": [dict(a=a, e=0, w="phaser", i=2, aim="Star_Warp", sh="full", d=6, g=2, s=3, b="Dorsal_Phaser_3")
                          for a in (90, 75, 60, 45, 30, 15, 105, 120, 135, 150, 165)],
    # bank-origin prediction check: one bank at the Galaxy warp core from the six pilot bearings
    "predict_check": [dict(a=BEARINGS[b][0], e=BEARINGS[b][1], w="phaser", i=2, aim="Warp_Core", sh="off", d=5, g=2, s=3,
                           b="Dorsal_Phaser_3") for b in BEARINGS],
    # D: validate instant-read engine limits with real flights (attacker = the flying ship)
    "motion_check": [dict(w="none", mv=mv, mf=mf, tf=1, ipw=ipw, ic=ic, fa=1, a=0, e=0, sh="full", d=10, g=1, s=2)
                     for (mv, mf, ipw, ic) in (
                         ("impulse", 1, 1, 1), ("impulse", 1, 0.5, 1), ("impulse", 1, 1, 0.75), ("impulse", 1, 1.25, 1),
                         ("impulse", 0.5, 1, 1),
                         ("yaw", 1, 1, 1), ("yaw", 1, 0.5, 1), ("yaw", 1, 1, 0.75),
                         ("pitch", 1, 1, 1), ("roll", 1, 1, 1),
                         ("impyaw", 1, 1, 1), ("impyaw", 0.5, 1, 1))],
}


SESSIONS["resume_test"] = SESSIONS["predict_check"]

# 3: repair (Galaxy = target is repaired; nothing fires).  Complexity: sensor 1, warp core and
# shield generator 2, tubes/impulse/hull 3, phasers 7.  Galaxy has 3 repair teams.
_R = dict(w="none", sh="full", d=30, g=1, s=1)
SESSIONS["repair"] = [dict(_R, dmg=x, **extra) for (x, extra) in (
    ("Sensor_Array/0.5", {}),                                                          # 1 item
    ("Sensor_Array/0.5+Forward_Torpedo_1/0.5", {}),                                     # 2 items
    ("Sensor_Array/0.5+Forward_Torpedo_1/0.5+Ventral_Phaser_1/0.5", {}),                # 3 items (= teams)
    ("Sensor_Array/0.5+Forward_Torpedo_1/0.5+Ventral_Phaser_1/0.5+Port_Impulse/0.6", {}),  # 4 > teams: queue
    ("Port_Impulse/0.6+Ventral_Phaser_1/0.5+Forward_Torpedo_1/0.5+Sensor_Array/0.5", {}),  # same 4, other order
    ("Sensor_Array/0.5+Forward_Torpedo_1/0.0+Forward_Torpedo_2/0.5", {}),               # one destroyed item
    ("Sensor_Array/0.5", {"rpw": 0.5}),                                                 # repair power 50%
    ("Sensor_Array/0.5", {"rc": 0.5}),                                                  # repair system at 50%
    ("Sensor_Array/0.5", {"rpw": 0.0}),                                                 # repair power off
    ("Warp_Core/0.6+Shield_Generator/0.6", {}),                                         # complexity 2 pair
)]
# 4: torpedo reload path: natural first salvo, then forced reloads; then quantum after ammo switch
_T = dict(w="torpedo", aim="Warp_Core", sh="off", d=6, g=4, s=2, a=0, e=60)
SESSIONS["torp_reload"] = [dict(_T), dict(_T), dict(_T), dict(_T, tt=1), dict(_T, tt=1), dict(_T, tt=0)]
# 5: shield-face map of the Galaxy: attacker all around, full shields, short bursts
SESSIONS["faces_galaxy"] = [dict(w="phaser", i=2, aim="none", sh="full", d=2.5, g=0.5, s=1.5, a=a, e=e)
                            for e in (-75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75) for a in range(0, 360, 15)] \
                           + [dict(w="phaser", i=2, aim="none", sh="full", d=2.5, g=0.5, s=1.5, a=0, e=e) for e in (-89, 89)]
# 2b: rate effects of power sliders: target front shield face at 50% regenerating under the
# target's shield slider; attacker phaser banks recharging from empty under its phaser slider
# (w=none: nothing fires); then torpedo reload from empty tubes under the torpedo slider.
SESSIONS["power_effects"] = [dict(w="phaser", mv="none", aim="none", sh="0:0.5", d=8, g=0.5, s=1, chg=0,
                                  tpw="Shields/%s" % pw, apw="PhaserSystem/%s" % pw, nf=1)
                             for pw in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25)] \
                            + [dict(w="torpedo", aim="none", sh="full", d=45, g=0.5, s=1, tub=0, nf=1,
                                    apw="TorpedoSystem/%s" % pw) for pw in (0.5, 1.0, 1.25)]
# Impulse matrix (Galaxy flies, faces away): the game's throttle levels k/9, level changes,
# reverse (-2/9), and turning at levels 3/6/9, at engine power 1.0 / 0.75 / 0.5 / 1.25.
def _impulse_matrix():
    out = []
    for pw in (1.0, 0.75, 0.5, 1.25):
        base = dict(w="none", fa=1, a=0, e=0, sh="full", g=1, s=2, ipw=pw, ic=1)
        for k in range(1, 10):                                   # 0 -> level k
            out.append(dict(base, mv="impulse", mf=round(k / 9.0, 6), d=12))
        for a, b in ((9, 0), (9, 4), (4, 9), (3, 6), (6, 3), (0, -2), (9, -2), (-2, 9)):   # level changes
            out.append(dict(base, mv="impulse", mf=round(a / 9.0, 6), mf2=round(b / 9.0, 6), t2=10, d=22))
        for k in (3, 6, 9):                                      # turning at speed: reach level, then yaw
            out.append(dict(base, mv="impyaw", mf=round(k / 9.0, 6), tf=1, d=14))
    return out
SESSIONS["impulse_matrix"] = _impulse_matrix()
SESSIONS["impulse_matrix_sovereign"] = SESSIONS["impulse_matrix"]
SESSION_SHIPS_EXTRA = {"impulse_matrix": ("Galaxy", "Sovereign")}
# Power budget (Galaxy = the observed, flying ship): battery regen/drain vs total demand.
def _power_budget():
    out = []
    for L in (0.5, 0.75, 1.0, 1.25):
        apw = "+".join(f"{g}/{L}" for g in ("Shields", "SensorSubsystem", "TorpedoSystem", "PhaserSystem", "ImpulseEngineSubsystem"))
        base = dict(w="phaser", nf=1, aim="none", sh="full", d=30, g=1, s=1, a=0, e=0, apw=apw)
        out.append(dict(base))                                       # idle, weapons full
        out.append(dict(base, chg=0))                                # phasers recharging from empty
        out.append(dict(base, chg=0, mv="impulse", mf=1, fa=1))      # recharging + full impulse
    out.append(dict(w="tractor", aim="none", sh="full", d=30, g=1, s=1, a=0, e=0, range=30,
                    apw="+".join(f"{g}/1.0" for g in ("Shields", "SensorSubsystem", "TorpedoSystem", "PhaserSystem",
                                                       "ImpulseEngineSubsystem", "TractorBeamSystem"))))
    return out
SESSIONS["power_budget"] = _power_budget()
# v2: batteries start at 50% so both regen and drain show; 120 s per condition; fine steps around
# break-even; each weapon drawing alone.
def _power_budget2():
    out = []
    G = ("Shields", "SensorSubsystem", "TorpedoSystem", "PhaserSystem", "ImpulseEngineSubsystem")
    for L in (0.5, 0.75, 0.9, 1.0, 1.1, 1.15, 1.2, 1.25):
        out.append(dict(w="phaser", nf=1, aim="none", sh="full", d=120, g=1, s=1, a=0, e=0, bat=0.5, chg=0,
                        apw="+".join(f"{g}/{L}" for g in G)))
    out.append(dict(w="tractor", aim="none", sh="full", d=60, g=1, s=1, a=0, e=0, bat=0.5,
                    apw="+".join(f"{g}/1.0" for g in G + ("TractorBeamSystem",))))
    return out
SESSIONS["power_budget2"] = _power_budget2()
# Torpedo reload vs torpedo-system slider: fire a real salvo (reload timers start on firing),
# then watch every tube's NumReady for 55 s.  Also the original oracle's shield-power-50 regen
# case, to reconcile 'regen unaffected by 50% power' with our linear result.
# Natural torpedo timing on the Sovereign: reload after firing per type, type-switch cost,
# torpedo power 50%, and a switch made while tubes are mid-reload.  rl=0: no forced reloads.
_N = dict(aim="Warp_Core", sh="off", g=0.5, s=1, a=0, e=60, rl=0)
SESSIONS["torp_timing"] = [
    dict(_N, w="torpedo", tt=0, d=60),                 # photon salvo (spawn load), watch reloads
    dict(_N, w="torpedo", nf=1, tt=1, d=70),           # switch to quantum, no fire: switch cost
    dict(_N, w="torpedo", tt=1, d=70),                 # quantum salvo, watch reloads
    dict(_N, w="torpedo", nf=1, tt=0, d=70),           # switch back to photon
    dict(_N, w="torpedo", tt=0, d=90, apw="PhaserSystem/0.5+TorpedoSystem/0.5"),     # photon salvo at 50% torpedo power
    dict(_N, w="torpedo", tt=0, d=20),                 # photon salvo ...
    dict(_N, w="torpedo", nf=1, tt=1, d=80),           # ... then switch to quantum mid-reload
]
# The Galaxy has photons only: reload-after-firing timing at 100% and 50% torpedo power.
SESSIONS["torp_timing_galaxy"] = [dict(_N, w="torpedo", d=60), dict(_N, w="torpedo", d=90, apw="PhaserSystem/0.5+TorpedoSystem/0.5")]
# Torpedo spread modes (Single / Dual / Quad = firing chain 0 / 1 / 2), tubes force-loaded,
# fired at the target from ahead (forward tubes bear) and from astern (aft tubes bear).
SESSIONS["torp_spread"] = [dict(w="torpedo", aim="none", sh="off", d=8, g=2, s=2, a=a, e=0, chain=c)
                           for a in (0, 180) for c in (0, 1, 2)]
SESSIONS["torp_spread_galaxy"] = SESSIONS["torp_spread"]
# v2: long gaps so no torpedo outlives its shot; both bearings; trajectories via xt1 rows (rows abx).
SESSIONS["torp_spread2"] = [dict(w="torpedo", aim="none", sh="off", d=10, g=14, s=2, a=a, e=0, chain=c)
                            for a in (0, 180) for c in (0, 1, 2)]
SESSIONS["torp_spread2_galaxy"] = SESSIONS["torp_spread2"]
# What the four Engineering controls change beyond the instant limits:
#  - phaser damage per hit / firing duration vs the Weapons control (one bank, full charge, shields down)
#  - torpedo damage vs the Weapons control
#  - shield absorption vs the Shields control (same phaser fire into a full front face)
def _slider_effects():
    out = []
    W = lambda x: f"PhaserSystem/{x}+TorpedoSystem/{x}"
    for x in (0.25, 0.5, 1.0, 1.25):
        out.append(dict(w="phaser", i=2, aim="Warp_Core", sh="off", d=8, g=2, s=2, a=0, e=60, chg=1,
                        b="Dorsal_Phaser_3", apw=W(x)))
    for x in (0.5, 1.25):
        out.append(dict(w="torpedo", aim="Warp_Core", sh="off", d=8, g=2, s=2, a=0, e=60, apw=W(x)))
    for x in (0.0, 0.5, 1.0, 1.25):
        out.append(dict(w="phaser", i=2, aim="none", sh="full", d=8, g=2, s=2, a=0, e=0, chg=1,
                        b="Dorsal_Phaser_3", tpw=f"Shields/{x}"))
    return out
SESSIONS["slider_effects"] = _slider_effects()
SESSION_PARAMS_EXTRA = None
SESSIONS["torp_reload_power"] = [dict(w="torpedo", aim="Warp_Core", sh="off", d=55, g=1, s=2, a=0, e=60,
                                      apw=f"PhaserSystem/{pw}+TorpedoSystem/{pw}") for pw in (0.5, 1.0, 1.25)] \
                                + [dict(w="phaser", nf=1, aim="none", sh="0:0.5", d=12, g=1, s=1, tpw="Shields/0.5"),
                                   dict(w="phaser", nf=1, aim="none", sh="0:0.5", d=12, g=1, s=5, tpw="Shields/0.5")]
# Gap 2/3: partially damaged weapons and shield generator (Sovereign attacker, Galaxy target).
def _partial_damage():
    out = []
    B = "Dorsal_Phaser_3"
    for x in (1.0, 0.9, 0.8):       # damage per hit / firing duration of a damaged (still working) bank
        out.append(dict(w="phaser", i=2, aim="Warp_Core", sh="off", d=8, g=2, s=2, a=0, e=60, chg=1, b=B, admg=f"{B}/{x}"))
    for x in (1.0, 0.8):            # recharge of a damaged bank, from empty, nothing firing
        out.append(dict(w="phaser", nf=1, aim="none", sh="full", d=12, g=1, s=1, chg=0, admg=f"{B}/{x}"))
    out.append(dict(w="torpedo", aim="Warp_Core", sh="off", d=50, g=12, s=2, a=0, e=60, rl=0,
                    admg="Forward_Torpedo_1/0.8"))   # reload of a damaged tube vs healthy ones
    for x in (1.0, 0.9, 0.8):       # target shield generator partially damaged: regen + face cap
        out.append(dict(w="phaser", nf=1, aim="none", sh="0:0.5", d=12, g=1, s=1, dmg=f"Shield_Generator/{x}"))
    return out
SESSIONS["partial_damage"] = _partial_damage()
# Warp-core damage vs the power system (Galaxy flying ship, everything drawing, batteries half).
SESSIONS["power_core"] = [dict(w="phaser", nf=1, aim="none", sh="full", d=60, g=1, s=1, a=0, e=0, bat=0.5, chg=0,
                               mv="impulse", mf=1, fa=1, admg=f"Warp_Core/{c}",
                               apw="+".join(f"{g}/1.0" for g in ("Shields", "SensorSubsystem", "TorpedoSystem",
                                                                 "PhaserSystem", "ImpulseEngineSubsystem")))
                          for c in (1.0, 0.6, 0.49, 0.3)]
# Repair queue order: damage applied in sequence (dmg at shot start, dmg2 at td2 s).
_RO = dict(w="none", sh="full", d=40, g=1, s=1)
SESSIONS["repair_order"] = [
    dict(_RO, dmg="Port_Impulse/0.6", dmg2="Sensor_Array/0.5+Forward_Torpedo_1/0.5+Ventral_Phaser_1/0.5", td2=3),
    dict(_RO, dmg="Ventral_Phaser_1/0.5", dmg2="Port_Impulse/0.6+Sensor_Array/0.5+Forward_Torpedo_1/0.5", td2=3),
    dict(_RO, dmg="Forward_Torpedo_1/0.5+Ventral_Phaser_1/0.5+Port_Impulse/0.6", dmg2="Sensor_Array/0.5", td2=3),
    dict(_RO, dmg="Sensor_Array/0.95+Forward_Torpedo_1/0.5+Ventral_Phaser_1/0.5", dmg2="Port_Impulse/0.6", td2=1),
]
# Spread modes vs range: does a fan converge at longer range? (attacker faces target, shields off)
SESSIONS["torp_spread_range"] = [dict(w="torpedo", aim="none", sh="off", d=14, g=16, s=2, a=0, e=0, chain=c, rng=rg)
                                 for rg in (30, 57, 120, 200) for c in (0, 1, 2)]
SESSIONS["torp_spread_range_galaxy"] = SESSIONS["torp_spread_range"]
# Phaser damage vs range and intensity (single isolated bank, shields off unless noted).
def _phaser_range(bank):
    out = []
    for rg in (30, 57, 70, 90, 120, 150, 200, 300):
        out.append(dict(w="phaser", i=2, aim="none", sh="off", d=8, g=2, s=2, a=0, e=0, chg=1, b=bank, rng=rg))
    for i in (0, 1, 2):
        out.append(dict(w="phaser", i=i, aim="none", sh="off", d=8, g=2, s=2, a=0, e=0, chg=1, b=bank, rng=57))
        out.append(dict(w="phaser", i=i, aim="none", sh="full", d=8, g=2, s=2, a=0, e=0, chg=1, b=bank, rng=57))
    return out
SESSIONS["phaser_range"] = _phaser_range("Dorsal_Phaser_3")            # Sovereign -> Galaxy
SESSIONS["phaser_range_galaxy"] = _phaser_range("all")     # Galaxy -> Sovereign (single-bank isolation fired nothing on the Galaxy; per-hit damage is per bank)
# Shield regen per face (target), each face preset to 50%, nothing firing.
SESSIONS["regen_faces"] = [dict(w="phaser", nf=1, aim="none", sh=f"{k}:0.5", d=12, g=1, s=1) for k in range(6)]
SESSIONS["regen_faces_sovereign"] = SESSIONS["regen_faces"]
# Step-4 questions (scorecard): turn stop, long turns at speed, Low intensity footprint, repair with a destroyed item.
SESSIONS["motion2"] = [
    dict(w="none", mv="yaw", mf=1, tf=1, tf2=0, t2=8, d=16, g=1, s=1, a=0, e=0, fa=1),            # yaw 8 s, then stop turning
    dict(w="none", mv="pitch", mf=1, tf=1, tf2=0, t2=8, d=16, g=1, s=1, a=0, e=0, fa=1),
    dict(w="none", mv="roll", mf=1, tf=1, tf2=0, t2=8, d=16, g=1, s=1, a=0, e=0, fa=1),
    dict(w="none", mv="impyaw", mf=1, tf=1, d=30, g=1, s=1, a=0, e=0, fa=1),                       # long full-speed turn: does the slide settle?
]
SESSIONS["motion3"] = [                 # movement never measured before (2026-10-16, Dauntless movement parity)
    dict(w="none", mv="yawpitch", mf=1, tf=1, tf2=0, t2=8, d=16, g=1, s=1, a=0, e=0, fa=1),       # diagonal turn, then stop
    dict(w="none", mv="yawroll", mf=1, tf=1, tf2=0, t2=8, d=16, g=1, s=1, a=0, e=0, fa=1),
    dict(w="none", mv="impyaw", mf=1, mf2=0.333333, t2=12, tf=1, d=24, g=1, s=1, a=0, e=0, fa=1),  # throttle down mid-turn
    dict(w="none", mv="impyaw", mf=0.333333, mf2=1, t2=12, tf=1, d=24, g=1, s=1, a=0, e=0, fa=1),  # throttle up mid-turn
    dict(w="none", mv="impyaw", mf=-0.222222, tf=1, d=16, g=1, s=1, a=0, e=0, fa=1),              # turning in reverse
    dict(w="none", mv="imppitch", mf=1, tf=1, d=20, g=1, s=1, a=0, e=0, fa=1),                    # slide in the pitch plane
    dict(w="none", mv="impyawpitch", mf=1, tf=1, d=20, g=1, s=1, a=0, e=0, fa=1),                 # diagonal turn at speed
    dict(w="none", mv="impyaw", mf=1, tf=1, tf2=0, t2=10, d=22, g=1, s=1, a=0, e=0, fa=1),         # full-speed turn, then straighten
]
SESSIONS["low_footprint"] = [dict(w="phaser", i=0, aim=a_, sh="off", d=6, g=2, s=2, a=0, e=0, chg=1, b="all")
                             for a_ in ("none", "Sensor_Array", "Shield_Generator", "Warp_Core")]
SESSIONS["repair_dead"] = [dict(w="none", sh="full", d=12, g=1, s=1, dmg="Port_Impulse/0+Sensor_Array/0.5"),
                           dict(w="none", sh="full", d=12, g=1, s=1, dmg="Sensor_Array/0.5")]
# Unmeasured-items batch (2026-10-16)
_TM = dict(w="torpedo", aim="none", sh="off", d=20, g=12, s=6, e=0, chain=0, rng=100)
SESSIONS["torp_moving"] = [            # Sovereign photons (single fire) at a Galaxy flying at the given throttle
    dict(_TM, a=90),                                  # parked target (reference)
    dict(_TM, a=90, tmv=0.5),                         # crossing at half impulse
    dict(_TM, a=90, tmv=1),                           # crossing at full impulse
    dict(_TM, a=0, tmv=1),                            # target flying at the shooter
    dict(_TM, a=180, tmv=1),                          # target flying away
    dict(_TM, a=90, tmv=1, ttf=1),                    # crossing while turning hard
    dict(_TM, a=90, tmv=1, rng=150),                  # crossing at full impulse, 150 GU
    dict(_TM, a=90, tmv=1, chain=2),                  # Quad spread at a crossing target
]
SESSIONS["batteries_flat"] = [         # Galaxy, batteries empty, everything at 125%, flying, phasers recharging
    dict(w="phaser", nf=1, aim="none", sh="full", d=60, g=1, s=1, a=0, e=0, bat=0.0, chg=0, mv="impulse", mf=1, fa=1,
         apw="+".join(f"{g_}/1.25" for g_ in ("Shields", "SensorSubsystem", "TorpedoSystem", "PhaserSystem", "ImpulseEngineSubsystem"))),
    dict(w="phaser", nf=1, aim="none", sh="full", d=60, g=1, s=1, a=0, e=0, bat=0.0, chg=0, mv="impulse", mf=1, fa=1, admg="Warp_Core/0.6",
         apw="+".join(f"{g_}/1.0" for g_ in ("Shields", "SensorSubsystem", "TorpedoSystem", "PhaserSystem", "ImpulseEngineSubsystem"))),
]
SESSIONS["torp_stock"] = [             # Sovereign: torpedo stock capped low, then a salvo; watch firing and reload
    dict(w="torpedo", tt=1, stock="1:2", aim="none", sh="off", d=50, g=12, s=2, a=0, e=0, rl=0),
    dict(w="torpedo", tt=0, stock="0:0", aim="none", sh="off", d=50, g=12, s=2, a=0, e=0, rl=0),
]
SESSIONS["torp_moving2"] = SESSIONS["torp_moving"][4:]          # the 4 shots after the target rammed the shooter
SESSIONS["torp_moving1"] = SESSIONS["torp_moving"][:3] + [dict(_TM, a=0, tmv=1, rng=150, d=12)]   # approaching: 150 GU start, 18 s window, can't reach the shooter
for _k in (3, 6):
    SESSIONS[f"coll_k{_k}_a0_full"] = [dict(w="none", mv="impulse", mf=round(_k / 9, 4), fa=0, a=0, e=0, rng=25, sh="full", d=14, g=2, s=1)]
for _k, _a, _sh in ((9, 0, "full"), (6, 90, "full"), (9, 90, "full"), (9, 0, "off")):   # one ram per fresh launch
    SESSIONS[f"coll_k{_k}_a{_a}_{_sh}"] = [dict(w="none", mv="impulse", mf=round(_k / 9, 4), fa=0, a=_a, e=0, rng=25, sh=_sh, d=14, g=2, s=1)]
SESSIONS["collisions"] = [             # Galaxy flies into a parked Sovereign from 25 GU; slowest first
    dict(w="none", mv="impulse", mf=round(k / 9, 4), fa=0, a=a_, e=0, rng=25, sh=sh_, d=14, g=2, s=1)
    for (k, a_, sh_) in ((3, 0, "full"), (6, 0, "full"), (9, 0, "full"), (6, 90, "full"), (9, 90, "full"), (9, 0, "off"))
]
# Death tests REMOVED 2026-10-16: destroying a ship inside a session crashes stbc.exe (ACCESS_VIOLATION
# 0x0044E6A9, twice, incl. the automatic retry). Death is measured from the duels instead.
# Sovereign shield-face map (Galaxy fires at the Sovereign from all around)
SESSIONS["faces_sovereign"] = SESSIONS["faces_galaxy"]
SESSION_PARAMS = {"repair": {"disable_target_weapons": 0}, "repair_order": {"disable_target_weapons": 0},
                  "faces_sovereign": {"sample_dt": 0.25},
                  # mapping sessions: hits come from CombatTap; telemetry at 4 Hz is plenty
                  "faces_galaxy": {"sample_dt": 0.25}, "incidence": {"sample_dt": 0.25},
                  "incidence_shields": {"sample_dt": 0.25}}
SESSION_SHIPS = {"motion_check": ("Galaxy", "Sovereign"), "impulse_matrix": ("Galaxy", "Sovereign"),
                 "power_budget": ("Galaxy", "Sovereign"), "torp_timing_galaxy": ("Galaxy", "Sovereign"),
                 "torp_spread_galaxy": ("Galaxy", "Sovereign"), "impulse_matrix_sovereign": ("Sovereign", "Galaxy"),
                 "torp_spread2_galaxy": ("Galaxy", "Sovereign"), "power_budget2": ("Galaxy", "Sovereign"),
                 "power_core": ("Galaxy", "Sovereign"), "faces_sovereign": ("Galaxy", "Sovereign"),
                 "torp_spread_range_galaxy": ("Galaxy", "Sovereign"),
                 "phaser_range_galaxy": ("Galaxy", "Sovereign"), "regen_faces_sovereign": ("Galaxy", "Sovereign")}


SESSION_SHIPS.update({"motion2": ("Galaxy", "Sovereign"), "motion3": ("Galaxy", "Sovereign"), "low_footprint": ("Galaxy", "Sovereign")})
SESSION_PARAMS.update({"repair_dead": {"disable_target_weapons": 0}})

SESSION_SHIPS.update({"batteries_flat": ("Galaxy", "Sovereign"), "collisions": ("Galaxy", "Sovereign")})
SESSION_SHIPS.update({n: ("Galaxy", "Sovereign") for n in SESSIONS if n.startswith("coll_")})
SESSION_PARAMS.update({n: {"sample_dt": 0.05} for n in SESSIONS if n.startswith("coll_")})
SESSION_PARAMS.update({"torp_moving2": {"sample_dt": 0.1}, "torp_moving1": {"sample_dt": 0.1}})
SESSION_PARAMS.update({"torp_moving": {"sample_dt": 0.1}, "collisions": {"sample_dt": 0.05}})

def run_session(name, attacker="Sovereign", target="Galaxy", attempts=None):
    """Run a session; if a launch dies part-way, relaunch with only the unfinished shots.
    One part -> results_mac/sweep/<name>.json is that run (plus shot_index).  Several parts ->
    {"parts": [{"shot_index": [...], "result": {...}}, ...]} so every shot keeps its own run."""
    import re
    if attempts is None:
        attempts = int(os.environ.get("SWEEP_ATTEMPTS", "3"))   # 1 = no automatic relaunch after a crash
    attacker, target = SESSION_SHIPS.get(name, (attacker, target))
    shots = SESSIONS[name]
    remaining = list(range(len(shots)))
    extra = SESSION_PARAMS.get(name, {})
    parts = []
    for attempt in range(attempts):
        p = base(attacker, target)
        p["rows"] = "abx"
        p["lockstep"] = 2
        p["weapon"] = shots[remaining[0]].get("w", "phaser")
        p.update(extra)
        p["shots"] = len(remaining)
        for j, g in enumerate(remaining):
            p["shot%02d" % j] = ",".join(f"{k}={v}" for k, v in shots[g].items())
        print(f"== session {name}: {len(remaining)} shots (attempt {attempt + 1})", flush=True)
        # Budget from the shots' own game-time (lockstep runs ~1.25-1.6x real time; allow 2x) + boot.
        game_s = sum(float(shots[g].get("d", 6)) + float(shots[g].get("g", 1)) + float(shots[g].get("s", 1)) + 3.0
                     for g in remaining)
        r = run_oracle.run(run_oracle.DEFAULT_ORACLE_DIR, p, max(120.0 + 20.0 * len(remaining), 150.0 + 2.0 * game_s), None)
        done_local = sorted(int(k.split("_shot")[1]) for k in r["boot"] if re.match(r"\d+_shot\d+$", k))
        r["shot_index"] = [remaining[j] for j in done_local]
        print(f"   done={r['done']} elapsed={r['elapsed_s']} shots {len(done_local)}/{len(remaining)} "
              f"validation: {'OK' if not r['validation'] else '; '.join(r['validation'])}", flush=True)
        parts.append({"shot_index": r["shot_index"], "result": r})
        remaining = [g for j, g in enumerate(remaining) if j not in done_local]
        # Save after every attempt, so a stopped or crashed session keeps the shots already captured.
        partial = parts[0]["result"] if len(parts) == 1 else {"parts": parts, "shots": shots}
        (OUT / f"{name}.json").write_text(json.dumps(partial))
        if not remaining:
            break
    out = parts[0]["result"] if len(parts) == 1 else {"parts": parts, "shots": shots}
    if remaining:
        print(f"   UNFINISHED shots after {attempts} attempts: {remaining}", flush=True)
    (OUT / f"{name}.json").write_text(json.dumps(out))


def plan(name):
    if name == "pilot":
        for w in ("phaserH", "photon"):
            for b in BEARINGS:
                yield f"sov_{w}_galaxy_WarpCore_{b}", "Sovereign", "Galaxy", "Warp_Core", w, b
    else:
        raise SystemExit(f"unknown sweep {name}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] in SESSIONS:
        name = sys.argv[1]
        if (OUT / f"{name}.json").exists():
            print(f"{name}: already done", flush=True)
            return
        # One instance per session across parallel bottles: atomic lock file.
        import os
        lock = OUT / f"{name}.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{run_oracle.CX_BOTTLE} {os.getpid()}".encode())
            os.close(fd)
        except FileExistsError:
            print(f"{name}: locked by another instance ({lock.read_text()}), skipping", flush=True)
            return
        try:
            run_session(name)
        finally:
            lock.unlink(missing_ok=True)
        return
    for tag, att, tgt, sub, w, b in plan(sys.argv[1] if len(sys.argv) > 1 else "pilot"):
        dst = OUT / f"{tag}.json"
        if dst.exists():
            continue
        p = base(att, tgt)
        p.update(WEAPONS[w])
        p["angle_deg"], p["elev_deg"] = BEARINGS[b]
        p["aim_sub"] = sub
        print(f"== {tag}", flush=True)
        r = run_oracle.run(run_oracle.DEFAULT_ORACLE_DIR, p, 200.0, None)
        print(f"   done={r['done']} elapsed={r['elapsed_s']} tap_lines={len(r.get('combat_tap', []))}", flush=True)
        if r["done"]:
            dst.write_text(json.dumps(r))


# Shield-face maps of flat hulls (Dauntless's hull-box face rule was validated on the Galaxy/Sovereign only)
SESSIONS["faces_keldon"] = SESSIONS["faces_galaxy"]
SESSIONS["faces_akira"] = SESSIONS["faces_galaxy"]
SESSION_SHIPS.update({"faces_keldon": ("Vorcha", "Keldon"), "faces_akira": ("Nebula", "Akira")})
SESSION_PARAMS.update({"faces_keldon": {"sample_dt": 0.25}, "faces_akira": {"sample_dt": 0.25}})


if __name__ == "__main__":
    main()


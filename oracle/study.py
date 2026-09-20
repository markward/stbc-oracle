"""Run the behaviour-bible study matrix through the oracle.

Each entry is one stbc.exe launch (~30 s).  Results land in
docs/oracle/results/<name>.json and are skipped when already present, so
the matrix can be re-run incrementally.  `--only <substring>` filters.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_oracle  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"

BASE = dict(attacker="KessokHeavy", target="Galaxy", weapon="phaser", motion="none",
            range_gu=57.0, angle_deg=0.0, elev_deg=0.0, intensity=2, charge=-1.0,
            power_wanted=-1.0, shield_face=-1, shield_frac=1.0, shields_off=0,
            settle_s=2.0, fire_at=1.0, duration=12.0, sample_dt=0.03,
            disable_target_weapons=1, rows="ab", torp_type=-1, pulse_power=-1,
            time_scale=1.0, target_alert="red", tractor_mode="hold")

MATRIX: dict[str, dict] = {
    # --- phasers: intensity table -------------------------------------------
    "phaser_high_front_57":      dict(),
    "phaser_med_front_57":       dict(intensity=1),
    "phaser_low_front_57":       dict(intensity=0),
    # --- shield state: routing to hull/subsystems ---------------------------
    "phaser_high_front_57_noshields": dict(shields_off=1),
    "phaser_high_front_57_face50":    dict(shield_face=0, shield_frac=0.5),
    "phaser_high_front_57_face25":    dict(shield_face=0, shield_frac=0.25),
    "phaser_low_front_57_noshields":  dict(intensity=0, shields_off=1),
    # --- facing geometry ----------------------------------------------------
    "phaser_high_stbd_57":       dict(angle_deg=90.0),
    "phaser_high_aft_57":        dict(angle_deg=180.0),
    "phaser_high_top_57":        dict(elev_deg=89.0),
    "phaser_high_bottom_57":     dict(elev_deg=-89.0),
    "phaser_high_stbd_57_noshields": dict(angle_deg=90.0, shields_off=1),
    "phaser_high_aft_57_noshields":  dict(angle_deg=180.0, shields_off=1),
    # --- range falloff (Kessok forward beams: MaxDamageDistance 200) --------
    "phaser_high_front_150":     dict(range_gu=150.0),
    "phaser_high_front_250":     dict(range_gu=250.0),
    "phaser_high_front_400":     dict(range_gu=400.0),
    "phaser_high_front_600":     dict(range_gu=600.0),
    # --- charge / power terms -----------------------------------------------
    "phaser_high_front_57_charge3": dict(charge=3.0),
    "phaser_high_front_57_power50": dict(power_wanted=0.5),
    # --- other weapon families ---------------------------------------------
    "pulse_warbird_front_40":            dict(attacker="Warbird", weapon="pulse", range_gu=40.0),
    "pulse_warbird_front_40_noshields":  dict(attacker="Warbird", weapon="pulse", range_gu=40.0, shields_off=1),
    "pulse_bop_front_40":                dict(attacker="BirdOfPrey", weapon="pulse", range_gu=40.0),
    "beam_warbird_front_57":             dict(attacker="Warbird", weapon="phaser"),
    "torpedo_kessok_front_57":           dict(weapon="torpedo", duration=20.0),
    "torpedo_kessok_front_57_noshields": dict(weapon="torpedo", duration=20.0, shields_off=1),
    "torpedo_sovereign_front_57":        dict(attacker="Sovereign", weapon="torpedo", duration=20.0),
    "torpedo_galaxy_front_57":           dict(attacker="Galaxy", weapon="torpedo", duration=20.0),
    # --- motion (weapon none; the attacker is the moving hull) -------------
    "motion_kessok_impulse": dict(weapon="none", motion="impulse", rows="c", range_gu=300.0, duration=20.0),
    "motion_kessok_coast":   dict(weapon="none", motion="coast", rows="c", range_gu=300.0, duration=30.0),
    "motion_kessok_yaw":     dict(weapon="none", motion="yaw", rows="c", range_gu=300.0, duration=15.0),
    "motion_kessok_pitch":   dict(weapon="none", motion="pitch", rows="c", range_gu=300.0, duration=15.0),
    "motion_kessok_roll":    dict(weapon="none", motion="roll", rows="c", range_gu=300.0, duration=15.0),
    "motion_galaxy_impulse": dict(attacker="Galaxy", weapon="none", motion="impulse", rows="c", range_gu=300.0, duration=25.0),
    "motion_galaxy_yaw":     dict(attacker="Galaxy", weapon="none", motion="yaw", rows="c", range_gu=300.0, duration=15.0),
    "motion_bop_impulse":    dict(attacker="BirdOfPrey", weapon="none", motion="impulse", rows="c", range_gu=300.0, duration=20.0),
    "motion_bop_yaw":        dict(attacker="BirdOfPrey", weapon="none", motion="yaw", rows="c", range_gu=300.0, duration=15.0),
    # --- matrix 2: the bible's open items -----------------------------------
    "phaser_high_elev45_57":  dict(elev_deg=45.0),
    "phaser_high_elev60_57":  dict(elev_deg=60.0),
    "phaser_high_elev75_57":  dict(elev_deg=75.0),
    "phaser_galaxy_front_57":    dict(attacker="Galaxy"),
    "phaser_sovereign_front_57": dict(attacker="Sovereign"),
    "torpedo_sovereign_quantum_57": dict(attacker="Sovereign", weapon="torpedo", torp_type=1, settle_s=8.0, duration=20.0),
    "torpedo_warbird_front_57":     dict(attacker="Warbird", weapon="torpedo", duration=20.0),
    "torpedo_galaxy_front_57_noshields": dict(attacker="Galaxy", weapon="torpedo", duration=20.0, shields_off=1),
    "pulse_warbird_front_40_low":  dict(attacker="Warbird", weapon="pulse", range_gu=40.0, pulse_power=0),
    "pulse_warbird_front_40_high": dict(attacker="Warbird", weapon="pulse", range_gu=40.0, pulse_power=2),
    "pulse_warbird_front_100":     dict(attacker="Warbird", weapon="pulse", range_gu=100.0),
    "pulse_warbird_front_150":     dict(attacker="Warbird", weapon="pulse", range_gu=150.0),
    "phaser_high_front_57_timescale05": dict(time_scale=0.5, duration=8.0),
    "regen_red_face50":    dict(weapon="none", shield_face=0, shield_frac=0.5, duration=20.0),
    "regen_yellow_face50": dict(weapon="none", shield_face=0, shield_frac=0.5, duration=20.0, target_alert="yellow"),
    "regen_green_face50":  dict(weapon="none", shield_face=0, shield_frac=0.5, duration=20.0, target_alert="green"),
    "ram_kessok_galaxy":  dict(weapon="none", motion="impulse", rows="abc", range_gu=30.0, duration=15.0),
    "ram_galaxy_galaxy":  dict(attacker="Galaxy", weapon="none", motion="impulse", rows="abc", range_gu=30.0, duration=15.0),
    "ram_bop_galaxy":     dict(attacker="BirdOfPrey", weapon="none", motion="impulse", rows="abc", range_gu=30.0, duration=15.0),
    "tractor_galaxy_hold": dict(attacker="Galaxy", weapon="tractor", tractor_mode="hold", rows="abc", range_gu=20.0, duration=15.0),
    "tractor_galaxy_tow":  dict(attacker="Galaxy", weapon="tractor", tractor_mode="tow", rows="abc", range_gu=20.0, duration=15.0),
    "tractor_galaxy_push": dict(attacker="Galaxy", weapon="tractor", tractor_mode="push", rows="abc", range_gu=20.0, duration=15.0),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="run only entries whose name contains this")
    ap.add_argument("--force", action="store_true", help="re-run even if a result exists")
    ap.add_argument("--oracle-dir", type=Path, default=run_oracle.DEFAULT_ORACLE_DIR)
    a = ap.parse_args(argv)
    RESULTS.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, over in MATRIX.items():
        if a.only and a.only not in name:
            continue
        out = RESULTS / f"{name}.json"
        if out.exists() and not a.force:
            print(f"skip {name} (exists)")
            continue
        params = dict(BASE)
        params.update(over)
        timeout = 60 + params["duration"] * 2
        print(f"=== {name}", flush=True)
        result = run_oracle.run(a.oracle_dir, params, timeout, None)
        result["name"] = name
        ok = result["done"] and (result["rows"] or result["motion_rows"])
        print(run_oracle.summarise(result), flush=True)
        if ok:
            out.write_text(json.dumps(result, indent=1))
            print(f"    -> {out.name}", flush=True)
        else:
            failures.append(name)
            print(f"    FAILED: done={result['done']} boot={list(result['boot'].values())[-3:]}", flush=True)
    if failures:
        print("FAILED:", failures)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

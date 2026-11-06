# Dauntless combat implementation map (2026-10-16)

This is the input for the scorecard. Every claim comes from a read-only code survey of a Dauntless checkout, citing file:line. One in-memory check built a Galaxy and dumped its live subsystem fields. Paths are relative to the dauntless repo.

## Headline: hardpoint fields are dropped for weapons and the warp core (verified live)

`ShipClass.SetupProperties` copies only `SetProperty`, `MaxCondition`, `Targetable` and the charge/reload fields onto leaf weapons (`engine/appc/ships.py:1489-1505`). The PowerProperty branch (`ships.py:1330-1346`) has the same gap.

| Subsystem (Galaxy) | Hardpoint | Live in Dauntless |
|---|---|---|
| Phaser banks, torpedo tubes, tractor emitters | r 0.20 (tube), disabled below 75%, repair complexity 3 | r 0, disabled at ≤25% (class default, `subsystems.py:355`), complexity 1 |
| Warp core | critical, r 0.4, disabled below 50%, complexity 2 | not critical, r 0, disabled at ≤25%, complexity 1 |

Group parents, sensors, shield generator, engineering, impulse/warp masters and pods are correct (`_copy_powered_subsystem_fields` `ships.py:1581-1607`).

## Per mechanic

1. **Hit point:** mesh ray trace when a renderer instance exists, else bounding-sphere entry, else the aim point. Headless, the hit is always the aim point. Phasers aim at the locked subsystem's exact centre, with no scatter (`host_loop.py:895-912`).
2. **Distribution (`combat.apply_hit` :610-898):**
   - Shields first, then the hull takes the full post-shield damage.
   - Subsystems with `d < r_sub + r_hit` take the full damage. This matches BC.
   - **Gaps:**
     - no targetability filter, so group parents and Engineering are damaged
     - hull children (the Bridge) are never splashed (`_iter_subsystems` :284-286)
     - destroyed subsystems are still offered damage
3. **Overflow:** not implemented; the excess is discarded (`objects.py:1040-1066`).
4. **Angle of incidence:** no effect (matches BC).
5. **Phasers:**
   - **Damage:** `MaxDamage × intensity(0.25/0.5/0.5) × min(1, R/dist) × dt`, delivered in pulses (on-delay 0.66 s, flush ≈0.533 s).
   - **Discharge:** 0.35/1.0/1.0 per s.
   - **Recharge:** `RechargeRate × NormalPowerPercentage × bank condition`.
   - **CanFire:** `dp < bank cond × parent cond` (product rule).
   - **Damage independent of bank condition:** ⚠️ BC scales damage with bank condition (133 → 107 at 80%).
   - **Fire gate:** 700 GU. Phasers also stop when `can_detect` fails.
6. **Torpedoes:**
   - **Launch:** straight down the tube's Direction (no lead); ±30° square fire cone; second-order guided.
   - **Reload:** `prog += NormalPowerPercentage × dt` to ReloadDelay.
   - **Ammo switch:** the SDK path unloads; ⚠️ the player UI path `CycleAmmoType` does NOT, so a player switch is free.
   - **Spreads:** ⚠️ any non-Single chain becomes a simultaneous skew fan at 0.033×Right, a deliberate deviation. BC fires pairs or fours with a 3.8° fan that steers back.
7. **Shields:**
   - **Faces:** dominant axis of the hull-box-normalised delta (raw axes headless).
   - **Regen:** `ShieldChargePerSecond × dt` every 0.5 s.
     - ⚠️ Not gated by power or the shields slider. BC: regen is linear in the Shields control.
     - ⚠️ Authored 11/s vs BC's measured 9.4/s.
   - **Absorption ramp:** matches BC (0.6 / 0.1 thresholds).
   - **Generator disabled:** faces go to 0.
8. **Disable rule:** `cond <= dp × max`, inclusive. ⚠️ BC is strict (`<`). Weapon parents are disabled only when all children are.
9. **Repair:** `MaxRepairPoints × bay cond / min(n, teams) / complexity`, FIFO, destroyed items skipped. Matches BC apart from the dropped complexities.
10. **Impulse:**
    - **Limits:** authored × `impulse_output_fraction` = mean over pods of (disabled ? 0 : cond) × slider. Matches BC.
    - ⚠️ Uses the slider value wanted, not power received, so a starved reactor still makes full speed.
    - **Throttle:** k/9.
    - ⚠️ Reverse = −0.25 × max; BC is 2/9 (−0.222).
    - **Linear ramp:** τ = 1.0.
    - ⚠️ No speed bleed while turning; BC bleeds −26%/−30% at full impulse.
    - ⚠️ 125% power is not applied for the AI.
11. **Power:**
    - **Interval:** 1 s. Output × cond fills main, then backup.
    - **Conduit budgets:** main = min(battery, MainConduit × cond × dt); backup = BackupConduit × dt.
    - **Consumers:** drawn in attach order (Torpedo → Phaser → Pulse → Tractor → Sensor → Impulse → Warp → Shield → Repair).
    - ⚠️ A shortfall only lowers weapon recharge, torpedo reload and sensor range. It does not cut shields or impulse. BC cuts shields and impulse FIRST, as all-or-nothing hand-outs 3 times a second.
12. **Sensors:** base × cond × power, 0 when offline. Matches BC.
13. **Death:** hull 0 (critical) → death, then a cascade 1.5 s later. Warp core 0 → breach → death (via the breach path, since the core's critical flag is dropped). The death splash uses a guessed linear falloff.
14. **AI:** SDK AI trees through ai_driver. Trees may sleep up to 4 ticks; avoidance runs at 4 Hz.
15. **Ticks and cadences:** 60 Hz. Shields every 0.5 s, power every 1 s, phaser pulse ≈0.533 s, torpedo stagger 0.5 s.

## Test infrastructure

- **Location:** `tests/oracle/` (`conftest.py` `oracle` fixture → `OracleScene`; strict xfails via `bible_xfail`).
- **Setup:**
  - headless QuickBattleRegion
  - `loadspacehelper.CreateShip`
  - ships placed by SetTranslateXYZ / AlignToVectors
  - red alert
- **Stepping:** `loop.tick(); host_loop._advance_weapons; host_loop._advance_combat; collisions.tick_collisions`.
- **Helpers:**
  - `s.fire(kind, intensity)`
  - `s.sample_until`
  - `s.preset_face`
  - `s.zero_shields`
  - `s.speed_of`
  - `s.turn_rate_of`
  - `s.torpedoes_in_flight`
- **Run:** `uv run pytest tests/oracle -q`
- **Headless limits:**
  - no hull mesh, so hits land exactly at the aim point
  - shield faces are chosen by raw axes
  - the footprint can't be tested without `./build/dauntless`

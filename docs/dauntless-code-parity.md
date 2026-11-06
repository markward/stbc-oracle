# Dauntless code parity: Galaxy and Sovereign combat (2026-10-16)

For each rule in `docs/mechanics-reference-galaxy-sovereign.md` (provisional until its captures are in `docs/results/`): what the original game does (measured), where Dauntless implements it, what that code computes, and the scorecard checks (`scorecard/results.jsonl` ids) that confirm the verdict by simulation.

- **Paths:** relative to the Dauntless repo root. Line numbers are as of 2026-10-16 (uncommitted tree).
- **Verdicts:**
  - ✅ same
  - ≈ close
  - ❌ different
  - ⛔ not implemented

## Ship data

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Every subsystem keeps its hardpoint DisabledPercentage, Radius, RepairComplexity, Critical | `ShipClass.SetupProperties` `engine/appc/ships.py:1195`. The leaf-weapon pass copies only MaxCondition, Targetable and charge/reload fields; the Power branch has the same gap. Defaults: `subsystems.py:355` `_disabled_percentage = 0.25`, radius 0, complexity 1, critical 0 | ❌ for all 19 phaser banks, torpedo tubes, tractors and the warp core per ship | P-*, P2-*-DisabledPercentage/Radius/RepairComplexity/IsCritical |
| All other authored values (HP, positions, weapon stats, ranges, engine, power plant, sensors, repair) | Copied correctly | ✅ (36 of 40 property types) | P2-* |
| Phaser and tube arcs | `PhaserBank.CanHit` `weapon_subsystems.py:2467` (+ `_emitter_in_arc` :163); tubes `_in_torpedo_cone` :2792 (±30° square) | ✅ 99.8% / 100% of the game's own arc maps | A-* |
| `CanHit` has no range limit (BC answers the same at 150 GU as at 50 GU) | Dauntless returns 0 beyond MaxDamageDistance (`weapon_subsystems.py:2467`), so its AI won't fire phasers beyond 60/70 GU | ❌ 88–91% agreement at 150 GU: every in-arc direction disagrees | A-*-r150 |

## Hits and damage

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Hull takes the full post-shield damage | `combat.apply_hit` `engine/appc/combat.py:610` | ✅ | H2 |
| Every targetable subsystem with `d < r_sub + r_weapon` takes the full damage | `apply_hit` subsystem walk over `_iter_subsystems` `combat.py:268` | ≈ the rule is right; results are wrong wherever the radius was dropped (tubes, warp core) | H1 (44% / 83% identical sets), H2 (amounts 100%) |
| Untargetable subsystems (group parents, Engineering) are never damaged | No targetability filter in `apply_hit` | ❌ the Tractors / Phasers / Torpedoes / Warp Engines groups are damaged in replays | H1, D2 |
| The Bridge (hull child) is damaged like any subsystem | `_iter_subsystems` skips the hull's children (`combat.py:284-286`) | ❌ the Bridge can never be damaged | D3, H1 |
| Overflow: excess beyond a destroyed subsystem re-applied as a new hit | `DamageableObject.DamageSystem` `objects.py:1040` clamps at 0 and discards the excess | ⛔ | D1 |
| Angle of incidence has no effect on damage | No incidence term | ✅ | — |
| Impact point = first hull surface on the shot's path | Mesh ray trace with a renderer instance; headless = aim point | ✅ in the full game (renderer); not testable headless | — |

## Phasers

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Damage rate in range (about 133/s per Sovereign bank) | `_phaser_damage_for_tick` `host_loop.py:827`: MaxDamage × intensity × dt | ✅ | W1 |
| Range falloff × MaxDamageDistance / range | Same function: `MaxDamage × R/dist` beyond R | ✅ | PR1 |
| Damage scales with bank condition | Not scaled | ❌ | W2 |
| Low intensity: half damage; hull spared only when the footprint holds a subsystem (6 samples) | `PHASER_INTENSITY_SCALE = (0.25, 0.5, 0.5)` `host_loop.py:824`; Low → `damage_hull=False` always | ✅ half damage and hull spared over a subsystem; ❌ the hull is never damaged when no subsystem is in the footprint | PR2, PR3 |
| Recharge = 0.08 × Weapons power × bank condition | `UpdateCharge` `weapon_subsystems.py:810` | ✅ | W3-100, W3-80 |
| Weapons power doesn't change damage | — | ✅ | M12 |
| Wind-up (bank IsFiring to first damage) 1.10–1.16 s on the Sovereign (raw rows, 6 runs; corrected from 0.55–0.60) | `BEAM_ON_DELAY_S = 0.66` + first 0.5 s dwell flush = 1.15 s | ✅ | M5 |
| Pulse interval 0.50–0.52 s | Dwell flush ≈ 0.533 s | ≈ | M6 |
| Firing time from a full bank (High) 5.3–5.5 s; Low discharge ≈ 0.34/s | Discharge 1.0/s (High), 0.35/s (Low) | ≈ / ✅ | M7, M8 |
| A disabled Phasers group stops all banks | CanFire uses the product `bank cond × parent cond > dp` (dp wrongly 0.25) | ❌ (scripted damage only; parents are never damaged in combat) | M15 |

## Torpedoes

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Damage per type (500 / 550 / 900), stocks 250 / 200 + 60 | Projectile scripts' `GetDamage`; ammo `GetAvailable` | ✅ | W4-*, M9-* |
| Reload 40 s / Weapons power; tube condition no effect | `UpdateReload` (prog += NormalPowerPercentage × dt) | ✅ | W5-*, M33 |
| Any type switch empties all tubes and restarts every reload | Script path `SetAmmoType` unloads ✅; player UI `CycleAmmoType` `weapon_subsystems.py:1878` does **not** | ✅ script / ❌ player | W6, M11 |
| Spread: Dual = pairs 0.65 s apart, Quad = 4 at once, 3.8° fan steering back | `TorpedoSystem.SetFiringChainMode` `weapon_subsystems.py:1949` → simultaneous skew fan | ≈ Dual pairs 0.31 s apart; Quad ✅; fan 2.9° | T1-*, M36 |
| Flight time (photon 3.0 s, quantum 2.6–2.8 s at 57 GU) | Launch speed from the script + guidance | ≈ (headless impact is early by design) | M10-* |

## Shields

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Face strengths | `GetMaxShields` | ✅ | M30-* |
| Face selection: dominant axis of the bubble entry, hull-box normalised | `_shield_face_from_hit_point` `combat.py:485`, `shield_bubble_entry` :403 | ≈ 91–92% of the game's 266-direction maps (differences on the ±15° boundary bands; hull box estimated from game samples) | F1-* |
| Pass-through ramp (0 at ≥60%, linear to 0.6 at 10%, all below 10%) | `ShieldClass.ApplyDamage` `subsystems.py:2064` | ✅ | S2-* |
| Regen ≈ 0.84 × authored ChargePerSecond × Shields power | `Update` adds the authored `_charge_per_second × dt` every 0.5 s (`subsystems.py:2016-2050`); no power term | ❌ 11.37 vs 9.44 (Galaxy), 12.40 vs 10.10 (Sovereign); Shields power ignored | S1-*, M31 |
| Shields power doesn't change absorption | — | ✅ | M13 |
| Generator below 75% → all faces 0; recovery from 0 | — | ✅ | S3, M14 |
| Generator at 80–90% regenerates fully | — | ✅ | M32 |

## Thresholds, repair, death

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Disabled iff condition **<** threshold (strict) | `IsDisabled` `subsystems.py:1103` uses `<=` | ❌ off by one value: exactly at the threshold Dauntless says disabled. A pod at exactly 50% counts 0 instead of 0.5. | S4-*, E1 (pods 100/75/50) |
| Repair = 50 × bay condition / min(n, 3) / complexity; FIFO; destroyed items skipped and not counted; repair power no effect | `RepairSubsystem.Update` `subsystems.py:2600-2640` | ✅ formula; ❌ results for weapons and the warp core (complexity dropped to 1) | R1-*, M17–M19 |
| Death: hull 0 or warp core destroyed | Hull → `ship_death.begin`; core → breach path | ✅ | D4-* |
| Group parents zero at the death instant | Cascade 1.5 s after death destroys every subsystem | ✅ at the instant of death | M22 |

## Engines and movement

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Top speed / acceleration cap / turn rate = max × Engines power × pod factor | `impulse_output_fraction` `subsystems.py:163`, `_effective_motion` `ship_motion.py:91` | ✅ except 125% on the AI/script path and the pod exactly at 50% | E1-*, M1–M3 |
| Throttle k/9; reverse 2/9 | Player `REVERSE_FRACTION = 0.25` `host_loop.py:2623` | ✅ / ❌ reverse | E5 |
| Acceleration curve (t50 / t90 per level) | `_asymptote_step` `ship_motion.py:149` (τ = 1.0) | ✅ exact at levels 1/5/9, both paths | MV3-* |
| Deceleration 9 → 0 in 10.8 s; 9 → reverse 8.75 s | Same asymptote | ❌ 6.35 s; 7.3 / 6.1 s | MV4-* |
| Turn ramp eases in (t90 2.75 s, t99 5.05 s), same for yaw, pitch and roll; stopping mirrors it (99% in 5.1 s) | `_ramp_toward` at MaxAngularAccel, linear (helm `host_loop.py:2868+`, AI `ship_motion`) | ❌ t90 2.10 s, full at 2.32 s; stop in 2.32 s | MV1-*, MV2-* |
| Turning bleeds speed (−26% at full impulse) | Velocity = nose × speed every tick | ⛔ | MV5-*, E4 |
| Course lags the nose while turning (16° at half impulse; at full: 22° after 9 s, settling at 32°, speed settling at 85%) | Same: velocity locked to the nose | ⛔ | MV6-*, MV7-* |
| Player turning through the SDK's `SetTargetAngularVelocityFraction` | Not implemented; Dauntless's own `_PlayerControl` | ⛔ (replaced) | — |

## Power

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Core fills main; draw capped by the main conduit (× core condition), then backup ≤ 200/s | `PowerSubsystem` interval `subsystems.py:2289+`, `_pump_consumers` :2405 | ✅ healthy core; ❌ damaged core (backup −200 vs −118 at core 60%) | PW1-*, M35 |
| A disabled core still produces output × condition | (Dauntless's core isn't even disabled at 49%: threshold 0.25) | ✅ result, for the wrong reason | M20 |
| Brownout cuts shields and impulse first, all-or-nothing, 3 hand-outs per second | Consumers in attach order; a shortfall only slows weapon recharge, torpedo reload and sensor range | ❌ | PW2, PW3 |
| Tractor drain ≈ −650/s | Tractor draws directly from main | ✅ | M21 |
| Sensor range = base × power × condition, 0 below 50% | `effective_sensor_range` `sensor_detection.py:226` | ✅ | M4-* |

## Whole fights

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Sovereign wins every duel with 96–100% hull | AI vs AI headless | ≈ Sovereign wins 8/8, but with 64–96% hull | X1-* |

## Intercept (in-system warp)

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Steps to exactly 75 GU/s; duration = distance / 75 | `ShipClass.InSystemWarp` `ships.py:722`; `IN_SYSTEM_WARP_SPEED_GUPS = 400.0` `ships.py:715` | ❌ 400 GU/s (5.3×); 1.35 s instead of 7.2 s from 600 GU | I1, I2 |
| Drops out at about the stop distance (asked 50 → 54–61 GU) | `warp_flight` drop distance | ✅ 53 GU | I3 |
| Exit speed = top impulse speed, whatever the pre-warp speed | `exit_policy="keep_pre_warp"` `ships.py:786`, `warp_flight._finish` :295 | ❌ 0 from rest; keeps 3.5 when entered at impulse 5 | I4, I5 |
| Engages with both nacelles disabled | No nacelle gate | ✅ | I6 |
| (Dauntless only) Facing gate: nose within ~10° of the target before engaging | `IN_SYSTEM_WARP_FACING_COS = 0.985` `ships.py:720` | not measured in BC (the oracle's ship always faced the target) | — |

## Torpedoes against moving targets

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Torpedoes chase a target flying straight away (4/4) but miss one crossing at half or full impulse at 100 GU (0/8, 0/5) | `projectiles._guide` (second-order lead, turn budget decaying over GuidanceLifetime) | ✅ except 1/4 hits on a half-impulse crossing target (headless hit sphere is generous) | TM-* |

## Collisions (lowest priority)

| Rule (BC) | Dauntless | Verdict | Checks |
|---|---|---|---|
| Each contact damages both ships, radius 1.5 GU, linear in impact speed (≈ 490 + 990 v / 490 + 820 v), rammed ship ≈ 1.16× the rammer | `collisions._ke_damage` `collisions.py:331`: `COLLISION_DAMAGE_COEFF (5.0) × ½ × reduced mass × v²`, equal to both | ❌ 601 vs 2562 at 2.1 GU/s; 5008 vs 6505 at 6.1 GU/s | C1-* |
| Shields absorb no collision damage | `collisions.py:608/615` `bypass_shields=not shielded` (shields absorb when up) | ✅ headless (no bubble), ❌ with the renderer | C2-* |

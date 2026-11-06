# Bridge Commander combat mechanics: Galaxy and Sovereign

> **Provisional: not yet verifiable from this repo.** The captures behind these numbers are not in `docs/results/` yet; they are kept locally (`results_mac/`, `results_win/`). Until they are added, treat every number here as unverified, and don't cite it the way the bible's numbers are cited. The ✅ marks below mean measured on the original, not checkable here.

**Status:** v1.2 (2026-10-16 02:30), provisional (see above). All planned measurements for the Galaxy and Sovereign are in. Items marked ❓ are open questions, not pending runs.

**Source:** the original game (`stbc.exe`, GOG 1.1), measured by the stbc-oracle harness on CrossOver.
- Lockstep mode 2 gives exact 60 Hz steps and deterministic results.
- CombatTap records every hit inside the engine.
- Full per-ship telemetry is recorded.
- The raw captures are kept locally (results_mac/, results_win/), not in this repo; some sections name the run they rest on. A curated set will be added under docs/results/, and this note removed then.

**Legend:**
- ✅ measured on the original (exact unless a tolerance is given); not yet backed by a capture in docs/results/
- ❓ open question

**Units:**
- 1 GU = 175 m; speeds are in GU/s.
- Angles in the appendix tables are in degrees (the game stores radians).
- "Condition" = current HP / max HP.

---

## 1. How a hit does damage

### 1.1 Where a shot lands ✅
- A weapon aims at a point (the targeted subsystem, or the ship), but the shot **hits the first hull surface on its path**.
  - Aiming at an internal or far-side subsystem only sets the direction.
  - Example: the Galaxy warp core cannot be hit by a level shot from the front; it is reachable from about 60° above or below.
- The impact point is predictable from the firing bank's position with the game's own ray test (LineCollides): within 0.004–0.010 GU in 5 of 6 test directions.
- **Pass-through zones exist.** On the Galaxy underside (from 60° below) the beam passes through the lower hull and lands on the upper engineering hull (exit side). So from below, the subsystems near the TOP of the engineering hull take the damage.

### 1.2 What a hit damages: the footprint rule ✅ (267/267 hit events)
- The **hull always takes the full damage**.
- **Every targetable subsystem** whose sphere overlaps the hit sphere also takes the **full** damage: `|impact − subsystem centre| < subsystem radius + weapon damage radius`.
- Example: a 550 photon on the Galaxy's front damaged the sensor array and all 4 forward tubes by 550 each.
- **No falloff** inside the footprint: a subsystem 0.09 GU away and one 0.25 GU away take the same damage.
- **Untargetable subsystems are never damaged by weapons:** the group parents (Phasers, Torpedoes, Tractors, Impulse_Engines, Warp_Engines) and Engineering/Repair.
- **Angle of incidence has NO effect on damage.** Phaser per-hit damage stayed at 64.7–67.4 for incidence 0–73°; torpedoes did 550 at every angle.
- The angle matters only through (a) which shield face takes the hit (§2.1) and (b) where the shot lands, which decides what lies in the footprint.

### 1.3 Overflow ✅
- When a hit destroys a subsystem, the damage beyond that subsystem's remaining HP **re-applies as a new hit** from the same projectile:
  - damage = summed excess
  - radius = original radius × (excess / original damage)
- It mostly lands on the hull.
- Proven case: a 900 quantum destroyed 2 aft tubes and the centre impulse pod (excess 292.67 + 292.67 + 100 = 685.33), and a 685.33 hit followed on the hull.
- This is general to any weapon, not quantum-specific.

### 1.4 Randomness ✅
- Torpedo damage is exact on every hit (Galaxy photon 500; Sovereign photon 550, quantum 900).
- Phaser per-hit damage is deterministic under lockstep. Variation between normal (non-lockstep) runs comes from frame timing and random bank start delays, not from a damage roll.
- **Duels are not deterministic** (AI choices); see §8.

### 1.5 Phasers ✅
- **Damage per firing-second, one bank at full condition, in range:** about 133 /s (Sovereign bank on the Galaxy, shields off; about 65–68 per hit).
- **Range doesn't gate firing:** the game's own `PhaserBank.CanHit` says yes at 150 GU exactly as at 50 GU (the same arc points). Banks fire at any range inside their arc, with damage reduced by the falloff below. So the AI opens fire from far beyond the full-damage distance.
- **Range falloff:** full damage out to the bank's MaxDamageDistance, then **damage × MaxDamageDistance / range**. MaxDamageDistance is 70 GU for the Sovereign's banks and 60 GU for the Galaxy's (catalogue).

  | Range (GU) | 30 | 57 | 70 | 90 | 120 | 150 | 200 | 300 |
  |---|---|---|---|---|---|---|---|---|
  | Sovereign bank, measured /s | 133 | 134 | 133 | 106 | 80 | 63 | 47 | 31 |
  | 133 × min(1, 70 / range) | 133 | 133 | 133 | 104 | 78 | 62 | 47 | 31 |

  Galaxy banks (all banks firing, damage per hit):

  | Range (GU) | 30 | 57 | 70 | 90 | 120 | 150 | 200 | 300 |
  |---|---|---|---|---|---|---|---|---|
  | Galaxy, measured per hit | 62.5 | 62.5 | 58.3 | 43.3 | 33.2 | 25.6 | 19.7 | 13.1 |
  | 62.5 × min(1, 60 / range) | 62.5 | 62.5 | 53.6 | 41.7 | 31.3 | 25.0 | 18.8 | 12.5 |

  All eight Galaxy banks have MaxDamageDistance 60 (hardpoint). The measured values sit 3–9% above the centre-to-centre prediction because the game measures range from the firing bank to the impact point, which is a few GU shorter than the ships' centre spacing. The Sovereign data fits the same way (effective distance about 2–3 GU less than the set range).
- **Intensity (the phaser power level; the UI offers Low and High):**
  - **High:** full damage.
  - **Low:** **half** damage per hit (34 vs 66), and the beam fires longer (7.9 s vs 5.4 s from a full bank).
  - **Low spares the hull whenever the hit covers a subsystem.** Sovereign → Galaxy front (footprint covering the sensor array and 4 tubes): hull 0, while the sensor array took −406 and the tubes −501 to −549. Galaxy → Sovereign front (no subsystem in the footprint): the hull took the half-strength hits (−317 vs −680 at High). Confirmed over 6 samples (4 more aimed at the Sovereign: two footprints holding a tractor projector spared the hull; two with no subsystem damaged it, −225 and −224). The rule: at Low, damage goes to the subsystems in the footprint, and to the hull only when there are none. It's a "disable, don't destroy" setting; the AI uses it when it wants to disable a ship.
  - The engine also has a Medium setting that nothing uses; it deals the same damage as High.
- **Damage scales with bank condition:** 133.4 → 120.7 (90%) → 106.5 (80%) per second.
- **Beam timing:** a bank that starts firing deals its first damage 1.10–1.16 s later (6 Sovereign runs), then one pulse about every 0.5 s (0.50–0.52 s at the capture's frame rate). A full Sovereign bank (charge 5) fires for about 5.4 s at High.
- The Weapons power control does **not** change damage or firing duration.
- **Hull damage from phasers is batched:** hits that pass through shields queue up, and one distribution call applies the sum.

### 1.6 Torpedoes ✅
Each ship's torpedo types come from its hardpoint file, and their stats from `Tactical/Projectiles/*.py`. Measured damage matches exactly.

| | Galaxy | Sovereign |
|---|---|---|
| Photon | PhotonTorpedo: **500** damage, launch speed 19 | PhotonTorpedo2: **550** damage, launch speed 19 |
| Quantum | none | QuantumTorpedo: **900** damage, launch speed 22 |
| Third slot | none | Phased Plasma (1900) with **0 carried**, so unusable |
| Stock carried | 250 photons | 200 photons + **60 quantums** |

- The two ships' photons are different torpedo types; the Galaxy's does 500, the Sovereign's 550.
- Quantum torpedoes are faster (arrival 2.6–2.8 s vs 3.0 s at 57 GU).
- ❓ What happens when the stock runs out (60 quantums last the Sovereign about 10 full salvos) has not been measured.

---

## 2. Shields

### 2.1 Which face takes a hit ✅ (both ships, 266 directions each)
- **Six faces:** front, rear, top, bottom, left (port), right (starboard).
- The face is chosen by the direction the shot arrives from, relative to the ship's hull box (not by 45° cones). BC hulls are long and flat, so **top and bottom cover most of the sphere**.
- Both ships share the same pattern. Bearing is measured from dead ahead, increasing to starboard; elevation is positive above.

| Elevation of the shooter | Galaxy | Sovereign |
|---|---|---|
| +30° and above | top | top |
| +15° | top 0–30° and 330–345°; right 45–120°; rear 135–225°; left 240–315° | top 0–30°, 150–210° and 330–345°; right 45–135°; left 225–315° |
| level (0°) | front 0–15° and 345°; right 30–120°; rear 135–225°; left 240–330° | front 0–15° and 345°; right 30–150°; rear 165–195°; left 210–330° |
| −15° and below | bottom | bottom |

- **Consequence:** only a shooter within about 15° of level can reach the front, rear or side faces. In real fights the **top and bottom faces take most hits**, which is where the Sovereign (11000) and the Galaxy (4000) differ most.
- The front face covers only about ±15° around dead ahead, and the Sovereign's rear face only about ±15° around dead astern.

### 2.2 Face strengths ✅

| Face | Galaxy | Sovereign |
|---|---|---|
| Front | 8000 | 11000 |
| Rear | 4000 | 5500 |
| Top | 4000 | 11000 |
| Bottom | 4000 | 11000 |
| Left | 4000 | 5500 |
| Right | 4000 | 5500 |

### 2.3 How much gets through (pass-through ramp) ✅
Let `f` be the face's current fraction of its maximum. The share of each hit that passes through to the hull and subsystems is:
- `f ≥ 0.6`: **0** (the face absorbs everything)
- `0.1 < f < 0.6`: `0.6 × (1 − 2(f − 0.1))`, rising linearly to 0.6
- `f ≤ 0.1`: **1.0**

So a face must be worn below 60% before anything leaks. Shields power does **not** change absorption, even at 0%.

### 2.4 Regeneration ✅
- **Regen = 9.44/s × Shields power** (Galaxy front face), exactly linear: 0 / 2.38 / 4.72 / 7.12 / 9.44 / 11.85 at 0 / 25 / 50 / 75 / 100 / 125%.
- A shield generator above its 75% threshold regenerates at the full rate, even at 80–90% condition. It is all-or-nothing.
- **Every face regenerates at about the same rate, whatever its size** (Shields 100%, each face preset to 50%):

  | | Front | Rear | Top | Bottom | Left | Right |
  |---|---|---|---|---|---|---|
  | Galaxy /s | 9.26 | 9.25 | 9.25 | 9.29 | 9.77 | 9.25 |
  | Sovereign /s | 10.67 | 10.10 | 10.10 | 10.14 | 10.10 | 10.10 |

  So a 4000 face refills from empty in about 7 minutes, and an 11000 face in about 18. ❓ What sets the per-ship rate is not identified (the Sovereign's generator draws 450 vs 400).
- **Note:** the original stbc-oracle notes say regen is unaffected at 50% power. Its own capture shows the 50% setting never took effect, so that note is believed wrong.

### 2.5 Shield generator loss ✅
- The generator below **75%** condition sets **all six faces to 0 instantly**.
- When repaired back above 75%, the faces regenerate **from 0**.

---

## 3. Subsystem thresholds and what disabling does ✅

- **Rule:** a subsystem is disabled when `condition < DisabledPercentage` (strict). For example, 75.0% still works and 74.9% is disabled.
- It re-enables immediately when repaired above the threshold.
- Destroyed means condition 0.

| Subsystem | Disabled below | Effect when disabled |
|---|---|---|
| Phaser bank / torpedo tube / tractor | 75% | cannot fire |
| Shield generator | 75% | all faces 0; on recovery they regenerate from 0 |
| Sensor array | 50% | sensor range 0 |
| Impulse pod | 50% | contributes 0 to the engine total (§5.2) |
| Warp core | 50% | flagged disabled, but still produces output × condition (§6) |
| Warp nacelles | 50% | no impulse, turn, power or sensor effect, and in-system warp (intercept) still engages (§10) |
| Engineering / Repair | 10% (Galaxy), 1% (Sovereign) | repair stops |
| Hull, Bridge | never | Hull at 0 destroys the ship in combat (§7). Setting it by script does not. |

- **Partly damaged but still working** (above the threshold):
  - phaser damage and recharge scale with condition
  - torpedo tube reload is unaffected (40 s at 80%)
  - shield regen is unaffected

---

## 4. Repair ✅

- **Rate per item** = `MaxRepairPoints (50) × repair-system condition / min(items being repaired, 3 teams) / item repair complexity`.
  - Measured: sensor 16.9/s (formula 16.7), tube 5.6/s (5.56).
- **Teams:** 3. At most 3 items are repaired at once; the rest wait.
- **Queue order:** first damaged, first repaired. When an item finishes, the longest-waiting item takes the free team immediately.
- **Destroyed items (condition 0) are skipped**; they are never repaired in combat, take no team and don't slow the others (a damaged sensor array repaired at the same 50/s with a destroyed impulse pod in the list).
- The repair power setting has **no effect**.

---

## 5. Engines and manoeuvring

### 5.1 Limits ✅

| | Galaxy | Sovereign |
|---|---|---|
| Max speed | 6.3 | 7.5 |
| Max acceleration | 1.5 | 1.6 |
| Max turn rate (rad/s), yaw = pitch = roll | 0.28 | 0.30 |
| Max angular acceleration | 0.12 | 0.15 |
| Impulse pods | 3 | 2 |

### 5.2 Formulas ✅ (exact)
- **Top speed / acceleration cap / turn rate** = max value × Engines power × pod factor.
  - The pod factor is the average of the pods' conditions, with a pod counted as 0 once it is below 50%.
  - Galaxy: 1 pod disabled → 2/3; 2 pods → 1/3; all three → 0.
  - Sovereign: 1 pod disabled → 1/2; both → 0.
  - A pod at 51% counts as 0.51.
- **Throttle:** keys 1..9 give k/9 of top speed; 0 = stop; R = reverse at 2/9; +/− = ±1/9.
- **Speed at level k** = (k/9) × max speed × Engines power × pod factor.
- **One law for all motion** ✅ (fits all 184 recorded flights over their whole curves): every rate changes as **dv/dt = (target − v) / 1 s, capped at the acceleration limit**. Large changes therefore ramp linearly at the cap, then close the last gap exponentially (about 0.7 s to 50% for small steps). Deceleration and reverse use the same law.
  - It acts on the **velocity vector**, not just speed: in a turn the target direction (the nose) moves away and the course lags it. That one law gives the slide angles and the turn speed loss below.
  - It acts on the **turn-rate vector** too: holding two turn keys (a diagonal) turns at 0.707 of the rate on each axis, and the total rate eases in exactly like a single axis (measured 2026-10-16, `motion3`).
  - Time to 90% of the target speed is the same at every power level:

  | Level | Galaxy | Sovereign |
  |---|---|---|
  | 1 | 2.3 s | 2.3 s |
  | 5 | 2.8 s | 3.0 s |
  | 9 | 4.1 s | 4.45 s |

- **Turn rate does not depend on speed.**
- **Turn ramp (yaw, pitch and roll identical, at every power level):** the ship eases into a turn. It reaches 50% of the turn rate at 1.15 s, 90% at 2.75 s and 99% at 5.05 s. **Stopping a turn mirrors this:** half the rate gone in 1.18 s, 90% in 2.8 s, 99% in 5.1 s.
- **Turning slides the ship:** its course lags the nose. Turning from rest at half impulse, the lag settles at about 16°. In a full-speed turn it grows to 22° after 9 s and settles at about **32°** after roughly 25 s, while speed settles at 5.36 (85% of full).
- **Deceleration:** throttle 9 → stop is within 1% of the target after 6.4 s; 9 → reverse after 7.25 s (to within 0.001 GU/s: about 10.8 / 8.75 s).
- **Turning bleeds forward speed** (impulse + full yaw from rest): the Galaxy peaks at 5.98 at 7 s and settles at 5.36 (level 9); level 6 settles at 4.05 and level 3 at 2.02. The Sovereign peaks at 6.63 and is at 5.90 after 13 s. (An earlier "−26% / −30%" figure was not in the raw curves.)
- **Throttle changes mid-turn, turning in reverse, pitching at speed and straightening out after a turn** all follow the same law (measured 2026-10-16, `motion3`).

---

## 6. Power ✅

### 6.1 Plant ✅

| | Galaxy | Sovereign |
|---|---|---|
| Warp core output | 1000 | 1200 |
| Main battery | 250000 | 200000 |
| Backup battery | 80000 | 100000 |
| Main conduit | 1200 | 1450 |
| Backup conduit | 200 | 250 |

- **Core output** = PowerOutput × core condition. The output is NOT zeroed when the core is disabled: 490 at 49%.
- **Max power the ship can draw per second** = `MainConduitCapacity × core condition + BackupConduitCapacity`.
  - Galaxy measured 1400 / 920 / 788 / 560 at core 100 / 60 / 49 / 30%, exact.
  - So **warp-core damage limits how much power can be pulled at all**, not just the output.
  - Sovereign by the same formula: 1450 × condition + 250 (formula prediction; the Sovereign was not measured).

### 6.2 Normal draw per system (catalogue NormalPowerPerSecond) ✅

| System | Galaxy | Sovereign |
|---|---|---|
| Shields | 400 | 450 |
| Phasers | 300 | 400 |
| Impulse | 150 | 200 |
| Sensors | 100 | 150 |
| Torpedoes | 100 | 150 |
| Tractors (when firing) | 600 | 700 |
| Total at 100% (no tractors) | 1050 | 1350 |

### 6.3 Engineering controls ✅
The player has 4 controls, in 25% keyboard steps from 0 to 125%:
- **Weapons:** phasers + torpedoes + pulse
- **Engines:** impulse + warp
- **Sensors**
- **Shields**

| Control | Changes | Does NOT change |
|---|---|---|
| Engines | top speed, acceleration cap, turn rate (linear) | |
| Weapons | phaser recharge and torpedo reload, linear in power | damage, firing duration, torpedo damage |
| Shields | regen (linear) | absorption |
| Sensors | range (linear) | |
| Repair (not a player control) | nothing | |

- ❓ Mouse-drag granularity of the controls is unverified.

### 6.4 Batteries and over-draw ✅ (power budget v2, Galaxy, batteries starting at 50%)
**Model (healthy core):**
- The warp core **fills the main battery** at its output (Galaxy 1000/s).
- Systems draw from the main battery **through the main conduit, capped at 1200/s**.
- Demand above that comes from the **backup battery, capped at 200/s** (the backup conduit).
- Demand = Σ per-system normal draw × control level. Galaxy at 100% = 1050/s with phasers recharging; full banks draw only a trickle.

| Controls | Demand /s | Predicted main / backup | Measured main / backup |
|---|---|---|---|
| 50% | 525 | +475 / 0 | +479 / 0 |
| 75% | 788 | +212 / 0 | +208 / 0 |
| 90% | 945 | +55 / 0 | +60 / −2 |
| 100% | 1050 | −50 / 0 | −42 / −5 |
| 110% | 1155 | −155 / 0 | −143 / −3 |
| 115% | 1208 | −200 / −8 | −199 / −6 |
| 120% | 1260 | −200 / −60 | −203 / −53 |
| 125% | 1313 | −200 / −113 | −197 / −104 |

- So the **Galaxy breaks even at about 95% on all controls**. Above that the main battery (250000) drains at up to 200/s, after which the backup (80000) carries the excess up to 200/s.
- No system went short in these runs (≤1% of hand-outs) while the batteries held.
- **Tractor beam firing** drains the main battery at about **−650/s** (100% controls + tractor) and does NOT spill to the backup. ❓ It seems to bypass the conduit cap.
- Sovereign by the same model: core 1200/s, main conduit 1450, backup conduit 250, demand 1350 at 100%, so it would break even at about 89%. This is a formula prediction; the Sovereign was not measured.
- **Damaged core:** the drains are larger than this model predicts (main −118 / −591 / −362 /s at core 60 / 49 / 30%), and systems brown out (below).

- **Batteries empty** ✅ (Galaxy, flying, phasers recharging): nothing shuts down outright; the ship runs on the core's output and the same rule applies.
  - Core 100%, everything at 125% (demand ≈ 1313 vs 1000): shields and impulse miss 1 hand-out in 3; sensors and torpedoes are always served; speed averages 95% of top.
  - Core 60%, everything at 100% (demand ≈ 1050 vs 600): shields get their full share 1 hand-out in 3, impulse misses 2 in 3, sensors and torpedoes miss 1 in 3; speed averages 89%.
- **Which systems go short first** ✅ (Galaxy, everything at 100%, batteries at half). Power is handed out 3 times a second. In each hand-out a system gets its full share or nothing, and the biggest consumers are cut first:

  | Core | Shields | Impulse | Sensors | Torpedoes | Phasers (topping up) |
  |---|---|---|---|---|---|
  | 100% | always | always | always | always | 5.0 per hand-out |
  | 60% / 49% | miss 1 in 3 | miss 1 in 3 | ~always | ~always | 4.7 / 3.8 |
  | 30% | miss 2 in 3 | miss 2 in 3 | miss 1 in 3 | miss 1 in 3 | 3.0 |

- **How the hand-outs work** ✅ (per-system rows, `power_core`, `batteries_flat`): each second's budget (main conduit × core condition + backup conduit, limited by the batteries) is spent in time order until it runs out.
  - Phasers (and other energy weapons) take their share every frame, all-or-nothing (5 a frame while recharging).
  - The other systems are served 3 times a second in two groups, each group fed or starved together: sensors + torpedoes at the budget reset, **shields + impulse 5 frames later**. Shields and impulse are always fed or starved together, even when impulse's small share would still fit.
  - This reproduces the fed fractions above at every core level, and the same pattern with the batteries empty.
- **A starved engine coasts**: it is never switched off. In a missed hand-out the ship gets no thrust and holds its speed, then accelerates again on the next fed one, so it climbs in a stop-start staircase (core 30%: 2.57 / 4.94 / 6.04 / 6.25 at 5 / 10 / 15 / 20 s). Turning stutters the same way. A starved shield generator doesn't regenerate.

---

## 7. Death ✅ (16 duels)
- **A ship dies when a critical subsystem is destroyed.** The catalogue flags Hull, Warp_Core and Bridge as critical.
  - **Hull reaches 0:** 14 of 16 deaths. IsDying follows within one sample (≤0.25 s) of the hit that zeroed the hull. That hit took the hull from 16–1351 HP.
  - **Warp core destroyed:** 2 of 16. A 900 quantum zeroed a core at 250 / 759 HP and the ship began dying with its hull still at 3333 / 1039 HP.
    - In both cases a 600-damage hull hit appears at the same moment (❓ possibly the core-breach explosion).
  - **Bridge:** never destroyed in any of the duels (12000 / 10000 HP, small and central). From the user's play experience, destroying the bridge also kills, but it almost never happens (the AI doesn't seem to target it, and it is hard to reach). Not measured: scripted ship destruction crashes the game, so it can't be tested in isolation.
- **No death splash on other ships at 28 GU or more:** in 29 deaths (26 duels plus 3 close-range runs; nearest 28 GU) the surviving ship took no damage and its shields kept regenerating. The death sequence's 600-damage explosions land only on the dying ship.
- **Group parents** (Phasers, Torpedoes, Tractors, Impulse_Engines, Warp_Engines) are never damaged in combat. They drop to 0 at the instant the ship starts dying, as part of the death sequence. Other subsystems (e.g. the bridge) are also zeroed during the death sequence.
  - So a group-wide weapons shutdown never happens through damage; each weapon disables individually.
  - (By script, a disabled group parent does stop all its weapons.)

---

## 8. Weapons timing

### 8.1 Phaser recharge ✅
- **Recharge per bank** = `RechargeRate (0.08/s) × Weapons power × bank condition`.
  - Measured 0.079–0.083/s at 100%; 0.0626/s for a bank at 80%.
- A bank holds a max charge of 5 and needs 3 to fire (catalogue).
- Single-fire phasers keep a round-robin between banks.

### 8.2 Torpedo reload ✅
- **40 s per tube after it fires**, the same for photon and quantum. Reload time = 40 s / Weapons power.
- A tube at 80% condition still reloads in 40 s.
- **Switching torpedo type** (Sovereign) empties ALL tubes and restarts every reload from zero. Progress is lost, and all tubes are ready 40 s after the switch.

### 8.3 Spread modes ✅
The firing chain string is `0;Single;123;Dual;53;Quad`.
- **Single:** one tube every 0.65 s, launched straight at the target, no steering.
- **Dual:** two tubes at once (pairs 0.65 s apart). A second set followed 8 s later in one run (❓ which tubes).
- **Quad:** all four at once.
- Dual and Quad torpedoes leave on a **3.8° fan** and steer back toward the target.
- Hit rate by range (Sovereign, from ahead, shields off):

  | Range | Single | Dual | Quad |
  |---|---|---|---|
  | 30 GU | 4/4 | 2/8 | 1/4 |
  | 57 GU | 4/4 | 6/8 | 3/4 |
  | 120 GU | 4/4 | all | 4/4 |
  | 200 GU | 4/4 | all | 4/4 |

  At close range the spread torpedoes have to turn up to 26° and overshoot; at long range they need only 2–3°.
- **Spreads are long-range modes.** Galaxy, the same test:

  | Range | Single | Dual | Quad |
  |---|---|---|---|
  | 30 GU | 4/4 | 0/8 | 0/4 |
  | 57 GU | 4/4 | 0/8 | 0/4 |
  | 120 GU | 4/4 | 8/8 | 4/4 |
  | 200 GU | 4/4 | 8/8 | 4/4 |

  The Galaxy's spread torpedoes miss entirely inside about 60 GU (they turn 26° and overshoot); the Sovereign's still land some.

---

### 8.4 Torpedoes against a moving target ✅
Raw speed can't outrun a torpedo (photon 19 GU/s, quantum 22, against at most 7.9–9.4 GU/s at 125% impulse), but a ship moving **across** a torpedo's path evades it. A photon steers for only about 6 s (about 114 GU) and must lead its target. Sovereign photons, single fire, at a Galaxy:

| Target | Range | Hits |
|---|---|---|
| Parked | 100 GU | 4 / 4 |
| Flying straight at the shooter, full impulse | 150 GU | 4 / 5 |
| Flying straight away, full impulse | 100 GU | 4 / 4 |
| Crossing at full impulse while turning hard | 100 GU | 3 / 8 |
| **Crossing at half impulse** | 100 GU | **0 / 8** (missed by 3.5–22 GU) |
| **Crossing at full impulse** | 100 GU | **0 / 5** (missed by 30–60 GU) |
| Crossing at full impulse | 150 GU | 0 / 7 |
| Quad spread at a target crossing at full impulse | 100 GU | 0 / 4 |

- **Torpedo stock running out:** not measured. The game has no script call that lowers the stock (`SetMaxTorpedoes` left the count at 60), so it would take firing all 60 quantums (about 10 minutes).

## 9. Duels ✅ (26 duels, both AIs at difficulty 0.5, pinned)
**Setup:** Quick Battle, one Galaxy vs one Sovereign, each flown by the stock AI. Each ship played both roles (the AI enemy, and the player's ship under friendly AI). Starting range was 57–200 GU, from bearings 0°, 45°, 90°, 135°, 180° and 270°.

**Result: the Sovereign won all 26.**

| | Duels | Galaxy destroyed after | Sovereign hull at the end |
|---|---|---|---|
| Sovereign as the AI enemy | 13 | 205–343 s | 100% |
| Sovereign as the player's ship | 13 | 178–413 s | 96–100% |

- Average time to kill by starting range: 57 GU 313 s, 60 GU 284 s, 100 GU 292 s, 150 GU 267 s, 200 GU 255 s. Starting range barely matters; the AI closes to fighting range.
- Duels are not deterministic: AI choices vary between runs even with identical starts.

**How the stock AI fights** (both AIs at 0.5, about 2 hours of fighting pooled over the 26 duels; `oracle/reports/ai_tactics.py`):
- **It fights at range:** median 105 GU, and 70% of the time between 60 and 150 GU, beyond the phasers' full-damage distance (60/70 GU). Range falloff therefore shapes most of every fight.
- **Phasers fire more at long range:** the Sovereign fires 64% of the time beyond 150 GU against 33% inside 60 GU; the Galaxy 52% against 29%.
- **It targets subsystems, weapons first.** From Medium up the AI's `ChooseSubsystemTargets` rates every targetable subsystem (AI/Preprocessors.py `RateSubsystemForTargeting`):
  - weapon or weapon system +5, shield generator +5, critical (warp core) +6, hittable from its position +1, hull −200
  - −0.0005 per HP still needed to disable it and to destroy it, so weak subsystems score higher

  It aims its weapons at the winner. The choice lives inside the AI, not in the ship's target subsystem; the oracle's telemetry read only the latter, which is why it first looked like "always the hull" (corrected 2026-10-16 after the user's report).
- **Evidence, losing Galaxy, HP lost before death:**

  | | Medium AI (26 duels) | High AI (9 duels) |
  |---|---|---|
  | Ventral phasers 1 and 4 | 86% (destroyed 20/26) | 87% (7/9) |
  | Forward torpedo tubes 1–4 | 69–74% (destroyed about half) | 76–84% |
  | Other phaser banks | 30–44% | 48–69% |
  | Forward tractor 2 | 72% | 67% |
  | Shield generator | 32%, never destroyed | not in the top 14 |

  The forward tubes and the phasers bearing on the approach go first; High hits the tubes harder.
- **Phasers fire on High intensity.**
- **The Sovereign switches to quantum torpedoes once, early, at about 100 GU, and never goes back.** The Galaxy fires photons; median launch range is about 100–120 GU.
- **Throttle:** median about half impulse; full impulse only 22–31% of the time.
- **Tractors are never used.**

**Death sequence:** a dying ship is wrecked by a series of 600-damage internal explosions (12–32 over about 12 s). In 25 of 26 duels no splash reached the winner at 30–156 GU; its shields kept regenerating through the explosion. Splash at closer range is being measured.

**Why the Sovereign wins** (per-face analysis of the 4 original duels):
- The Galaxy's 4000-point top and bottom faces are its most-hit faces (§2.1) and spend **51–85% of each fight below the 60% leak threshold**.
- The Sovereign's 11000-point front/top/bottom faces stay above 60%, except its bottom face in some fights.
- Both ships regenerate each face at about the same rate (§2.4), so the bigger faces simply last longer.
- Damage that got through: **Galaxy 52–97k vs Sovereign 6–23k.**
- Late in the fight (164–367 s) the Galaxy's shield generator drops below 75%, all its faces go to 0, and the hull goes quickly. 35–65% of the Galaxy's leaked damage came before that point.
- Also against the Galaxy: its phasers lose damage beyond 60 GU (Sovereign 70), and its photons do 500 vs 550 + 900 quantums.

---

## 10. Intercept (in-system warp) ✅
The Helm's intercept order, and the AI's Intercept, use the game's in-system warp (`ShipClass.InSystemWarp(target, stop distance)`). It's part of Quick Battle combat; only system-to-system warp is campaign-only.
- **Entry is a step to exactly 75 GU/s** on the next sample, whatever the ship's own speed. That's about 4× a photon torpedo, so intercept is the only way to outrun one.
- **Duration = distance / 75:** 7.2 s from 600 GU with a 50 GU stop distance.
- **Drop-out** at about the requested stop distance (asked 50, dropped out at 54–61 GU).
- **Exit speed = the ship's top impulse speed** (Galaxy 6.25–6.28) along the warp heading, whatever the speed before the warp; it then coasts down.
- **Damaged nacelles don't stop it:** the Galaxy warped at 75 GU/s with both nacelles at 49% (disabled). The Helm's own warp button does check the Warp Engines group.
- System-to-system warp (the campaign's Warp button) is out of scope here.

## 11. Collisions ✅ (lowest priority: the original game's collisions are crude)
- **Each contact damages both ships at once**, with a **1.5 GU damage radius**. That's ten times a phaser's footprint, so every subsystem near the contact point takes the full amount (sensors, phaser banks, tractors, even the bridge).
- **Shields absorb none of it:** an identical full-speed ram did exactly the same damage with shields up and down.
- **Damage per ship = 490 + 1800 × m_other / (m_a + m_b) × impact speed**: each ship's share of the closing speed (its velocity change), so the lighter ship takes more. One constant fits all five rams measured (these and the original project's Kessok, Galaxy and Bird of Prey into a parked Galaxy). Masses: Galaxy 120, Sovereign 100. For this pair that is about 490 + 990 × v to the Sovereign and 490 + 820 × v to the Galaxy:

  | Impact speed | Rammed Sovereign | Rammer Galaxy |
  |---|---|---|
  | 2.10 GU/s | 2,562 | 2,218 |
  | 4.18 GU/s | 4,607 | 3,922 |
  | 6.10 GU/s | 6,505 | 5,504 |

- **The angle doesn't matter:** a side impact equals head-on at the same speed (4,611 / 3,926 at 4.19 GU/s).
- **No overflow from a ram:** subsystems destroyed by the impact log their excess, but it is not re-applied; the hull loses exactly the impact amount (Galaxy 15,000 → 9,495.6 for 5,504.4). Weapon hits do re-apply it.
- **A ship that keeps thrusting rams again on every bounce:** at impulse 3 the Galaxy's repeated rams destroyed the Sovereign within 14 s.
- The stock AIs never collided in 26 duels.

## 12. Open questions
- ❓ **The AI's actual chosen target subsystem, recorded live** (planned; the first hook couldn't intercept the engine's AI calls). Targeting above is measured from its effects.
- ❓ **Difficulty other than 0.5:** Quick Battle difficulty may scale damage and HP as well as AI skill; only 0.5 was measured.
- ❓ **Torpedo stock running out:** needs all 60 quantums fired (no script call lowers the stock).
- ❓ **Tractor beams from the Sovereign:** measured on the Galaxy by the original project (engagement range, pull rate, stopping distance, slowing force = MaxDamage / mass); the Sovereign run crashed the game. The AIs never used tractors in 26 duels.
- ❓ **Engineering mouse-slider granularity:** the slider is compiled code; keyboard steps are 25%.
- ❓ Shield regen factor: the game delivers about 0.84 × the authored ShieldChargePerSecond; why 0.84 isn't known.
- ❓ Damaged-core power budget: drains larger than the healthy-core model; shortages start at a 60% core even though demand is under the draw cap.
- ❓ A 600-damage hull hit coincides with warp core destruction (possibly the breach explosion).

## Appendix A. Per-ship data (from the game's own catalogue dump)

Generated by `oracle/reports/ship_tables.py` from `results_mac/catalogue_galaxy_sovereign.json`. Angles in degrees; positions in model units, ship frame.

#### Galaxy: subsystems

| Subsystem | Parent | HP | Disabled below | Repair complexity | Radius | Position (x,y,z) | Targetable | Critical |
|---|---|---|---|---|---|---|---|---|
| Hull | - | 15000 | 0% | 3 | 1 | 0,-1.5,-0.5 | 1 | 1 |
| Warp_Core | - | 7000 | 50% | 2 | 0.400 | 0,-1.4,-0.48 | 1 | 1 |
| Shield_Generator | - | 12000 | 75% | 2 | 0.500 | 0,-0.4,0.2 | 1 | 0 |
| Sensor_Array | - | 8000 | 50% | 1 | 0.280 | 0,-0.45,-0.5 | 1 | 0 |
| Torpedoes | - | 8000 | 75% | 3 | 0.200 | 0,0,0 | 0 | 0 |
| Forward_Torpedo_1 | Torpedoes | 2400 | 75% | 3 | 0.200 | 0,-0.25,-0.25 | 1 | 0 |
| Forward_Torpedo_2 | Torpedoes | 2400 | 75% | 3 | 0.200 | 0,-0.25,-0.25 | 1 | 0 |
| Forward_Torpedo_3 | Torpedoes | 2400 | 75% | 3 | 0.200 | 0,-0.25,-0.25 | 1 | 0 |
| Forward_Torpedo_4 | Torpedoes | 2400 | 75% | 3 | 0.200 | 0,-0.25,-0.25 | 1 | 0 |
| Aft_Torpedo_1 | Torpedoes | 2400 | 75% | 3 | 0.250 | -0.065,-1.24841,-0.174909 | 1 | 0 |
| Aft_Torpedo_2 | Torpedoes | 2400 | 75% | 3 | 0.250 | 0.065,-1.24841,-0.174909 | 1 | 0 |
| Phasers | - | 4000 | 75% | 7 | 0.400 | 0,0,0 | 0 | 0 |
| Ventral_Phaser_1 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.3,0.16 | 1 | 0 |
| Ventral_Phaser_2 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.3,0.16 | 1 | 0 |
| Ventral_Phaser_3 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.3,0.16 | 1 | 0 |
| Ventral_Phaser_4 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.3,0.16 | 1 | 0 |
| Dorsal_Phaser_1 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.27,0.5 | 1 | 0 |
| Dorsal_Phaser_2 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.27,0.5 | 1 | 0 |
| Dorsal_Phaser_3 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.27,0.5 | 1 | 0 |
| Dorsal_Phaser_4 | Phasers | 1000 | 75% | 7 | 0.250 | 0,1.27,0.5 | 1 | 0 |
| Impulse_Engines | - | 2400 | 50% | 3 | 0.250 | 0,-0.98,-0.45 | 0 | 0 |
| Port_Impulse | Impulse_Engines | 2600 | 50% | 3 | 0.250 | -1.22,-0.2,0.32 | 1 | 0 |
| Star_Impulse | Impulse_Engines | 2600 | 50% | 3 | 0.250 | 1.22,-0.2,0.32 | 1 | 0 |
| Center_Impulse | Impulse_Engines | 2600 | 50% | 3 | 0.250 | 0,-1.1,-0.08 | 1 | 0 |
| Warp_Engines | - | 500 | 50% | 3 | 0.250 | -0.3,-0.98,-0.45 | 0 | 0 |
| Port_Warp | Warp_Engines | 5000 | 50% | 3 | 1.200 | -1.3,-2.1,-0.06 | 1 | 0 |
| Star_Warp | Warp_Engines | 5000 | 50% | 3 | 1.200 | 1.3,-2.1,-0.06 | 1 | 0 |
| Tractors | - | 3000 | 75% | 7 | 0.300 | 0,-0.6,-0.16 | 0 | 0 |
| Aft_Tractor_2 | Tractors | 1500 | 75% | 7 | 0.250 | 0,-1,-0.73 | 1 | 0 |
| Aft_Tractor_1 | Tractors | 1500 | 75% | 7 | 0.250 | 0,0.18,0.57 | 1 | 0 |
| Forward_Tractor_1 | Tractors | 1500 | 75% | 7 | 0.200 | 0,2.4,0.52 | 1 | 0 |
| Forward_Tractor_2 | Tractors | 1500 | 75% | 7 | 0.200 | 0,1.7,0.06 | 1 | 0 |
| Bridge | - | 12000 | 0% | 4 | 0.500 | 0,1.2,0.56 | 1 | 1 |
| Engineering | - | 12000 | 10% | 2 | 0.250 | 0,-1.83114,-0.4 | 0 | 0 |

#### Galaxy: beam weapons (phasers and tractors)

| Weapon | Type | Max damage | Damage radius | Max charge | Min firing charge | Recharge /s | Arc width | Arc height |
|---|---|---|---|---|---|---|---|---|
| Ventral_Phaser_1 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -50..50° | -60..3° |
| Ventral_Phaser_2 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -80..20° | -60..3° |
| Ventral_Phaser_3 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -20..80° | -60..3° |
| Ventral_Phaser_4 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -50..50° | -60..3° |
| Dorsal_Phaser_1 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -50..50° | -3..60° |
| Dorsal_Phaser_2 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -80..20° | -3..60° |
| Dorsal_Phaser_3 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -20..80° | -3..60° |
| Dorsal_Phaser_4 | PhaserBank | 250 | 0.150 | 5 | 3 | 0.080 | -50..50° | -3..60° |
| Aft_Tractor_2 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.500 | -60..60° | -80..50° |
| Aft_Tractor_1 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.500 | -15..15° | -10..50° |
| Forward_Tractor_1 | TractorBeamProjector | 50 | 0.300 | 5 | 3 | 0.300 | -60..60° | -5..70° |
| Forward_Tractor_2 | TractorBeamProjector | 50 | 0.300 | 5 | 3 | 0.300 | -60..60° | -70..5° |

#### Galaxy: torpedo tubes

Damage, speed and guidance belong to the torpedo type, not the tube; tubes do not charge. The tube's own DamageRadiusFactor (0.2) is not the hit radius; measured torpedo hits use the torpedo type's radius (about 0.13-0.14). The firing arc is the game's own in-arc test sampled every 5° (azimuth from dead ahead, positive to starboard).

| Tube | Torpedo damage | Direction | Arc at level | Elevation range | Holds | Reload | Launch delay | Spread group |
|---|---|---|---|---|---|---|---|---|
| Forward_Torpedo_1 | photon 500 | 0,1,0 | -30..30° | -30..25° | 1 | 40 s | 0.25 s | 25 |
| Forward_Torpedo_2 | photon 500 | 0,1,0 | -30..30° | -30..25° | 1 | 40 s | 0.25 s | 25 |
| Forward_Torpedo_3 | photon 500 | 0,1,0 | -30..30° | -30..25° | 1 | 40 s | 0.25 s | 26 |
| Forward_Torpedo_4 | photon 500 | 0,1,0 | -30..30° | -30..25° | 1 | 40 s | 0.25 s | 26 |
| Aft_Torpedo_1 | photon 500 | 0,-1,0 | astern ±25° | -25..25° | 1 | 40 s | 0.25 s | 4 |
| Aft_Torpedo_2 | photon 500 | 0,-1,0 | astern ±25° | -25..25° | 1 | 40 s | 0.25 s | 4 |

#### Galaxy: ship-level systems

- **Warp_Core**: PowerOutput 1000, MainBatteryLimit 250000, BackupBatteryLimit 80000, MainConduitCapacity 1200, BackupConduitCapacity 200
- **Shield_Generator**: NormalPowerPerSecond 400
- **Sensor_Array**: BaseSensorRange 2000, NormalPowerPerSecond 100, MaxProbes 10
- **Torpedoes**: NormalPowerPerSecond 100, FiringChainString <TGString>, NumAmmoTypes 1
- **Phasers**: NormalPowerPerSecond 300, FiringChainString <TGString>
- **Impulse_Engines**: MaxSpeed 6.30, MaxAccel 1.50, MaxAngularVelocity 0.28, MaxAngularAccel 0.12, NormalPowerPerSecond 150
- **Warp_Engines**: NormalPowerPerSecond 0
- **Tractors**: NormalPowerPerSecond 600, FiringChainString <TGString>
- **Engineering**: MaxRepairPoints 50, NumRepairTeams 3, NormalPowerPerSecond 1

#### Sovereign: subsystems

| Subsystem | Parent | HP | Disabled below | Repair complexity | Radius | Position (x,y,z) | Targetable | Critical |
|---|---|---|---|---|---|---|---|---|
| Hull | - | 12000 | 0% | 3 | 0.700 | 0,-0.2,-0.25 | 1 | 1 |
| Shield_Generator | - | 10000 | 75% | 2 | 0.300 | 0,0.5,0 | 1 | 0 |
| Sensor_Array | - | 8000 | 50% | 1 | 0.250 | 0,2.35,0.07 | 1 | 0 |
| Warp_Core | - | 7000 | 50% | 2 | 0.300 | 0,-0.4,-0.2 | 1 | 1 |
| Impulse_Engines | - | 3000 | 50% | 3 | 0.150 | 0.49222,0.933819,0.1 | 0 | 0 |
| Port_Impulse | Impulse_Engines | 3000 | 50% | 3 | 0.250 | -0.6,0.4,0 | 1 | 0 |
| Star_Impulse | Impulse_Engines | 3000 | 50% | 3 | 0.250 | 0.6,0.4,0 | 1 | 0 |
| Torpedoes | - | 6000 | 75% | 3 | 0.250 | 0,0,-0.1 | 0 | 0 |
| Forward_Torpedo_1 | Torpedoes | 2200 | 75% | 3 | 0.040 | -0.076,0.7,-0.375 | 1 | 0 |
| Forward_Torpedo_2 | Torpedoes | 2200 | 75% | 3 | 0.040 | -0.031225,0.7,-0.375 | 1 | 0 |
| Forward_Torpedo_3 | Torpedoes | 2200 | 75% | 3 | 0.040 | 0.031225,0.7,-0.375 | 1 | 0 |
| Forward_Torpedo_4 | Torpedoes | 2200 | 75% | 3 | 0.040 | 0.082957,0.7,-0.375 | 1 | 0 |
| Aft_Torpedo_1 | Torpedoes | 2200 | 75% | 3 | 0.150 | -0.13,-0.65,-0.35 | 1 | 0 |
| Aft_Torpedo_2 | Torpedoes | 2200 | 75% | 3 | 0.150 | 0.13,-0.65,-0.35 | 1 | 0 |
| Repair | - | 8000 | 1% | 1 | 0.500 | 0,-0.2,-0.2 | 0 | 0 |
| Phasers | - | 8000 | 75% | 7 | 0.250 | 0,0,0 | 0 | 0 |
| Ventral_Phaser_1 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.7,-0.075 | 1 | 0 |
| Ventral_Phaser_2 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.7,-0.075 | 1 | 0 |
| Ventral_Phaser_3 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.7,-0.075 | 1 | 0 |
| Ventral_Phaser_4 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.7,-0.075 | 1 | 0 |
| Dorsal_Phaser_1 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.6,0.14 | 1 | 0 |
| Dorsal_Phaser_2 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.6,0.14 | 1 | 0 |
| Dorsal_Phaser_3 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.6,0.14 | 1 | 0 |
| Dorsal_Phaser_4 | Phasers | 1000 | 75% | 7 | 0.050 | 0,1.6,0.14 | 1 | 0 |
| Tractors | - | 3000 | 75% | 7 | 0.250 | 0,0,0 | 0 | 0 |
| Aft_Tractor_1 | Tractors | 1500 | 75% | 7 | 0.250 | 0,0.29,0.1 | 1 | 0 |
| Aft_Tractor_2 | Tractors | 1500 | 75% | 7 | 0.280 | 0,-2,-0.17 | 1 | 0 |
| Forward_Tractor_1 | Tractors | 1500 | 75% | 7 | 0.150 | 0,3.1,0.07 | 1 | 0 |
| Forward_Tractor_2 | Tractors | 1500 | 75% | 7 | 0.150 | 0,3,-0.08 | 1 | 0 |
| Warp_Engines | - | 8000 | 50% | 3 | 0.250 | 0,0,0 | 0 | 0 |
| Port_Warp | Warp_Engines | 4500 | 50% | 3 | 1 | -0.88,-2.3,0.15 | 1 | 0 |
| Star_Warp | Warp_Engines | 4500 | 50% | 3 | 1 | 0.88,-2.3,0.15 | 1 | 0 |
| Bridge | - | 10000 | 0% | 4 | 0.350 | 0,1.8,0.16 | 1 | 1 |

#### Sovereign: beam weapons (phasers and tractors)

| Weapon | Type | Max damage | Damage radius | Max charge | Min firing charge | Recharge /s | Arc width | Arc height |
|---|---|---|---|---|---|---|---|---|
| Ventral_Phaser_1 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -60..60° | -70..-1° |
| Ventral_Phaser_2 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -100..20° | -70..-1° |
| Ventral_Phaser_3 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -20..100° | -70..-1° |
| Ventral_Phaser_4 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -60..60° | -70..-1° |
| Dorsal_Phaser_1 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -58..58° | -3..70° |
| Dorsal_Phaser_2 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -100..20° | -3..70° |
| Dorsal_Phaser_3 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -20..100° | -3..70° |
| Dorsal_Phaser_4 | PhaserBank | 300 | 0.150 | 5 | 3 | 0.080 | -58..58° | -3..70° |
| Aft_Tractor_1 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.300 | -20..20° | -15..60° |
| Aft_Tractor_2 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.300 | -20..20° | -60..20° |
| Forward_Tractor_1 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.500 | -70..70° | -5..75° |
| Forward_Tractor_2 | TractorBeamProjector | 80 | 0.300 | 5 | 3 | 0.500 | -75..75° | -75..0° |

#### Sovereign: torpedo tubes

Damage, speed and guidance belong to the torpedo type, not the tube; tubes do not charge. The tube's own DamageRadiusFactor (0.2) is not the hit radius; measured torpedo hits use the torpedo type's radius (about 0.13-0.14). The firing arc is the game's own in-arc test sampled every 5° (azimuth from dead ahead, positive to starboard).

| Tube | Torpedo damage | Direction | Arc at level | Elevation range | Holds | Reload | Launch delay | Spread group |
|---|---|---|---|---|---|---|---|---|
| Forward_Torpedo_1 | photon 550 / quantum 900 | 0,1,0 | -25..25° | -25..25° | 1 | 40 s | 0.25 s | 25 |
| Forward_Torpedo_2 | photon 550 / quantum 900 | 0,1,0 | -25..25° | -25..25° | 1 | 40 s | 0.25 s | 25 |
| Forward_Torpedo_3 | photon 550 / quantum 900 | 0,1,0 | -25..25° | -25..25° | 1 | 40 s | 0.25 s | 26 |
| Forward_Torpedo_4 | photon 550 / quantum 900 | 0,1,0 | -25..25° | -25..25° | 1 | 40 s | 0.25 s | 26 |
| Aft_Torpedo_1 | photon 550 / quantum 900 | 0,-1,0 | astern ±25° | -25..25° | 1 | 40 s | 0.25 s | 4 |
| Aft_Torpedo_2 | photon 550 / quantum 900 | 0,-1,0 | astern ±25° | -25..25° | 1 | 40 s | 0.25 s | 4 |

#### Sovereign: ship-level systems

- **Shield_Generator**: NormalPowerPerSecond 450
- **Sensor_Array**: BaseSensorRange 2400, NormalPowerPerSecond 150, MaxProbes 10
- **Warp_Core**: PowerOutput 1200, MainBatteryLimit 200000, BackupBatteryLimit 100000, MainConduitCapacity 1450, BackupConduitCapacity 250
- **Impulse_Engines**: MaxSpeed 7.50, MaxAccel 1.60, MaxAngularVelocity 0.30, MaxAngularAccel 0.15, NormalPowerPerSecond 200
- **Torpedoes**: NormalPowerPerSecond 150, FiringChainString <TGString>, NumAmmoTypes 3
- **Repair**: MaxRepairPoints 50, NumRepairTeams 3, NormalPowerPerSecond 1
- **Phasers**: NormalPowerPerSecond 400, FiringChainString <TGString>
- **Tractors**: NormalPowerPerSecond 700, FiringChainString <TGString>
- **Warp_Engines**: NormalPowerPerSecond 0

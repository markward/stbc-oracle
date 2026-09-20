# Star Trek: Bridge Commander — measured behaviour bible

**Status:** living document. Every number here was measured on the original
`stbc.exe` (GOG release, 2002-04-09 build) by the unattended oracle in this
repo, and every claim names the capture in [`results/`](results/) that backs
it. Nothing is taken from disassembly or memory; where a reverse-engineered
formula is mentioned it is because the measurement confirmed it.

The point of the document is to be **the contract a reimplementation is
tested against**: §9 lists the assertions, with tolerances, that a harness
for any remake (Dauntless or otherwise) should encode. To regenerate any
table: `python oracle/study.py` re-runs the matrix, `python oracle/analyze.py`
reduces it.

Conventions: **GU** = BC game unit (1 GU = 175 m in the HUD's km readout);
**tick** = one engine update (measured 16.5 ms ≈ 60 Hz); samples were taken
every 2 ticks (~31 ms) so any time quoted is ±31 ms. "Face" = one of the six
shield facings; "fraction" = current / max of that face. Scenario geometry
unless stated: attacker parked, AI removed, at the stated range and bearing
from a parked Galaxy-class target with its own weapons zeroed, both at red
alert; one weapon system commanded to fire at the target.

---

## 1. Time base and sampling

| Fact | Value | Evidence |
|---|---|---|
| Engine update period | **16.5 ms** (60.5 Hz) | `f` (update number) vs `t` over 750 samples, `phaser_high_front_57.json` |
| Game clock is what timers, pulses and regen run on | — | every cadence below is stable in `t` |

---

## 2. Beam weapons (phasers, positron beams, disruptor beams)

All `PhaserBank` emitters: Federation phasers, Kessok positron beams, the
Romulan Warbird's beam disruptor. Reference emitter: Kessok Heavy
`Forward Beam 1..4`, `MaxDamage 400`, `MaxDamageDistance 200`, `MaxCharge 7`.

### 2.1 Damage rate

```
rate_per_beam  = MaxDamage × intensity_scale × min(1, MaxDamageDistance / range)
intensity_scale: LOW 0.25   MED 0.5   HIGH 0.5
```

| Scenario | beams | measured rate (all beams) | model | file |
|---|---|---|---|---|
| Kessok → Galaxy, 57 GU, HIGH | 4 | **825/s** | 800 | `phaser_high_front_57` |
| same, MED | 4 | 849/s | 800 | `phaser_med_front_57` |
| same, LOW | 4 | **408/s** | 400 | `phaser_low_front_57` |
| 150 GU (inside R=200) | 4 | 832/s | 800 | `phaser_high_front_150` |
| 250 GU | 4 | 683/s | 640 (×0.80) | `phaser_high_front_250` |
| 400 GU | 4 | 418/s | 400 (×0.50) | `phaser_high_front_400` |
| 600 GU | 4 | 283/s | 267 (×0.33) | `phaser_high_front_600` |
| Warbird beam disruptor, 57 GU, HIGH | 1 | 120/s | — | `beam_warbird_front_57` |

Measured rates run ~3–6 % above the model because the pulse period is
0.53 s, not 0.5 s (see §2.2), which the model above folds into `× 0.5 s`
pulses; per pulse the model is exact.

**Things that do NOT change the rate** (each tested, all within noise):

* remaining charge — rate is flat from charge 7 down to 0 (`phaser_high_front_57`), and a bank preset to charge 3 fires at the same 805/s (`phaser_high_front_57_charge3`);
* `SetPowerPercentageWanted(0.5)` on the phaser system (`phaser_high_front_57_power50`, 846/s);
* which face is hit — front/starboard/aft/bottom all 810–842/s.

### 2.2 Pulse cadence, windup, burst

Damage is **not** continuous. Each beam deposits a discrete quantum every
**0.53 s** (32 ticks) of `MaxDamage × intensity_scale × 0.53125`:

| emitter | quantum | file |
|---|---|---|
| MaxDamage 400, HIGH/MED, in range | **106.25** | every front run |
| MaxDamage 400, LOW | 53.1 | `phaser_low_front_57` |
| MaxDamage 400, HIGH, 250 GU | 87.4 (= 106.25 × 200/250 × 1.03) | `phaser_high_front_250` |
| MaxDamage 400, HIGH, 400 GU | 53.4 | `phaser_high_front_400` |
| MaxDamage 400, HIGH, 600 GU | 35.9 | `phaser_high_front_600` |

Multiple beams of one system are staggered by 1–4 ticks, so a 4-beam volley
lands as four quanta 31–62 ms apart, then ~0.35 s of nothing.

* **Windup: 1.156 s** (70 ticks) from `IsFiring` going true to the first
  quantum landing — identical in all 20 beam runs regardless of ship,
  intensity, range or face.
* **Discharge** while the beam is up: HIGH/MED **1.0 charge/s**, LOW
  **0.35/s** (7 → 0 in 7.0 s at HIGH; LOW still had charge at 12 s). A bank
  stops the instant charge reaches 0.
* **Recharge** starts immediately at `RechargeRate` per second (Kessok forward
  beams 0.17/s: 0 → 0.62 in 3.6 s).
* Kessok Heavy at HIGH: 4 beams × 7 s ⇒ **~5 400 damage per full volley**
  (5 469 / 5 494 / 5 421 / 5 505 / 5 423 measured across five geometries).

### 2.3 Which banks fire

Only banks whose arc contains the target fire; for the Kessok Heavy at any
bearing the four forward beams bear and the dorsal/ventral pairs do not.
The Warbird has one beam. (`ws_SingleFire` is 0 for these systems; the
Galaxy's phaser system is single-fire — not yet measured as attacker.)

---

## 3. Pulse weapons (disruptor cannons)

`PulseWeapon` emitters fire bolts; each bolt is one hit of a fixed size.

| Ship | emitters | bolt | volley pattern | file |
|---|---|---|---|---|
| Warbird, 40 GU | 4 | **200** | 4 bolts, then 4 more 0.34 s later; 1600 per 2.7 s burst; then recharge | `pulse_warbird_front_40` |
| Bird of Prey, 40 GU | 2 | **220** | pairs every 2.28 s; 8 bolts / 1760 in 10.6 s | `pulse_bop_front_40` |

Time from `IsFiring` to first hit at 40 GU: 0.66–0.91 s (bolt flight
included). Bolts deliver the same amount to hull when shields are down as to
a face when they are up (Warbird 1600 either way).

---

## 4. Torpedoes

A torpedo is one hit of the projectile script's `GetDamage()`, applied
whole; no intensity or range term. Tubes fire in sequence
**0.656 s** apart (40 ticks).

| Torpedo (ship) | hit | launch speed (script) | flight for 57 GU | tracking (`MaxAngularAccel`) | file |
|---|---|---|---|---|---|
| Photon (Galaxy) | **500** | 19 GU/s | 2.9 s | 0.15 | `torpedo_galaxy_front_57` |
| Photon2 (Sovereign) | **550** | — | 2.9 s | — | `torpedo_sovereign_front_57` |
| Positron (Kessok Heavy) | **2200** | 3.8 GU/s | **13.3 s** | 3.0 (40 s guidance) | `torpedo_kessok_front_57` |

Reference values for types not yet fired: Quantum 900 @ 22 GU/s, Antimatter
440 @ 35 GU/s, Klingon "Adv. Photon" 1400 @ 10 GU/s
(`scripts/Tactical/Projectiles/*.py`).

Two Positron torpedoes on an **unshielded** Galaxy (15 000 hull) killed it:
the hull went to 270 and the death sequence zeroed every subsystem
(`torpedo_kessok_front_57_noshields`) — a torpedo's damage reaches hull and
subsystems the same way a beam quantum does (§6).

---

## 5. Shields

### 5.1 Facing selection

The face that absorbs is the one the shot arrives through, chosen by
geometry, not by the target's orientation to the attacker's bow:

| attacker bearing | face drained | file |
|---|---|---|
| dead ahead | FRONT (index 0, max 8000) | `phaser_high_front_57` |
| 90° starboard | index 5 (max 4000) — **starboard is face 5** | `phaser_high_stbd_57` |
| astern | index 1 (max 4000) — **rear is face 1** | `phaser_high_aft_57` |
| directly below | index 3 (max 4000) — **bottom is face 3** | `phaser_high_bottom_57` |
| directly above | *not measured*: the attacker did not fire from 89° elevation (arc/placement issue in the harness) | `phaser_high_top_57` |

Index map established so far: 0 front, 1 rear, 3 bottom, 5 right; by
elimination 2/4 are top/left (order unconfirmed).

### 5.2 Absorption ramp (pass-through)

For every hit, the share that reaches the hull depends on the face's
fraction **before** the hit. Pooled over 350 hits from eight shielded runs:

| face fraction before hit | hull share (median) | n |
|---|---|---|
| ≥ 0.60 | **0.00** | 152 |
| 0.55–0.60 | 0.02 | 15 |
| 0.50–0.55 | 0.04 | 17 |
| 0.45–0.50 | 0.12 | 19 |
| 0.40–0.45 | 0.20 | 23 |
| 0.35–0.40 | 0.25 | 20 |
| 0.30–0.35 | 0.30 | 12 |
| 0.25–0.30 | 0.35 | 11 |
| 0.20–0.25 | 0.435 | 15 |
| 0.15–0.20 | 0.49 | 21 |
| 0.10–0.15 | 0.55 | 23 |
| < 0.10 | **1.00** — the face no longer stops the shot | 50 |

This is the ramp `passthrough(f) = 0.6 × (1 − 2 (f − 0.1))` for
0.1 < f < 0.6, clamped to [0, 0.6], with a hard gate at f = 0.1 below which
the shot bypasses the face entirely. Consequences a remake must reproduce:

* a full face absorbs everything until it is down to 60 %;
* a face preset to 50 % lets **39 %** of a full Kessok volley through
  (2015 of 5206, `phaser_high_front_57_face50`); at 25 %, **75 %**
  (4102 of 5485, `phaser_high_front_57_face25`); at 100 %, 5 % (279 of 5469);
* the 4000-point side/rear/bottom faces therefore leak much sooner than the
  8000-point front: 1567–1743 hull damage per volley vs 279 (§5.1 files).

### 5.3 Regeneration

Each face regains **6.15 points every 0.656 s** (≈ 9.4/s per face, Galaxy,
`ShieldGenerator` at full power) while below max, starting immediately —
even a zeroed face is back to ~105 after 11 s (`*_noshields` runs). Regen
ticks are visible as −6.1/−6.2 "negative damage" steps in every capture.

---

## 6. Hull and subsystem damage

### 6.1 Routing

Whatever passes the shield (§5.2) is applied **in full** to the hull **and in
full, independently, to every subsystem whose damage sphere the hit
overlaps** — subsystems do not share it, and the hull is not reduced by what
subsystems take.

| Scenario (Kessok HIGH, front, 57 GU) | hull | sensor array | fwd torpedo tubes ×4 | file |
|---|---|---|---|---|
| shields up (full) | 279 | 174 | 240 / 240 / 273 / 273 | `phaser_high_front_57` |
| front face 50 % | 2015 | 1620 | 1734 / 1734 / 1790 / 1790 | `..._face50` |
| front face 25 % | 4062 | 3893 | 2400 ×4 (destroyed) | `..._face25` |
| **no shields** | **5571** | **5402** | 2400 ×4 (destroyed) | `..._noshields` |

The unshielded numbers equal the volley total (5 400–5 600) — each
overlapping subsystem took the whole volley. Which subsystems are in the
footprint is geometric: from starboard the hit lands on the starboard warp
nacelle (`Star Warp` 5000 = destroyed, `phaser_high_stbd_57_noshields`);
from below on the warp core (`phaser_high_bottom_57`); from astern nothing
but hull (`phaser_high_aft_57_noshields`).

### 6.2 Intensity LOW: disable, don't destroy

At **LOW** phaser intensity the hull takes **zero** damage whatever the
shield state — subsystems only (`phaser_low_front_57_noshields`: hull 0,
sensor array −4056, tubes destroyed; `phaser_low_front_57`: hull 0 through a
weakened face). MED and HIGH damage both.

### 6.3 Subsystem catalogue (Galaxy)

34 subsystems (top level + children) with max condition, radius and mount
position are in every result's `subsystems` list; e.g. Hull 15000, Sensor
Array 8000, Shield Generator 12000, Warp Core 7000, each forward torpedo tube
2400, each phaser bank 1000, nacelles 5000, Bridge 600.

---

## 7. Motion

Commanded with `SetImpulse(1.0, model-forward)` and
`SetTargetAngularVelocityFraction(axis)`; the attacker's velocity and angular
velocity sampled every 31 ms.

### 7.1 The law

Both linear speed and angular rate follow the same first-order controller:

```
dv/dt = clamp(v_target − v, −MaxAccel, +MaxAccel)          (per second)
dω/dt = clamp(ω_target − ω, −MaxAngularAccel, +MaxAngularAccel)
```

i.e. constant acceleration at the hardpoint cap until within one cap-second
of the target, then exponential approach with a **1.0 s time constant**.
Mass and rotational inertia do not enter (Galaxy mass 120 vs Kessok 500 —
profiles match the law exactly). Stopping (`SetImpulse(0)`) is the same law
towards 0: from 3.7 GU/s the Kessok falls at 2.5 GU/s² to 2.3, then decays
e-fold per second (0.92 @ 1.5 s, 0.51 @ 2.1 s, 0.20 @ 3.0 s;
`motion_kessok_coast`).

### 7.2 Per-ship measurements

| Ship (hardpoint MaxSpeed / MaxAccel / MaxAngVel / MaxAngAccel) | speed @ 1 s | @ 2 s | @ 4 s | max | 95 % at | file |
|---|---|---|---|---|---|---|
| Kessok Heavy (3.7 / 2.5 / 0.22 / 0.11) | 2.226 | 3.166 | 3.630 | **3.700** | 3.1 s | `motion_kessok_impulse` |
| Galaxy (6.3 / 1.5 / 0.28 / 0.12) | 1.500 | 3.000 | 5.635 | **6.300** | 4.75 s | `motion_galaxy_impulse` |
| Bird of Prey (6.2 / 2.5 / 0.50 / 0.35) | 2.500 | 4.726 | 6.007 | **6.200** | 3.6 s | `motion_bop_impulse` |

| Ship | ω @ 1 s | @ 2 s | @ 4 s | max (rad/s) | 95 % at | files |
|---|---|---|---|---|---|---|
| Kessok Heavy | 0.110 | 0.180 | 0.215 | **0.220** | 3.25 s | `motion_kessok_{yaw,pitch,roll}` — identical on all three axes |
| Galaxy | 0.120 | 0.219 | 0.272 | **0.280** | 3.4 s | `motion_galaxy_yaw` |
| Bird of Prey | 0.304 | 0.429 | 0.491 | **0.500** | 3.0 s | `motion_bop_yaw` |

Model check: Galaxy @ 4 s → 6.3 − 1.5·e^{−(4−3.2)} = 5.63 (measured 5.635);
BoP yaw @ 1 s → 0.5 − 0.35·e^{−(1−0.43)} = 0.302 (measured 0.304).

---

## 8. Things measured that were *not* as documented elsewhere

* No `charge_ratio` term in beam damage (a decompilation transcription had
  suggested one).
* The phaser damage pulse is 0.53 s, not per tick and not 0.5 s.
* Beam windup is 1.16 s, not the 0.35 + 0.25 s sometimes quoted.
* The AI ship's phaser system defaults to **MED**; a remake driving AI ships
  at HIGH by default over-damages… by nothing (MED = HIGH), but at LOW it
  matters.

---

## 9. Harness contract

Assertions a remake's test harness should implement, in the same scenario
geometry (parked ships, red alert, target weapons off). Tolerances are
chosen from the run-to-run spread seen here (±5 % on totals, ±1 tick on
cadences). File = the capture whose raw rows are the reference.

| # | Assertion | Tolerance | File |
|---|---|---|---|
| B1 | 4 × MaxDamage-400 beams at HIGH, 57 GU, deliver 5 400 ± 5 % over one 7 s charge | ±5 % | `phaser_high_front_57` |
| B2 | MED total equals HIGH total | ±5 % | `phaser_med_front_57` |
| B3 | LOW rate is half of HIGH (0.25 vs 0.5) and LOW never damages hull | ±5 %; hull = 0 | `phaser_low_front_57*` |
| B4 | rate at range d > R scales by R/d: 0.80 @ 250, 0.50 @ 400, 0.33 @ 600 (R = 200) | ±6 % | `phaser_high_front_{250,400,600}` |
| B5 | rate inside R is flat (57 vs 150 GU within 2 %) | ±3 % | `phaser_high_front_150` |
| B6 | first damage lands 1.16 s after firing starts | ±0.05 s | any beam run |
| B7 | damage arrives as quanta of MaxDamage × scale × 0.53 every 0.53 s per beam | quantum ±2 %, period ±1 tick | `phaser_high_front_57` |
| B8 | rate independent of remaining charge and of power-wanted | ±5 % | `..._charge3`, `..._power50` |
| B9 | HIGH/MED drain 1.0 charge/s, LOW 0.35/s; bank stops at 0 | ±3 % | `phaser_high_front_57`, `phaser_low_front_57` |
| P1 | Warbird pulse bolt = 200, 4 emitters, 8 bolts in 2.7 s | exact / ±1 bolt | `pulse_warbird_front_40` |
| P2 | Bird of Prey bolt = 220, pairs every 2.28 s | exact / ±0.1 s | `pulse_bop_front_40` |
| T1 | torpedo hit = script damage (500 / 550 / 2200) applied whole | exact | `torpedo_*_front_57` |
| T2 | tubes launch 0.656 s apart | ±1 tick | `torpedo_galaxy_front_57` |
| T3 | Positron torpedo flight for 57 GU ≈ 13.3 s; Photon ≈ 2.9 s | ±0.5 s | `torpedo_kessok_front_57`, `torpedo_galaxy_front_57` |
| S1 | facing index: 0 front, 1 rear, 3 bottom, 5 starboard | exact | §5.1 files |
| S2 | pass-through = 0 for face ≥ 0.6, ramps linearly to 0.6 at face 0.1, 1.0 below 0.1 | ±0.05 per bin | pooled §5.2 |
| S3 | front face at 50 % passes 39 % of a volley; at 25 %, 75 % | ±5 pts | `..._face50`, `..._face25` |
| S4 | face regen 6.15 per 0.656 s per face | ±5 % | any run, after firing stops |
| H1 | every subsystem overlapping the hit takes the full post-shield amount; hull too | ±5 % | `phaser_high_front_57_noshields` |
| H2 | from starboard the starboard nacelle is hit; from below the warp core; from astern hull only | set membership | `phaser_high_{stbd,bottom,aft}_57*` |
| M1 | speed follows `clamp(v_max − v, ±MaxAccel)` with 1 s time constant; reaches MaxSpeed exactly | ±2 % at 1/2/4 s | `motion_*_impulse` |
| M2 | angular rate follows the same law with MaxAngularAccel / MaxAngularVelocity, identical on yaw/pitch/roll | ±2 % | `motion_*_{yaw,pitch,roll}` |
| M3 | stopping follows the same law towards 0 | ±5 % | `motion_kessok_coast` |
| M4 | mass / rotational inertia do not affect M1–M3 | — | Galaxy vs Kessok vs BoP |

---

## 10. Not yet measured / open

* Top-elevation facing (the 89° run did not fire) — re-run with the attacker
  yawed rather than pitched onto the target.
* Galaxy/Sovereign as *attacker* (single-fire phaser systems, quantum
  torpedoes): needs the harness's `player=attacker` mode.
* Pulse weapons at LOW/HIGH power settings; pulse falloff with range.
* Whether the 0.53 s pulse and 1.16 s windup are frame-count constants
  (32 / 70 ticks) or time constants — needs a run at a different frame rate.
* Collision damage, tractor beams, warp; what mass and rotational inertia
  *do* affect.
* Shield regen dependence on generator power / alert level.
* Torpedo splash radius (`DamageRadiusFactor`) vs subsystem footprint.

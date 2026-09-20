# Star Trek: Bridge Commander — measured behaviour bible

**Status:** living document (83 captures, five study matrices). Every number here was measured on the original
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
  intensity, range or face. It is a **game-time** constant, not a frame
  count: at `SetTimeScale(0.5)` the windup is still 1.11 s of game time
  (142 frames) and the quanta still arrive every ~0.53 s of game time
  (`phaser_high_front_57_timescale05`).
* **Discharge** while the beam is up: HIGH/MED **1.0 charge/s**, LOW
  **0.35/s** (7 → 0 in 7.0 s at HIGH; LOW still had charge at 12 s). A bank
  stops the instant charge reaches 0.
* **Recharge** starts immediately at `RechargeRate` per second (Kessok forward
  beams 0.17/s: 0 → 0.62 in 3.6 s).
* Kessok Heavy at HIGH: 4 beams × 7 s ⇒ **~5 400 damage per full volley**
  (5 469 / 5 494 / 5 421 / 5 505 / 5 423 measured across five geometries).

### 2.3 Which banks fire; single-fire systems

Only banks whose arc contains the target fire; for the Kessok Heavy at any
bearing or elevation the four forward beams bear (all four at elevations
45/60/75°, `phaser_high_elev*_57`) and the dorsal/ventral pairs do not. The
Warbird has one beam.

Federation phaser systems are **single-fire** (`Phasers.SetSingleFire(1)`):
one bank fires until its charge is exhausted, then the next bank starts,
round-robin — never two at once.

| Ship | bank `MaxDamage` | quantum per 0.53 s | sequence | file |
|---|---|---|---|---|
| Galaxy | 250 | **66** | bank 5 for 5.5 s, then bank 6, then bank 1 | `phaser_galaxy_front_57` |
| Sovereign | 300 | **80** | bank 6 for 5.9 s, then bank 5 | `phaser_sovereign_front_57` |

So a Galaxy's sustained phaser output is ~125/s (one 250-point bank at
0.5), which is why a Galaxy-vs-Galaxy duel is slow: 1112 damage in the
12 s window.

---

## 3. Pulse weapons (disruptor cannons)

`PulseWeapon` emitters fire bolts; each bolt is one hit of
`projectile script GetDamage() × PulseWeapon.GetDamageScale()`. The Warbird's
`RomulanCannon` script says 400 and its cannons report `DamageScale 0.5`
(power setting MED), so bolts land as 200; the Bird of Prey's
`PulseDisruptor` (220) lands whole (`pulse_warbird_front_40_meta`).

| Ship | emitters | bolt | volley pattern | file |
|---|---|---|---|---|
| Warbird, 40 GU | 4 | **200** | 4 bolts, then 4 more 0.34 s later; 1600 per 2.7 s burst; then recharge | `pulse_warbird_front_40` |
| Bird of Prey, 40 GU | 2 | **220** | pairs every 2.28 s; 8 bolts / 1760 in 10.6 s | `pulse_bop_front_40` |

Time from `IsFiring` to first hit at 40 GU: 0.66–0.91 s (bolt flight
included). Bolts deliver the same amount to hull when shields are down as to
a face when they are up (Warbird 1600 either way).

**No range falloff and no power-setting effect on bolts:** Warbird bursts
at 40 / 100 / 150 GU are 1501 / 1514 / 1526, and `EnergyWeapon.SetPowerSetting`
LOW or HIGH on the emitters leaves the burst at 1501
(`pulse_warbird_front_{40_low,40_high,100,150}`). What the setting does
change is the **charge cost per shot**: Warbird cannon `MaxCharge` 2.0 drops
by **0.5 / 1.0 / 2.0** per bolt at LOW / MED / HIGH (2.0 → 1.53 / 1.03 /
0.03), recharging at ~0.16/s — the setting buys more or fewer bolts per
charge, never bigger ones.

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
| Quantum (Sovereign, ammo type 1) | **900** | 22 GU/s | 2.4 s | 0.15 | `torpedo_sovereign_quantum_57` |
| Klingon "Adv. Photon" (Warbird) | **1400** | 10 GU/s | ~5.5 s | 0.2 | `torpedo_warbird_front_57` |

Switching ammo type (`TorpedoSystem.SetAmmoType`) **unloads the tubes**; the
Sovereign's `ReloadDelay` is 40 s, so the first quantum salvo needs ~45 s
after the switch. Reference for the type not fired: Antimatter 440 @ 35 GU/s.

Photon torpedoes on a bare hull (`torpedo_galaxy_front_57_noshields`): four
500-point hits gave the hull 2000 **and** each subsystem in the footprint
1725–2000 (sensor array, four forward tubes) — the §6.1 rule applies to
torpedoes as to beams. Klingon torpedoes (`DamageRadiusFactor` 0.2 vs the
photon's 0.13) reach further: four 1400-point hits gave the hull 7108, the
sensor array 6938, every forward tube 2400 and the shield generator 1475
(`torpedo_warbird_front_57_noshields`).

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
| 45° / 60° / 75° above | index 2 (max 4000) — **top is face 2** | `phaser_high_elev{45,60,75}_57` |

| 270° (port) | index 4 (max 4000) — **port is face 4** | `phaser_high_port_57` |

**Index map (all six measured): 0 front, 1 rear, 2 top, 3 bottom, 4 port,
5 starboard.** From above, the hit footprint walks aft with elevation:
shield generator at 45°, warp core + aft tubes + centre impulse at 60–75°.
(`phaser_high_top_57` at 89° is void: an earlier harness bug left the
attacker's nose off the target.)

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
The rate is the same at **red, yellow and green alert** (a face preset to
50 % climbs at 9.2–9.5/s in all three, `regen_{red,yellow,green}_face50`)
and at 50 % generator power wanted (`regen_power50_face50`).

**Generator condition gate:** with the shield generator's condition below
its hardpoint `DisabledPercentage` (0.75 for the Galaxy), **every face drops
to 0 immediately and nothing regenerates** — at 50 % and at 20 % condition
alike (`regen_gen{50,20}_face50`). A remake must treat the generator as
binary: healthy ⇒ shields; disabled ⇒ no shields at all.

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
profiles match the law exactly).

**What the "max" values actually cap.** `v_target = MaxSpeed × impulse
fraction × engine power fraction`: the impulse fraction is clamped to 1.0
(`SetImpulse(1.25)` and `(2.0)` both give 3.700, `motion_kessok_impulse{125,200}`),
but the **impulse engine's power fraction is not** — at
`SetPowerPercentageWanted(1.25)` the Kessok cruises at **4.625 = 1.25 ×
3.7** (`motion_kessok_impulse_power125`). That is how AI ships (and a player
who boosts engine power) exceed `MaxSpeed`. Likewise `MaxAngularVelocity`
caps only the *fraction* command: `SetTargetAngularVelocityDirect(1.0 rad/s)`
ramps at `MaxAngularAccel` (0.11 rad/s², linear) with the same 1 s approach
and settles at **1.0 rad/s**, 4.5× the hardpoint "max"
(`motion_kessok_yawdirect`). Stopping (`SetImpulse(0)`) is the same law
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

### 7.3 Collisions — what mass is for

Ramming runs (attacker at full impulse into the parked Galaxy from 30 GU,
`ram_*`): the bounce is a **perfectly elastic collision with the hardpoint
masses**, and the damage is proportional to the impulse exchanged.

| Rammer (mass) → Galaxy (120) | speed at impact | Galaxy speed after (measured / elastic model) | rammer speed after | damage to Galaxy | damage to rammer |
|---|---|---|---|---|---|
| Kessok Heavy (500) | 3.70 | **5.97** / 5.97 | 2.55 (still under power) / 2.27 | **5870** | 1789 |
| Galaxy (120) | 6.21 | **5.88–6.21** / 6.21 | 0.33 / 0 | **6089** | 6089 |
| Bird of Prey (45) | 6.17 | **3.36** / 3.36 | 2.80 (rebound) / −2.80 | **3527** | 4000 (= its whole hull) |

Elastic model: `v_target' = 2 mₐ v / (mₐ + mₜ)`, `v_attacker' = (mₐ − mₜ) v / (mₐ + mₜ)`.
Damage to the rammed Galaxy is **8.2 × J** with `J = 2 μ v` (μ the reduced
mass): 744 → 6089, 716 → 5870, 404 → 3527. The rammer's own damage per unit
impulse depends on the hull (Galaxy 8.2, Kessok 2.5, BoP ≥ 9.9), and the
reverse pairing does not reduce to one constant either: a Galaxy hitting a
parked Kessok Heavy at 3.83 GU/s took **9561** itself and gave the Kessok
2675, and that impact was *not* elastic (the Galaxy stayed under power and
kept 3.5 GU/s; `ram_galaxy_kessok`). The RE puts collision damage on the
per-contact impulse with a clamp, so the split is contact-geometry
dependent: treat the elastic bounce and the ~8 × J order of magnitude as the
contract, and measure any specific pairing. Collision
damage **bypasses shields entirely** (every face unchanged in all three
runs) and a rammer left under power hits again every ~3 s (Kessok: 5870,
4487, 4693 → Galaxy destroyed).

### 7.4 Tractor beam

With a Galaxy's tractor system engaged on a parked target
(`tractor_galaxy_*`, Kessok Heavy at 20 GU; `tractor_galaxy_galaxy_*`,
Galaxy at 15 GU, 30 s) the beam fires (one emitter) and the target creeps
toward the projector at **0.007 GU/s regardless of target mass (500 or
120) and of mode** (hold / tow / pull / push all identical), stopping after
~5 GU of travel (~2.7 GU in one hold run); the projector never moves. The
tractor as scripted here is nearly inert — whatever makes it useful in play
(projector motion, relative velocity) is not exercised by a parked pair.

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
| M5 | impulse fraction clamps at 1.0, engine power fraction does not: 125 % power ⇒ 1.25 × MaxSpeed | exact | `motion_kessok_impulse{125,200,_power125}` |
| M6 | direct angular command is uncapped, ramps at MaxAngularAccel with the 1 s approach | ±3 % | `motion_kessok_yawdirect` |
| A1 | AI reaction ≈ 4 s after spawn; fires every weapon in arc from 150 GU | ±0.5 s | `ai_*` |
| A2 | Kessok AI pass: close to ~47 GU at ≤4.2 GU/s, break away at 4.6 GU/s to ~123 GU, turn at 0.40 rad/s; identical at all three difficulties | ±5 GU | `ai_kessok_vs_parked_galaxy_*` |
| A3 | AI difficulty changes weapons use, not motion: LOW never fires torpedoes | — | `ai_kessok_vs_parked_galaxy_low` |
| A4 | AI runs impulse engines at 125 % power (speed = 1.25 × MaxSpeed) | exact | `ai_*` |
| A5 | AI cannot catch a faster target: head-on pass to ~23 GU then a losing stern chase | ±5 GU | `ai_kessok_vs_moving_galaxy_med` |
| A6 | AI against a circling target closes monotonically and attacks rear/port | — | `ai_kessok_vs_circling_galaxy_med` |
| A7 | BoP AI: closest 37 GU, 7.75 GU/s, 0.72 rad/s | ±5 % | `ai_bop_vs_parked_galaxy_med` |
| F1 | single-fire phaser systems fire one bank at a time, round-robin on exhaustion; Galaxy quantum 66, Sovereign 80 | exact / ±1 bank | `phaser_{galaxy,sovereign}_front_57` |
| F2 | windup and pulse period are game-time constants (unchanged at time scale 0.5) | ±0.1 s | `phaser_high_front_57_timescale05` |
| P3 | bolt damage independent of range (40–150 GU) and of emitter power setting | ±2 % | `pulse_warbird_front_*` |
| T4 | quantum 900, Klingon 1400; ammo switch unloads tubes (Sovereign reload 40 s) | exact | `torpedo_sovereign_quantum_57`, `torpedo_warbird_front_57` |
| S5 | regen rate identical at red/yellow/green alert | ±5 % | `regen_*_face50` |
| C1 | collision is elastic with hardpoint masses (post-impact speeds) | ±3 % | `ram_*` |
| C2 | rammed-ship damage = 8.2 × 2μv; shields untouched | ±10 % | `ram_*` |
| P4 | bolt = script damage × emitter DamageScale; power setting changes shot cost 0.5/1/2, not damage | exact | `pulse_warbird_front_40_{meta,low,high}` |
| S6 | shield generator below DisabledPercentage ⇒ all faces 0, no regen | exact | `regen_gen{50,20}_face50` |
| S7 | port is face 4 | exact | `phaser_high_port_57` |

---

## 10. Not yet measured / open

* Tractor beam: what produces its in-game pull (a parked pair shows 0.007
  GU/s in every mode).
* Collision damage split per hull pairing (BoP → Kessok: 1417 to the
  Kessok, BoP survived at 5.2 GU/s — no clean constant).
* Warp: entry/exit velocity, in-system vs set-to-set.
* Shield regen vs a reactor that cannot supply the generator's
  `NormalPowerPerSecond` (only the generator's own power-wanted was varied).
* AI: the Warbird AI crashes the game (Bird of Prey, also a cloaker, does
  not); AI versus a player who both moves *and* shoots; the engine's
  `ArtificialIntelligence_LogAITree` is unusable here (armed after an AI
  exists it kills the process, armed at boot it stalls the load).
* Whether the Galaxy's own fire in the shooting run ever reached the
  Kessok's shields (attacker faces are not sampled yet).

---

## 11. AI behaviour (Quick Battle `BasicAttack`)

Captured with the stock Quick Battle AI left on the attacker (`--ai`),
difficulty 0.0 / 0.5 / 1.0, against a parked Galaxy with its weapons live
but nobody at the controls, from 150 GU dead ahead, 90 s, all rows at 31 ms.
The AI is the SDK's own Python (`AI/Compound/BasicAttack.py` →
`NonFedAttack` / `FedAttack`), so a remake that runs those scripts should
reproduce the *decisions*; what the oracle pins down is the *engine side*
they drive — speeds, turn rates, fire gates — and the resulting trajectory.

### 11.1 Timeline (Kessok Heavy, MED; `ai_kessok_vs_parked_galaxy_med`)

| t (s) | range (GU) | speed | what happens |
|---|---|---|---|
| 0–4 | 150 | 0 | idle (spawn settle; AI reaction 4.0 s after the sim starts) |
| 6.1 | 150 | 0.07 | target acquired; **phasers and torpedoes open at 150 GU** |
| 8–14 | 145→136 | 1.5–2.8 | throttles up and down while turning in |
| 16–32 | 130→67 | 3.7–4.1 | straight approach at full power (1.1 × MaxSpeed) |
| 34–40 | 60→47.5 | 2.5–4.2 | slows, **closest approach 47.5 GU**, turns at 0.37–0.39 rad/s |
| 40–54 | 47→106 | 4.2→**4.63** | breaks away at 1.25 × MaxSpeed, phasers only |
| 56–64 | 114→123 | 2.8→1.5 | turns back (0.33–0.40 rad/s) at the far end |
| 66–90 | 123→86 | 0.6–3.4 | second approach, torpedoes resume, throttle hunting |

Phasers were "trying to fire" 93 % of the run, torpedoes 42 %; both are
commanded whenever the target is inside the AI's range rule (here the full
150 GU — well under the 700 GU engine gate) and in arc. Result on the parked
Galaxy: all six faces down, hull −13 265, 11 subsystems hit.

### 11.2 Difficulty

| level | trajectory | phasers | torpedoes | Galaxy hull damage |
|---|---|---|---|---|
| 0.0 (LOW) | identical (min 47.6, break to 123.4) | 94 % | **never** | 5 755 |
| 0.5 (MED) | identical | 93 % | 42 % | 13 265 |
| 1.0 (HIGH) | identical | 94 % | 42 % | 13 967 |

Motion is **deterministic and difficulty-independent** for the same start;
difficulty gates weapon use (torpedoes off at LOW) and, presumably, the
accuracy/pattern flags in `BasicAttack.SetFlagsFromDifficulty`.

### 11.3 Federation attacker (`ai_galaxy_vs_parked_galaxy_med`)

`FedAttack` on a Galaxy: reaction 4.1 s, opens at 150 GU, runs passes
between ~64 and ~147 GU at **7.8 GU/s** (1.25 × 6.3) turning at 0.40 rad/s,
attacks from **above** (top face −3619, front −1854), torpedo duty only
12 %, and does 1 724 hull damage in 90 s — single-fire phasers (§2.3) make
Federation AIs slow killers.

### 11.4 Against a player who moves or shoots (`ai_kessok_vs_*_galaxy_med`)

| player behaviour | what the AI did | Galaxy shield / hull damage | Kessok hull damage |
|---|---|---|---|
| runs straight at 6.3 GU/s | head-on pass to **23 GU** at t=18 s, then a stern chase it cannot win (4.6 < 6.3): range 54 → 237 GU by t=90 s, phasers on the rear face only | front 4413, rear 3591 / 1576 | 0 |
| circles (half impulse, full yaw) | closes steadily 150 → 66 GU over 90 s, works the **rear and port** faces, hits the warp core and aft tubes | rear 3629, port 2546 / 3365 | 0 |
| parked, fires back (one phaser bank + photons, no manoeuvring) | same pass pattern as against a parked target; the Galaxy's fire never got through the Kessok's 8500-point front face | all faces / **15 000 — destroyed at t = 89 s** | **0** |

### 11.5 Bird of Prey (`ai_bop_vs_parked_galaxy_med`)

`NonFedAttack` with cloak available: reaction 4.0 s, pulse cannons and
torpedoes from 150 GU, closest approach **36.9 GU**, speed **7.75 GU/s**
(1.25 × 6.2), turns at **0.72 rad/s** (hardpoint max 0.5), all six faces
down and hull −5531 in 90 s. The Warbird AI crashes the game reproducibly
(jump to an invalid address shortly after the sim starts, `CloakAttack`
branch) — open.

### 11.6 Engine facts the AI relies on

* engines at **125 % power** (§7.1) — every AI run peaks at exactly 1.25 × MaxSpeed;
* turns commanded through the **direct** angular API (0.40 rad/s on a
  0.22-rad/s Kessok; 0.40 on a 0.28 Galaxy), so a remake must expose an
  uncapped direct command and cap only the fraction command;
* firing is a per-tick "try to fire" on every system; the engine's arc,
  range and charge gates do the rest.

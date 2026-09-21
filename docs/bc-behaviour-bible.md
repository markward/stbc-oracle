# Star Trek: Bridge Commander — measured behaviour bible

**Status:** living document (88 captures, five study matrices). Every number here was measured on the original
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

### 7.3 In-system warp (`warp_*`, player run confirmed visually)

`ShipClass.InSystemWarp(target, stopDistance)` — the AI's `Intercept` path
and the helm's in-system warp:

* **Entry is a step, not a ramp**: speed goes from whatever it was to
  **exactly 75.0 GU/s** on the next sample and holds there; identical for
  Kessok Heavy (`MaxSpeed` 3.7), Galaxy (6.3) and the player's Galaxy.
* **Duration = distance / 75**: 7.25 s for 550 GU, 25.9 s for 1950 GU
  (`warp_kessok_rest_{600,2000}`).
* **Exit**: when the remaining distance reaches ~the requested stop
  distance (asked 50, dropped out at 54–61 GU) the flag clears and speed
  steps down to the ship's **`MaxSpeed`** — Kessok 3.62, Galaxy 6.25 — then
  decays under the coast law to rest 40–50 GU from the target.
* **Pre-warp speed is not preserved**: a Kessok entering from rest and one
  entering at 3.69 GU/s both exit at 3.62 (`warp_kessok_{rest,moving}_600`).
  Exit velocity is `MaxSpeed` along the warp heading, neither zero nor the
  entry speed.

**Set-to-set warp** (`WarpSequence_Create(ship, "Systems.Vesuvi.Vesuvi5",
5.0, "Player Start").Play()`, the AI `Warp.py` recipe: warp/impulse power
on, speed and turn zeroed first; `warpset_kessok_rest_clear`, Kessok Heavy
from the Quick Battle region into Vesuvi5 with the Galaxy parked 200 GU off
the streak line) is a scripted five-phase sequence, not physics:

| phase | duration | what the samples show |
|---|---|---|
| 1. entry delay | **1.0 s** after `Play()` | parked, speed 0 (the script's `fEntryDelayTime`) |
| 2. streak in the origin set | **~2.25 s** | `GetVelocity` reports **700 GU/s** and the position really does move along the heading at that rate (−300 → +400 on the axis in 1 s) — and it **collides with anything in the way** (see below) |
| 3. the "warp" set | **exactly `warp_time`** (5.0 s) | ship parked at the origin of a set named `warp`, speed 0 |
| 4. dewarp in the destination | **~1.9 s** | appears ~640 GU from the placement and is *moved* to it (~340 GU/s) with `GetVelocity` = 0 — scripted motion, not velocity |
| 5. arrival | — | at the placement (`Player Start`), facing the placement's heading, speed 0, no rotation; the script then commands `SetImpulse(0.2)` and the ship approaches **0.740 GU/s = 0.2 × MaxSpeed** under the ordinary 1 s law (0.49 at +1 s, 0.71 at +3 s, 0.740 from +6 s) |

Total 11.5 s for a 5 s warp *for an AI ship*. **For the player ship the same
sequence takes 15.5 s** (`warpcam_galaxy`, Galaxy, `warp_time` 5.0): the
entry delay is one second longer (2.5 s from `Play()` to the streak instead
of 1.5), the streak is the same 2.0 s, the stay in the `warp` set is **7.0 s
= `warp_time` + 2.0** (the during-warp actions wait for the rendered set to
switch to the bridge), the dewarp slide is 2.0 s (838 GU → placement, ~320
GU/s) and the completed event fires 2.0 s after arrival, when control is
returned (§12.2). Contract for a remake: after a set-to-set warp
the ship is **at the placement, at rest, then creeping at 0.2 × MaxSpeed**
— it does not arrive with its pre-warp velocity (the sequence zeroes it
before entry) and it does not arrive at `MaxSpeed` as an in-system warp
does. `SetImpulse(f)` is linear in `f` below 1.0 as well: 0.2 → 0.740,
0.5 → 1.850 on the Kessok (`motion_kessok_impulse{020,050}`), and the
commanded fraction is readable back with `GetImpulse()`.

**The warp streak is a real, colliding move.** The earlier capture
`warpset_kessok_rest` had the Galaxy at the set origin, on the streak
line: at t = 2.94 s the Kessok's position crosses the origin at 700 GU/s,
speed dips to 429 for one sample and the ship comes out with an angular
velocity of **10.4 rad/s** that never decays (8.9 rad/s 27 s later —
nothing damps a free spin). The spin persists through the "warp" set and
into Vesuvi5, and with the heading turning that fast the 1 s velocity
controller only keeps the component along the spin axis: the 0.2 coast
settled at 0.370 (half) and a re-commanded `SetImpulse(1.0)` at only 1.278
(`warpset_kessok_recmd`), with `GetImpulse()` = 1.0 and impulse power = 1.0
throughout. The engine and impulse laws were never involved. Moving the
target 200 GU aside (`warp_clear=200`, `warpset_kessok_rest_clear`) gives
zero angular velocity and the 0.740 above. **Remake requirement (W3): the
warping ship keeps colliding during the outbound streak** — do not turn
collision off for the warp. The one stock exception is `AI/PlainAI/Warp.py`,
which calls `SetCollisionsOn(0)` only when the warping ship's impulse
engines are disabled (`bWarpBlindlyIfNoImpulse`). A harness must never put
anything on the warp line. Two harness notes: the destination must be given as the **system
module name**, not the set name (the script strips to the set after the
last dot and loads the system itself); and a warp with no destination
(`WarpSequence_Create(ship, None, t)`, the AI "bail out" form) removes the
ship from the world, which breaks anything still sampling it.

### 7.4 Collisions — what mass is for

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

### 7.5 Tractor beam

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
| W1 | in-system warp: step to 75.0 GU/s, duration = distance/75, exit at MaxSpeed regardless of entry speed, drop-out at the requested stop distance | exact / ±10 GU | `warp_*` |
| W2 | set-to-set warp: 1.0 s entry delay, ~2.25 s at 700 GU/s in the origin set, `warp_time` in the warp set, ~1.9 s scripted dewarp to the placement, arrive at rest and unrotated then creep to 0.2 × MaxSpeed (`SetImpulse(0.2)`) | ±0.2 s per phase; speed ±2 % | `warpset_kessok_rest_clear`, `motion_kessok_impulse020` |
| W3 | **collision stays ON during the outbound warp streak**: a ship on the streak line is hit at 700 GU/s and the warping ship arrives spinning at ~10 rad/s, undamped. The only stock exception is `AI/PlainAI/Warp.py` switching collisions off when the warping ship's impulse engines are disabled | qualitative | `warpset_kessok_rest`, `warpset_kessok_recmd` |
| C1 | collision is elastic with hardpoint masses (post-impact speeds) | ±3 % | `ram_*` |
| C2 | rammed-ship damage = 8.2 × 2μv; shields untouched | ±10 % | `ram_*` |
| P4 | bolt = script damage × emitter DamageScale; power setting changes shot cost 0.5/1/2, not damage | exact | `pulse_warbird_front_40_{meta,low,high}` |
| S6 | shield generator below DisabledPercentage ⇒ all faces 0, no regen | exact | `regen_gen{50,20}_face50` |
| S7 | port is face 4 | exact | `phaser_high_port_57` |
| V1 | player camera frustum: right 0.250, top 0.1875 at near 1.0 (28.1° × 21.2°, 4:3), far 5000 | exact | `cam_galaxy_tactical` (meta `player_camera`) |
| V2 | Chase (external view, no target): camera 17.38 GU astern and 1.74 GU above the ship origin, aimed at the origin; at steady speed it trails a further 0.26–0.29 s × speed (19.18 at 6.30 GU/s); in a 0.28 rad/s turn it swings 5.45 GU to the outside | ±0.1 GU at rest, ±5 % moving | `cam_galaxy_tactical`, `cam_galaxy_chase_impulse`, `cam_galaxy_chase_yaw` |
| V3 | Target mode (player has a target): same station as Chase, 0.35 GU higher (17.34 astern, 2.09 up), reached in 1 s | ±0.1 GU | `cam_galaxy_target` |
| V4 | cinematic mode on a parked ship: DropAndWatch at exactly 15.15 GU from the ship, aimed at it, drifting around it | ±0.1 GU | `cam_galaxy_cinematic` |
| N1 | a freshly loaded campaign mission has the player ship parked at the scripted placement (speed 0, green alert, full hull/shields, no target) and it stays parked for 90 s without input | exact | `scene_*` (11 missions) |
| N2 | every non-player object spawns at red alert (E1M1's dock scene: green) with full hull and shields; ambient traffic runs `AvoidObstacles` at 4.0 GU/s; nothing is hidden, cloaked or dying at t = 0 | exact / ±2 % | `scene_*` |
| N3 | per-mission cast, placements and 90 s autonomous evolution as tabulated in §13 / `docs/mission-scenes.md` (E2M6 fight, E3M2 Warbird warps out by 30 s, E4M5 Enterprise arrives at 46 s) | ±5 GU, ±5 s | `scene_E2M6`, `scene_E3M2`, `scene_E4M5` |
| V6 | camera-mode stations scale with the watched object's `GetRadius()`: Chase/ReverseChase 4.0 R astern/ahead + 0.1 R up, Target 3.97 R + 0.48 R, ZoomTarget 4.0 R_target short of the target, ViewscreenZoomTarget 8.0 R_target, CinematicReverseTarget 3.97 R_source beyond the source, WideTarget 31.6 R + 4.9 R; absolute GU for FreeOrbit (75), Map (1000, 10 % up), TorpCam (4.00 behind the torpedo, Chase 2.0 s after it is gone), Placement / Locked (exact); FirstPerson at the hardpoint; sweeps settle in 1.0 s (TorpCam 2 s); viewscreen directions at the model hardpoints (§12.1a) | ±2 % | `cam_galaxy_space_modes`, `cam_galaxy_cin_modes`, `cam_galaxy_viewscreen`, `cam_galaxy_torpcam`, `cam_galaxy_script_modes` |
| X3 | `CreateDisruptorModel(shell, core, length, width)`: length 1.8 → 6.0 makes the bolt 4× longer at the same width (aspect 12:1 stock), width 0.15 → 0.6 makes it 6× wider, the two colours recolour it; `GetRadius` = length / 2 | ±15 % | `docs/results/vfx/pb_*` |
| X2 | beam levers read at fire time: `MainRadius` scales the beam width linearly (9 → 44 px for 0.15 → 0.6), `CoreScale` the bright core (9 → 15 px), the four colour slots set the beam colour, `NumSides` is real geometry, the texture row band changes nothing visible; taper is at the emitter end | ±15 % on widths | `docs/results/vfx/ph_*` |
| X1 | `CreateTorpedoModel` argument semantics (core scale, flare rotation/count/length/lifespan, glow base size / pulse rate / pulse amplitude) as tabulated in §14.2; projectile `GetRadius()` = sprite bound (photon 0.770) | ±5 % on radii | `docs/results/vfx/*` |
| V5 | player warp camera choreography: pre-warp cutscene camera 30.8 GU astern within 0.2 s of `Play()`, stays put while the ship streaks away; bridge viewscreen from 2.0 s after the ship enters the warp set until 0.6 s before it leaves; destination cutscene camera 53 GU ahead of the placement, aimed at the arriving ship, live 0.6 s before the ship appears; external Chase view and control back 2.0 s after arrival | ±0.2 s, ±1 GU | `warpcam_galaxy` |

---

## 10. Not yet measured / open

* Tractor beam: what produces its in-game pull (a parked pair shows 0.007
  GU/s in every mode).
* Collision damage split per hull pairing (BoP → Kessok: 1417 to the
  Kessok, BoP survived at 5.2 GU/s — no clean constant).
* Mission scenes: 11 of 26 missions sampled (§13); the rest, and what the
  scenes do beyond 90 s / after the player acts, are not.
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


---

## 12. Camera

Sampled from the player ship (`sample=target`, rows `c`+`d`+`e`): row `d`
is the **player camera** (`Camera.MakePlayerCamera`, a `SpaceCamera` named
`MainPlayerCamera` that follows the player between sets and carries the
named modes Chase / Target / DropAndWatch / Viewscreen…); row `e` is the
**active camera of the rendered set** — what is actually on screen, which
during cutscenes is a separate `CameraObjectClass` (`CutsceneCameraBegin`)
made active in the set. All camera modes are engine-side (C++
`CameraMode`); the scripts only pick modes and set attributes, so a remake
has to reproduce the numbers below, not a script.

Harness facts: the Quick Battle intro cutscene (XO exposition) owns the
view until **t ≈ 7.3 s** after the first sample — camera scenarios act at
`fire_at` 10. In the oracle the game is in the external (tactical) view
from the first sample (`bv=0 tv=1`) regardless of `ForceBridgeVisible`.

### 12.1 Player camera, external view (`cam_galaxy_*`)

* **Frustum** (`GetNiFrustum`): right 0.250, top 0.1875 at near 1.0 →
  horizontal FOV 2·atan(0.25) = **28.1°**, vertical **21.2°** (4:3), far
  5000 GU (meta `player_camera`, every capture).
* **Chase** (no target selected; Galaxy at rest): camera at **17.38 GU
  astern, 1.74 GU above** the ship origin, exactly on the ship's centre
  line, aimed at the origin (pitched down 4°). The station is fixed in the
  ship's frame — it rotates with the heading.
* **Chase while moving** (`cam_galaxy_chase_impulse`, 0 → 6.3 GU/s): the
  camera trails farther the faster the ship goes — 17.47 at 0.47 GU/s,
  17.89 at 1.12, 18.93 at 3.47, **19.18 at 6.30** — i.e. an extra
  0.26–0.29 s × speed (0.78 GU at 3.04, 1.80 at 6.30), settled within
  ~0.5 s of the speed settling. Height stays 1.74.
* **Chase while turning** (`cam_galaxy_chase_yaw`, 0.28 rad/s at 3.04
  GU/s): the camera swings to the **outside of the turn by 5.45 GU** (an
  angular lag of 16.7° = 0.29 rad ≈ 1.0 s × ω) while still 18.16 astern
  and aimed at the ship; the swing builds over ~4 s with the turn rate.
* **Target mode** (`cam_galaxy_target`, player targets the Kessok 300 GU
  dead ahead): the hierarchy `InvalidSpace → Target → Chase` switches the
  mode the instant a target exists; the station is Chase's, lifted to
  **2.09 GU up** (17.34 astern) over 1.0 s so both ships are framed. With
  the target elsewhere than dead ahead the framing will differ — not
  measured.
* **Cinematic mode** (`cam_galaxy_cinematic`, `StartCinematicMode(0)` on a
  parked ship): the cinematic window puts the player camera into
  `DropAndWatch` (`InvalidCinematic → DropAndWatch`): **15.15 GU from the
  ship**, aimed at it, starting above and to port (8.2, −2.3, +12.5 in
  world axes) and drifting round the ship at an accelerating rate (63° in
  9 s). Tactical view is hidden (`tv=0`) and input is off.


### 12.1a The rule behind the numbers: mode attributes are in ship radii

`CameraModes.py` defines Chase as `Distance 4.0`, `DefaultPosition (0, −1,
0.1)`; the Galaxy's `GetRadius()` is **4.366** (meta `player_radius`), and
4.0 × 4.366 = 17.46 = the measured 17.47, with the 0.1 giving the 1.74 rise.
Every Chase/Target-family mode scales its distances by the **radius of the
object it watches** (`cam_galaxy_{space_modes,cin_modes,viewscreen,script_modes,torpcam}`, the
player targeting the Kessok Heavy, radius 6.174, 300 GU dead ahead;
Map-class and scripted modes are in absolute GU):

| mode (how the game reaches it) | station, measured | in radii | aimed at |
|---|---|---|---|
| Chase (`InvalidSpace → Chase`) | 17.38 astern, 1.74 up | 4.0 R, 0.1 R (player) | player |
| ReverseChase (tactical "reverse" key) | 17.38 **ahead**, 1.74 up | 4.0 R, 0.1 R | player, looking aft |
| Target (a target exists) | 17.34 astern, 2.09 up | 3.97 R, 0.48 R | player (+ target framed) |
| ZoomTarget (tactical zoom) | 275.3 ahead = **24.7 GU short of the target** | 4.0 × R_target (6.174) | the target, from the player's side |
| ViewscreenZoomTarget (bridge viewscreen, target selected) | 250.6 ahead = 49.4 GU short of the target | 8.0 × R_target | the target |
| CinematicReverseTarget (cinematic "Reverse Cyclable View") | 324.5 ahead = **24.5 GU beyond the Source** (the Kessok), 2.93 up | 3.97 × R_source, 0.47 × R_source | the player, looking back past the source |
| WideTarget (cinematic "Wide Target View") | 138.05 astern, 21.57 up | 31.6 R, 4.9 R (attributes 32 / 1.25) | player |
| FreeOrbit (cinematic "Free Orbit View", a Map mode) | 74.63 astern, 7.46 up = **75.00 GU** | absolute: `Distance 75` | player, pitched −6° |
| DropAndWatch (cinematic "Flyby View") | 15.15 GU on a fresh start, 18.6 and drifting 1.5 GU/s when entered from another mode | dynamic (`AnticipationTime 2.5`, `SideOffset 3`) | player |
| TorpCam (cinematic "Torpedo View") | sweeps from the Chase station to **exactly 4.00 GU directly behind the torpedo** (on its line, ≤ 0.1 GU off) within 2.1 s of launch and holds 4.00 for the whole 7.6 s flight of a photon to a target 150 GU away; Chase again **2.0 s** after the torpedo is gone (`DelayAfterTorpGone`) | `StartDistance 4` **in GU** (not radii); `LaterDistance 8` never engaged | the torpedo (row `f`, `cam_galaxy_torpcam`, one torpedo) |
| Map (nav map, `InvalidMap → Map`) | 995 astern, 99.5 up = **1000.00 GU**, snaps | absolute: `Distance 1000`, 10 % up | player |
| Placement (scripted `Camera.Placement`) | exactly at the placement object, aimed at the target ship, snaps | absolute | target |
| Locked spherical (`LockedSphericalLookCenter(45°, 30°, 40)`) | (24.5 ahead, 24.5 starboard, 20.0 up) = **40.00 GU**, i.e. cos 30·cos 45, cos 30·sin 45, sin 30 × distance in the ship frame, aimed at the ship's centre; snaps | absolute | ship centre |
| Locked normal (`LockedNormal(pos, fwd, up)`) | exactly at the model-space point (model +Y = ahead, +X = starboard), facing the given model-space direction; snaps | absolute | as given |
| FirstPerson (scripted) | the ship's `FirstPersonCamera` hardpoint — Galaxy 3.30 ahead, 0.31 up — looking forward; snaps | hardpoint | forward |
| `Camera.Pop()` | leaves the camera where it is with no mode | — | — |

Every switch settles in **exactly 1.0 s** (`SweepTime 1.0`; the first sample
at the final station is 1.00–1.06 s after the key), except ZoomTarget's
sibling ViewscreenZoomTarget and the six viewscreen directions, which snap
(`SweepTime 0`). Chase's `MaxLagDist 2.0` (= 8.7 GU) is the cap on the
speed lag of §12.1; the measured 1.80 GU at 6.3 GU/s is well inside it.

**Bridge viewscreen directions** (`ViewscreenDirection`, `Locked` modes at
the ship model's `Viewscreen*` hardpoints — Galaxy, GU, ship frame):

| mode | camera position (ahead, to port, up) | looks |
|---|---|---|
| ViewscreenForward | 2.90, 0, 0.50 | forward |
| ViewscreenLeft | 2.00, 2.20, 0.50 | to port |
| ViewscreenRight | 2.00, −2.20, 0.50 | to starboard |
| ViewscreenBack | 0, 0, 0.56 | aft |
| ViewscreenUp | 2.00, 0, 0.70 | up |
| ViewscreenDown | 2.00, 0, 0.00 | down |

### 12.2 What the viewer sees during a player set-to-set warp (`warpcam_galaxy`)

The Galaxy at the origin, `WarpSequence_Create(player, "Systems.Vesuvi.Vesuvi5",
5.0, "Player Start")` at t = 10.0, preceded by the helm's own pre-warp
camera (`HelmMenuHandlers.WarpPressed`: `StartCinematicMode`, `RemoveControl`,
a `PreWarpCutsceneCamera` in `DropAndWatch` with ForwardOffset −7, SideOffset
random ±7, RangeAngle 230–310°). Times are seconds after `Play()`.

| t | rendered set / active camera | mode | where the camera is |
|---|---|---|---|
| 0.0–0.2 | origin / `MainPlayerCamera` | Chase | 17.4 astern (above) |
| 0.2 | origin / **`PreWarpCutsceneCamera`** | DropAndWatch | **30.8 GU from the ship: 30.6 astern, ~3 to port, 3–5 below**, aimed at it; drifts < 1 GU/s |
| 2.5 | (same) | | ship streaks off at 700 GU/s; the camera **stays where it dropped** and tracks the ship (205 GU behind at +0.25 s, 1298 at +1.75 s) — the ship simply shrinks to a point |
| 4.5 | (same) | | ship moved to the `warp` set; origin set still rendered for 2.0 s with nothing in frame |
| 6.5 | **`bridge` / `maincamera`** | GalaxyBridgeCaptain | the bridge; the viewscreen shows the `warp` set from the player camera's `ViewscreenForward` station (2.9 GU behind and 0.5 above the ship origin, looking forward) |
| 10.9 | **Vesuvi5 / `WarpCutsceneCamera`** | DropAndWatch | switched **0.6 s before the ship appears** (`warp_time` − 0.6 after the bridge cut); camera parked **53 GU ahead of the placement**, aimed back along the arrival line |
| 11.5 | (same) | | ship appears 838 GU out and slides in at ~320 GU/s, camera tracks it (709 → 53 GU) |
| 13.5 | (same) | | ship at the placement, `SetImpulse(0.2)`; camera holds 52–53 GU ahead, drifting ~4.5 GU/s sideways |
| 15.5 | Vesuvi5 / `MainPlayerCamera` | Chase | cutscene cameras dropped, tactical view and input back; Chase re-acquires from 16.4 to 18.6 GU astern over 1 s as the ship creeps at 1.26 GU/s (= 0.2 × 6.3) |

Player camera bookkeeping during this: it moves to the `warp` set with the
ship (4.6 s), takes `ViewscreenForward` when the bridge is rendered (6.6
s), moves to Vesuvi5 with the ship (11.6 s) and returns to Chase at 15.5 s.
`IsCutsceneMode()` is **0** throughout — the warp is cinematic-window mode,
not a cutscene.

### 12.3 Harness notes (cost a session)

* A **player** set-to-set warp access-violates at the destination switch
  (fault `0x004090EB`, ~11 s after `Play()`) unless the destination set
  already exists — the engine's on-demand load of the system for the
  *rendered-set* switch is what dies. Create it first (`_create_dest_set`:
  import the system module in `QuickBattle`'s namespace and `Initialize()`).
  The AI-ship warp never rendered the destination, which is why it worked.
* The stock player warp always has the helm's pre-warp cutscene camera in
  place; replicate `WarpPressed` before `Play()` or the origin set is
  rendered through the player camera while its target leaves the set.
* The Galaxy's streak runs along its heading (−Y at the origin) — straight
  through the attacker at (0, −300, 0). `warp_clear` moves the *other*
  ship 200 GU off the line (W3).


---

## 13. Mission scenes — what a stock mission puts in the player's set

Eleven campaign missions loaded through the game's own developer path
(`MainMenu.mainmenu.RunOverrideMission`: `Options/EpisodeOverride` +
`MissionOverride`, then `ET_NEW_GAME "Maelstrom.Maelstrom"`), the mission
module's `Initialize` wrapped only to arm a sampler, **no input at all**,
every ship in the player's set dumped every 5 s for 90 s
(`scene_<mission>.json`, `Oracle/OracleScene.py`). The ten were drawn with
`random.seed(20260921).sample(...)` from the 26 shipped missions; E1M1 (the
campaign start) was added. The full per-ship tables — position, forward,
speed, hull, six shield faces, alert, AI, target, flags at t = 0, +30 s and
+90 s — are in **`docs/mission-scenes.md`** (`oracle/scene_report.py`
regenerates it). What a remake has to reproduce, mission by mission:

| mission | player (script, position) | set | other objects at t = 0 (script, AI) | what happens in 90 s of nobody touching anything |
|---|---|---|---|---|
| E1M1 | Galaxy at (1, 1, 1) facing +Y | `DryDock` | Dry_Dock ×3, Station (SpaceFacility), Nightingale (Nebula, docked at Dry_Dock2's position), Shuttle1–3 (Shuttle; 1–2 `AvoidObstacles`) | cutscene from t = 10 s onward; Shuttle1/2 fly at 4.0 GU/s (185 / 347 GU in 90 s); nothing else moves; no damage |
| E1M2 | Galaxy at (146, −90, 0) | `Vesuvi6` | Facility (FedOutpost), Debris1–6 (Asteroid variants) | cutscene t 0–40 s; static scene |
| E2M0 | Galaxy at (−825, −769, 238) | `Tevron2` | Sovereign (`PriorityList`), RanKuf, Trayor (RanKuf, `AvoidObstacles`) | no cutscene; Trayor drifts 54 GU; static otherwise |
| E2M6 | Galaxy at (309, −426, 98) | `Biranu2` | Biranu_Station (`PriorityList`), Galor_1–4, RanKuf, Trayor | cutscene t 6–60 s; **a fight plays out by itself**: Galor_1/2 front shields to 0.58/0.57, Galor_4 rear/top 0.93/0.96, RanKuf and Trayor scratched (Trayor hull 6891/7000), five ships moving at t = 90 |
| E3M1 | Sovereign at (−23, 104, 16) | `Starbase12` | Starbase_12 (FedStarbase), USS_Dauntless (Galaxy), USS_Excalibur (Ambassador), USS_Geronimo, USS_Prometheus (Nebula, `AvoidObstacles`) | cutscene the whole 90 s; Prometheus travels 181 GU |
| E3M2 | Sovereign at (146, −90, 0) | `Vesuvi6` | Facility (FedOutpost), Warbird (`AvoidObstacles`, 0.23 GU/s) | cutscene t 6–20 s; the Warbird takes `Warp` AI and is **gone from the set by t = 30 s** |
| E4M4 | Sovereign at (−33, −227, −1) | `Belaruz4` | Asteroid_1–7, Mavjop (BirdOfPrey, `AvoidObstacles`) | cutscene the whole 90 s; static |
| E4M5 | Sovereign at (−30, −156, 1) | `Starbase12` | Starbase_12, USS_Prometheus (`AvoidObstacles`) | no cutscene; Prometheus travels 296 GU; **USS_Enterprise appears at t = 46 s** (warp-in) and is moving at t = 90 |
| E4M6 | Sovereign at (−30, −156, 1) | `Starbase12` | Starbase_12 | cutscene t 0–80 s; static |
| E7M6 | Sovereign at (−30, −605, 1) | `Starbase12` | Starbase_12, USS_Geronimo, HoH'egh (Vorcha), Chilvas (Warbird) — all `AvoidObstacles` | no cutscene; the three escorts cruise 54–123 GU |
| E8M1 | Sovereign at (0, 151, 1) | `Starbase12` | Starbase_12, USS_Geronimo, USS_San_Francisco (Galaxy) — `AvoidObstacles` | no cutscene; escorts cruise 64–73 GU |

Invariants across all eleven (assertions N1–N3 in §9):

* The **player ship is parked**: speed 0.00 at every snapshot, never moves,
  green alert, full hull and shields, no target, and it carries the
  `GoForward` AI (the player's helm AI slot) in every mission.
* In every mission but E1M1, **every non-player ship, station and asteroid
  is at red alert (2)** from the first snapshot and the player is the only
  object at green (0). E1M1's dock scene is the exception: docks, station,
  Nightingale and Shuttle1/2 are at green (the `GreenAlert` AI), only
  Shuttle3 (no AI) is red.
* Ambient traffic is the `AvoidObstacles` AI at **4.0 GU/s** (shuttles,
  escorts, the Prometheus); scripted actors use `PriorityList` /
  `MainSequence` / `Warp`. No ship in these first 90 s takes damage unless
  the mission scripts a fight (E2M6), and nothing is ever hidden, cloaked or
  dying.
* All mission ships spawn with **full hull and full shields** (values are
  the hardpoint maxima — Galaxy 15000 / 8000-4000, Sovereign 12000,
  FedStarbase and BiranuStation as listed in `mission-scenes.md`).
* Missions that begin docked at Starbase 12 place the Sovereign at
  (−30, −156, 1) (E4M5, E4M6) or nearby; E1M2 and E3M2 share the Vesuvi6
  placement (146, −90, 0).

Harness notes: the mission path needs `NonSerializedObjects` in every
oracle module (`MissionLib.SaveGame` in a mission's `Initialize` pickles all
script globals — a module alias or a C handle in a global pops the debug
console and freezes the game; E1M1 does not save, the rest do); the
freeze-detector budget is the mission `duration` + 23 s; and the driver's
`PrintWindow` screenshot blocks on a frozen window — use a desktop capture.


---

## 14. Weapon visuals — how each effect is built

Read from the SDK scripts (`ships/Hardpoints/*.py`, `Tactical/Projectiles/*.py`,
`Effects.py`, `LoadTacticalSounds.py`, `Tactical/EffectTextures.py`) and the
asset files in the game copy; the unnamed model-builder arguments (§14.2,
§14.3) and the beam levers (§14.1) were then verified on the exe. The renderers
themselves are engine code — the scripts only choose assets and set the
levers below, so a remake reproduces the *parameters*, not a script.

### 14.1 Beams: phasers, beam disruptors, tractor beams (one renderer)

A beam is a **hardpoint property** on the ship (`PhaserProperty` for every
beam weapon regardless of species, `TractorBeamProperty` for tractors),
created in the hardpoint file and registered with
`g_kModelPropertyManager.RegisterLocalTemplate`. The engine draws it as a
**tube of `NumSides` sides from the emitter to the hit point**, made of two
nested layers — an outer *shell* and an inner *core* — each with a colour
at the emitter end and at the far end, and a scrolling grey texture that
multiplies the colours:

| lever (`PhaserProperty.Set…`) | Galaxy value | what it does |
|---|---|---|
| `TextureName` | `data/phaser.tga` | 64 × 32, 24-bit **greyscale noise** (rows average 167–240); the beam's brightness modulation. Species colour is *not* in the texture |
| `PhaserTextureStart` / `End` | 0 / 7 | the band of **1-pixel rows** of that texture the beam cycles through: Federation 0–7, Cardassian 8–15, Klingon and Cardassian stations 16–23, Romulan and Kessok 24–31 (the whole 32-row image is divided into four 8-frame animations) |
| `TextureSpeed` | 2.5 | scroll rate of the texture along the beam (Sovereign 2.0) |
| `LengthTextureTilePerUnit` | 0.5 | texture repeats per GU of beam length (Sovereign 1.0) |
| `PerimeterTile` | 1.0 | repeats around the circumference |
| `NumSides` | 6 | tube cross-section |
| `MainRadius` | 0.15 GU | shell radius (Marauder 0.30, Shuttle 0.02) |
| `CoreScale` | 0.5 | core radius as a fraction of the shell (Marauder 0.2, Sunbuster 0.3) |
| `TaperRadius`, `TaperRatio`, `TaperMinLength`, `TaperMaxLength` | 0.01, 0.25, 5, 30 | the beam narrows to `TaperRadius` over the last `TaperRatio` of its length, the tapered part clamped to 5–30 GU |
| `PhaserWidth` | 0.3 | the beam's collision/hit width (every stock beam 0.3) |
| `OuterShellColor`, `InnerShellColor`, `OuterCoreColor`, `InnerCoreColor` | see below | RGBA at the two ends of each layer |
| `Width`, `Length` | 1.33, 1.01 | the emitter's firing-arc extents, not the drawn beam |
| `FireSound` | `"Galaxy Phaser"` | the engine plays **`<name> Start`** then loops **`<name> Loop`** (`LoadTacticalSounds`: `sfx/Weapons/galaxy_phaser_a.wav` / `_b.wav`) |

Species palettes (outer shell / inner shell / outer core / inner core, RGB 0–1):

| beams | shell out | shell in | core out | core in | texture rows | sound |
|---|---|---|---|---|---|---|
| Federation phasers (Galaxy, Sovereign, Akira, Nebula, Ambassador, stations, shuttles) | 1.00 0.16 0.00 | same | 0.99 0.83 0.64 | 0.99 0.90 0.86 | 0–7 | `Galaxy Phaser` / `Akira Phaser` / `Ambassador Phaser` |
| Cardassian beams (Galor, Keldon, hybrid) | 1.00 0.50 0.00 | 1.00 0.50 0.25 | 1.00 1.00 0.00 | 1.00 1.00 0.50 | 8–15 | `Galor Phaser` / `Card Phaser` |
| Cardassian stations | 0.50 0.25 0.00 | 0.50 0.50 0.00 | 1.00 1.00 0.00 | 1.00 1.00 0.50 | 16–23 | `Galor Phaser` |
| Klingon beam (Vor'cha "Disruptor") | 0.50 0.00 0.00 | same | 1.00 0.00 0.00 | 1.00 0.50 0.50 | 16–23 | `Vorcha Phaser` |
| Romulan beam (Warbird "Disruptor") | 0.00 0.50 0.00 | 0.00 0.50 0.25 | 0.50 1.00 0.00 | 0.50 1.00 0.50 | 24–31 | `Warbird Phaser` (`romulan phaser_a/b.wav`) |
| Kessok Heavy beam | 0.00 0.00 1.00 | 0.00 0.50 1.00 | 0.00 1.00 1.00 | 0.50 1.00 1.00 | 24–31 | `Kessok Phaser2` (`kessock beam2_a/b.wav`) |
| Kessok Light beam | 0.00 0.50 0.75 | 0.00 0.50 1.00 | 0.50 1.00 1.00 | 0.00 1.00 1.00 | 24–31 | `Kessok Phaser` |
| Ferengi Marauder | 1.00 0.50 0.00 | 0.50 0.25 0.00 | 1.00 0.50 0.25 | 1.00 1.00 1.00 | 8–15 | `Marauder Phaser` |
| **Tractor beam** (every ship) | 0.40 0.40 1.00 | same | same | same | row **32** of `data/Textures/Tactical/TractorBeam.tga` | `Tractor Beam` (`sfx/Weapons/tractor.wav`) |

The tractor is the same tube with `TractorBeamWidth 0.3`, a 64 × 64 texture
that is pure white with an alpha-noise pattern (alpha 84–131 per row), a
single texture row (`TextureStart = TextureEnd = 32`) so it does not
animate, and one flat blue-violet colour for all four colour slots.
`data/Textures/Tactical/PhaserLights.tga` (32 × 32 radial white sprite,
centre α 251 → edge 15) is the only other beam asset in the folder; it is
not referenced from any script, so it is the engine's emitter glow.

**Verified on the exe** (`docs/results/vfx/ph_*.png`, `vfx_ph_*.json`): the
player's eight `PhaserProperty` objects were patched at runtime
(`cam_mode` step `phaserpatch:<Attr>=<v>`), one bank fired at the Kessok
60 GU dead ahead, six chase-view frames measured along the beam
(`oracle/vfx_measure.py` style row scan, width of the bright column and
its centre colour):

| lever changed | stock frame | changed frame | reading |
|---|---|---|---|
| `MainRadius` 0.15 → 0.6 | width 9 px | **44 px** | shell radius, linear (`ph_radius_00.png`) |
| `CoreScale` 0.5 → 1.0 | 9 px | 15 px | core radius = CoreScale × shell (`ph_core_00.png`) |
| four colour slots → 0,0,255 | centre RGB 248,194,165 | **29,26,244** | the colours are the beam's colour, read at fire time (`ph_blue_00.png`) |
| `NumSides` 6 → 3 | 9 px | 5 px, patchy | real tube geometry — fewer sides, thinner edge-on (`ph_sides_00.png`) |
| `PhaserTextureStart/End` 0–7 → 24–31 | 9 px, 248,194,165 | 9 px, 247,190,161 | **no visible change** — the rows are grey-noise modulation only, species colour is not in the texture (`ph_rows_00.png`) |

The beam is **thin at the emitter and full width at the far end** in every
frame — the taper (`TaperRadius` 0.01 → `MainRadius` over `TaperRatio`
of the length, clamped 5–30 GU) is at the emitter end. Taper lengths and
`TextureSpeed` were not varied. Locked/Placement cutscene cameras are not
a way to film beams: the beam is only in frame from Chase-family views in
these runs.

Beam identification for a remake: emitter = hardpoint name (`"Ventral
Phaser 3"`), position (`SetPosition`), orientation and arcs; look = the
row band + four colours + radii above; sound = `FireSound` + " Start"/" Loop".

### 14.2 Torpedoes (`Torpedo.CreateTorpedoModel`)

A torpedo has no mesh. Each projectile script in `Tactical/Projectiles/`
(selected by the tube's ammo type, `TorpedoTubeProperty` → `GetName()` /
`GetLaunchSpeed()` / `GetLaunchSound()` / damage etc., see §4) calls
`CreateTorpedoModel` with 14 positional arguments that build **three sprite
layers** at the projectile's position. The SDK carries no argument names;
the readings below were **verified on the exe** by replacing
`PhotonTorpedo.Create` at runtime with one argument changed (`vfx_patch`),
firing one photon under TorpCam (camera 4.00 GU behind it, §12.1a) and
measuring 12 screenshots 0.25 s apart (`run_oracle.py --shot-on stopfire`,
`oracle/vfx_measure.py`; frames and captures in `docs/results/vfx/`), plus
the projectile's own `GetRadius()` — its bounding radius — in row `f`:

| # | Photon | Quantum | argument | evidence |
|---|---|---|---|---|
| 1 | `data/Textures/Tactical/TorpedoCore.tga` | same | **core** sprite: 32 × 32 white, alpha 255 at the centre → 0 at the edge (a hard dot) | file |
| 2 | core colour 255,252,100 (yellow-white) | 222,222,253 | core RGBA | the stock frames show a yellow-white dot inside an orange halo (`stock_04.png`) |
| 3 | 0.2 | 0.2 | **core scale** | 0.2 → 0.8: core radius 21 px → 90 px in every frame (×4.2); `GetRadius` 0.770 → 0.906 (`core_00.png`) |
| 4 | 1.2 | 1.0 | **flare rotation rate** | with flares made permanent (arg 14 = 100): at 1.2 the dominant flare directions move every frame; at 0 the same three direction bins hold for all 8 frames (histogram change ≤ 0.08 vs 0.3–0.8) (`life100_07.png`, `life100rot0_04.png`) |
| 5 | `TorpedoGlow.tga` | same | **glow** sprite: 32 × 32 white, alpha 160 centre → 0 edge (soft halo) | file |
| 6 | glow colour 255,65,0 (orange) | 61,98,239 (blue) | glow RGBA — the species colour | stock frames: orange halo |
| 7 | 3.0 | 4.0 | **glow pulse rate** | stock halo radius swings 59 ↔ 107 px between frames 0.25 s apart; at 0.5 it holds 100–115 px across frames (`pulse_01.png`) |
| 8 | 0.3 | 0.3 | **base glow size** | 0.3 → 1.0: halo radius 115–168 px vs 59–107 (`min1_06.png`) |
| 9 | 0.6 | 0.6 | **glow pulse amplitude** — *not* "growth" that can be zeroed safely | at 0 (with arg 8 at 0.3 or 1.5) the halo is absent in most frames (radius = core edge) and the bounding radius pulses 0.80–1.04 GU; the engine degenerates rather than holding the base size (`growth0_04.png`, `glowbig_01.png`) |
| 10 | `TorpedoFlares.tga` | same | **flares**: 32 × 64 white streak sprite (alpha 255 centre line → ~2 edges) | file |
| 11 | flare colour = glow colour | = glow colour | flare RGBA | stock frames: orange streaks |
| 12 | 8 | 12 | **flare count** | 8 → 0: no streaks in any frame (`flares0_00.png`) |
| 13 | 0.7 | 0.5 | **flare length** | 0.7 → 2.5: streak reach 291 → 514 px (frame-limited); `GetRadius` 0.770 → 2.557 (`flarelen_01.png`) |
| 14 | 0.4 | 0.4 | **flare lifespan** (s) | 0.4 → 100: streaks persist and pile up (flare pixels 17 000 vs ≤ 10 000) instead of respawning (`life100_07.png`) |

A torpedo's `GetRadius()` (0.770 GU stock photon, `cam_galaxy_torpcam`) is
therefore the sprite bound — core scale, flare length and the pulsing glow
all move it — not a physics size.

Every stock torpedo uses the same three textures; only colours, counts and
speeds differ:

| script | core RGB | glow RGB (flares = glow unless noted) | speed GU/s | launch sound (`sfx/Weapons/…`) |
|---|---|---|---|---|
| `PhotonTorpedo`, `PhotonTorpedo2` | 255,252,100 | 255,65,0 | 19 | `Photon Torpedo` (`Photon Torp.wav`) |
| `QuantumTorpedo` | 222,222,253 | 61,98,239 | 22 | `Quantum Torpedo` |
| `KlingonTorpedo` | 250,218,202 | 190,49,48 | 10 | `Klingon Torpedo` |
| `CardassianTorpedo` | 250,200,202 | 255,45,0 | 15 | `Cardassian Torpedo` |
| `PositronTorpedo` / `2` (Kessok) | 181,230,253 | 65,82,255 (flares 236,255,17) | 3.8 / 5.0 | `Positron Torpedo` |
| `AntimatterTorpedo` | 240,60,10 | 180,40,40 (flares 80,120,70) | 35 | `Antimatter Torpedo` |
| `PhasedPlasma` | 240,0,15 | 100,40,40 (flares 80,60,70) | 12 | `Antimatter Torpedo` |

The composite is: hard core-coloured dot, pulsing coloured halo (size cycling
between #8 and #8+#9 at rate #7), `#12` coloured streaks rotating about the
core at rate #4 and respawning every `#14` s. Launch sound = `GetLaunchSound()`; flight: §4 (Photon guidance 6 s,
0.15 rad/s² turn).

### 14.3 Pulse bolts (`Torpedo.CreateDisruptorModel`)

Pulse weapons (`PulseWeaponProperty` on the hardpoint: `FireSound
"Pulse Disruptor"` = `sfx/Weapons/Pulse Disruptor.wav`, `MaxDamage`,
charge — §3) fire projectiles from the same `Tactical/Projectiles`
scripts, whose `Create` calls `CreateDisruptorModel(outerShellColor,
outerCoreColor, length, width)` — a **two-colour elongated bolt** (shell
around a brighter core), no texture:

| bolt script | shell | core | length × width | speed GU/s | lifetime s | launch sound |
|---|---|---|---|---|---|---|
| `Disruptor` (Klingon) / `RomulanCannon` | 0.01 1.00 0.01 (green) | 0.64 1.00 0.64 | 2.0 × 0.2 | 43 | 8 | `Klingon Disruptor` (`Disruptor Cannon.wav`) |
| `PulseDisruptor` (Bird of Prey) | 0.17 1.00 0.17 | 0.64 1.00 0.64 | 1.8 × 0.15 | 55 | 8 | `Klingon Disruptor` |
| `CardassianDisruptor` | 1.00 0.00 0.00 (red) | 1.00 0.17 0.17 | 1.8 × 0.15 | 42 | 10 | `Klingon Disruptor` |
| `FusionBolt` (Ferengi) | 1.00 0.38 0.00 (orange) | 1.00 0.87 0.66 | 2.8 × 0.17 | 46 | 8 | `Klingon Disruptor` |
| `KessokDisruptor` | 0.17 0.17 1.00 (blue) | 0.64 0.64 1.00 | **11 × 0.6** | 27 | 12 | `Cardassian Torpedo` |

**Verified on the exe** (`docs/results/vfx/pb_*.png`, `vfx_pb_*.json`):
Bird of Prey as the player, `PulseDisruptor.Create` replaced with one
argument changed and the launch speed patched to 3 GU/s so the bolts
linger, a Locked camera 20 GU behind and 50° above, ten frames from the
moment of firing; the two bolts measured by principal axes of their
green/blue pixels, plus the bolt's `GetRadius()` in row `f`:

| argument | stock | changed | on screen | `GetRadius` |
|---|---|---|---|---|
| 3 length | 1.8 | 6.0 | bolt **87 → 350 px long** at the same width (7 → 9 px); aspect 12 : 1 stock = 1.8 / 0.15 exactly | 0.900 → **3.000 = length / 2** |
| 4 width | 0.15 | 0.6 | **7 → 45 px wide**, and 1.9× longer (the shell scales with width) | 0.900 → 0.975 |
| 1, 2 colours | green 0.17/1/0.17 + 0.64/1/0.64 | blue 0,0,255 + 200,200,255 | centre RGB 66,195,66 → **74,73,198** | — |

TorpCam does not follow bolts (it stays in Chase), and from a chase view
the bolts leave the wing-tip cannons below the frame edge — the high rear
Locked station is the way to film them.

### 14.4 Impacts — what is composited on a hit

The engine raises the hit and calls the Python hooks in `Effects.py`
(`TorpedoShieldHit`, `TorpedoHullHit`, `PhaserHullHit`; the shield flare for
beams is engine-side using `data/Textures/Tactical/shieldhit01–04.TGA`,
four 32 × 32 inverse-radial masks — dark centre, bright rim — stamped on the
shield surface at the hit point). Everything below is emitted **at the hit
point, along the hit normal, attached to the target's node** (`GetObjectHitPoint`,
`GetObjectHitNormal`), and scaled by the *weapon's* `DamageRadiusFactor` × the
target radius (`pEvent.GetRadius()`, the same radius that sets the damage
footprint in §6):

| hit | always | at effect level ≥ MEDIUM | sound |
|---|---|---|---|
| torpedo on shields | `CreateWeaponExplosion(radius × 3, life 1.25 s)` | — | random `Explosion 1–19` (`sfx/Explosions/explo1–19.WAV`), 3-D at the target |
| torpedo on hull | same explosion | 50 %: sparks 1.0 s; 20 %: smoke jet 1–3 s starting 0.5 s later | same |
| beam on hull | only on 50 % of hits: 50 % of those get an explosion (radius × 2, 1.0 s) with sound | 50 %: sparks; 30 %: smoke jet | with the explosion only |

`CreateWeaponExplosion` at HIGH detail is an `AnimTSParticleController`
"puff": particles emitted from a radius of 0.25 × size every 0.09 s for
1.5 s, growing 0.1 → 0.5 → 1.6 → 2.0 × size over their life, colour white
until 60 % then fading to (5, 5, 35)/255, alpha 1 → 0.5 at 70 % → 0; texture
`data/Textures/Effects/ExplosionA.tga` (256 × 256, an 8 × 8 animated sheet,
additive blend) 70 % of the time, else `ExplosionB.tga`; on 50 % of HIGH hits
2–7 extra "plume" emitters in a 120° cone at 0.2 × size. MEDIUM uses a
lighter puff with plumes on 10 %; LOW a single puff. Sparks are a
`SparkParticleController` on `data/rough.tga`: 2.5 GU/s, 120° variance, tails
0.1–0.2, size 0.01 → 0.04 → 0.01, white→fade, damping 0.3, emit every 5 ms
for the duration. Smoke is `CreateSmokeHigh` on `ExplosionB.tga`.

Ship death (`ObjectExploding` / `CreateObjectExplosion`) reuses the same
puff/plume/smoke builders at the ship's radius with `Death Explosion 1–6`
(`explo_flame_01–06.WAV`) — not weapon VFX, noted for completeness.

### 14.5 Asset inventory (the game copy, `data/`)

| file | size | used by |
|---|---|---|
| `phaser.tga` | 64 × 32, 24-bit grey | every beam weapon (row bands per species) |
| `Textures/Tactical/TractorBeam.tga` | 64 × 64, white + alpha noise | tractor beams (row 32) |
| `Textures/Tactical/PhaserLights.tga` | 32 × 32 radial | engine beam glow (no script reference) |
| `Textures/Tactical/TorpedoCore.tga`, `TorpedoGlow.tga` | 32 × 32 radial | torpedo core / halo |
| `Textures/Tactical/TorpedoFlares.tga` | 32 × 64 streak | torpedo flares |
| `Textures/Tactical/shieldhit01–04.TGA` | 32 × 32 inverse radial | shield impact stamp (engine) |
| `Textures/Effects/ExplosionA.tga` (RLE), `ExplosionB.tga` | 256 × 256 sheets | hit puffs, plumes, smoke, death |
| `rough.tga`, `spark.tga`, `sphere.tga` | 64 × 64 | sparks (space), bridge sparks/smoke |
| `sfx/Weapons/*.wav`, `sfx/Explosions/explo*.WAV` | — | `LoadTacticalSounds` name → file table |

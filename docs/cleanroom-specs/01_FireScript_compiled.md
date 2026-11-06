# FireScript as the shipped game runs it

Clean-side behavioural specification. Behaviour, constants and measurements only.

## Context

The SDK's `AI.Preprocessors.FireScript` says its script "is only used for setup. Once the AI
containing it is created, it's replaced with an optimized version in the code." Measured on the
original game: the Python `FireScript.Update` is never called in play. The engine copies the Python
instance's settings and runs its own node. This specification describes that node. The settings it
reads are the SDK class's own fields: the weapon list `lWeapons`, `bEnabled`, `idTargetedSubsystem`,
`bAttackIfNoSubsystemsLeft`, `bChangePowerSetting`, `bHighPower`, `bSmartPhasers`, `bDumbFireTorps`
and `bCallUsingWeaponTypeFunc`. The SDK helper methods named below (`TargetInRange`,
`TargetVisible`, `ChooseTargetSubsystem`, `CheckGoodShot`, `WeaponTooDangerous`, `StopFiring`, the
tractor and torpedo-type parts of `ConfigureWeaponSystem`) keep their SDK behaviour.

## Cadence

The node asks to be updated every **0.1 s** of game time. Its updates alternate between two kinds:

1. **Aim tick**: check visibility, then choose the target subsystem.
2. **Fire tick**: decide and fire every weapon system in the list, once each.

So each weapon system is re-decided every 0.2 s, whatever the number of systems. (The SDK Python
body decides one system per 0.2 s update.)

## One update

1. With no ship, or no target, the node reports done. (Dauntless's existing non-lethal wrapper for
   this preprocessor already turns that into "run the contained AI"; keep that.)
2. If the weapon-type broadcast flag is set, call `UsingWeaponType` with the weapon list on every AI
   in the ship's tree below the root, then clear the flag. While torpedoes are excluded (see
   Configure), torpedo systems are left out of the list passed.
3. If the node is not enabled, or the weapon list is empty, return "run the contained AI".
4. At the start of each aim tick, and on any tick while the target is not known to be visible:
   the target is visible when it is both in range and visible by the SDK helpers. If it is not,
   stop firing everything and stay at the start of the cycle; the next update tries again.
5. On an aim tick with a visible target, choose the target subsystem (SDK helper).
6. On a fire tick: look up the targeted subsystem from its stored id. For each weapon system in
   turn, if there is no targeted subsystem and the node is not set to attack when no subsystems
   are left, stop firing; otherwise fire that system at the target (next section).
7. Return "run the contained AI".

## Firing one system at the target

1. Configure the system (next section). If that fails, stop **this system** firing at the target
   and finish. (The SDK Python leaves it firing.)
2. If the SDK's good-shot check fails, stop this system firing at the target and finish.
3. Dumb-fire torpedoes: when the node is set to dumb-fire and the system is a torpedo system, every
   tube whose rough direction points toward the aim point (positive dot product with the vector from
   the system to the targeted subsystem, or to the target when none) fires dumb, and nothing else
   happens.
4. Otherwise start firing at the target, with the targeted subsystem's position as the offset (the
   zero vector when there is no subsystem).

## Configure

1. Too dangerous (SDK test): if the system is a torpedo system and torpedoes are not already
   excluded, exclude them and set the weapon-type broadcast flag. Configure fails.
2. A torpedo system that is no longer too dangerous while torpedoes are excluded: include them again
   and set the broadcast flag.
3. A phaser system that is not a tractor:
   - The phaser power level is set (high when `bHighPower`, else low) **only when
     `bChangePowerSetting` is set**. The SDK ignores that flag.
   - Without `bSmartPhasers`, configure succeeds.
   - With it, apply the smart-phaser rule (next section) and update this node's accumulator by the
     game time elapsed since its last update: it rises by **0.05 per second** while the rule passes
     (capped at 1) and falls by **0.025 per second** while it fails (floored at 0). Configure succeeds
     exactly when the rule passes.
4. Tractor and torpedo systems: the SDK's own configuration (tractor mode, torpedo-type choice).

Each node has its own accumulator, starting at 0 when the node is created, with its clock at the
creation time.

## The smart-phaser rule

`bSmartPhasers` means "may hold phasers for a good shot". The SDK's `BasicAttack` turns it on only
at AI difficulty 1.0.

- R is the maximum damage distance of the phaser system's first bank (1 when the system has no
  banks). d is the distance from the phaser system's world position to the aim point (the targeted
  subsystem, or the target).
- If d is less than 2R, fire.
- If d is more than 6R, hold.
- Between them, let x be (6R minus d) divided by 4R, and let s be 1, except when the target ship's
  shields are on and not disabled and the face toward the shooter is stronger than avg, the sum of
  the other five faces divided by 5. In that case s is the arctangent of (avg divided by that face's
  strength), divided by a quarter turn (pi/2). The face toward the shooter is chosen the way a hit
  from the shooter's position chooses its face. Fire when s plus the accumulator plus x is greater
  than **1.75**.

## Measured consequences (original game, matrix of 2,184 AI difficulty 1.0 duels)

- Cardassian ships, whose first bank is a 30 GU forward beam, fire beams only inside their
  close-range branch: 0% of about 20,000 samples with the mid-range branch in focus.
- Each ship's first beam shot comes at d under 3R: Galor, Keldon and Cardassian Hybrid median 83 GU
  from a 100 GU start. Federation ships (R 60-70) fire at once.

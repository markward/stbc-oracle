# ManagePower as the shipped game runs it

Clean-side behavioural specification. Behaviour, constants and measurements only.

## Context

The SDK's `ManagePower.Update` is a stub ("Unused"); the shipped game runs an engine node instead.
It reads `bConservePower` from the Python instance it replaces: `CloakAttack` passes 1,
`FedAttack` and `NonFedAttack` pass 0. Every **3.0 s** it sets the wanted power level of each
powered system on its ship, and it always reports "run the contained AI".

## The budget

Let A be the main battery's power, L its limit, P the power plant's output (already scaled by the
plant's condition), and S the power available through the conduits: the smaller of A and the main
conduit capacity, plus the smaller of the backup battery's power and the backup conduit capacity.

- With no battery limit (L at most 0), the budget is P.
- The threshold T is 0.9 L, or 1.0625 L when conserving power.
- The battery factor f is half of A divided by T when A is below T; otherwise 1 minus half of
  (L minus A) divided by (L minus T).
- When f is below 0.5, the budget is P times 2f plus 0.1 P times (1 minus 2f). This equals
  P times (0.1 plus 0.9 A divided by T): below the plant's output.
- Otherwise, the budget is P times (2 minus 2f) plus (2f minus 1) times S: the output at T, rising to
  S on a full battery.

When conserving, A is always below 1.0625 L, so a cloaking ship's budget stays below its output
(about 0.94 times it on a full battery).

## The split

Every powered system of the ship takes part, except the power plant itself and the cloaking device
(never touched; it keeps its own level). Each system has a weight: sensors 0.25, warp engines 0.05,
everything else 1. Each has a normal demand: 0 when it is disabled or off, and 0 for a tractor that
is not firing; otherwise its normal power per second.

Let W be the sum of the weights. Repeat:

1. For each system still in the split, its share is its weight divided by W, times the budget; its
   level is that share divided by its normal demand (0 when the demand is 0).
2. Any system whose level would be above **1.25** is set to 1.25 and leaves the split: 1.25 times
   its normal demand comes off the budget, and its weight comes off W. Every other system is set to
   its level.
3. If anything was capped, repeat with the remaining systems; otherwise stop.

A system that wants no power still keeps its weight, so its share is simply lost. That dead weight,
and the conserve-mode budget, are what an earlier fitted model lacked.

## Measured

Measured against 2,000+ logged power updates per class, with no fitting: the medians match exactly
for the Galaxy, Galor, Vor'cha, Warbird, Kessok Light, Kessok Heavy and Bird of Prey. A
consequence: AI ships run their impulse engines at 125% (bible A4: every AI run peaks at exactly
1.25 times MaxSpeed; Kessok 4.63).

# AvoidObstacles as the shipped game runs it

Clean-side behavioural specification. Behaviour, constants and measurements only.

## Context

Like FireScript, the SDK's `AI.Preprocessors.AvoidObstacles` is replaced in the shipped game by an
engine node. That node reads **none** of the Python instance's settings: `fPredictionTime`,
`fPersonalSpace` and the update delays the SDK sets are all ignored. It asks to be updated again at
once, so it runs every time the AI tree reaches it.

## Constants

| Name | Value |
|---|---|
| Look-ahead | 10 s |
| Step | 0.5 s (20 steps) |
| Personal-space factor | 2.5 at speeds up to 0.1 GU/s, 4.0 at 2.0 GU/s and above, linear between |
| Minimum query radius | 225 GU |
| Big-obstacle threshold | 25 GU |
| Big-obstacle inflation | the smaller of 1.25 r and r + 125 |
| Obstacle memory | 1.0 s |
| Favourability | minus 50 divided by the obstacle's distance |
| Blocked factor | 3.25 |
| Forward factor | minus 0.25 |
| "Moving" speed | above 0.0625 GU/s |
| Impulse power while avoiding | 1.25 (125%) |

## One update

1. No ship: Dauntless policy, keep running the contained AI (the engine's own value is "done";
   the project's non-lethal rule applies).
2. If the ship is doing an in-system warp, has no impulse engines, or its impulse engines are
   disabled, run the contained AI.
3. Test the course (below). If it returns a direction and a speed:
   - turn the ship toward that direction and set its impulse to that speed along model forward;
   - for any ship other than the player's: remember the impulse engines' wanted power the first time
     (only if nothing is remembered yet) and set it to 1.25;
   - report "skip the contained AI, stay active".
4. Otherwise, if a wanted power was remembered, restore it and forget it; run the contained AI.

## Testing the course

Inputs: the ship's position p, world velocity v, world acceleration a (as `GetAccelerationTG`
reports it), and its radius.

1. Predicted point C is p plus v times 10 s plus half of a times (10 s) squared. D is the distance
   from p to C.
2. Personal space R is the ship's radius times the personal-space factor at the ship's speed.
3. Query radius Q is the larger of D plus R, and 225 GU.
4. Candidates are the other objects of the ship's set that take part in proximity (the ones the
   set's proximity index holds), whose surface is within Q of C: their centre distance to C minus
   their radius is at most Q. Leave out cloaked ships. Leave out the types the existing SDK-based
   code already never avoids.
5. For each candidate, decide whether it must be avoided (next section). Each one that must be is
   added to the current list and stamped with the current time in the node's memory.
6. Memory: any object stamped within the last 1.0 s that is not in the current list, and is still
   in the ship's set, is added at its current position and velocity without being tested again.
   Older or departed entries are forgotten. So one detection holds the avoidance for at least a
   second.
7. With nothing in the list, there is nothing to avoid. Otherwise choose the flee direction and
   speed (last section).

## Must it be avoided?

For one obstacle with centre o, velocity w, acceleration b and radius r:

1. Its effective radius is r, or, when r is over 25 GU, the smaller of 1.25 r and r + 125.
2. If the centre distance between ship and obstacle is less than R plus the effective radius, yes.
3. An object without physics (a planet, a rock) has zero velocity and acceleration.
4. Step both bodies forward 20 times by 0.5 s. In each step, each body's position moves by its
   velocity times the step plus half its acceleration times the step squared, and then its velocity
   grows by its acceleration times the step (acceleration held, no speed limit). Within each step,
   treat the relative motion as a straight segment: yes if the obstacle's centre comes within R
   (the personal space only; the obstacle's radius does not enter here) of the ship at any fraction
   of the step from 0 inclusive to 1 exclusive.
5. Otherwise no.

## Choosing the flee direction

For each obstacle in the list: its unit direction from the ship, its velocity, its favourability
(minus 50 divided by its distance), and its blocked cone. The cone is the cosine of the half-angle
the obstacle subtends: with rs the obstacle's radius plus the ship's radius, 0 when the distance is
at most rs, else the square root of (distance squared minus rs squared), divided by the distance.

The appeal of a candidate unit direction t, summed over every obstacle:
- If t points into the obstacle's cone (the dot of t with the obstacle direction is at least the
  cone value): add 3.25 times the favourability, and nothing else for this obstacle.
- Otherwise, if the obstacle is moving (speed above 0.0625):
  - add 2 times the favourability times (|cos| between t and the obstacle's velocity direction,
    minus 0.5);
  - then take t and the obstacle direction, each with its component along the velocity direction
    removed and normalised, and let c be their dot product. Add 2 times the favourability times
    (c minus 0.5) when c is at least 0, else the favourability times (minus 1 minus c).
- Otherwise (not moving): add 2 times the favourability times ((the dot of t with the obstacle
  direction, plus 1) divided by (the cone value plus 1), minus 0.5).
- For every obstacle not skipped by the cone rule, also add minus 0.25 times the favourability
  times the dot of t with the ship's forward direction.

Candidates, in this order: the opposite of each obstacle's direction, then the 26 unit directions
of the cube lattice (each of x, y and z in {-1, 0, 1}, not all zero, normalised). The flee direction
is the candidate with the highest appeal; the earliest wins a tie. The flee speed is 0 when the
ship's forward direction lies inside any obstacle's cone, else 1.

## Dauntless policies to keep (pre-existing, not from the original)

- A pair with collisions disabled between them (`EnableCollisionsWith`, e.g. a ship docking with a
  starbase) is never an obstacle.
- Large rock-field rocks, which are not set objects, are offered as static obstacles through the
  same test.

## Measured in the original

Avoidance episodes last a median of 2.1 s (90th percentile 5.7 s), and the node re-issues its
command every few frames. The SDK script Dauntless ran before released after a median of 0.25 s, so
a ship never built up the escape speed that keeps a closing cloaker at 50-100 GU.

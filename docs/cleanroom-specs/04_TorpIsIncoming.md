# Which torpedoes count as incoming

Clean-side behavioural specification. Behaviour, constants and measurements only.

## Context

`AIScriptAssist_TorpIsIncoming` and `AIScriptAssist_GetIncomingTorpIDsInSet` (the latter asks the
former about every torpedo in the set) back the SDK's `ConditionIncomingTorps`. The engine's rule,
for a torpedo, an observing ship, a danger threshold in seconds and an optional source filter:

1. When the source filter is armed, the torpedo's firing object must be the given one.
2. The torpedo must be in the observing ship's set.
3. The torpedo's **target** must be the observing ship. A torpedo aimed at someone else, an
   unguided one, or the ship's own never counts, however it flies.
4. It must be moving toward the ship: the dot product of (torpedo position minus ship position)
   with the torpedo's velocity is at most 0.
5. Its distance to the ship divided by **the torpedo's own speed** (not a closing speed) must be
   less than the threshold.

## Measured consequence

The SDK-inferred rule Dauntless used counted any projectile closing on the ship, so pulse bolts and
torpedoes aimed elsewhere (and the ship's own, launched from behind its centre) flickered
`ConditionIncomingTorps`. A Vor'cha's IncomingTorps went true 5.96 times a minute for a median
0.5 s, against 1.76 times a minute for 5.0 s in the original. Each flicker re-armed CloakAttack's
15 s ConditionTimer through the branch it interrupts, so the Vor'cha never left its torpedo run and
fought at point blank.

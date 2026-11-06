# SequenceAI: reset if interrupted

Clean-side behavioural specification. Behaviour, constants and measurements only.

## Behaviour

`SequenceAI.SetResetIfInterrupted(flag)` stores a flag that is read in exactly one place: when the
sequence is **deactivated**. Deactivation clears the sequence's active state and deactivates its
current child. Then, if the flag is set, the sequence resets:

- its remaining-loop count goes back to its loop count;
- it has no current child, so when it is next reached it starts again at its **first** child;
- each child is reset as it becomes current again, before it is activated.

With the flag clear, a deactivated sequence resumes where it was.

## Why it matters

A priority list deactivates every child below the one it is running. CloakAttack's
`OuterSequence` sets the flag, so whenever `EvadeIncomingTorps` or `WayTooFar` takes the list from
it, it later restarts at `FarEnough_TimeNotPassed`: the attack phase, with its 15 s timer re-armed.

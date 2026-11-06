# Clean-room specifications

Behavioural specifications for five Dauntless behaviours, written under
stbc_reference's CLEANROOM-RULE: behaviour, constants and measurements only,
no code. Each passes `check_cleanroom.py --tier T3` with no findings.

They were implemented in Dauntless by an agent that read only these
specifications, the clean reference corpus, the SDK and Dauntless itself; it
never saw the original program or any earlier implementation. Each resulting
Dauntless commit names its specification.

| Specification | Dauntless behaviour |
|---|---|
| 01_FireScript_compiled.md | the FireScript node the shipped game runs |
| 02_AvoidObstacles_compiled.md | the AvoidObstacles node the shipped game runs |
| 03_ManagePower_compiled.md | the AI's power budget and split |
| 04_TorpIsIncoming.md | which torpedoes count as incoming |
| 05_SequenceAI_ResetIfInterrupted.md | SequenceAI reset when interrupted |

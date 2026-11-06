# Native capture plugins

Four plugins for the oracle's own copy of the game. Each is a 32-bit Windows DLL with an `.asi` extension, loaded by an ASI loader (Ultimate ASI Loader, installed as `winmm.dll` next to `stbc.exe`). They hook the game in memory at run time and never change `stbc.exe` on disk. Install them only in the oracle copy, never in a copy you play.

Where they are needed:

- **Windows, one game at a time (`run_oracle.py`):** all optional. Without OracleAssist the driver focuses the window and presses ESC through the movies, as before. Without Lockstep the clock follows the host. Without CombatTap a run simply has no per-hit log.
- **Mac (CrossOver):** OracleAssist and Lockstep are required, because the game must run unattended in the background.
- **Several instances at once (`batch.py`):** OracleAssist, Lockstep and CombatTap are required in every copy. OracleAssist is what lets copies run unfocused side by side.

| Plugin | What it gives the oracle | Without it |
|---|---|---|
| **CombatTap** | One log line per damage event inside the engine: impact point, radius, each subsystem damaged and by how much, shield faces, overflow. The duel summaries, the aim and torpedo reports and `analyze_tap.py` read it. | No per-hit log; telemetry still records each subsystem's condition per sample. |
| **Lockstep** | A fixed 60 Hz virtual clock, so every game step is the same size on any host, plus mode 2, which also skips the scene draw for speed. Runs become deterministic. | Step size follows the host's frame rate. |
| **RandTap** | Seeds and records the game's C runtime `rand()`, and records the script-level `GetRandomNumber` sequence, for replaying a fight from a seed (`harness_win/randtap_test.py`). | No seed control. |
| **OracleAssist** | Lets the game run in the background on a Mac (CrossOver) without taking focus, the mouse or the cursor. It tells the game it is active, skips the opening movies, and keeps keys typed in other windows out of the run. | The driver needs the window focused, as on Windows. |

Each plugin reads an optional `.ini` and writes a `.log` in the game folder. The header comment of each source file documents its options.

## How they hook

The game's functions are found by address, taken from the public [STBC-Reverse-Engineering](https://github.com/SandboxServers/STBC-Reverse-Engineering) project. Each plugin checks the function's first bytes against the GOG 1.1 `stbc.exe` before hooking, and skips that hook (and logs it) on a mismatch, so another build of the game degrades instead of crashing. Hooks use [MinHook](minhook/README.md) (BSD 2-clause, `minhook/LICENSE.txt`).

## Build

MinGW-w64 for 32-bit Windows (`brew install mingw-w64` on macOS, `apt install gcc-mingw-w64-i686` on Debian or Ubuntu), then:

```sh
oracle/native/build.sh        # writes oracle/native/out/{CombatTap,Lockstep,RandTap,OracleAssist}.asi
```

Copy the ones you want, and the ASI loader, into the oracle copy of the game. Built plugins are not committed.

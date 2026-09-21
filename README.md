# tools/oracle — the original `stbc.exe` as an unattended measurement oracle

`run_oracle.py` launches an isolated copy of the real game, boots it straight
into a scripted Quick Battle with two ships at a fixed range and bearing,
performs one action (fire a weapon system, preset a shield face, command
full impulse or a turn), samples the world every ~30 ms, writes the samples
out through the engine's own config I/O and quits — about 30 s per run,
nobody at the keyboard. `study.py` runs the matrix behind
[`docs/bc-behaviour-bible.md`](docs/bc-behaviour-bible.md);
`analyze.py` reduces the raw captures to the numbers the bible quotes.

```
python oracle/run_oracle.py --attacker KessokHeavy --target Galaxy \
    --weapon phaser --intensity 2 --range-gu 57 --out result.json --shot shot.png
python oracle/study.py            # whole matrix, skips existing results
python oracle/analyze.py          # report per docs/oracle/results/*.json
```

## Layout

| | |
|---|---|
| `scripts/Local.py` | startup hook (imported by the stock `Autoexec.py`): schedules `ET_NEW_GAME("Oracle.OracleGame")` once the main menu is built |
| `scripts/Oracle/OracleGame.py` | Game module — mirrors `QuickBattleGame` and loads `Oracle.OracleEpisode` |
| `scripts/Oracle/OracleEpisode.py` | loads the **real** `QuickBattle.QuickBattle` mission with two functions wrapped |
| `scripts/Oracle/OracleMission.py` | the wrappers: inject the ship list, take the ships over after the sim starts, act, sample, flush, quit |
| `scripts/Oracle/OracleLog.py` | `SaveConfigFile`-backed markers, metadata and chunked rows |
| `run_oracle.py` | Python 3 driver: deploy scripts, write inputs, launch, focus, skip movies, collect, parse |
| `capture.py` | `PrintWindow(PW_RENDERFULLCONTENT)` screenshots — BitBlt shows the 3D view black |
| `study.py` / `analyze.py` / `scene_report.py` | the study matrix and its reductions (`scene_report.py` writes `docs/mission-scenes.md`) |

The oracle directory (`--oracle-dir`, default
`~/Documents/Star Trek Bridge Commander/bc_oracle`) is a clean BC install plus
`options.cfg`; `scripts/` under it receives a copy of `scripts/` here on every
run. Nothing in the stock script tree is modified.

## Things that cost a session to learn

1. **The game's main loop does not start until its window has focus.** An
   unfocused launch is a black window forever. The driver finds
   "Bridge Commander" and clicks into it.
2. **Windowed + compatibility layers or the 16-bit D3D8 window is black.**
   `options.cfg` must say `Fullscreen Mode|0`, and the exe path must be
   registered under `HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers`
   as `~ DWM8And16BitMitigation DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE 16BITCOLOR`.
   Do not add `WINXPSP2`/`RUNASADMIN`: they force elevation, and an elevated
   game can be neither focused nor killed from an ordinary shell.
3. **Only the stock start path survives the first frame.** A custom
   Game/Episode/Mission that builds its own set — or the stock Quick Battle
   mission started before the real menu has been built — access-violates on
   the first rendered frame (`0x004EDE16`, `0x0044E6A9`). What works: let the
   stock movies run (the driver presses ESC to skip them), hook `StartMusic`
   (the last call of `FinishOpeningMovie`) to schedule `ET_NEW_GAME` through a
   game-clock timer, load the real `QuickBattle.QuickBattle` mission and wrap
   its `Initialize` / `StartSimulation2`.
4. **Python 1.5 inside the game:** no closures (a nested `def` cannot see the
   enclosing scope — use a class), `Mission_GetNextEventType()` returns the
   same value every call until a mission exists (use
   `UtopiaModule_GetNextEventType()`), a repeating `TGTimer` needs duration
   `-1`, `ShipClass.SetTarget` takes a *name*, `SetVelocity` takes only the
   vector, and every config value must stay under 180 characters.
5. **The game rewrites `options.cfg` from its in-memory config**, which by then
   contains our `Oracle*` sections; the driver scrubs them before each launch.
6. The QuickBattle AI ship's phaser system defaults to **PP_MEDIUM**; the
   mission sets the requested level explicitly at act time.
7. **A set-to-set warp streak collides.** The ship really moves at 700 GU/s
   along its heading for ~2 s before the set switch, and the harness parks
   the target at the origin, dead ahead: the first `warpset_*` capture hit
   it and arrived spinning at 10 rad/s, which masqueraded as a post-warp
   speed law for a session. `warp_clear=<GU>` moves the target aside first.
   Sample angular velocity whenever a speed looks wrong.
8. **A player-ship set-to-set warp crashes at the destination switch** unless
   the destination set was created beforehand (the engine loading it for the
   rendered-set switch access-violates, `0x004090EB`), and the stock warp
   assumes the helm's pre-warp cutscene camera exists (`WarpPressed`). The
   Quick Battle intro cutscene owns the view until ~7.3 s — camera scenarios
   act at `fire_at` 10. `oracle_boot.cfg`'s `zz_pulse` heartbeat (rewritten
   every 16 samples) is how a crash gets timed.
9. **Stock missions load through the developers' own override** (`mission=E3M2`
   in `oracle_in.cfg` → `mainmenu.RunOverrideMission`), with the mission's
   `Initialize` wrapped only to arm `Oracle/OracleScene.py`. Missions call
   `MissionLib.SaveGame` in `Initialize`, which pickles every script module's
   globals: any oracle global holding a module or a C handle must be listed in
   that module's `NonSerializedObjects` or the debug console pops and the game
   freezes (E1M1 does not save, so it worked first; nothing else did).

## Inputs (`oracle_in.cfg [OracleIn]`, all set by the driver)

`attacker`, `target` (ship script names from `scripts/ships/`), `weapon`
(`phaser|pulse|torpedo|none`), `motion` (`none|impulse|impulseNNN|coast|yaw|pitch|roll|warp*|warpset*`),
`range_gu`, `angle_deg` (0 ahead of the target, 90 off its starboard side,
180 astern), `elev_deg`, `intensity` (0/1/2 = LOW/MED/HIGH), `charge`,
`power_wanted`, `shield_face`/`shield_frac`, `shields_off`, `settle_s`,
`fire_at`, `duration`, `sample_dt`, `disable_target_weapons`, `rows`
(`a` weapon/shields/hull, `b` subsystem conditions, `c` motion of the
`sample` ship, `d` player camera, `e` the rendered set's active camera);
`cam_mode` steps the player camera through modes every `cam_step_s`
(`space:<Mode>`, `cin:<Mode>`, `vs:<Dir>`, `map`, `placement`, `lockedsph`,
`lockednormal`, `firstperson`, `pop`, `settarget`, `fire`/`stopfire`, `cinoff`);
row `f` is the first torpedo in the sample ship's set.

## Outputs

`oracle_out.cfg` (+ `oracle_out1.cfg` … chunks of 400 rows) `[OracleOut]`:
`m_*` metadata (bank stats, subsystem catalogue, impulse limits, mass) and
`rNNNN` rows of the three kinds; `oracle_boot.cfg` holds progress markers
(`[OracleBoot]` mission, `[OracleHook]` startup) — the first thing to read
when a run does nothing.

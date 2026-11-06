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
| `native/` | optional native capture plugins (CombatTap per-hit log, Lockstep fixed-step clock, RandTap seed control, OracleAssist background running) and their build script; see `native/README.md` |

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
row `f` is the first torpedo in the sample ship's set. `vfx_patch`
(`photon:<i>=<v>,…` / `pulse:<i>=<v>,…`, `5=<speed>` for bolts) replaces the
projectile module's `Create` with one argument changed; `--shot-on <marker>
--shot-count N --shot-every s --shot-delay s` takes a burst of screenshots
once a boot marker appears (`oracle/vfx_measure.py` reduces them). Note
`PrintWindow` returns an all-black frame now and then — bursts, not
single shots. `hp_patch` (`--hp-patch "<hardpoint>:<Var>.<Setter>=<v>;pulse.<Setter>=<v>;-<Template Name>"`)
deploys a patched copy of the SDK hardpoint source for one run — a setter
appended after the templates are registered, `pulse.` for every
`PulseWeaponProperty`, `-Name` dropping that template from `LoadPropertySet` —
and restores the stock `.pyc` afterwards (`ships.Hardpoints.*` is `reload()`ed
on every ship creation, so patching the module in-game is useless).
`dscale_set` probes for a `PulseWeapon_SetDamageScale` binding (there is
none in this build). `phaserpatch:<Attr>=<v>[;…]` / `firephaser` / `stopphaser` /
`phaserstate` do the same for the player's beams (colours as r/g/b), and
`tractorpatch` / `firetractor` / `stoptractor` for the tractor;
`--effects-wrap` counts calls into the `Effects.py` hit hooks (`fx_*` markers);
`--nebula h/s/R/dx/dy/dz[/sensor[/count]]` builds a MetaNebula around the
target at act time (`count` also logs `ET_ENVIRONMENT_DAMAGE` events;
`/dx2/dy2/dz2/R2` adds a second sphere); `weaken` / `yawplayer` / `stopyaw` / `cleartarget` / `cloak` / `decloak` /
`killbeams` are further `cam_mode` steps; `--difficulty 0|1|2` sets
`Game_SetDifficulty` (Quick Battle's own default is 1).

## Outputs

`oracle_out.cfg` (+ `oracle_out1.cfg` … chunks of 400 rows) `[OracleOut]`:
`m_*` metadata (bank stats, subsystem catalogue, impulse limits, mass) and
`rNNNN` rows of the three kinds; `oracle_boot.cfg` holds progress markers
(`[OracleBoot]` mission, `[OracleHook]` startup) — the first thing to read
when a run does nothing.

A result written under `docs/results/` (committed, public) is a trimmed copy
(`run_oracle.for_docs`): no hostname, no second copy of `params` in the
manifest, and `raw_rows` only for row kinds that are not already parsed. A
result written anywhere else, such as the ignored `results_mac/` / `results_win/`, keeps everything.

## Settings (environment)

| Variable | Used by | Meaning |
|---|---|---|
| `DAUNTLESS_ORACLE_DIR` | `run_oracle.py` | the game copy to run (default: the platform's `bc_oracle` / CrossOver bottle path) |
| `ORACLE_BOTTLE` | `run_oracle.py` (Mac) | CrossOver bottle name (default `BC Oracle`) |
| `ORACLE_SDK_HARDPOINTS` | `run_oracle.py --hp-patch`, `reports/aim_bank.py`, `reports/export_hittable_tables.py` | the SDK's `scripts/ships/Hardpoints` folder (Windows default: the SDK beside the oracle copy; no default on the Mac) |
| `ORACLE_RESULTS` | `scorecard/`, `reports/export_hittable_tables.py` | the folder of captures (default `results_mac/`) |
| `DAUNTLESS_ROOT` | `reports/rating_replay.py` | a built Dauntless checkout, for ship meshes |

`export_hittable_tables.py` writes into `<results>/exports/` unless given `--out-dir`; it never writes into a Dauntless checkout by default.

## AI duel comparison (original vs Dauntless)

| | |
|---|---|
| `oracle/reports/duel_summary.py` | one summary per duel, same format for both games: winner/length, damage and hits by weapon (each hit counted once), torpedo launches + nose/tail split + loaded-and-lined-up conversion, damage taken split shield / passed / hull / per subsystem, behaviour shares, shield and hull curves. Cached under `results_mac/summary_cache/`. |
| `oracle/reports/matchup_stats.py` | per matchup, every metric as a distribution over duels: medians and a bootstrap 90% interval on the difference; flags only gaps outside the noise and > 10%. `--only <class>`, `--flagged`, `--json` |
| `scorecard/test_matchups.py` | the same, as scorecard rows (wrong / close / match) |
| `scorecard/dauntless_aim_duels.py` | the Dauntless side. `AIM_DUEL_PAIRS`, `AIM_DUEL_LEVELS`, `AIM_DUEL_ANGLES`, `AIM_DUEL_REPEATS` (repeat k > 0 writes `_rep<k>`), `AIM_DUEL_SKIP_EXISTING=1` to resume |

Capture details the summaries rely on: `tele_X_ptr` / `tele_X_sptr<k>` meta (ship and subsystem
addresses, so CombatTap rows are attributed exactly; older captures fall back to inference and say so),
`xac` rows (`GetAccelerationTG`). CombatTap re-logs a bleed-through hit under the same `hit=` ID and
reuses IDs later: count a hit once per ID within 0.5 s.

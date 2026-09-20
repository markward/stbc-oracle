# stbc-oracle — Claude context

## What this is

An unattended measurement harness for the original *Star Trek: Bridge
Commander* (`stbc.exe`, GOG build). `oracle/run_oracle.py` boots an isolated
copy of the game into a scripted Quick Battle, takes over both ships, performs
one action, samples every ~30 ms and quits. The captures in `docs/results/`
back every number in `docs/bc-behaviour-bible.md`, which is the contract a
reimplementation (e.g. Dauntless) is tested against. Read `README.md` first,
then the bible's §9 (harness assertions) and §10 (open items).

## Hard rules

- **Never launch the game without a bounded run.** Every launch goes through
  `run_oracle.run()` / `study.py`, which has a timeout and kills the process.
  The game takes the user's screen and keyboard focus while it runs; do not
  launch while the user is doing something else, and stop launching the
  moment they ask.
- **Commits are authored `Mark Ward <mark.ward@gmail.com>`** (pinned in the
  repo config). Never pass another identity on the command line.
- **The scripts under `oracle/scripts/` run inside the game's Python 1.5.2.**
  No closures (a nested `def` cannot see its enclosing scope), no `True`/`False`,
  no `import X as Y`, no ternary `a if c else b`, no list comprehensions,
  `except E, e:` syntax, `string.replace` not `str.replace`, `dict.has_key`.
  A syntax error or uncaught exception in-game pops the TG debug console and
  **freezes the process** until someone types `abort` — a run that sits on a
  black window with no `stbc.RPT` almost certainly hit this. Wrap anything
  that can raise in `try:/except:` and `_log.mark()` the error.
- **Only the stock start path survives.** Do not write a custom set/mission:
  ride `QuickBattle.QuickBattle` via the wrappers in `OracleMission.py`
  (README, "Things that cost a session to learn").
- `ArtificialIntelligence_LogAITree` is unusable (kills or stalls the game);
  don't re-try it without a new idea.
- Every config value written from the game must stay under 180 characters.

## Layout

| | |
|---|---|
| `oracle/run_oracle.py` | Python 3 driver: deploy scripts, write `oracle_in.cfg`, launch, focus-click, ESC through movies, collect `oracle_out*.cfg`, parse |
| `oracle/study.py` | the study matrix (`MATRIX` dict); `--only <substring>`; skips existing results |
| `oracle/analyze.py`, `oracle/ai_report.py` | reduce captures to the bible's numbers |
| `oracle/capture.py` | `PrintWindow(PW_RENDERFULLCONTENT)` screenshots; BitBlt shows the 3D view black |
| `oracle/scripts/Local.py` | startup hook (stub `MainMenu.mainmenu`, deferred `ET_NEW_GAME`) |
| `oracle/scripts/Oracle/*.py` | Game/Episode/Mission/Log modules deployed into the game |
| `docs/bc-behaviour-bible.md` | the measured contract |
| `docs/results/*.json` | raw captures, one per scenario; never hand-edit |

## Environment on this machine

- Oracle copy: `C:\Users\user\Documents\Star Trek Bridge Commander\bc_oracle`
  (clean install + `options.cfg`, windowed). The exe is registered under HKCU
  AppCompat layers `~ DWM8And16BitMitigation DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE 16BITCOLOR`
  — no `WINXPSP2`/`RUNASADMIN`, they force elevation.
- SDK source for reference: `C:\Users\user\Documents\Star Trek Bridge Commander\sdk\Build\scripts`.
- Python for the driver: `C:\Users\user\Projects\bc_dauntless\.venv\Scripts\python.exe`
  (stdlib only is required; any Python ≥ 3.10 works).

## Adding a scenario

1. Add inputs to `_read_inputs()` in `OracleMission.py` (and the matching
   `argparse` option + `params` entry in `run_oracle.py`, and the `BASE`
   default in `study.py`).
2. Act in `OnAct` / `_act_weapon` / `_act_motion` / `_act_target`; sample in
   `OnSample` (row kinds `a` weapon/shields/hull, `b` subsystems, `c` motion).
3. Add the entry to `MATRIX`, run `study.py --only <name>`, reduce with
   `analyze.py`/`ai_report.py`, and write the finding into the bible with the
   result file named — the bible never states a number without its capture.

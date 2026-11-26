# QuestieForeverFixes

A small companion addon for [Questie](https://github.com/Questie/Questie) on WoW Forever. It fills gaps in
Questie's database (missing or misplaced NPC spawns, objective sources) and is loaded through QuestieDB's
public correction API. Questie updates therefore never overwrite it, and every refresh is diffed against the
installed QuestieDB, so the patch shrinks as Questie fixes things upstream. Not affiliated with the Questie
team.

## Install (players)

1. Download `QuestieForeverFixes-<version>.zip` from the Releases page.
2. Extract it so the folder is `<WoW>\_forever_\Interface\AddOns\QuestieForeverFixes\`.
3. Fully restart the game. A new addon folder is not picked up by `/reload`.
4. Type `/qff` in game to see the status.

Requires Questie and QuestieDB. To update, replace the folder and `/reload`. To disable, `/qff off` then
`/reload`, or delete the folder. `/qff on` enables it again.

## What it fixes right now

Version 0.2.0, generated against Questie 12.15.0 / QuestieDB 1.1.6:

| Type | Rows | From QuestieTrace | From Wowhead tooltips |
|---|---|---|---|
| Quest | 1 | 1 | 0 |
| NPC | 49 | 35 | 14 |
| Object | 11 | 11 | 0 |
| Item (drop sources) | 80 | 80 | 0 |

Examples:

- Devilsaurs in Un'Goro Crater: spawn points moved to where Wowhead shows them.
- Lumbering Horror (and other Argent Dawn invasion mobs) in Burning Steppes: no spawns in QuestieDB, so the
  Argent Dawn quests had nothing to show on the map.
- Dark Iron Marksman in Searing Gorge: no spawns in QuestieDB.
- Blackrock Raider in Burning Steppes: no spawns in QuestieDB.

See [docs/FINDINGS.md](docs/FINDINGS.md) for the full audit.

## Build your own local fixes

You can turn your own [QuestieTrace](https://github.com/Questie/QuestieTrace) recordings into extra fixes on
your PC, on top of the ones this addon ships. They go into a second addon folder, `QuestieForeverFixes_Local`,
which no download or addon manager ever ships or touches, so it survives every update of Questie Forever Fixes.

Privacy: the local build runs only on your PC and never uploads anything. It downloads the QuestieTrace
extractor and its npm packages once, reads your QuestieTrace SavedVariables and writes the local addon folder.
The generated file contains no account or character names.

Requirements (Windows):

- Questie Forever Fixes 0.2.0 or later, plus Questie and QuestieDB.
- [QuestieTrace](https://github.com/Questie/QuestieTrace) installed and enabled while you play; it records
  what you see in game.
- [Python 3.12](https://www.python.org/downloads/) or newer (tick "Add python.exe to PATH" in the installer),
  [Node.js 24](https://nodejs.org) LTS and [Git](https://git-scm.com).

Steps:

1. Download this repository (green "Code" button, "Download ZIP", then extract it), or `git clone` it.
2. Play with QuestieTrace enabled, then log out or `/reload` so the game saves its recordings.
3. Open PowerShell in the repository folder and run:

   ```
   .\refresh.ps1 --local --install
   ```

   The first run sets up `.venv`, downloads the QuestieTrace extractor into `vendor\` and installs its
   packages. Add `--wow "D:\Games\World of Warcraft\_forever_"` if the game is not in the default location
   (`C:\Program Files (x86)\World of Warcraft\_forever_`). If PowerShell refuses to run the script, run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. If you used "Download ZIP", also run
   `Get-ChildItem -Recurse *.ps1 | Unblock-File` in the folder once: Windows marks downloaded scripts as
   coming from the internet, and `RemoteSigned` blocks those.
4. Restart the game the first time (a new addon folder is not picked up by `/reload`); afterwards `/reload`
   is enough. `/qff` shows the shipped and the local row counts.

Rerun step 3 after playing more and after updating Questie or Questie Forever Fixes (`/qff` says "rebuild"
when the local build is out of date). Only differences from the installed QuestieDB and the shipped fixes end
up in the local folder, so it stays small. Without `--install` the folder is written to
`work\local\QuestieForeverFixes_Local` for you to inspect. To remove your local fixes, delete
`Interface\AddOns\QuestieForeverFixes_Local` or disable it in the addon list.

Your recordings are also archived in `archive\sessions\` inside the repository folder, because QuestieTrace
keeps only the newest 10 sessions per character. Keep that folder if you want older areas to stay covered.

How local rows combine with the shipped ones:

- Spawn points: per zone, every shipped point is kept and your points are added (a point within 0.5 map
  units of one already there is skipped). New zones are added.
- Drop sources and the other `_add` lists (`npcDrops_add`, `objectDrops_add`, quest starters and enders):
  union.
- Everything else (zone, name, quest objectives and other single values): the shipped value wins; yours is
  used only where the shipped fixes have none.
- Entities the shipped fixes do not cover are used as they are.

## Help us

- Install [QuestieTrace](https://github.com/Questie/QuestieTrace), play, then run `/qlt export` and paste the
  result at https://questie.dev/trace. That is what fixes Questie for everyone.
- Or share your QuestieTrace SavedVariables with the maintainer so this local patch can use them.
  QuestieTrace keeps only the newest 10 sessions per character, so older areas are lost unless exported.

## For maintainers

### How refresh works

`refresh.py` does the following:

1. copies the QuestieTrace SavedVariables from the WoW folder (read-only access) and archives new sessions
   in `archive/sessions/`;
2. runs the vendored, patched QuestieTrace corrections extractor over all archived sessions;
3. fetches Wowhead Forever tooltip coordinates for the audited zones (cached in `work/wh/`) and runs the
   zone and dungeon audits (`work/audit/`);
4. diffs everything against the installed QuestieDB;
5. writes `addon/QuestieForeverFixes/Data.lua`, `work/patch.json` and `work/report.txt`. Reruns are
   idempotent ("Data.lua unchanged").

Run it after every play session and after every Questie / QuestieDB update. `archive/sessions/` is the only
long-term copy of your recordings; never delete it.

### Never losing a session

QuestieTrace keeps only 10 sessions per character and prunes the oldest every time the game saves (each
`/reload`, logout and exit). `refresh.py --archive-only` copies new sessions into `archive/sessions/` and does
nothing else; it is fast, idempotent and deduplicated.

On Windows, `tools\archive-watch.ps1` runs it every time the game saves QuestieTrace's file.
`.\tools\install-archive-watch.ps1` registers that watcher as a hidden scheduled task at logon and starts it
(`-Uninstall` removes it; `-Wow <path>` if the game is elsewhere). Its log is `work\archive-watch.log`.

### Requirements

- Python 3.12 and Node 24. `.\refresh.ps1` creates `.venv` and installs `lupa` on first run (manually:
  `python -m venv .venv`, then `.venv\Scripts\python.exe -m pip install lupa`).
- The extractor is vendored from QuestieTrace. `.\refresh.ps1` clones it when it is missing and `refresh.py`
  runs `npm ci` when `node_modules` is missing; manually:

  ```
  git clone https://github.com/Questie/QuestieTrace vendor/QuestieTrace
  cd vendor/QuestieTrace/tools/corrections-extractor
  npm ci
  ```

  `extract/patches.json` lowers upstream aggregation thresholds (they assume thousands of contributors) to
  1. If upstream changed the patched files, refresh aborts with "upstream extractor changed; update
  extract/patches.json".

### Commands

```
.\refresh.ps1 [--install] [--archive-only] [--wh-offline] [--no-wh] [--no-extract] [--wow <path>] [--verbose]
.\refresh.ps1 --local [--install] [--local-out <dir>] [--shipped <Data.lua>|none] [--no-extract] [--wow <path>]
```

- `--install` copies the addon into the game's AddOns folder.
- `--wh-offline` uses only cached Wowhead tooltips; `--no-wh` skips Wowhead and the audit entirely.
- `--no-extract` reuses the last extractor output.
- `--wow <path>` points at `<WoW>\_forever_` if it is not in the default location.
- `--archive-only` only archives new QuestieTrace sessions (see "Never losing a session").
- `--local` is the player mode (see "Build your own local fixes"): no Wowhead; diffed against the installed
  QuestieDB with the shipped `Data.lua` applied on top; written to `work\local\QuestieForeverFixes_Local`
  (`--local-out` to change) and, with `--install`, copied to `AddOns\QuestieForeverFixes_Local`.
  `--shipped` picks the baseline (default: the installed `QuestieForeverFixes\Data.lua`, else the repo copy;
  `none` for no baseline). It never writes `addon\`, `work\patch.json` or `work\report.txt`; its report and
  extractor output live in `work\local\`.
- `refresh.ps1` passes its arguments to `refresh.py`; without PowerShell, run
  `.venv\Scripts\python.exe -I refresh.py` with the same arguments.
- Verify the generated addon: `.\.venv\Scripts\python.exe -I tools\verify_lua.py` (also checks a
  LocalData.lua: `--local-data <path>`, default `tools\fixtures\LocalData.lua`). Merge unit tests:
  `.\.venv\Scripts\python.exe -I tools\test_merge.py`.
- Audits on their own: `python -I tools\zone_audit.py [--offline]`.

### Patch policy

Only differences from the installed DB are kept:

- Entity not in the DB: the whole extracted row is kept.
- Relations (`startedBy_add`, `finishedBy_add`, `questStarts_add`, `questEnds_add`, `npcDrops_add`,
  `objectDrops_add`): only ids the DB does not already have.
- Quest objectives: only observed groups holding an id the DB does not know are rewritten.
- Scalar fields (`requiredRaces` and others) are only filled when the DB value is missing or empty.
- Spawns: new zones are added. Existing spawns are replaced only when every Questie point is more than 3
  map units from the observed/Wowhead points; otherwise only extra points more than 3.0 units from every
  DB point are appended.
- Prerequisites and races of existing QuestieDB quests are never touched or inferred.
- Wowhead coordinates are never used on redrawn maps 44, 139, 215 and 1519 (they return stale Era-frame
  points), and a trace patch wins over Wowhead for the same uiMap group.
- Wowhead network policy: `refresh.py` uses the tooltip API only (`nether.wowhead.com/tooltip/...?dataEnv=16`),
  plus wago.tools DB2 CSVs; single-threaded, at most 3 requests/s, never www.wowhead.com pages.

Curated layers, checked in under `data/` and applied by `refresh.py` after the trace and Wowhead steps:

- `added_quests.json`: quests QuestieDB lacks, curated once from Wowhead Forever quest pages
  (`tools/wh_quest_page.js` in a browser, then `missing_build.py` and `added_quests_build.py`). Each entry carries
  its provenance; manual edits go in `overrides`. A quest QuestieDB has since added is retired automatically.
  Givers get `questStarts_add`/`questEnds_add`, and starter items get `startQuest`. Giver ids are never guessed:
  quests without a giver on Wowhead ship without one.
- `class_restrictions.json`: requiredClasses for the Forever Tier 0.5 quests, derived from the objective items'
  item set (DB2 ItemSet, `class_restrictions.py`). It is applied only where QuestieDB has no requiredClasses.
- `gap_fills.json`: entities QuestieDB has no spawns for (all-zones audit, `gap_fill_select.py`; Scourge
  Invasion mobs and redrawn maps excluded). Each ships through the Wowhead tooltip rules only while QuestieDB
  still has no spawns. Instance points become QuestieDB's `{-1, -1}` sentinel.

`Data.lua` rows carry a `-- src:` comment naming their sources, joined by `+`: `trace`, `wh-tooltip`, `wh-page`
(added quests) and `class-map` (class restrictions).

### Release steps

See [docs/RELEASING.md](docs/RELEASING.md). Releases are built and uploaded by tagging `vX.Y.Z`.

## Credits

Questie, QuestieDB and QuestieTrace and their teams (all GPLv3). Some coordinates come from Wowhead Forever
tooltips, and the added quests come from Wowhead Forever quest pages. ForeverDungeonJournal is used read-only
for the dungeon audit.

## License

GNU GPL v3, see [LICENSE](LICENSE).

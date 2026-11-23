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

Version 0.1.0, generated against Questie 12.12.0 / QuestieDB 1.1.5:

| Type | Rows | From QuestieTrace | From Wowhead tooltips |
|---|---|---|---|
| Quest | 1 | 1 | 0 |
| NPC | 29 | 15 | 14 |
| Object | 7 | 7 | 0 |
| Item (drop sources) | 45 | 45 | 0 |

Examples:

- Devilsaurs in Un'Goro Crater: spawn points moved to where Wowhead shows them.
- Lumbering Horror (and other Argent Dawn invasion mobs) in Burning Steppes: no spawns in QuestieDB, so the
  Argent Dawn quests had nothing to show on the map.
- Dark Iron Marksman in Searing Gorge: no spawns in QuestieDB.
- Blackrock Raider in Burning Steppes: no spawns in QuestieDB.

See [docs/FINDINGS.md](docs/FINDINGS.md) for the full audit.

## Help us

- Install [QuestieTrace](https://github.com/Questie/QuestieTrace), play, then run `/qlt export` and paste the
  result at https://questie.dev/trace. That is what fixes Questie for everyone.
- Or share your QuestieTrace SavedVariables with the maintainer so this local patch can use them.
  QuestieTrace keeps only the newest 10 sessions per character, so older areas are lost unless exported.

## For maintainers

### How refresh works

`refresh.ps1` runs `refresh.py`, which:

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

### Requirements

- Python 3.12 and Node 24. `refresh.ps1` creates `.venv` and installs `lupa` on first run.
- The extractor is vendored from QuestieTrace:

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
.\refresh.ps1 [--install] [--wh-offline] [--no-wh] [--no-extract] [--wow <path>] [--verbose]
```

- `--install` copies the addon into the game's AddOns folder.
- `--wh-offline` uses only cached Wowhead tooltips; `--no-wh` skips Wowhead and the audit entirely.
- `--no-extract` reuses the last extractor output.
- `--wow <path>` points at `<WoW>\_forever_` if it is not in the default location.
- If PowerShell blocks the script: `powershell -ExecutionPolicy Bypass -File .\refresh.ps1`, or call
  `.\.venv\Scripts\python.exe -I refresh.py` directly.
- Verify the generated addon: `.\.venv\Scripts\python.exe -I tools\verify_lua.py`.
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
- Prerequisites and races are never touched or inferred.
- Wowhead coordinates are never used on redrawn maps 44, 139, 215 and 1519 (they return stale Era-frame
  points), and a trace patch wins over Wowhead for the same uiMap group.
- Wowhead network policy: tooltip API only (`nether.wowhead.com/tooltip/...?dataEnv=16`), plus wago.tools
  DB2 CSVs; single-threaded, at most 3 requests/s, never www.wowhead.com pages.

`Data.lua` rows carry a `-- src: trace|wh-tooltip|trace+wh-tooltip` comment.

### Release steps

1. Run `refresh.ps1` and `verify_lua.py`; review `work/report.txt`.
2. Bump `## Version` in `addon/QuestieForeverFixes/QuestieForeverFixes.toc` and add a CHANGELOG entry.
3. Run `python tools/package.py`; it writes `dist/QuestieForeverFixes-<version>.zip`.
4. Commit, tag, and attach the zip to a GitHub release.

## Credits

Questie, QuestieDB and QuestieTrace and their teams (all GPLv3). Some coordinates come from Wowhead Forever
tooltips. ForeverDungeonJournal is used read-only for the dungeon audit.

## License

GNU GPL v3, see [LICENSE](LICENSE).

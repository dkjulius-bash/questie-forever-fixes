# QuestieForeverFixes

Local Questie corrections generated from your own QuestieTrace recordings. The addon layers them at
runtime on top of the installed QuestieDB through LibQuestieDB, under the owner name
`QuestieForeverFixes`. Everything is diffed against the installed QuestieDB on every refresh, so the
patch shrinks automatically as upstream catches up.

## Requirements

- Python 3.12 venv in `.venv` with `lupa` (`refresh.ps1` creates it on first run).
- Node 24.
- The vendored QuestieTrace clone in `vendor/QuestieTrace`. To re-create it:

  ```
  git clone https://github.com/Questie/QuestieTrace vendor/QuestieTrace
  cd vendor/QuestieTrace/tools/corrections-extractor
  npm ci
  ```

  To update it: `git -C vendor/QuestieTrace pull`, then rerun refresh. If upstream changed the files
  that `extract/patches.json` edits, refresh aborts with "upstream extractor changed; update
  extract/patches.json"; adjust the `find` strings and rerun.

## Refresh

```
.\refresh.ps1
```

Run it after every play session and after every Questie / QuestieDB update.

IMPORTANT: QuestieTrace keeps only the newest 10 sessions per character. Refresh at least every few
sessions. `archive/sessions/` is the only long-term copy of your recordings; never delete it.

Refresh copies the SavedVariables (read-only access to the WoW folder), archives new sessions, runs the
patched extractor over all archived sessions, diffs the result against the installed QuestieDB, and
writes `addon/QuestieForeverFixes/Data.lua`, `work/patch.json` and `work/report.txt`. Reruns are
idempotent: if nothing changed it prints "Data.lua unchanged". Options: `--wow <path>`,
`--no-extract` (reuse the last extractor output), `--verbose`.

## Install

Copy `addon\QuestieForeverFixes` into `World of Warcraft\_forever_\Interface\AddOns\` and `/reload`.

- `/qff` shows status
- `/qff off` disables the layer, `/qff on` enables it again

## Remove

Delete the `AddOns\QuestieForeverFixes` folder, or `/qff off` and `/reload`.

## Policy

Only differences from the installed DB are kept:

- Entity not in the DB: the whole extracted row is kept.
- Relations (`startedBy_add`, `finishedBy_add`, `questStarts_add`, `questEnds_add`, `npcDrops_add`,
  `objectDrops_add`): only ids the DB does not already have.
- Quest objectives: only observed groups (creature/object/item) holding an id the DB doesn't know are rewritten (matching DB rows kept); every other DB objective group is preserved.
- `questLevel`: kept if missing or different. `requiredRaces` and all other scalar fields: only filled
  when the DB value is missing/empty.
- Spawns: new zones are added; for quest givers whose observed position matches no DB point (1.5 map
  units) the zone is replaced; otherwise points more than 3.0 units from every DB point are appended.
  `spawns` is a replacement field, so the full merged table is emitted.
- Invalid fields (unknown name, wrong type) are dropped and counted in the report.

Threshold patches (`extract/patches.json`): upstream aggregation thresholds assume thousands of
contributors (a quest giver needs 5 sessions, a spawn cluster 2, a newest value 2). This is one
player's data, so they are lowered to 1.

Known limits: no prerequisite inference (the extractor has no such observer); `requiredLevel` and
`zoneOrSort` are not exported by the extractor; single-player data means lower confidence than the
upstream crowd-sourced data.

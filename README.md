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

If the PowerShell execution policy blocks the script, run
`powershell -ExecutionPolicy Bypass -File .\refresh.ps1` or call
`.\.venv\Scripts\python.exe -I refresh.py` directly.

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

## Wowhead tooltip source (wh-tooltip)

Second data source next to the traces: Wowhead's Forever tooltip API. For every quest giver, finisher and
objective entity (objective NPCs/objects, kill credit, and drop sources of item objectives; items with more
than 25 drop sources are ignored as generic loot) of every Alliance quest in six zones (Riverglades,
Un'Goro Crater, Eastern Plaguelands, Western Plaguelands, Searing Gorge, Burning Steppes), refresh fetches
`https://nether.wowhead.com/tooltip/{npc|object}/{id}?dataEnv=16&locale=0` and compares the tooltip's
coordinates (Forever-native percent, one zone per entity) with the Questie spawns in the same uiMap group.

Rules (`tools/zone_audit.py: wh_patch`), starting from the trace-patched spawns if any:

- no Questie points in that uiMap group: add the tooltip points under the zone's main AreaID (`wh-add-zone`);
- nearest Questie point more than 3.0 map units from every tooltip point: replace all AreaIDs of that uiMap
  group with the tooltip points under the main AreaID (`wh-replace-zone`);
- otherwise nothing. If the trace patch already changed spawns in that uiMap group, the trace wins.
- Entities missing from QuestieDB also get `name` and `zoneID`. Quest fields are never taken from Wowhead.

Stale Era points: for Eastern Plaguelands (and the other transformed zones in `eraToForever.lua`) the tooltip
contains both the Forever point and the stale Era-frame point. A tooltip point whose Era->Forever image is
within 1.0 of another tooltip point of the same entity is dropped (counted in the audit summary; an upstream
Wowhead issue).

Network policy: only the tooltip API and `https://wago.tools/db2/<Table>/csv?product=wowf`, single-threaded,
at most 3 requests/s, `User-Agent: Mozilla/5.0`; never www.wowhead.com pages. Responses are cached in
`work/wh/{npc|object}_{id}.json` with a `fetchedAt` stamp (refetched after 30 days, failures after 1 day);
DB2 CSVs are cached in `work/db2/` (refetched after 7 days).

Flags: `--no-wh` disables the source and the audit completely (Data.lua then only has `-- src: trace` rows),
`--wh-offline` uses only the cache, `--wh-refresh-days N` changes the cache lifetime (default 30).
Data.lua rows carry a `-- src: trace|wh-tooltip|trace+wh-tooltip` comment and `ns.meta.sources` the counts;
`work/patch.json` has the per-row source and `work/report.txt` a "Patch rows by source" section.

Zone audit: `python -I tools\zone_audit.py [--offline]` (also run by refresh) writes `work/audit/<Zone>.json`
and `work/audit/summary.txt` (entity status per zone, chains, POI coverage, QuestV2 gaps, patch candidates,
frame diagnostics). It is report-only apart from the wh-tooltip patch rows.

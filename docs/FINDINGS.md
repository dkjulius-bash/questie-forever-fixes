# Findings and progress log

2026-11-23. Questie 12.12.0, QuestieDB 1.1.5, WoW Forever, Alliance quests only. All numbers come from the
refresh/audit output of that date.

## Coverage

QuestieDB contains 5,977 of the 6,215 quests Wowhead lists for Forever. About 40 Alliance or both-faction
quests listed by Wowhead are absent (excluding UNUSED/NYI entries), and the Forever client has 1,301
QuestV2 ids that are not in QuestieDB (most likely unused or internal).

## Why a quest may not show even when it is in the DB

- It is started by an item rather than an NPC or object.
- It is dungeon-only, so there is nothing to show on the open-world map.
- The starter is missing: 5 dungeon quests of level 48+ have no `startedBy` (Somber News, More Valuable Than
  Gold, Feeding Time!, Ever After, Digestible Research); some may be item or auto-accept starts.
- Its givers or objective entities have no spawns in QuestieDB (see below).
- It is on Questie's blacklist. The dungeon audit found 0 blacklisted quests among the 175 checked.

## Per-zone audit (Alliance quests)

Entities are unique givers/finishers (a) and objective entities (b). "ok" means the Questie spawns agree with
Wowhead tooltip coordinates within 3 map units.

| Zone | Quests | Givers (a) | Objectives (b) | Notes |
|---|---|---|---|---|
| Riverglades | 128 | 46 ok | 78 ok, 13 no coords, 1 Era frame, 1 zone mismatch | Giver/finisher spawns all fine |
| Un'Goro Crater | 98 | 24 ok | 73 ok, 3 far, 22 no coords, 1 zone mismatch | 3 far = Devilsaurs; patched |
| Eastern Plaguelands | 302 | 28 ok, 20 Era frame, 1 no spawns | 51 ok, 10 Era frame, 2 zone mismatch, 14 no coords | Era-frame hits are Wowhead errors |
| Western Plaguelands | 143 | 40 ok, 1 no coords | 57 ok, 19 no coords, 3 zone mismatch | 1 Wowhead add |
| Searing Gorge | 89 | 23 ok, 1 zone mismatch | 50 ok, 1 no spawns, 14 no coords | Dark Iron Marksman added |
| Burning Steppes | 115 | 24 ok | 55 ok, 6 no spawns, 16 no coords, 1 zone mismatch | 7 Wowhead adds |

Wowhead-based patch candidates: 14 NPCs (3 `wh-replace-zone`, 11 `wh-add-zone`). Most impactful: Lumbering
Horror (Burning Steppes), used by 7 Argent Dawn quests.

## Dungeons 48+

17 dungeons selected (level max 48 or higher, Alliance or both), 175 quests:

- 1 quest missing from QuestieDB (Stratholme: Living, "The Medallion of Faith").
- 6 quests with no starter in Questie; 16 giver name mismatches against ForeverDungeonJournal.
- Prerequisites: 4 missing in Questie, 6 partial, 11 extra.
- 20 quests with objectives that have no spawns (7 of them in Blackmaw Hold).
- 1 Horde-restricted quest that ForeverDungeonJournal lists for both factions (Da Voodoo, Sunken Temple).
- 0 blacklisted quests.

## Wowhead Eastern Plaguelands Era-frame pitfall

For redrawn maps such as Eastern Plaguelands (139), Wowhead tooltips return stale Era-frame coordinates:
68 NPCs return both the Era and Forever point, 30 return only the Era point (7 to 13.8 units off). Example:
Rayne (16135), tooltip (81.2, 59.0) vs QuestieDB (71.4, 49.4). QuestieDB matches once converted back with the
inverse of `EraToForever`, so Wowhead is the stale side. Redridge (Snargl, 255906) shows the same. This is
why Wowhead is never used on maps 44, 139, 215 and 1519.

## What we can't fix yet, and why

- Riverglades: no QuestieTrace data. QuestieTrace keeps only 10 sessions per character and they had
  already been pruned.
- Wowhead: its quest pages are behind a bot wall, so only the tooltip API is used. Quest-level data (starters,
  prerequisites) is never taken from Wowhead.
- The client DB2 tables do not include POI or questline data for these zones, so those checks report
  "n/a" and prerequisite chains cannot be verified from the client.
- Prerequisites are never inferred: the extractor has no observer for them.

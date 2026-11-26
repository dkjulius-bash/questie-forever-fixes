# Changelog

## 0.3.0 – 2026-11-26

- Adds 22 quests that QuestieDB lacks (11 Alliance, 9 Horde, 2 neutral). They include the missing Tier 0.5 "Saving the Best for Last" and "Anthion's Parting Words" variants for both factions, "A Broken Ritual", "The Light and How To Swing It", "A More Fitting Reward", the Orgrimmar and Ironforge "A Quick Craft" chain, "Secret of the Barrow Deeps", "The Broken Glaive" and two "An Epic Ride" variants. 7 of them have no known quest giver yet. They ship without one, so Questie tracks their objectives once the quest is in your log but shows no "!" for them.
- Quest givers learn the new quests, and 3 new quest-starting items get their quest link. 3 objective items that QuestieDB lacks get a name.
- Class restrictions for WoW Forever's re-issued Tier 0.5 quests ("An Earnest Proposition", "Just Compensation", "Anthion's Parting Words", "Saving the Best for Last"). QuestieDB has no class on most of them, so Questie offered every class's version of each quest; 70 quests are now limited to their class. The class comes from the set the quest's items belong to (client ItemSet table). A class that QuestieDB already sets is never changed.
- Spawn points for 27 quest NPCs and objects that QuestieDB has no location for, taken from Wowhead Forever. They include the Alliance Strongboxes (Barrens, Alterac Mountains), the Obsidian Chunks in Silithus, the Ashenvale demon lords, Plaguewing Vultures and Darkfang Lurkers. Scourge Invasion event mobs are left out.
- Data regenerated from 45 recorded sessions.
- Maintainer tooling: an all-zones, both-factions location audit (`tools/zone_audit.py --all-zones`) and curated data files in `data/` (`added_quests.json`, `class_restrictions.json`, `gap_fills.json`) with their builder scripts. `refresh.py` checks every curated row against the installed QuestieDB, so rows retire as Questie catches up.

## 0.2.0 – 2026-11-26

- Data regenerated from 41 recorded sessions (was 39): 1 quest, 49 NPC, 11 object and 80 item corrections (was 1 / 44 / 9 / 74).
- Build your own local fixes: `refresh.ps1 --local --install` turns your own QuestieTrace recordings into a separate `QuestieForeverFixes_Local` addon folder that addon updates never touch. It contains only what the installed QuestieDB and the shipped fixes do not already cover, and nothing is uploaded. See "Build your own local fixes" in the README.
- The addon merges local rows onto the shipped ones at load time: spawn points per zone and drop-source lists are combined, shipped spawn points are never removed, and for single values (zone, name, quest objectives) the shipped value wins.
- `/qff` now shows the shipped and the local row counts, the local build date and a hint when the local build should be rebuilt.
- `refresh.ps1` now clones the QuestieTrace extractor when it is missing and gives clear messages when Python 3.12, Node.js 24 or Git is missing.

## 0.1.3 – 2026-11-26

- Data regenerated against Questie 12.15.0 / QuestieDB 1.1.6 from 39 recorded sessions (was 22): 1 quest, 44 NPC, 9 object and 74 item corrections (was 1 / 29 / 7 / 45).
- New drop sources and spawn points in Un'Goro Crater, Sunken Temple, Felwood, Azshara and Darrowshire (Eastern Plaguelands), plus more Runecloth sources and a missing Truesilver Deposit.
- Maintainer tooling: `refresh.py --archive-only` and an optional archive watcher, so that recorded sessions QuestieTrace prunes are kept.

## 0.1.2 – 2026-11-23

- Fixes the 0.1.1 download, which was an empty package. This is the first working CurseForge release.
- The release pipeline now checks the package contents before uploading.
- Same data and icon as 0.1.1.

## 0.1.1 – 2026-11-23

- New addon icon, shown in the in-game addon list.
- First release published to CurseForge. Releases are now built and uploaded automatically from GitHub tags.
- No data changes since 0.1.0.

## 0.1.0 – 2026-11-23

Initial release.

- Companion addon for Questie on WoW Forever, layered on QuestieDB through its public correction API.
- Data generated against Questie 12.12.0 / QuestieDB 1.1.5: 1 quest, 29 NPC, 7 object and 45 item corrections.
- Sources: QuestieTrace recordings (68 rows) and Wowhead Forever tooltip coordinates (14 rows).
- `/qff` shows status, `/qff on` and `/qff off` toggle the layer.
- Maintainer tooling: `refresh.py` (with `--install`), zone and dungeon audits, `tools/package.py`.

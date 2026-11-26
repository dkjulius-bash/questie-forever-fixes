# Questie Forever Fixes

A small companion addon for **Questie** on **WoW Forever**. It adds and corrects quest data that Questie's Forever database is missing: quests, class restrictions, NPC and object spawn points, and item drop sources. It works for Alliance and Horde. Quest objectives that had nothing to show on the map get their mobs, objects and drop sources back.

## What it does

- Adds quests that exist on WoW Forever but are missing from QuestieDB, with the right faction, so Questie shows and tracks them.
- Limits WoW Forever's re-issued Tier 0.5 quests to their class, so you no longer see every class's version of "Saving the Best for Last" and friends.
- Adds NPC and object spawn points that QuestieDB does not have, so quest objectives show up on the map and minimap.
- Moves spawn points that are in the wrong place (for example Era-frame coordinates) to where the mobs actually are.
- Adds missing item drop sources, so "kill X for item Y" objectives point at the right mobs.
- Everything is applied through QuestieDB's official correction API. Questie's own files are never edited, so Questie updates never overwrite this addon.
- Every data refresh is diffed against the installed QuestieDB. When Questie fixes something upstream, the patch for it disappears, so the addon shrinks over time.

## What is fixed in this version

Version 0.3.0, generated against Questie 12.15.0 / QuestieDB 1.1.6:

| Type | Corrections |
|---|---|
| New quests | 22 (11 Alliance, 9 Horde, 2 neutral) |
| Tier 0.5 class restrictions | 70 |
| Quest objectives | 1 |
| NPCs (spawns and quest givers) | 76 |
| Objects (spawns) | 19 |
| Items (drop sources and quest items) | 86 |

Examples:

- **Missing Tier 0.5 quests:** the Forever "Saving the Best for Last" and "Anthion's Parting Words" variants for several classes, on both factions, plus quests like "Karolek", "A Quick Craft" and "The Broken Glaive".
- **Alliance Strongboxes and Obsidian Chunks:** no spawns in QuestieDB, now added from Wowhead Forever.
- **Devilsaurs in Un'Goro Crater:** spawn points moved to where they really are.
- **Lumbering Horror and other Argent Dawn invasion mobs in Burning Steppes:** QuestieDB had no spawns for them, so the Argent Dawn quests had nothing to show on the map.
- **Dark Iron Marksman in Searing Gorge:** no spawns in QuestieDB, now added.
- **Blackrock Raider in Burning Steppes:** no spawns in QuestieDB, now added.

## Requirements

- **Questie** (required)
- **QuestieDB** (required)

## Installation

Install through your addon manager or extract the folder to `_forever_\Interface\AddOns\`. After the first install, **restart the game completely**; a new addon folder is not picked up by `/reload`.

- `/qff` shows the addon status.
- `/qff off` disables it, `/qff on` enables it again. Run `/reload` afterwards.

## Add your own recordings

If you play with QuestieTrace, you can turn your own recordings into extra fixes for your game, on top of the ones included here. A small script on your PC builds them into a separate `QuestieForeverFixes_Local` folder, so updates of this addon never overwrite them, and nothing is uploaded anywhere. You need Python, Node.js and a copy of the GitHub repository; the steps are in the guide: [Build your own local fixes](https://github.com/dkjulius-bash/questie-forever-fixes#build-your-own-local-fixes).

## How you can help

- Install **QuestieTrace**, play normally, then run `/qlt export` in game and send the export to the Questie team. That is what fixes Questie for everyone.
- Found a wrong or missing spawn? Report it at https://github.com/dkjulius-bash/questie-forever-fixes/issues

## Not affiliated

This is an independent project and is not affiliated with or endorsed by the Questie team.

## Credits and license

Thanks to the Questie, QuestieDB and QuestieTrace teams. Some coordinates were cross-checked against Wowhead Forever tooltips. Licensed under GPL-3.0.

Source code: https://github.com/dkjulius-bash/questie-forever-fixes

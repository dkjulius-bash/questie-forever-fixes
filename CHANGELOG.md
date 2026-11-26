# Changelog

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

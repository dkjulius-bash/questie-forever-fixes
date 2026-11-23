# Changelog

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
- Maintainer tooling: `refresh.ps1` (with `--install`), zone and dungeon audits, `tools/package.py`.

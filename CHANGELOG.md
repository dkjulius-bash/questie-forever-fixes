# Changelog

## 0.1.0 – 2026-11-23

Initial release.

- Companion addon for Questie on WoW Forever, layered on QuestieDB through its public correction API.
- Data generated against Questie 12.12.0 / QuestieDB 1.1.5: 1 quest, 29 NPC, 7 object and 45 item corrections.
- Sources: QuestieTrace recordings (68 rows) and Wowhead Forever tooltip coordinates (14 rows).
- `/qff` shows status, `/qff on` and `/qff off` toggle the layer.
- Maintainer tooling: `refresh.ps1` (with `--install`), zone and dungeon audits, `tools/package.py`.

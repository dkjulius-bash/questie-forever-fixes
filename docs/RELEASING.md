# Releasing

Releases are tag-driven: pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which uses the
[BigWigsMods packager](https://github.com/BigWigsMods/packager) (`.pkgmeta` at the repo root) to build the zip,
upload it to CurseForge and create the GitHub release.

## One-time setup

1. Create the CurseForge project manually:
   - Name: `Questie Forever Fixes`
   - Summary: contents of `curseforge/summary.txt`
   - Description: contents of `curseforge/description.md` (Markdown)
   - Avatar: `assets/icon-400.png`
   - Category: Quests & Leveling
   - License: GPL-3.0
   - Relations: add Questie as a required dependency (add QuestieDB too if it is a separate CurseForge
     project, and then add its slug to `required-dependencies` in `.pkgmeta`).
2. Copy the numeric project ID (the "About Project" box) into the `.toc` as
   `## X-Curse-Project-ID: <id>`. The packager needs it to upload. Do not commit a made-up ID.
3. Create a CurseForge API token at https://legacy.curseforge.com/account/api-tokens and store it as a repo
   secret:

   ```
   gh secret set CF_API_KEY
   ```

   The workflow passes it as both `CF_API_KEY` and `CF_API_TOKEN` because the packager's variable name
   differs between versions.

### Game version

The packager reads `## Interface: 16001` from the `.toc` and maps it to a CurseForge game version. WoW
Forever is a new client; if CurseForge has no matching game version for 16001, the upload fails or is
mis-tagged. Check the available versions on the project's upload page. If needed, pass the version
explicitly through the action (`with: args: -g <version>`) or upload the first file by hand. This mapping is
unverified.

## Release routine

1. Run `refresh.ps1`; review `work/report.txt`.
2. Update `CHANGELOG.md` with a real entry. CurseForge's Fair Play rules ban trivial or fake updates, so
   batch data refreshes into meaningful releases.
3. Bump `## Version` in `addon/QuestieForeverFixes/QuestieForeverFixes.toc`.
4. Commit, then tag and push:

   ```
   git tag vX.Y.Z
   git push --tags
   ```

`tools/package.py` remains available for building a local zip (`dist/`); it is not used by the release workflow.

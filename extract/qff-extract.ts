// Driver for the QuestieForeverFixes pipeline. Copied into <extractor>/.qff-src/ by refresh.py
// (next to a patched copy of the extractor's src/). Usage:
//   npx tsx .qff-src/qff-extract.ts <listFile.json> <outDir>
// <listFile.json> is a JSON array of absolute paths of session files, each holding one session's
// `encoded` string.
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { basename, resolve } from "path";
import { decodePayload } from "./core/trace-data/decode";
import { extractAll } from "./extract/index";
import type { SessionRecord } from "./core/types";

const [listFile, outDir] = process.argv.slice(2);
const files: string[] = JSON.parse(readFileSync(listFile, "utf8"));
const sessions: SessionRecord[] = [];
for (const f of files) sessions.push(decodePayload(readFileSync(f, "utf8").trim()) as SessionRecord);
// maxIds 0 is deliberate: we diff against the installed DB ourselves instead of the extractor's Classic-ID cut-off.
const b = extractAll(sessions, { sourceFileNames: files.map((f) => basename(f)), maxIds: { npc: 0, quest: 0, item: 0, object: 0 } });
mkdirSync(outDir, { recursive: true });
writeFileSync(resolve(outDir, "foreverQuestTraces.lua"), b.questFixes);
writeFileSync(resolve(outDir, "foreverNpcTraces.lua"), b.npcFixes);
writeFileSync(resolve(outDir, "foreverItemTraces.lua"), b.itemFixes);
writeFileSync(resolve(outDir, "foreverObjectTraces.lua"), b.objectFixes);
writeFileSync(resolve(outDir, "meta.json"), JSON.stringify({ sessionCount: sessions.length, files }, null, 2));
console.log(`sessions=${sessions.length}`);

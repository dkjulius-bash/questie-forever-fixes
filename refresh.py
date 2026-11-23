"""QuestieForeverFixes refresh: SavedVariables -> archive -> extractor -> diff vs installed DB -> Data.lua."""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lupa.lua51 import LuaRuntime  # noqa: E402

import luaser  # noqa: E402
import lua_modules  # noqa: E402
import patch_policy  # noqa: E402
import wh_tooltip  # noqa: E402
import zone_audit  # noqa: E402
import dungeon_audit  # noqa: E402
import fdj  # noqa: E402
import report  # noqa: E402
from qdb_decode import InstalledDB  # noqa: E402

WORK = os.path.join(ROOT, "work")
ARCHIVE = os.path.join(ROOT, "archive", "sessions")
EXTRACTOR = os.path.join(ROOT, "vendor", "QuestieTrace", "tools", "corrections-extractor")
DATA_LUA = os.path.join(ROOT, "addon", "QuestieForeverFixes", "Data.lua")
KINDS = ("Quest", "Npc", "Object", "Item")


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def sanitize(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def toc_version(path):
    with open(path, encoding="utf8") as f:
        for line in f:
            if line.startswith("## Version:"):
                return line.split(":", 1)[1].strip()
    return "unknown"


# ---------------------------------------------------------------- step 1
def collect_sessions(wow, verbose):
    svdir = os.path.join(WORK, "sv")
    os.makedirs(svdir, exist_ok=True)
    pattern = os.path.join(wow, "WTF", "Account", "*", "*", "*", "SavedVariables", "QuestieTrace.lua")
    found = []
    for src in sorted(glob.glob(pattern)):
        parts = os.path.normpath(src).split(os.sep)
        acct, realm, char = parts[-5], parts[-4], parts[-3]
        dst = os.path.join(svdir, "%s__%s__%s.QuestieTrace.lua" % (sanitize(acct), sanitize(realm), sanitize(char)))
        shutil.copyfile(src, dst)
        with open(dst, "rb") as f:
            code = f.read()
        lua = LuaRuntime(unpack_returned_tuples=True)
        try:
            lua.execute(code)
        except Exception as e:  # noqa: BLE001
            print("  skip %s: cannot parse (%s)" % (dst, e))
            continue
        qtc = lua.globals().QuestieTraceCharacter
        if qtc is None or qtc["sessions"] is None:
            continue
        sess = []
        for k, s in sorted(qtc["sessions"].items(), key=lambda kv: kv[0]):
            name, enc = s["name"], s["encoded"]
            if not name or not enc:
                continue
            if isinstance(enc, bytes): enc = enc.decode("utf8")
            if isinstance(name, bytes): name = name.decode("utf8")
            sess.append((name, enc))
        if not sess:
            continue
        if verbose: print("  %s/%s: %d sessions" % (realm, char, len(sess)))
        found.append((realm, char, sess))
    return found


# ---------------------------------------------------------------- step 2
def archive_sessions(found):
    new = 0
    for realm, char, sess in found:
        d = os.path.join(ARCHIVE, sanitize(realm), sanitize(char))
        os.makedirs(d, exist_ok=True)
        for name, enc in sess:
            base = sanitize(name)
            path = os.path.join(d, base + ".txt")
            if os.path.exists(path):
                with open(path, encoding="utf8", newline="") as f:
                    if f.read() == enc:
                        continue
                h = hashlib.sha1(enc.encode("utf8")).hexdigest()[:8]
                path = os.path.join(d, "%s__%s.txt" % (base, h))
                if os.path.exists(path):
                    continue
            with open(path, "w", encoding="utf8", newline="") as f:
                f.write(enc)
            new += 1
    allf = sorted(glob.glob(os.path.join(ARCHIVE, "*", "*", "*.txt")))
    print("Archive: %d new, %d total sessions" % (new, len(allf)))
    return allf


# ---------------------------------------------------------------- step 3
def prepare_extractor():
    if not os.path.isdir(os.path.join(EXTRACTOR, "src")):
        die("extractor not found at %s (see README: git clone vendor/QuestieTrace)" % EXTRACTOR)
    dst = os.path.join(EXTRACTOR, ".qff-src")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(EXTRACTOR, "src"), dst)
    with open(os.path.join(ROOT, "extract", "patches.json"), encoding="utf8") as f:
        patches = json.load(f)
    for p in patches:
        fp = os.path.join(dst, *p["file"].split("/"))
        if not os.path.isfile(fp):
            die("patch target %s missing: upstream extractor changed; update extract/patches.json" % p["file"])
        with open(fp, encoding="utf8", newline="") as f:
            text = f.read()
        n = text.count(p["find"])
        if n != 1:
            die("patch for %s: expected exactly 1 occurrence of %r, found %d: upstream extractor changed; update extract/patches.json" % (p["file"], p["find"], n))
        with open(fp, "w", encoding="utf8", newline="") as f:
            f.write(text.replace(p["find"], p["replace"]))
    shutil.copyfile(os.path.join(ROOT, "extract", "qff-extract.ts"), os.path.join(dst, "qff-extract.ts"))
    if not os.path.isdir(os.path.join(EXTRACTOR, "node_modules")):
        npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
        print("node_modules missing: running npm ci")
        r = subprocess.run([npm, "ci"], cwd=EXTRACTOR)
        if r.returncode: die("npm ci failed")


def run_extractor(files, outdir):
    prepare_extractor()
    listfile = os.path.join(WORK, "session-list.json")
    with open(listfile, "w", encoding="utf8") as f:
        json.dump([os.path.abspath(x) for x in files], f, indent=1)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx: die("npx not found on PATH")
    r = subprocess.run([npx, "tsx", ".qff-src/qff-extract.ts", listfile, outdir], cwd=EXTRACTOR)
    if r.returncode:
        die("extractor failed with exit code %d" % r.returncode)


# ---------------------------------------------------------------- step 5
def source_counts(sources):
    c = {"trace": 0, "wh-tooltip": 0, "trace+wh-tooltip": 0}
    for k in KINDS:
        for v in sources[k].values():
            c[v] += 1
    return c


def render_data_lua(patch, meta, generated_at, sources):
    counts = {k: len(patch[k]) for k in KINDS}
    sc = source_counts(sources)
    L = ["-- Generated by refresh.py. Do not edit; rerun refresh to regenerate.",
         "local _, ns = ...",
         'ns.meta = { generatedAt = %s, questieDBVersion = %s, questieVersion = %s, sessions = %d, characters = %d, extractorCommit = %s, counts = { %s }, sources = { trace = %d, wh = %d, both = %d } }' % (
             luaser.lua_string(generated_at), luaser.lua_string(meta["questieDBVersion"]), luaser.lua_string(meta["questieVersion"]),
             meta["sessionCount"], meta["characters"], luaser.lua_string(meta["extractorCommit"]),
             ", ".join("%s = %d" % (k, counts[k]) for k in KINDS),
             sc["trace"], sc["wh-tooltip"], sc["trace+wh-tooltip"]),
         "ns.data = function()",
         "    return {"]
    for k in KINDS:
        L.append("        %s = {" % k)
        for eid in sorted(patch[k]):
            row = patch[k][eid]
            L.append("            [%d] = %s, -- src: %s" % (eid, luaser.dumps(row), sources[k][eid]))
        L.append("        },")
    L.append("    }")
    L.append("end")
    return "\n".join(L) + "\n"


GEN_RE = re.compile(r'generatedAt = "[^"]*"')


def write_data_lua(patch, meta, sources):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = render_data_lua(patch, meta, now, sources)
    if os.path.exists(DATA_LUA):
        with open(DATA_LUA, encoding="utf8", newline="") as f:
            old = f.read()
        if GEN_RE.sub("", old) == GEN_RE.sub("", new):
            print("Data.lua unchanged")
            return False
    os.makedirs(os.path.dirname(DATA_LUA), exist_ok=True)
    with open(DATA_LUA, "w", encoding="utf8", newline="") as f:
        f.write(new)
    print("Data.lua written (%d bytes)" % len(new.encode("utf8")))
    return True


def git_commit():
    try:
        r = subprocess.run(["git", "-C", os.path.join(ROOT, "vendor", "QuestieTrace"), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
        return r.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wow", default=r"C:\Program Files (x86)\World of Warcraft\_forever_")
    ap.add_argument("--no-extract", action="store_true", help="reuse the last extractor output")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--install", action="store_true", help="copy addon/QuestieForeverFixes into the game's AddOns folder")
    ap.add_argument("--no-wh", action="store_true", help="skip the Wowhead tooltip source and the zone audit")
    ap.add_argument("--wh-offline", action="store_true", help="use only the cached Wowhead tooltips (no network)")
    ap.add_argument("--archive-only", action="store_true", help="only copy new QuestieTrace sessions into archive/ (used by tools/archive-watch.ps1)")
    ap.add_argument("--wh-refresh-days", type=float, default=30, help="refetch cached tooltips older than this (default 30)")
    args = ap.parse_args()

    os.makedirs(WORK, exist_ok=True)
    found = collect_sessions(args.wow, args.verbose)
    files = archive_sessions(found)
    if args.archive_only:
        return
    if not files:
        die("no sessions archived; nothing to extract")

    outdir = os.path.join(WORK, "extract-out")
    if args.no_extract:
        if not os.path.isfile(os.path.join(outdir, "foreverQuestTraces.lua")):
            die("--no-extract given but no previous extractor output in work/extract-out")
    else:
        run_extractor(files, outdir)

    extracted = {k: lua_modules.load_module(os.path.join(outdir, "forever%sTraces.lua" % k)) for k in KINDS}
    addons = os.path.join(args.wow, "Interface", "AddOns")
    db = InstalledDB(os.path.join(addons, "QuestieDB"))
    patch, reasons = patch_policy.build_patch(extracted, db)
    with open(os.path.join(WORK, "trace_patch.json"), "w", encoding="utf8") as f:
        json.dump(patch, f, sort_keys=True)
    sources = {k: {eid: "trace" for eid in patch[k]} for k in KINDS}
    if not args.no_wh:
        zone_audit.init_env(os.path.join(addons, "QuestieDB"))
        wh = wh_tooltip.WH(os.path.join(WORK, "wh"), offline=args.wh_offline, refresh_days=args.wh_refresh_days)
        zsets = zone_audit.Z.zone_sets()
        # Dungeons 48+ audit (ForeverDungeonJournal, read-only); its open-world givers/turn-ins
        # join the tooltip position patch under the same high-confidence rule.
        dres = None
        fdj_dir = os.path.join(addons, "ForeverDungeonJournal")
        if os.path.isdir(fdj_dir):
            dres = dungeon_audit.audit(db, fdj.load_fdj(fdj_dir), dungeon_audit.tooltip_checker(db, wh))
        extra = dungeon_audit.patch_candidates(dres) if dres else None
        wh_result = zone_audit.wh_patch(db, zsets, wh, patch, extra_entities=extra)
        wh_rows, wh_reasons, _info = wh_result
        for kind in ("Npc", "Object"):
            for eid, row in sorted(wh_rows[kind].items()):
                tr = patch[kind].get(eid)
                merged = dict(tr) if tr else {}
                for f, v in row.items():
                    if f == "spawns" or f not in merged:
                        merged[f] = v
                sources[kind][eid] = "trace+wh-tooltip" if tr else "wh-tooltip"
                patch[kind][eid] = merged
        reasons = list(reasons) + wh_reasons
        zone_audit.run(db, wh, patch, wh_result=wh_result, offline=args.wh_offline)
        if dres:
            dtxt = dungeon_audit.write_outputs(dres)
            with open(os.path.join(WORK, "audit", "summary.txt"), "a", encoding="utf8") as f:
                f.write("\n" + dtxt)
        print("Zone audit written to work/audit (%d tooltip requests)" % wh.fetched)
    invalid = sum(1 for r in reasons if r[3] == "invalid-dropped")
    if invalid:
        print("WARNING: %d invalid extracted fields dropped (see report)" % invalid)

    with open(os.path.join(outdir, "meta.json"), encoding="utf8") as f:
        xmeta = json.load(f)
    chars = {tuple(os.path.normpath(p).split(os.sep)[-3:-1]) for p in xmeta["files"]}
    meta = {
        "questieDBVersion": db.version,
        "questieVersion": toc_version(os.path.join(addons, "Questie", "Questie_Forever.toc")),
        "sessionCount": xmeta["sessionCount"],
        "characters": len(chars),
        "extractorCommit": git_commit(),
    }
    write_data_lua(patch, meta, sources)

    with open(os.path.join(WORK, "patch.json"), "w", encoding="utf8") as f:
        json.dump({"meta": meta, "patch": patch, "sources": sources, "reasons": [list(r) for r in reasons]}, f, indent=1, sort_keys=True)
    text = report.build_report(patch, reasons, extracted, db, meta, sources)
    with open(os.path.join(WORK, "report.txt"), "w", encoding="utf8") as f:
        f.write(text)
    print(text)
    print("Summary: " + ", ".join("%s=%d" % (k, len(patch[k])) for k in KINDS) + " patched entities; sessions=%d characters=%d" % (meta["sessionCount"], meta["characters"]))
    if args.install:
        import shutil
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addon", "QuestieForeverFixes")
        dst = os.path.join(addons, "QuestieForeverFixes")
        shutil.copytree(src, dst, dirs_exist_ok=True)
        print("Installed to " + dst + " (new install: restart the game; update: /reload)")


if __name__ == "__main__":
    main()

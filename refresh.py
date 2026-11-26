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

if sys.version_info < (3, 12):
    print("ERROR: Python 3.12 or newer is required (this is %d.%d). Run .\\refresh.ps1, which sets up .venv for you." % sys.version_info[:2])
    sys.exit(1)
try:
    from lupa.lua51 import LuaRuntime  # noqa: E402
except ImportError:
    print("ERROR: the Python package 'lupa' is missing. Run .\\refresh.ps1 once (it creates .venv), or: .venv\\Scripts\\python.exe -m pip install lupa")
    sys.exit(1)

import luaser  # noqa: E402
import lua_modules  # noqa: E402
import patch_policy  # noqa: E402
import wh_tooltip  # noqa: E402
import zone_audit  # noqa: E402
import curated  # noqa: E402
import dungeon_audit  # noqa: E402
import fdj  # noqa: E402
import report  # noqa: E402
from qdb_decode import InstalledDB  # noqa: E402
from overlay_db import OverlayDB  # noqa: E402

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
def check_node():
    node = shutil.which("node")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not node or not npx:
        die("Node.js 24 is required to run the QuestieTrace extractor but 'node' is not on PATH. Install Node 24 LTS from https://nodejs.org and open a new terminal.")
    try:
        ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        if int(ver.lstrip("v").split(".")[0]) < 24:
            print("WARNING: Node %s found; Node 24 is recommended." % ver.lstrip("v"))
    except (OSError, ValueError):
        pass


def prepare_extractor():
    if not os.path.isdir(os.path.join(EXTRACTOR, "src")):
        die("QuestieTrace extractor not found in vendor\\QuestieTrace. Run .\\refresh.ps1 (it clones it), or: git clone https://github.com/Questie/QuestieTrace vendor/QuestieTrace")
    check_node()
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
    c = {}
    for k in KINDS:
        for v in sources[k].values():
            c[v] = c.get(v, 0) + 1
    return c


def render_data_lua(patch, meta, generated_at, sources):
    counts = {k: len(patch[k]) for k in KINDS}
    sc = source_counts(sources)
    L = ["-- Generated by refresh.py. Do not edit; rerun refresh to regenerate.",
         "local _, ns = ...",
         'ns.meta = { generatedAt = %s, questieDBVersion = %s, questieVersion = %s, sessions = %d, characters = %d, extractorCommit = %s, counts = { %s }, sources = { %s } }' % (
             luaser.lua_string(generated_at), luaser.lua_string(meta["questieDBVersion"]), luaser.lua_string(meta["questieVersion"]),
             meta["sessionCount"], meta["characters"], luaser.lua_string(meta["extractorCommit"]),
             ", ".join("%s = %d" % (k, counts[k]) for k in KINDS),
             ", ".join('[%s] = %d' % (luaser.lua_string(k), sc[k]) for k in sorted(sc))),
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


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_if_changed(path, new, label):
    if os.path.exists(path):
        with open(path, encoding="utf8", newline="") as f:
            old = f.read()
        if GEN_RE.sub("", old) == GEN_RE.sub("", new):
            print("%s unchanged" % label)
            return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8", newline="") as f:
        f.write(new)
    print("%s written (%d bytes)" % (label, len(new.encode("utf8"))))
    return True


def write_data_lua(patch, meta, sources):
    new = render_data_lua(patch, meta, utc_now(), sources)
    return write_if_changed(DATA_LUA, new, "Data.lua")


def render_local_data_lua(patch, meta, generated_at):
    counts = {k: len(patch[k]) for k in KINDS}
    ship = (" shippedGeneratedAt = %s," % luaser.lua_string(meta["shippedGeneratedAt"])) if meta.get("shippedGeneratedAt") else ""
    L = ["-- Generated by refresh.py --local from your own QuestieTrace recordings. Do not edit; rerun to regenerate.",
         "-- Lives only on this PC. Addon updates never touch this folder.",
         "QuestieForeverFixes_LocalData = {",
         "    meta = { generatedAt = %s, questieDBVersion = %s, questieVersion = %s, sessions = %d, characters = %d, extractorCommit = %s,%s counts = { %s } }," % (
             luaser.lua_string(generated_at), luaser.lua_string(meta["questieDBVersion"]), luaser.lua_string(meta["questieVersion"]),
             meta["sessionCount"], meta["characters"], luaser.lua_string(meta["extractorCommit"]), ship,
             ", ".join("%s = %d" % (k, counts[k]) for k in KINDS)),
         "    data = function()",
         "        return {"]
    for k in KINDS:
        L.append("            %s = {" % k)
        for eid in sorted(patch[k]):
            L.append("                [%d] = %s, -- src: trace" % (eid, luaser.dumps(patch[k][eid])))
        L.append("            },")
    L.append("        }")
    L.append("    end,")
    L.append("}")
    return "\n".join(L) + "\n"


def local_toc():
    iface = "## Interface: 16001"
    with open(os.path.join(ROOT, "addon", "QuestieForeverFixes", "QuestieForeverFixes.toc"), encoding="utf8") as f:
        for line in f:
            if line.startswith("## Interface:"):
                iface = line.strip()
                break
    return "\n".join([
        iface,
        "## Title: Questie Forever Fixes (local)",
        "## Notes: Your own fixes, built on this PC from your QuestieTrace recordings (refresh.py --local). Used by Questie Forever Fixes; addon updates never touch this folder.",
        "## Author: built locally",
        "## Version: local",
        "",
        "LocalData.lua",
        ""])


def load_shipped(path):
    """Run a shipped Data.lua chunk in a fresh Lua state -> ({kind: {id: {field: value}}}, generatedAt)."""
    with open(path, encoding="utf8") as f:
        src = f.read()
    lua = LuaRuntime(unpack_returned_tuples=True)
    ns = lua.eval("{}")
    chunk = lua.eval("loadstring")(src, "@Data.lua")
    if chunk is None:
        die("cannot parse shipped Data.lua at %s" % path)
    chunk("QuestieForeverFixes", ns)
    meta = ns["meta"]
    gen = meta["generatedAt"] if meta is not None else None
    if isinstance(gen, bytes): gen = gen.decode("utf8")
    data = ns["data"]()
    rows = {k: {} for k in KINDS}
    for k in KINDS:
        t = data[k]
        if t is None: continue
        for eid, row in t.items():
            rows[k][int(eid)] = lua_modules.to_py(row, lua)
    return rows, gen


def git_commit():
    try:
        r = subprocess.run(["git", "-C", os.path.join(ROOT, "vendor", "QuestieTrace"), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
        return r.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def run_local(args, db, addons, extracted, outdir):
    shipped, shipped_gen = {k: {} for k in KINDS}, None
    if args.shipped and args.shipped.lower() == "none":
        print("Shipped baseline: none")
    else:
        path = args.shipped
        if not path:
            path = os.path.join(addons, "QuestieForeverFixes", "Data.lua")
            if not os.path.isfile(path):
                path = DATA_LUA
        if not os.path.isfile(path):
            die("shipped Data.lua not found: %s" % path)
        shipped, shipped_gen = load_shipped(path)
        print("Shipped baseline: %s (%d rows, generated %s)" % (path, sum(len(shipped[k]) for k in KINDS), shipped_gen))
    overlay = OverlayDB(db, shipped)
    patch, reasons = patch_policy.build_patch(extracted, overlay)
    sources = {k: {eid: "trace" for eid in patch[k]} for k in KINDS}
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
        "shippedGeneratedAt": shipped_gen,
    }
    local_out = os.path.abspath(args.local_out) if args.local_out else os.path.join(WORK, "local", "QuestieForeverFixes_Local")
    os.makedirs(local_out, exist_ok=True)
    write_if_changed(os.path.join(local_out, "LocalData.lua"), render_local_data_lua(patch, meta, utc_now()), "LocalData.lua")
    with open(os.path.join(local_out, "QuestieForeverFixes_Local.toc"), "w", encoding="utf8", newline="") as f:
        f.write(local_toc())
    localwork = os.path.join(WORK, "local")
    os.makedirs(localwork, exist_ok=True)
    with open(os.path.join(localwork, "patch.json"), "w", encoding="utf8") as f:
        json.dump({"meta": meta, "patch": patch, "sources": sources, "reasons": [list(r) for r in reasons]}, f, indent=1, sort_keys=True)
    text = report.build_report(patch, reasons, extracted, overlay, meta, sources)
    with open(os.path.join(localwork, "report.txt"), "w", encoding="utf8") as f:
        f.write(text)
    print(text)
    nship = sum(len(shipped[k]) for k in KINDS)
    print("Local: Quest=%d, Npc=%d, Object=%d, Item=%d rows on top of %d shipped rows; sessions=%d characters=%d" % (
        len(patch["Quest"]), len(patch["Npc"]), len(patch["Object"]), len(patch["Item"]), nship, meta["sessionCount"], meta["characters"]))
    print("Local addon written to " + local_out)
    if args.install:
        dst = os.path.join(addons, "QuestieForeverFixes_Local")
        shutil.copytree(local_out, dst, dirs_exist_ok=True)
        print("Installed local fixes to %s (first install: restart the game; later: /reload)" % dst)
        core = os.path.join(addons, "QuestieForeverFixes", "Core.lua")
        if not os.path.isfile(core):
            print("WARNING: Questie Forever Fixes is not installed; the local addon only works together with Questie Forever Fixes.")
        else:
            with open(core, encoding="utf8", errors="replace") as f:
                if "QuestieForeverFixes_LocalData" not in f.read():
                    print("WARNING: the installed Questie Forever Fixes is too old to load local fixes; update it to 0.2.0 or later.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wow", default=r"C:\Program Files (x86)\World of Warcraft\_forever_")
    ap.add_argument("--no-extract", action="store_true", help="reuse the last extractor output")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--install", action="store_true", help="copy addon/QuestieForeverFixes into the game's AddOns folder")
    ap.add_argument("--no-wh", action="store_true", help="skip the Wowhead tooltip source and the zone audit")
    ap.add_argument("--wh-offline", action="store_true", help="use only the cached Wowhead tooltips (no network)")
    ap.add_argument("--archive-only", action="store_true", help="only copy new QuestieTrace sessions into archive/ (for a file watcher)")
    ap.add_argument("--wh-refresh-days", type=float, default=30, help="refetch cached tooltips older than this (default 30)")
    ap.add_argument("--local", action="store_true", help="player mode: build your own fixes into a separate QuestieForeverFixes_Local addon on top of the shipped fixes (no Wowhead, never uploads anything)")
    ap.add_argument("--local-out", metavar="DIR", help="with --local: output addon folder (default work/local/QuestieForeverFixes_Local)")
    ap.add_argument("--shipped", metavar="PATH", help="with --local: shipped Data.lua to build on, or 'none' for no baseline (default: the installed addon's Data.lua, else the repo copy)")
    args = ap.parse_args()
    if not args.local and (args.local_out or args.shipped):
        ap.error("--local-out and --shipped need --local")
    if args.local:
        args.no_wh = True

    os.makedirs(WORK, exist_ok=True)
    found = collect_sessions(args.wow, args.verbose)
    files = archive_sessions(found)
    if args.archive_only:
        return
    if not files:
        die("no sessions archived; nothing to extract")

    outdir = os.path.join(WORK, "local", "extract-out") if args.local else os.path.join(WORK, "extract-out")
    if args.no_extract:
        if not os.path.isfile(os.path.join(outdir, "foreverQuestTraces.lua")):
            die("--no-extract given but no previous extractor output in %s" % os.path.relpath(outdir, ROOT))
    else:
        run_extractor(files, outdir)

    extracted = {k: lua_modules.load_module(os.path.join(outdir, "forever%sTraces.lua" % k)) for k in KINDS}
    addons = os.path.join(args.wow, "Interface", "AddOns")
    db = InstalledDB(os.path.join(addons, "QuestieDB"))
    if args.local:
        return run_local(args, db, addons, extracted, outdir)
    patch, reasons = patch_policy.build_patch(extracted, db)
    with open(os.path.join(WORK, "trace_patch.json"), "w", encoding="utf8") as f:
        json.dump(patch, f, sort_keys=True)
    sources = {k: {eid: "trace" for eid in patch[k]} for k in KINDS}
    extras = {}
    gf_done = gf_skipped = 0
    gf_reasons_ok = []
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
        gf_data = curated.load("gap_fills.json")
        if gf_data is not None:
            gf_rows, gf_reasons, gf_log = zone_audit.gap_fill_patch(db, wh, patch, curated.gap_fill_entities(gf_data))
            for kind in ("Npc", "Object"):
                for eid, row in sorted(gf_rows[kind].items()):
                    cur = patch[kind].get(eid)
                    if cur is not None and "spawns" in cur:
                        gf_log.append("already patched %s %d" % (kind, eid))
                        continue
                    merged = dict(cur) if cur else {}
                    for f, v in row.items():
                        if f == "spawns" or f not in merged:
                            merged[f] = v
                    patch[kind][eid] = merged
                    curated.add_source(sources, kind, eid, "wh-tooltip")
                    gf_done += 1
                    gf_reasons_ok.append((kind, eid))
            reasons += [r for r in gf_reasons if (r[0], r[1]) in set(gf_reasons_ok)]
            extras["(f) Location gap fills"] = gf_log
            gf_skipped = sum(1 for l in gf_log if l.startswith(("skip", "retired", "already")))
        zone_audit.run(db, wh, patch, wh_result=wh_result, offline=args.wh_offline)
        if dres:
            dtxt = dungeon_audit.write_outputs(dres)
            with open(os.path.join(WORK, "audit", "summary.txt"), "a", encoding="utf8") as f:
                f.write("\n" + dtxt)
        print("Zone audit written to work/audit (%d tooltip requests)" % wh.fetched)
    aq = curated.load("added_quests.json")
    cr = curated.load("class_restrictions.json")
    aq_log = cr_log = []
    if aq is not None:
        aq_log = curated.apply_added_quests(patch, sources, reasons, db, aq)
        extras["(d) Added quests"] = aq_log
    if cr is not None:
        cr_log = curated.apply_class_restrictions(patch, sources, reasons, db, cr)
        extras["(e) Class restrictions"] = cr_log
    if aq is not None or cr is not None or "(f) Location gap fills" in extras:
        n_added = sum(1 for l in aq_log if l.startswith("added "))
        n_ret = sum(1 for l in aq_log if l.startswith("retired "))
        n_giver = sum(1 for k in ("Npc", "Object") for v in sources[k].values() if "wh-page" in v.split("+"))
        n_item = sum(1 for v in sources["Item"].values() if "wh-page" in v.split("+"))
        n_cls = sum(1 for l in cr_log if not l.startswith("skip"))
        print("Curated: %d quests added (%d retired), %d giver rows, %d items; %d class restrictions; %d gap fills (%d skipped)" % (
            n_added, n_ret, n_giver, n_item, n_cls, gf_done, gf_skipped))
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
    text = report.build_report(patch, reasons, extracted, db, meta, sources, dict(sorted(extras.items())) or None)
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

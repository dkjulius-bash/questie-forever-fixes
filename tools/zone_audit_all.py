"""All-zones, both-factions audit (standalone, read-only): QuestieDB spawns vs Wowhead Forever tooltip coordinates.

CLI: python -I tools\\zone_audit.py --all-zones [--faction both|alliance|horde] [--offline] [--outdir work/audit-all] [--dry-count]

Zone buckets: every AreaID is mapped to its uiMap (zones.load_area_uimap); all AreaIDs sharing a uiMap form one
bucket ("ui", uiMapID). AreaIDs without a uiMap (or mapped to 0) get their own bucket ("area", AreaID). Dungeons and
raids are NOT merged: each instance uiMap/area is its own bucket. A quest belongs to every bucket that holds its
zoneOrSort (when > 0) or any spawn area of its giver/finisher/objective entities; an entity is reported in a bucket only
if its tooltip zone or one of its DB spawn areas falls in it (unlocated entities stay visible in all of the quest's buckets).
Bucket names: QuestieDB zoneIDs enum (main area, then any area of the uiMap), then UiMap.csv, else uiMap_<id>/area_<id>.
Nothing here writes to addon/ or work/audit.
"""
import json
import math
import os
import re
import time
import datetime
from collections import Counter, defaultdict, OrderedDict

import zones as Z
import wh_tooltip
import zone_audit as ZA
from qdb_decode import InstalledDB, groups, spawn_points, is_sentinel

# Race masks: QuestieDB src/corrections/enum/expansions.lua (raceMaskById, lines 8-26; faction sums lines 33-39;
# bit 32 = SKYBORNE_ALLIANCE (raceID 95), bit 33 = SKYBORNE_HORDE (raceID 96); neutral Pandaren excluded).
ALLIANCE_MASK = 1 | 4 | 8 | 64 | 1024 | 2097152 | 16777216 | (1 << 32)   # human dwarf nelf gnome draenei worgen pand-A skyborne-A
HORDE_MASK = 2 | 16 | 32 | 128 | 512 | 256 | 33554432 | (1 << 33)         # orc undead tauren troll belf goblin pand-H skyborne-H
FACTIONS = ("Alliance", "Horde", "Both")


def quest_faction(row):
    rr = row.get("requiredRaces") or 0
    a, h = bool(rr & ALLIANCE_MASK), bool(rr & HORDE_MASK)
    if a and not h:
        return "Alliance"
    if h and not a:
        return "Horde"
    return "Both"


def keep_faction(tag, want):
    return want == "both" or tag == "Both" or tag.lower() == want


# ------------------------------------------------------------------ naming
def _enum_names(qdb_dir):
    path = os.path.join(qdb_dir, "src", "corrections", "enum", "zones.lua")
    with open(path, encoding="utf8") as f:
        text = f.read()
    m = re.search(r"constants\.zoneIDs\s*=\s*\{(.*?)\n\}", text, re.S)
    out = {}
    for n, a in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*=\s*(\d+)", "\n".join(l.split("--", 1)[0] for l in m.group(1).splitlines())):
        out.setdefault(int(a), n.replace("_", " ").title().replace("'S", "'s"))
    return out


def _uimap_csv_names(offline):
    try:
        rows = ZA.ensure_csv("UiMap", offline)
    except Exception:  # noqa: BLE001
        return {}
    return {int(r["ID"]): r.get("Name_lang") for r in rows if r.get("ID", "").isdigit() and r.get("Name_lang")}


# ------------------------------------------------------------------ collect
def bkey(a2u, area):
    u = a2u.get(area)
    return ("ui", u) if u else ("area", area)


def collect_all(db, a2u, want):
    """-> (buckets {key: {qid: info}}, qinfo {qid: {name, faction}}, spawn_weight {key: Counter(area)})."""
    buckets = defaultdict(dict)
    qinfo = {}
    weight = defaultdict(Counter)
    area_cache = {}

    def areas(kind, eid):
        k = (kind, eid)
        if k not in area_cache:
            exists, by_area, all_areas = ZA._db_pts(db, kind, eid)
            area_cache[k] = (all_areas, {a: len(p) for a, p in by_area.items()})
        return area_cache[k]

    for qid in sorted(db.ids("Quest")):
        row = db.get("Quest", qid)
        if not row:
            continue
        tag = quest_faction(row)
        if not keep_faction(tag, want):
            continue
        roles = {}
        for role, field in (("giver", "startedBy"), ("finisher", "finishedBy")):
            g = groups(row.get(field))
            roles[role] = [("Npc", i) for i in g.get(1, [])] + [("Object", i) for i in g.get(2, [])]
        roles["objective"], generic = ZA._objective_entities(db, row)
        allents = set(roles["giver"]) | set(roles["finisher"]) | set(roles["objective"])
        zs = row.get("zoneOrSort")
        keys = set()
        if isinstance(zs, int) and zs > 0:
            keys.add(bkey(a2u, zs))
        for k, i in allents:
            all_areas, cnt = areas(k, i)
            for a in all_areas:
                keys.add(bkey(a2u, a))
            for a, n in cnt.items():
                weight[bkey(a2u, a)][a] += n
        qinfo[qid] = {"name": row.get("name"), "faction": tag, "zoneOrSort": zs}
        info = {"name": row.get("name"), "zoneOrSort": zs, "faction": tag, "giver": roles["giver"],
                "finisher": roles["finisher"], "objective": roles["objective"], "generic-drop-item": generic}
        for key in keys:
            buckets[key][qid] = info
    return buckets, qinfo, weight


def name_buckets(buckets, a2u, weight, enum_names, ui_names):
    """-> OrderedDict name -> {key, main, areas(set), uimap}."""
    out = OrderedDict()
    used = set()
    for key in sorted(buckets, key=lambda k: (k[0], k[1])):
        kind, v = key
        if kind == "ui":
            group = Z.uimap_group(v)
            w = weight.get(key) or Counter()
            main = max(sorted(group), key=lambda a: (w.get(a, 0), -a)) if w else None
            if main is None or w.get(main, 0) == 0:
                inenum = sorted(a for a in group if a in enum_names)
                main = inenum[0] if inenum else (min(group) if group else None)
            name = enum_names.get(main) or next((enum_names[a] for a in sorted(group) if a in enum_names), None) \
                or ui_names.get(v) or "uiMap_%d" % v
            areas = set(group)
        else:
            main = v
            name = enum_names.get(v) or "area_%d" % v
            areas = {v}
        if name in used:
            name = "%s [%s %d]" % (name, "uiMap" if kind == "ui" else "area", v)
        used.add(name)
        out[name] = {"key": key, "main": main, "areas": areas, "uimap": v if kind == "ui" else None}
    return out


# ------------------------------------------------------------------ wowhead cache
def needs_fetch(wh, kind, eid):
    path = wh._path(kind.lower(), eid)
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        return True
    limit = wh_tooltip.ERROR_RETRY_DAYS if "error" in cached else wh.refresh_days
    return wh_tooltip._age_days(cached) > limit


def all_entities(buckets):
    s = set()
    for qd in buckets.values():
        for info in qd.values():
            for role in ("giver", "finisher", "objective"):
                s.update(info[role])
    return sorted(s)


def prefetch(wh, ents, log):
    todo = [e for e in ents if needs_fetch(wh, ZA.KMAP[e[0]], e[1])]
    t0 = time.time()
    last = 0
    for n, (kind, eid) in enumerate(todo, 1):
        wh.get(ZA.KMAP[kind], eid)
        if wh.fetched - last >= 200 or n == len(todo):
            last = wh.fetched
            log("prefetch %d/%d (%d requests, %.0fs elapsed, ETA %.0fs)" % (
                n, len(todo), wh.fetched, time.time() - t0, (time.time() - t0) / n * (len(todo) - n)))


# ------------------------------------------------------------------ audit
def audit_all(db, wh, transforms, zinfo, buckets):
    results = OrderedDict()
    for zname, zi in zinfo.items():
        qd = buckets[zi["key"]]
        areas = zi["areas"]
        zr = {"uimap": zi["uimap"], "main_area": zi["main"], "quests": len(qd),
              "quests_by_faction": dict(Counter(i["faction"] for i in qd.values()))}
        for part, roles in (("a", ("giver", "finisher")), ("b", ("objective",))):
            ents = ZA._entities_of(qd, roles)
            rows = []
            for (kind, eid), info in sorted(ents.items()):
                res = ZA.check_entity(db, wh, transforms, kind, eid)
                cand = ([res["whzone"]] if res["whzone"] else []) + list(res["db_areas"])
                if cand and not any(a in areas for a in cand):
                    continue
                r = dict(res)
                r["quests"] = sorted(info["quests"])
                r["roles"] = sorted(info["roles"])
                r["factions"] = sorted({qd[q]["faction"] for q in info["quests"]})
                rows.append(r)
            qbad = defaultdict(set)
            for r in rows:
                if r["status"] != "ok":
                    qbad[r["status"]].update(r["quests"])
            allbad = set().union(*qbad.values()) if qbad else set()
            zr[part] = {"rows": rows, "entity_counts": dict(Counter(r["status"] for r in rows)),
                        "partial": sum(1 for r in rows if r["partial"]),
                        "quest_counts": {s: len(qbad[s]) for s in ZA.STATUSES if s != "ok"},
                        "quests_with_problem": len(allbad)}
        results[zname] = zr
    return results


def propose_action(res, qbuckets, bucket_of_area):
    st = res["status"]
    if st == "questie-no-spawns":
        if res["wh"] and res["whzone"] is not None and bucket_of_area(res["whzone"]) in qbuckets:
            return "fill-gap"
        return "review"
    if st in ("far", "zone-mismatch"):
        return "review"
    return "ignore"


def candidates(results, buckets, zinfo, a2u):
    agg = {}
    qb = defaultdict(set)
    for zname, zi in zinfo.items():
        for q in buckets[zi["key"]]:
            qb[q].add(zi["key"])
    for zname, zr in results.items():
        for part in ("a", "b"):
            for r in zr[part]["rows"]:
                if r["status"] == "ok":
                    continue
                k = (r["kind"], r["id"])
                e = agg.setdefault(k, {"res": r, "quests": set(), "factions": set(), "roles": set(), "zones": set()})
                e["quests"].update(r["quests"])
                e["factions"].update(r["factions"])
                e["roles"].update(r["roles"])
                e["zones"].add(zname)
    out = []
    for (kind, eid), e in sorted(agg.items()):
        r = e["res"]
        keys = set()
        for q in e["quests"]:
            keys |= qb[q]
        out.append({"kind": kind, "id": eid, "name": r["name"], "status": r["status"], "distance": r["dist"],
                    "questie_points": r["qpts"], "wh_points": r["wh"], "wh_zone": r["whzone"],
                    "roles": sorted(e["roles"]), "zones": sorted(e["zones"]), "quests": sorted(e["quests"]),
                    "factions": sorted(e["factions"]),
                    "action": propose_action(r, keys, lambda a: bkey(a2u, a))})
    return out


# ------------------------------------------------------------------ summary
def build_summary(results, buckets, qinfo, cands, args, qcounts_total, fetched, wh_info, wh_rows):
    L = []
    P = L.append
    P("All-zones audit summary  (%s)  faction=%s offline=%s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), args.faction, args.offline))
    P("=" * 40)
    P("zones (buckets): %d | quests audited: %d | quests per faction: %s | quests with no bucket: %d" % (
        len(results), len(qinfo), dict(Counter(i["faction"] for i in qinfo.values())), qcounts_total["nobucket"]))
    P("a = giver/finisher entities, b = objective entities; columns ok/far/wh-era-frame/zone-mismatch/no-spawns/no-wh")
    hdr = "%-34s %7s %6s %6s %6s  %-26s %-26s"
    P(hdr % ("zone", "quests", "A", "H", "Both", "a", "b"))
    tot = {"a": Counter(), "b": Counter()}
    for zn, r in results.items():
        qf = r["quests_by_faction"]

        def cs(part):
            c = r[part]["entity_counts"]
            return "/".join(str(c.get(s, 0)) for s in ZA.STATUSES)
        P(hdr % (zn[:34], r["quests"], qf.get("Alliance", 0), qf.get("Horde", 0), qf.get("Both", 0), cs("a"), cs("b")))
    P("")
    # unique-entity totals (union over zones) and per-faction breakdown
    ent = {"a": {}, "b": {}}
    for r in results.values():
        for part in ("a", "b"):
            for row in r[part]["rows"]:
                e = ent[part].setdefault((row["kind"], row["id"]), {"status": row["status"], "factions": set()})
                e["factions"].update(row["factions"])
    P("Totals: unique entities (an entity can be in both a and b; zone-filtered union)")
    for part, label in (("a", "givers/finishers"), ("b", "objectives")):
        c = Counter(e["status"] for e in ent[part].values())
        P("  %-18s %d entities: %s" % (label, len(ent[part]), {s: c.get(s, 0) for s in ZA.STATUSES}))
    P("")
    P("Per-faction breakdown (entity counted for a faction if any of its quests carries that tag)")
    for f in FACTIONS:
        nq = sum(1 for i in qinfo.values() if i["faction"] == f)
        P("  %-9s quests=%d" % (f, nq))
        for part, label in (("a", "givers/finishers"), ("b", "objectives")):
            c = Counter(e["status"] for e in ent[part].values() if f in e["factions"])
            P("      %-18s %d: %s" % (label, sum(c.values()), {s: c.get(s, 0) for s in ZA.STATUSES}))
    P("")
    P("Candidates (non-ok entities): %d  by status %s" % (len(cands), dict(Counter(c["status"] for c in cands))))
    P("Proposed actions: %s" % dict(Counter(c["action"] for c in cands)))
    for act in ("fill-gap", "review"):
        P("")
        P("Top 15 %s by quests affected" % act)
        top = sorted((c for c in cands if c["action"] == act), key=lambda c: (-len(c["quests"]), c["kind"], c["id"]))[:15]
        for c in top:
            P("  %-6s %-8d %-30s %-18s quests=%-4d fac=%s dist=%s whzone=%s zones=%s" % (
                c["kind"], c["id"], (c["name"] or "?")[:30], c["status"], len(c["quests"]), "/".join(c["factions"]),
                c["distance"], c["wh_zone"], ",".join(c["zones"][:3])))
    P("")
    P("wh_patch preview: %s (rows: Npc %d, Object %d)" % (dict(Counter(i["reason"] for i in wh_info.values())),
                                                           len(wh_rows["Npc"]), len(wh_rows["Object"])))
    P("tooltip requests this run: %d" % fetched)
    return "\n".join(L) + "\n"


def _jd(o):
    if isinstance(o, (set, tuple)):
        return sorted(o) if isinstance(o, set) else list(o)
    return str(o)


def main(args):
    qdb = ZA.QDB_DIR
    ZA.init_env(qdb)
    a2u, transforms = Z._A2U, Z._TRANSFORMS
    outdir = args.outdir or os.path.join(ZA.WORK, "audit-all")
    os.makedirs(outdir, exist_ok=True)
    logf = open(os.path.join(outdir, "progress.log"), "a", encoding="utf-8")

    def log(msg):
        line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    db = InstalledDB(qdb)
    wh = wh_tooltip.WH(os.path.join(ZA.WORK, "wh"), offline=args.offline)
    log("collecting quests (faction=%s)" % args.faction)
    buckets, qinfo, weight = collect_all(db, a2u, args.faction)
    ents = all_entities(buckets)
    unc = [e for e in ents if needs_fetch(wh, ZA.KMAP[e[0]], e[1])]
    log("quests=%d buckets=%d entities=%d uncached=%d ETA ~%.0f min (%.2fs each, offline=%s)" % (
        len(qinfo), len(buckets), len(ents), len(unc), len(unc) * (wh_tooltip.SLEEP + 0.05) / 60, wh_tooltip.SLEEP, args.offline))
    if args.dry_count:
        return
    if not args.offline:
        prefetch(wh, ents, log)
    enum_names = _enum_names(qdb)
    ui_names = _uimap_csv_names(args.offline)
    zinfo = name_buckets(buckets, a2u, weight, enum_names, ui_names)
    log("auditing %d zones" % len(zinfo))
    results = audit_all(db, wh, transforms, zinfo, buckets)
    cands = candidates(results, buckets, zinfo, a2u)

    zmain = OrderedDict((n, zi["main"]) for n, zi in zinfo.items() if zi["uimap"])
    coll = {n: buckets[zinfo[n]["key"]] for n in zinfo}
    rows, reasons, info = ZA.wh_patch(db, None, wh, ZA.load_trace_patch(), coll=coll, zones_main=zmain)

    qcounts_total = {"nobucket": len(qinfo) - len({q for qd in buckets.values() for q in qd})}
    text = build_summary(results, buckets, qinfo, cands, args, qcounts_total, wh.fetched, info, rows)
    for zn, r in results.items():
        payload = dict(r)
        payload["quest_list"] = {str(q): buckets[zinfo[zn]["key"]][q] for q in sorted(buckets[zinfo[zn]["key"]])}
        fn = re.sub(r"[^A-Za-z0-9_.-]+", "_", zn) + ".json"
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, default=_jd)
    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(outdir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(cands, f, indent=1, default=_jd)
    preview = {"rows": {k: {str(i): v for i, v in d.items()} for k, d in rows.items()},
               "reasons": [list(r) for r in reasons],
               "info": [dict(kind=k, id=i, **v) for (k, i), v in sorted(info.items())]}
    with open(os.path.join(outdir, "wh_patch_preview.json"), "w", encoding="utf-8") as f:
        json.dump(preview, f, indent=1, default=_jd)
    log("done; outputs in %s" % outdir)
    print(text)

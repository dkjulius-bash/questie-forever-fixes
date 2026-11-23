"""Zone audit: compare QuestieDB with Wowhead Forever tooltip coordinates for 6 zones; propose wh-tooltip spawn patches.

CLI: python -I tools\\zone_audit.py [--offline]
"""
import argparse
import csv
import datetime
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import zones as Z  # noqa: E402
import wh_tooltip  # noqa: E402
from qdb_decode import InstalledDB, groups, id_list, spawn_points, is_sentinel  # noqa: E402
from patch_policy import _db_obj_groups, _rows_list  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
QDB_DIR = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
ALLY = (1 << 32) | 77
FAR = 3.0
PARTIAL = 0.5
GENERIC_DROPS = 25
KMAP = {"Npc": "npc", "Object": "object"}
# wh-era-frame: "far", but the tooltip matches Questie once Questie is projected back to the Era frame,
# i.e. Wowhead serves stale Era coordinates for a redrawn map (EPL 139, Redridge 44, Mulgore 215, Stormwind 1519).
STATUSES = ("ok", "far", "wh-era-frame", "zone-mismatch", "questie-no-spawns", "no-wh-coords")

_COLLECT = {}
_CHECKS = {}


def is_alliance(row):
    rr = row.get("requiredRaces") or 0
    return not rr or bool(rr & ALLY)


def _db_pts(db, kind, eid):
    """(entity exists, {area: [non-sentinel (x,y,...)]}, areas with any points incl. sentinels)."""
    row = db.get(kind, eid)
    if row is None:
        return False, {}, set()
    sp = spawn_points(row.get("spawns"))
    return True, {a: [p for p in pts if not is_sentinel(p)] for a, pts in sp.items()}, {a for a, pts in sp.items() if pts}


# ------------------------------------------------------------------ collect
def _first_ids(r):
    if isinstance(r, (list, tuple)):
        return id_list(r[:1])
    if isinstance(r, dict):
        return id_list(r.get(1))
    return id_list(r)


def _objective_entities(db, row):
    og = _db_obj_groups(row.get("objectives"))
    ents, generic = [], []
    for g, kind in ((1, "Npc"), (2, "Object")):
        for r in _rows_list(og.get(g)):
            ents += [(kind, i) for i in _first_ids(r)[:1]]
    for r in _rows_list(og.get(5)):
        if isinstance(r, (list, tuple)):
            ids = id_list(r[0]) if r else []
            if len(r) > 1:
                ids += id_list(r[1])
        else:
            ids = id_list(r)
        ents += [("Npc", i) for i in ids]
    for r in _rows_list(og.get(3)):
        for iid in _first_ids(r)[:1]:
            irow = db.get("Item", iid) or {}
            nd, od = id_list(irow.get("npcDrops")), id_list(irow.get("objectDrops"))
            if len(nd) + len(od) > GENERIC_DROPS:
                generic.append(iid)
            else:
                ents += [("Npc", i) for i in nd] + [("Object", i) for i in od]
    return list(dict.fromkeys(ents)), generic


def collect(db, zone_sets):
    """-> {zone: {qid: {name, zoneOrSort, by, giver, finisher, objective, generic-drop-item}}} (Alliance quests only)."""
    key = (id(db), tuple((n, len(s)) for n, s in zone_sets.items()))
    if key in _COLLECT:
        return _COLLECT[key]
    out = {n: {} for n in zone_sets}
    spawn_cache = {}

    def areas(kind, eid):
        k = (kind, eid)
        if k not in spawn_cache:
            spawn_cache[k] = _db_pts(db, kind, eid)[2]
        return spawn_cache[k]

    for qid in sorted(db.ids("Quest")):
        row = db.get("Quest", qid)
        if not row or not is_alliance(row):
            continue
        roles = {}
        for role, field in (("giver", "startedBy"), ("finisher", "finishedBy")):
            g = groups(row.get(field))
            roles[role] = [("Npc", i) for i in g.get(1, [])] + [("Object", i) for i in g.get(2, [])]
        roles["objective"], generic = _objective_entities(db, row)
        allents = set(roles["giver"]) | set(roles["finisher"]) | set(roles["objective"])
        zs = row.get("zoneOrSort")
        for name, zset in zone_sets.items():
            by = None
            if zs in zset:
                by = "zone"
            elif any(areas(k, i) & zset for k, i in allents):
                by = "spawn"
            if by:
                out[name][qid] = {"name": row.get("name"), "zoneOrSort": zs, "by": by,
                                  "giver": roles["giver"], "finisher": roles["finisher"],
                                  "objective": roles["objective"], "generic-drop-item": generic}
    _COLLECT[key] = out
    return out


# ------------------------------------------------------------------ entity check
def _nearest(p, qpts):
    return min(qpts, key=lambda q: math.dist(p, q[:2])) if qpts else None


def check_entity(db, wh, transforms, kind, eid):
    """Public per-entity check. kind 'Npc'/'Object'. -> dict(status, dist, whzone, wh, coverage, ...)."""
    key = (id(db), kind, eid)
    if key in _CHECKS:
        return _CHECKS[key]
    d = wh.get(KMAP[kind], eid)
    wz, wp, dropped = wh_tooltip.points(d, transforms) if d else (None, [], 0)
    exists, by_area, all_areas = _db_pts(db, kind, eid)
    row = db.get(kind, eid) or {}
    u = Z.uimap_of(wz) if wz else None
    qpts = []
    if wz:
        group = (Z.uimap_group(u) | {wz}) if u else {wz}
        qpts = [(p[0], p[1], a) for a, pts in by_area.items() if a in group for p in pts]
    dist = min((math.dist(a, q[:2]) for a in wp for q in qpts), default=None)
    cov = None
    if wp and qpts:
        cov = sum(1 for a in wp if min(math.dist(a, q[:2]) for q in qpts) <= FAR) / len(wp)
    if not wp:
        status = "no-wh-coords"
    elif not all_areas:
        status = "questie-no-spawns"
    elif not qpts:
        status = "zone-mismatch"
    elif dist > FAR:
        status = "far"
        conv = [Z.forever_to_era(q[2], q[0], q[1], transforms) for q in qpts]
        if any(q[2] in transforms for q in qpts) and                 min(math.dist(a, c) for a in wp for c in conv) <= FAR:
            status = "wh-era-frame"
    else:
        status = "ok"
    res = {"kind": kind, "id": eid, "name": row.get("name") or (d or {}).get("name"), "status": status,
           "dist": None if dist is None else round(dist, 2), "whzone": wz, "wh": [list(p) for p in wp],
           "coverage": None if cov is None else round(cov, 3),
           "partial": bool(status == "ok" and cov is not None and cov < PARTIAL),
           "era_dropped": dropped, "in_db": exists,
           "qpts": [list(q) for q in qpts], "db_areas": sorted(all_areas),
           "tooltip_error": ((d or {}).get("error") if d else "not-cached")}
    _CHECKS[key] = res
    return res


def entity_in_zone(res, zname, zset, a2u):
    zu = a2u.get(Z.ZONES[zname])
    cand = ([res["whzone"]] if res["whzone"] else []) + list(res["db_areas"])
    if not cand:
        return True  # unlocated entity of an in-scope quest: cannot be placed anywhere, keep it visible
    return any(a in zset or (zu and a2u.get(a) == zu) for a in cand)


# ------------------------------------------------------------------ db2
def ensure_csv(table, offline):
    path = os.path.join(WORK, "db2", table + ".csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < 7 * 86400
    if not fresh and not offline:
        req = urllib.request.Request("https://wago.tools/db2/%s/csv?product=wowf" % table, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:  # noqa: BLE001
            print("WARNING: could not fetch %s: %s" % (table, e))
        finally:
            time.sleep(wh_tooltip.SLEEP)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ chains
def _pre_ids(row):
    return set(id_list(row.get("preQuestSingle"))) | set(id_list(row.get("preQuestGroup")))


def chain_check(db, qids, lines):
    """QuestLineXQuest predecessor vs DB prereqs (report-only)."""
    by_line = defaultdict(dict)
    for r in lines:
        by_line[r["QuestLineID"]][int(r["OrderIndex"])] = int(r["QuestID"])
    res = {"match": 0, "db-missing": 0, "db-different": 0, "mismatches": []}
    for line, order in by_line.items():
        for oi, q in order.items():
            if q not in qids or oi - 1 not in order:
                continue
            pred = order[oi - 1]
            pre = _pre_ids(db.get("Quest", q) or {})
            kind = "match" if pred in pre else ("db-missing" if not pre else "db-different")
            res[kind] += 1
            if kind != "match":
                res["mismatches"].append({"quest": q, "line": line, "pred": pred, "db_pre": sorted(pre), "kind": kind})
    return res


def rg_chain_check(db):
    path = os.path.join(WORK, "rg_wh.txt")
    if not os.path.exists(path):
        return None
    res = {"match": 0, "db-missing": 0, "db-different": 0, "mismatches": []}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            q, prev = int(parts[0]), int(parts[1] or 0)
            row = db.get("Quest", q)
            pre = _pre_ids(row or {})
            if row is None:
                kind = "db-missing"
            elif prev == 0:
                kind = "match" if not pre else "db-different"
            elif prev in pre:
                kind = "match"
            else:
                kind = "db-missing" if not pre else "db-different"
            res[kind] += 1
            if kind != "match":
                res["mismatches"].append({"quest": q, "name": (row or {}).get("name"), "wh_prev": prev,
                                          "db_pre": sorted(pre), "kind": kind})
    return res


# ------------------------------------------------------------------ audit
def _entities_of(qd, roles):
    s = {}
    for q, info in qd.items():
        for role in roles:
            for e in info[role]:
                s.setdefault(e, {"quests": set(), "roles": set()})
                s[e]["quests"].add(q)
                s[e]["roles"].add(role)
    return s


def _examples(rows, n=5):
    rows = sorted(rows, key=lambda r: (-(r["dist"] if r["dist"] is not None else -1), r["id"]))
    return rows[:n]


def audit(db, wh, transforms, zsets, coll, offline=False):
    a2u = Z._A2U
    lines = ensure_csv("QuestLineXQuest", offline)
    blobs = ensure_csv("QuestPOIBlob", offline)
    v2 = ensure_csv("QuestV2", offline)
    ensure_csv("QuestPOIPoint", offline)
    ensure_csv("UiMapAssignment", offline)
    dbq = db.ids("Quest")
    missing_v2 = sorted(int(r["ID"]) for r in v2 if int(r["ID"]) not in dbq)
    missing_set = set(missing_v2)
    out = {}
    for zname, zset in zsets.items():
        qd = coll[zname]
        u = a2u.get(Z.ZONES[zname])
        zr = {"uimap": u, "quests": len(qd)}
        for part, roles in (("a", ("giver", "finisher")), ("b", ("objective",))):
            ents = _entities_of(qd, roles)
            rows = []
            for (kind, eid), info in sorted(ents.items()):
                res = check_entity(db, wh, transforms, kind, eid)
                if not entity_in_zone(res, zname, zset, a2u):
                    continue
                r = dict(res)
                r["quests"] = sorted(info["quests"])
                r["roles"] = sorted(info["roles"])
                rows.append(r)
            qbad = defaultdict(set)
            for r in rows:
                if r["status"] != "ok":
                    for q in r["quests"]:
                        qbad[r["status"]].add(q)
            allbad = set().union(*qbad.values()) if qbad else set()
            zr[part] = {"rows": rows, "entity_counts": dict(Counter(r["status"] for r in rows)),
                        "partial": sum(1 for r in rows if r["partial"]),
                        "quest_counts": {s: len(qbad[s]) for s in STATUSES if s != "ok"},
                        "quests_with_problem": len(allbad),
                        "examples": {s: _examples([r for r in rows if r["status"] == s]) for s in STATUSES if s != "ok"}}
        zr["generic_drop_items"] = sorted({i for info in qd.values() for i in info["generic-drop-item"]})
        zblobs = [r for r in blobs if int(r["UiMapID"]) == u]
        zr["c"] = {"blobs": len(zblobs), "quests": sorted({int(r["QuestID"]) for r in zblobs})}
        zr["d"] = chain_check(db, set(qd), lines)
        if zname == "Riverglades":
            zr["d_rg_wh"] = rg_chain_check(db)
        zr["e"] = {"total_missing": len(missing_v2),
                   "zone_attributed": [q for q in zr["c"]["quests"] if q in missing_set]}
        # frame diagnostics
        allrows = zr["a"]["rows"] + zr["b"]["rows"]
        dropped_ents = {(r["kind"], r["id"]): r["era_dropped"] for r in allrows if r["era_dropped"]}
        far = {(r["kind"], r["id"]): r for r in allrows if r["status"] in ("far", "wh-era-frame")}
        dxs, dys, fix_e2f, fix_f2e = [], [], 0, 0
        for r in far.values():
            for w in r["wh"]:
                q = _nearest(w, r["qpts"])
                dxs.append(w[0] - q[0])
                dys.append(w[1] - q[1])
            for fn, tag in ((Z.era_to_forever, "e2f"), (Z.forever_to_era, "f2e")):
                conv = [fn(q[2], q[0], q[1], transforms) for q in r["qpts"]]
                if min(math.dist(w, c) for w in r["wh"] for c in conv) <= FAR:
                    if tag == "e2f":
                        fix_e2f += 1
                    else:
                        fix_f2e += 1
        zr["frame"] = {"stale_era_entities": len(dropped_ents), "stale_era_points": sum(dropped_ents.values()),
                       "far_entities": len(far),
                       "median_dx": round(statistics.median(dxs), 2) if dxs else None,
                       "median_dy": round(statistics.median(dys), 2) if dys else None,
                       "far_ok_if_era_to_forever": fix_e2f, "far_ok_if_forever_to_era": fix_f2e}
        out[zname] = zr
    return out, len(missing_v2)


# ------------------------------------------------------------------ wh patch
def _rnd(pts):
    return [[round(c, 2) if isinstance(c, float) else c for c in p] for p in pts]


def _norm_pts(pts):
    return [(round(p[0], 4), round(p[1], 4)) for p in pts]


def wh_patch(db, zones, wh, trace_patch, extra_entities=None):
    """-> (rows {"Npc": {id: {field: v}}, "Object": {...}}, reasons [(kind, id, field, reason)], info {(kind,id): {...}}).

    extra_entities: optional iterable of (kind, id); for these any outdoor zone (tooltip zone with a uiMap) is allowed
    and the key AreaID is the one existing DB spawns already use for that uiMap, else the tooltip zone id.
    """
    a2u = Z._A2U
    transforms = Z._TRANSFORMS
    coll = collect(db, zones)
    umaps = {a2u.get(m): n for n, m in Z.ZONES.items()}
    qrefs = defaultdict(set)
    for qd in coll.values():
        for q, info in qd.items():
            for role in ("giver", "finisher", "objective"):
                for e in info[role]:
                    qrefs[e].add(q)
    extra = set(extra_entities or [])
    rows = {"Npc": {}, "Object": {}}
    reasons = []
    info = {}
    for kind, eid in sorted(set(qrefs) | extra):
        res = check_entity(db, wh, transforms, kind, eid)
        wz, wp = res["whzone"], [tuple(p) for p in res["wh"]]
        if not wp or not wz:
            continue
        u = a2u.get(wz)
        is_extra = (kind, eid) in extra
        if not u or (not is_extra and u not in umaps):
            continue
        group = Z.uimap_group(u) | {wz}
        if group & set(transforms):
            # Redrawn map: Wowhead tooltips mix/keep stale Era-frame points, so a single tooltip
            # point can't be trusted in either frame. Never patch from it.
            continue
        trace_row = (trace_patch.get(kind) or {}).get(eid) or {}
        dbrow = db.get(kind, eid)
        dbsp = spawn_points(dbrow.get("spawns")) if dbrow else {}
        tsp = trace_row.get("spawns")
        S = {z: [tuple(p) for p in pts] for z, pts in (spawn_points(tsp) if tsp is not None else dbsp).items()}
        if tsp is not None and any(a in group and _norm_pts(S.get(a, [])) != _norm_pts(dbsp.get(a, [])) for a in S):
            continue  # trace wins
        if is_extra and not (u in umaps):
            existing = sorted(a for a in group if dbsp.get(a))
            main = existing[0] if existing else wz
        else:
            main = Z.ZONES[umaps[u]]
        qpts = [p for a, pts in S.items() if a in group for p in pts if not is_sentinel(p)]
        dist = min((math.dist(a, p[:2]) for a in wp for p in qpts), default=None)
        newpts = [list(p) for p in wp]
        if not qpts:
            S[main] = newpts
            why = "wh-add-zone"
        elif dist > FAR:
            for a in list(S):
                if a in group:
                    del S[a]
            S[main] = newpts
            why = "wh-replace-zone"
        else:
            continue
        out = {"spawns": {z: _rnd(pts) for z, pts in S.items()}}
        reasons.append((kind, eid, "spawns", why))
        if dbrow is None:
            out["name"] = res["name"] or ""
            out["zoneID"] = main
            reasons.append((kind, eid, "name", "wh-new-entity"))
            reasons.append((kind, eid, "zoneID", "wh-new-entity"))
        rows[kind][eid] = out
        info[(kind, eid)] = {"name": res["name"], "reason": why, "dist": dist, "old": [list(p[:2]) for p in qpts],
                             "new": newpts, "quests": sorted(qrefs.get((kind, eid), [])), "zone": wz, "area": main}
    return rows, reasons, info


# ------------------------------------------------------------------ summary
def _fmt_pts(pts, n=4):
    s = ", ".join("(%.1f,%.1f)" % (p[0], p[1]) for p in pts[:n])
    return s + (" +%d" % (len(pts) - n) if len(pts) > n else "")


def build_summary(results, qsets, wh_info, wh_rows, qnames):
    L = []
    P = L.append
    P("Zone audit summary  (%s)" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    P("=" * 40)
    P("")
    P("Per-zone table (Alliance quests; a = giver/finisher entities, b = objective entities, unique entities)")
    P("  a/b columns: ok/far/wh-era-frame/zone-mismatch/no-spawns/no-wh ; d: QuestLine match/db-missing/db-different")
    hdr = "%-20s %6s  %-24s %-24s %9s %5s  %-34s %s"
    P(hdr % ("zone", "quests", "a", "b", "b-partial", "c", "d", "e (total/zone)"))
    for zn, r in results.items():
        def cs(part):
            c = r[part]["entity_counts"]
            return "/".join(str(c.get(s, 0)) for s in STATUSES)
        c_txt = str(r["c"]["blobs"]) if r["c"]["blobs"] else "n/a"
        d = r["d"]
        d_txt = "%d/%d/%d" % (d["match"], d["db-missing"], d["db-different"])
        if r.get("d_rg_wh"):
            w = r["d_rg_wh"]
            d_txt += " rg_wh %d/%d/%d" % (w["match"], w["db-missing"], w["db-different"])
        P(hdr % (zn, r["quests"], cs("a"), cs("b"), r["b"]["partial"], c_txt, d_txt,
                 "%d/%d" % (r["e"]["total_missing"], len(r["e"]["zone_attributed"]))))
    P("  a-partial (ok but coverage<0.5): " + ", ".join("%s=%d" % (zn, r["a"]["partial"]) for zn, r in results.items()))
    P("")
    for zn, r in results.items():
        P("--- %s (uiMap %s) ---" % (zn, r["uimap"]))
        for part, label in (("a", "(a) givers/finishers"), ("b", "(b) objectives")):
            p = r[part]
            P("  %s: entities %s | quests with >=1 non-ok entity: %d, by status %s" % (
                label, p["entity_counts"], p["quests_with_problem"], p["quest_counts"]))
            for s, ex in p["examples"].items():
                for e in ex:
                    P("      %-18s %s %d %s dist=%s whzone=%s wh=%s questie=%s" % (
                        s, e["kind"], e["id"], e["name"], e["dist"], e["whzone"], _fmt_pts(e["wh"], 2), _fmt_pts(e["qpts"], 2)))
        if r["c"]["blobs"]:
            P("  (c) POI blobs for this uiMap: %d (quests %s)" % (r["c"]["blobs"], r["c"]["quests"][:10]))
        else:
            P("  (c) POI coverage: n/a (client ships no POI blobs for this zone)")
        d = r["d"]
        P("  (d) QuestLine chains: match=%d db-missing=%d db-different=%d" % (d["match"], d["db-missing"], d["db-different"]))
        for m in d["mismatches"][:10]:
            P("      %s" % m)
        if r.get("d_rg_wh"):
            w = r["d_rg_wh"]
            P("  (d) rg_wh.txt prev vs DB prereq: match=%d db-missing=%d db-different=%d" % (w["match"], w["db-missing"], w["db-different"]))
            for m in w["mismatches"]:
                P("      %s" % m)
        P("  (e) QuestV2 ids not in QuestieDB: %d total; attributed to this zone via POI blobs: %d" % (
            r["e"]["total_missing"], len(r["e"]["zone_attributed"])))
        P("  generic-drop-item items ignored: %d" % len(r["generic_drop_items"]))
        P("")
    P("Patch candidates (wh-tooltip) by zone and reason (entity counted in each zone it has a quest in)")
    for zn in results:
        c = Counter(inf["reason"] for inf in wh_info.values() if qsets[zn] & set(inf["quests"]))
        P("  %-20s %s" % (zn, dict(c) or "-"))
    tot = Counter(inf["reason"] for inf in wh_info.values())
    P("  total unique entities: %s  (rows: Npc %d, Object %d)" % (dict(tot), len(wh_rows["Npc"]), len(wh_rows["Object"])))
    P("")
    P("Top 5 most impactful wh fixes (impact = in-scope Alliance quests referencing the entity; tiebreak distance)")
    ranked = sorted(wh_info.items(), key=lambda kv: (-len(kv[1]["quests"]), -(kv[1]["dist"] or 0), kv[0]))[:5]
    for (kind, eid), inf in ranked:
        P("  %s %d %s: %s, impact %d quests" % (kind, eid, inf["name"], inf["reason"], len(inf["quests"])))
        P("      quests: " + "; ".join("%d %s" % (q, qnames.get(q, "?")) for q in inf["quests"][:6])
          + (" ..." if len(inf["quests"]) > 6 else ""))
        P("      old Questie: %s" % (_fmt_pts(inf["old"]) if inf["old"] else "(none in this uiMap)"))
        P("      tooltip:     %s   distance: %s" % (_fmt_pts(inf["new"]), "%.2f" % inf["dist"] if inf["dist"] is not None else "n/a"))
    P("")
    P("Frame diagnostics (upstream bug report material)")
    for zn, r in results.items():
        f = r["frame"]
        P("  %-20s stale-Era tooltip points dropped: %d (entities %d) | far entities: %d, median(dx,dy) tooltip-minus-Questie: (%s, %s); "
          "far->ok if Questie pts era_to_forever: %d, if forever_to_era: %d" % (
              zn, f["stale_era_points"], f["stale_era_entities"], f["far_entities"], f["median_dx"], f["median_dy"],
              f["far_ok_if_era_to_forever"], f["far_ok_if_forever_to_era"]))
    P("")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ driver
def _json_default(o):
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def run(db, wh, trace_patch, outdir=None, wh_result=None, offline=False):
    """Run the full audit, write work/audit/*; returns (summary text, wh_result)."""
    transforms = Z._TRANSFORMS
    zsets = Z.zone_sets()
    coll = collect(db, zsets)
    results, _missing = audit(db, wh, transforms, zsets, coll, offline=offline)
    if wh_result is None:
        wh_result = wh_patch(db, zsets, wh, trace_patch)
    rows, reasons, info = wh_result
    qnames = {q: i["name"] for qd in coll.values() for q, i in qd.items()}
    qsets = {zn: set(coll[zn]) for zn in coll}
    text = build_summary(results, qsets, info, rows, qnames)
    outdir = outdir or os.path.join(WORK, "audit")
    os.makedirs(outdir, exist_ok=True)
    for zn, r in results.items():
        payload = dict(r)
        payload["quest_list"] = {str(q): coll[zn][q] for q in sorted(coll[zn])}
        with open(os.path.join(outdir, zn.replace("'", "").replace(" ", "_") + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, default=_json_default)
    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return text, wh_result


def load_trace_patch():
    path = os.path.join(WORK, "trace_patch.json")
    out = {"Npc": {}, "Object": {}}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    for kind in out:
        for eid, row in (raw.get(kind) or {}).items():
            if "spawns" in row:
                out[kind][int(eid)] = {"spawns": {int(z): pts for z, pts in row["spawns"].items()}}
    return out


def init_env(qdb_dir=QDB_DIR):
    Z.load_area_uimap(qdb_dir)
    Z.load_transforms(qdb_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    init_env()
    db = InstalledDB(QDB_DIR)
    wh = wh_tooltip.WH(os.path.join(WORK, "wh"), offline=args.offline)
    text, _ = run(db, wh, load_trace_patch(), offline=args.offline)
    print(text)
    print("tooltip requests this run: %d" % wh.fetched)


if __name__ == "__main__":
    main()

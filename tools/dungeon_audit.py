"""Audit ForeverDungeonJournal dungeon quests (max level >= 48, Alliance/Both) against the installed QuestieDB.

CLI: python -I tools\\dungeon_audit.py   -> work/audit/dungeons.json + work/audit/dungeons.txt
API: audit(db, fdj, entity_check=None) ; patch_candidates(result)
"""
import csv
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import qdb_decode as qd  # noqa: E402
import fdj as fdjmod  # noqa: E402

ROOT = os.path.abspath(os.path.join(_HERE, ".."))
WOW = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns"
FDJ_DIR = os.path.join(WOW, "ForeverDungeonJournal")
QDB_DIR = os.path.join(WOW, "QuestieDB")
BLACKLIST_CSV = os.path.join(ROOT, "data", "blacklist_forever.csv")
UIMAP_LUA = os.path.join(QDB_DIR, "support", "Forever", "Zones", "areaIdToUiMapId.lua")
OUT_DIR = os.path.join(ROOT, "work", "audit")

MIN_MAX_LEVEL = 48
ALLIANCE_MASK = (1 << 32) | 77
FAR_DIST = 3.0
GENERIC_ITEM_SOURCES = 25
BLACKLIST_NOTE = "snapshot of Questie 12.12.0's effective Forever blacklist"
EXPECTED = ["Uldaman", "Zul'Farrak", "Alcaz Prison", "Maraudon", "Sunken Temple", "Blackmaw Hold",
            "Shaper's Terrace", "Scholomance", "Dire Maul: East", "Dire Maul: West", "Dire Maul: North",
            "Stratholme: Living", "Stratholme: Undead", "Blackrock Depths", "Lower Blackrock Spire",
            "Upper Blackrock Spire"]


def load_blacklist(path=BLACKLIST_CSV):
    out = {}
    with open(path, encoding='utf8', newline='') as f:
        for row in csv.DictReader(f):
            try:
                qid = int(row['id'])
            except (ValueError, KeyError, TypeError):
                continue
            v = (row.get('value') or '').strip()
            out[qid] = 'hidden' if v.lower() == 'true' else ('hide-on-map' if v == 'HIDE_ON_MAP' else 'none')
    return out


def load_uimap(path=UIMAP_LUA):
    with open(path, encoding='utf8') as f:
        src = f.read()
    res = {}
    for var in ("areaIdToUiMapId", "areaIdToUiMapIdOverride"):  # override applied last -> wins
        m = re.search(r'\.' + var + r'\s*=\s*\[\[(.*?)\]\]', src, re.S)
        if m:
            for a, u in re.findall(r'^\s*\[(\d+)\]\s*=\s*(\d+)', m.group(1), re.M):
                res[int(a)] = int(u)
    return res


class _Ctx:
    def __init__(self, db, fdj, entity_check, blacklist, uimap):
        self.db, self.fdj, self.check = db, fdj, entity_check
        self.bl = blacklist
        self.uimap = uimap
        self.by_uimap = {}
        for a, u in uimap.items():
            self.by_uimap.setdefault(u, set()).add(a)
        self._sp = {}
        self._chk = {}
        self._clo = {}

    def name(self, kind, eid):
        e = self.db.get(kind, eid)
        return e.get('name') if e else None

    def spawns(self, kind, eid):
        """-> {"real": {zone: [(x,y)]}, "sentinel": bool, "state": open-world|in-dungeon|none}"""
        k = (kind, eid)
        if k in self._sp:
            return self._sp[k]
        e = self.db.get(kind, eid) if kind in ("Npc", "Object") else None
        real, sent = {}, False
        if e:
            for z, pts in qd.spawn_points(e.get('spawns')).items():
                for p in pts:
                    if qd.is_sentinel(p):
                        sent = True
                    else:
                        real.setdefault(z, []).append((p[0], p[1]))
        state = "open-world" if real else ("in-dungeon" if sent else "none")
        r = {"real": real, "sentinel": sent, "state": state}
        self._sp[k] = r
        return r

    def zones_like(self, zone):
        s = {zone}
        u = self.uimap.get(zone)
        if u is not None:
            s |= self.by_uimap.get(u, set())
        return s

    def entity_check(self, kind, eid):
        if self.check is None:
            return None
        k = (kind, eid)
        if k not in self._chk:
            self._chk[k] = self.check(kind, eid)
        return self._chk[k]

    def closure(self, qid):
        """transitive prereq ids of a Questie quest (excluding itself)."""
        if qid in self._clo:
            return self._clo[qid]
        seen, stack = set(), [qid]
        while stack:
            q = self.db.get('Quest', stack.pop())
            if not q:
                continue
            for p in direct_prereqs(q):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        seen.discard(qid)
        self._clo[qid] = seen
        return seen


def direct_prereqs(q):
    out = set(qd.id_list(q.get('preQuestSingle')))
    out |= set(qd.id_list(q.get('preQuestGroup')))
    return {p for p in out if p > 0}


def _givers(q, field):
    g = qd.groups(q.get(field))
    out = []
    for kind, idx in (("Npc", 1), ("Object", 2)):
        for i in g.get(idx, []):
            if i > 0:
                out.append((kind, i))
    return out


def _item_givers(q, field):
    return [i for i in qd.groups(q.get(field)).get(3, []) if i > 0]


def _pos_check(cx, text, givers, items=()):
    parsed = fdjmod.parse_place(text)
    res = {"text": text or "", "parsed": {"npc": parsed["npc"], "zone": parsed["zone"],
                                          "coords": list(parsed["coords"]) if parsed["coords"] else None},
           "givers": [], "name_match": None, "status": None, "dist": None, "best_giver": None}
    low = (text or "").lower()
    npc_low = (parsed["npc"] or "").lower()
    matched = []
    for kind, i in givers:
        nm = cx.name(kind, i) or ""
        sp = cx.spawns(kind, i)
        mt = bool(nm) and (nm.lower() in low or (bool(npc_low) and npc_low in nm.lower()))
        if mt:
            matched.append((kind, i))
        ent = {"kind": kind, "id": i, "name": nm, "spawn_state": sp["state"], "name_match": mt,
               "zones": sorted(sp["real"])}
        chk = cx.entity_check(kind, i) if sp["state"] != "in-dungeon" else None
        if chk is not None:
            ent["check"] = chk
        res["givers"].append(ent)
    if givers and text:
        res["name_match"] = bool(matched)
    res["item_givers"] = list(items)
    cand = matched or list(givers)
    if not cand and items:
        res["status"] = "item-giver"
        return res
    if not cand:
        res["status"] = "giver-missing"
        return res
    if all(cx.spawns(k, i)["state"] == "in-dungeon" for k, i in cand):
        res["status"] = "in-dungeon"
        return res
    if parsed["coords"] is None:
        res["status"] = "no-fdj-coords"
        return res
    if parsed["zone"] is None:
        res["status"] = "zone-missing"
        res["detail"] = "FDJ zone not parsed"
        return res
    zs = cx.zones_like(parsed["zone"])
    best = None
    for k, i in cand:
        for z, pts in cx.spawns(k, i)["real"].items():
            if z in zs:
                for (x, y) in pts:
                    d = math.hypot(x - parsed["coords"][0], y - parsed["coords"][1])
                    if best is None or d < best[0]:
                        best = (d, k, i)
    if best is None:
        res["status"] = "zone-missing"
        res["detail"] = "no Questie spawn in FDJ zone %s" % parsed["zone"]
        return res
    res["dist"] = round(best[0], 2)
    res["best_giver"] = [best[1], best[2]]
    res["status"] = "ok" if best[0] <= FAR_DIST else "far"
    return res


def _prereqs(cx, qid, q):
    C = list(cx.fdj["chains"].get(qid, []))
    P = direct_prereqs(q)
    Pstar = set(P)
    for p in P:
        Pstar |= cx.closure(p)
    Cclo = set(C)
    for c in C:
        Cclo |= cx.closure(c)
    missing = [c for c in C if c not in Pstar]
    extra = sorted(p for p in P if p not in C and p not in Cclo)
    if not C and not P:
        status = "none"
    elif C and not P:
        status = "questie-missing"
    elif missing:
        status = "questie-partial"
    elif extra:
        status = "questie-extra"
    else:
        status = "match"
    nm = lambda i: cx.name('Quest', i)
    return {"status": status, "fdj": C, "questie_direct": sorted(P), "questie_closure_size": len(Pstar),
            "missing_in_questie": [[c, nm(c)] for c in missing],
            "extra_in_questie": [[p, nm(p)] for p in extra],
            "exclusiveTo": [[e, nm(e)] for e in sorted(set(qd.id_list(q.get('exclusiveTo'))))]}


def _objectives(cx, q, fdj_objective):
    g = qd.groups(q.get('objectives'))
    ents = []  # (kind, id)
    for idx, kind in ((1, "Npc"), (2, "Object"), (5, "Npc")):
        for i in g.get(idx, []):
            if i > 0:
                ents.append((kind, i))
    items = [i for i in g.get(3, []) if i > 0]
    no_spawn, item_no_src, generic = [], [], []
    for kind, i in dict.fromkeys(ents):
        if cx.spawns(kind, i)["state"] == "none":
            no_spawn.append({"kind": kind, "id": i, "name": cx.name(kind, i), "via": "objective"})
    for it in dict.fromkeys(items):
        e = cx.db.get('Item', it) or {}
        srcs = [("Npc", n) for n in qd.id_list(e.get('npcDrops')) if n > 0] + \
               [("Object", n) for n in qd.id_list(e.get('objectDrops')) if n > 0]
        if len(srcs) > GENERIC_ITEM_SOURCES:
            generic.append(it)
        elif not srcs:
            item_no_src.append([it, e.get('name')])
        elif all(cx.spawns(k, n)["state"] == "none" for k, n in srcs):
            no_spawn.append({"kind": "Item", "id": it, "name": e.get('name'), "via": "drops:%d sources" % len(srcs)})
    has_obj = bool(ents or items)
    return {"has_objectives": has_obj, "no_objectives": (not has_obj) and bool(fdj_objective),
            "objective_no_spawns": no_spawn, "item_no_sources": item_no_src, "generic_items": generic}


def audit(db, fdj, entity_check=None, *, blacklist=None, uimap=None):
    """Audit in-scope FDJ dungeon quests against QuestieDB `db`.

    entity_check(kind, id) -> {"status": ..., "dist": float|None, "whzone": int|None, "wh": [[x,y],...]} | None
    Returns a JSON-serialisable dict, see render_text()."""
    bl = load_blacklist() if blacklist is None else blacklist
    cx = _Ctx(db, fdj, entity_check, bl, load_uimap() if uimap is None else uimap)
    selected = sorted(n for n, d in fdj["dungeons"].items() if d["level"][1] >= MIN_MAX_LEVEL)
    result = {"scope": {"rule": "level max >= %d, faction Alliance|Both" % MIN_MAX_LEVEL, "selected": selected,
                        "expected_not_selected": [n for n in EXPECTED if n not in selected],
                        "selected_not_expected": [n for n in selected if n not in EXPECTED]},
              "blacklist_source": BLACKLIST_NOTE,
              "entity_check": "enabled" if entity_check else "skipped (no entity_check callback)",
              "dungeons": {}}
    chain_ids = set()
    for name in selected:
        d = fdj["dungeons"][name]
        quests = []
        for fq in d["quests"]:
            qid = fq.get("id")
            if not isinstance(qid, int) or fq.get("faction") not in ("Alliance", "Both"):
                continue
            q = db.get('Quest', qid)
            rec = {"id": qid, "fdj_name": fq.get("name"), "faction": fq.get("faction"),
                   "hideFromMainList": bool(fq.get("hideFromMainList")), "fdj_level": fq.get("level"),
                   "fdj_requires": fq.get("requires"), "in_questiedb": q is not None,
                   "blacklist": bl.get(qid, "none"), "tag": fdj["tags"].get(qid)}
            chain_ids.update(fdj["chains"].get(qid, []))
            if q is not None:
                rr = q.get('requiredRaces') or 0
                rec["questie_name"] = q.get('name')
                rec["requiredRaces"] = rr
                rec["alliance_ok"] = (rr == 0) or bool(rr & ALLIANCE_MASK)
                st, fn = _givers(q, 'startedBy'), _givers(q, 'finishedBy')
                si, fi = _item_givers(q, 'startedBy'), _item_givers(q, 'finishedBy')
                rec["giver_missing"] = {"start": not (st or si), "end": not (fn or fi)}
                rec["pickup"] = _pos_check(cx, fq.get("pickup"), st, si)
                rec["turnin"] = _pos_check(cx, fq.get("turnin"), fn, fi)
                rec["prereqs"] = _prereqs(cx, qid, q)
                ql, fl = q.get('requiredLevel'), fq.get('requires')
                rec["level_diff"] = {"fdj": fl, "questie": ql} if (
                    isinstance(fl, int) and isinstance(ql, int) and fl != ql) else None
                rec["objectives"] = _objectives(cx, q, fq.get("objective"))
            quests.append(rec)
        result["dungeons"][name] = {"level": list(d["level"]), "location": d["location"], "quests": quests}
    result["chain_members"] = {}
    for c in sorted(chain_ids):
        result["chain_members"][str(c)] = {"name": cx.name('Quest', c), "in_questiedb": db.get('Quest', c) is not None,
                                           "blacklist": bl.get(c, "none")}
    result["_patch"] = _patch_list(result)
    return result


def _patch_list(result):
    seen = set()
    for d in result["dungeons"].values():
        for r in d["quests"]:
            for role in ("pickup", "turnin"):
                for g in (r.get(role) or {}).get("givers", []):
                    if g["spawn_state"] in ("open-world", "none"):
                        seen.add((g["kind"], g["id"]))
    return [[k, i] for (k, i) in sorted(seen)]


def patch_candidates(result):
    """-> [(kind, id), ...] giver/turn-in NPC/Object entities of in-scope quests with >=1 real spawn point or no
    spawns at all (excludes instance-sentinel-only entities). Takes the dict returned by audit()."""
    return [(k, i) for k, i in result["_patch"]]


# ----------------------------------------------------------------------------- text report

def _issues(r):
    """-> list of (category, short text, concrete detail)"""
    out = []
    if not r["in_questiedb"]:
        out.append((0, "missing-from-questiedb", "not in QuestieDB"))
        return out
    if r["blacklist"] != "none":
        out.append((0, "blacklisted", "blacklist=%s" % r["blacklist"]))
    if not r["alliance_ok"]:
        out.append((1, "horde-restricted", "requiredRaces=%d" % r["requiredRaces"]))
    for role in ("pickup", "turnin"):
        p = r[role]
        gm = r["giver_missing"]["start" if role == "pickup" else "end"]
        if gm:
            out.append((2, "giver-missing", "%s: Questie has no %s" % (role, "starter" if role == "pickup" else "finisher")))
            continue
        if p["name_match"] is False:
            out.append((3, "name-mismatch", "%s: FDJ '%s' vs Questie %s" % (
                role, p["text"], "/".join("%s(%d)" % (g["name"], g["id"]) for g in p["givers"]))))
        if p["status"] == "far":
            out.append((2, "giver-far", "%s: FDJ '%s' vs Questie giver %d dist %.1f" % (
                role, p["text"], p["best_giver"][1], p["dist"])))
    pr = r["prereqs"]
    if pr["status"] in ("questie-missing", "questie-partial", "questie-extra"):
        out.append((4, pr["status"], "FDJ chain %s; Questie direct %s; missing %s; extra %s" % (
            pr["fdj"], pr["questie_direct"], [m[0] for m in pr["missing_in_questie"]],
            [e[0] for e in pr["extra_in_questie"]])))
    ob = r["objectives"]
    if ob["objective_no_spawns"]:
        out.append((5, "objective-no-spawns", ", ".join("%s %s(%d)" % (e["kind"], e["name"], e["id"])
                                                         for e in ob["objective_no_spawns"])))
    if ob["no_objectives"]:
        out.append((6, "no-objectives", "FDJ has objective text but Questie has none"))
    if r["level_diff"]:
        out.append((6, "level-diff", "requires FDJ %s vs Questie %s" % (r["level_diff"]["fdj"], r["level_diff"]["questie"])))
    return out


def render_text(result):
    L = []
    sc = result["scope"]
    L.append("== Dungeons 48+ ==")
    L.append("Rule: %s" % sc["rule"])
    L.append("Selected (%d): %s" % (len(sc["selected"]), ", ".join(sc["selected"])))
    L.append("Expected but not selected: %s" % (sc["expected_not_selected"] or "none"))
    L.append("Selected but not in expected list: %s" % (sc["selected_not_expected"] or "none"))
    L.append("Blacklist: %s" % result["blacklist_source"])
    L.append("Entity (tooltip) check: %s" % result["entity_check"])
    L.append("")
    tot = dict(q=0, missing=0, bl_hidden=0, bl_map=0, horde=0, g_missing=0, g_name=0, g_far=0,
               p_missing=0, p_partial=0, p_extra=0, obj=0, lvl=0, t_far=0, t_era=0, t_zm=0, t_nosp=0)
    allissues = []
    for name, d in result["dungeons"].items():
        c = dict.fromkeys(tot, 0)
        for r in d["quests"]:
            c["q"] += 1
            if not r["in_questiedb"]:
                c["missing"] += 1
            else:
                c["bl_hidden"] += r["blacklist"] == "hidden"
                c["bl_map"] += r["blacklist"] == "hide-on-map"
                c["horde"] += not r["alliance_ok"]
                for role, gk in (("pickup", "start"), ("turnin", "end")):
                    c["g_missing"] += r["giver_missing"][gk]
                    c["g_name"] += r[role]["name_match"] is False
                    c["g_far"] += r[role]["status"] == "far"
                    st = {(g.get("check") or {}).get("status") for g in r[role]["givers"]}
                    c["t_far"] += "far" in st
                    c["t_era"] += "wh-era-frame" in st
                    c["t_zm"] += "zone-mismatch" in st
                    c["t_nosp"] += "questie-no-spawns" in st
                ps = r["prereqs"]["status"]
                c["p_missing"] += ps == "questie-missing"
                c["p_partial"] += ps == "questie-partial"
                c["p_extra"] += ps == "questie-extra"
                c["obj"] += len(r["objectives"]["objective_no_spawns"])
                c["lvl"] += r["level_diff"] is not None
            for cat, kind, detail in _issues(r):
                allissues.append((cat, name, r, kind, detail))
        for k in tot:
            tot[k] += c[k]
        L.append("%s [%d-%d]: quests=%d missing=%d blacklisted=%d(hidden)/%d(map) horde-restricted=%d "
                 "giver(missing=%d name-mismatch=%d far=%d) prereq(missing=%d partial=%d extra=%d) "
                 "obj-no-spawns=%d level-diff=%d tooltip(far=%d wh-era-frame=%d zone-mismatch=%d no-spawns=%d)" % (
                     name, d["level"][0], d["level"][1], c["q"], c["missing"], c["bl_hidden"], c["bl_map"], c["horde"],
                     c["g_missing"], c["g_name"], c["g_far"], c["p_missing"], c["p_partial"], c["p_extra"],
                     c["obj"], c["lvl"], c["t_far"], c["t_era"], c["t_zm"], c["t_nosp"]))
    L.append("")
    L.append("Top 10 notable:")
    allissues.sort(key=lambda t: (t[0], t[1], t[2]["id"]))
    shown, seenq = 0, set()
    for cat, name, r, kind, detail in allissues:
        if cat > 4 or r["id"] in seenq:
            continue
        seenq.add(r["id"])
        L.append("  %d. [%s] %s: %d '%s' (%s) - %s" % (shown + 1, kind, name, r["id"], r["fdj_name"],
                                                      r.get("questie_name") or "-", detail))
        shown += 1
        if shown >= 10:
            break
    L.append("")
    L.append("Totals: quests=%(q)d missing-from-questiedb=%(missing)d blacklisted-hidden=%(bl_hidden)d "
             "blacklisted-hide-on-map=%(bl_map)d horde-restricted=%(horde)d giver-missing=%(g_missing)d "
             "giver-name-mismatch=%(g_name)d giver-far=%(g_far)d prereq-questie-missing=%(p_missing)d "
             "prereq-partial=%(p_partial)d prereq-extra=%(p_extra)d objective-no-spawns=%(obj)d "
             "level-diff=%(lvl)d tooltip-far=%(t_far)d tooltip-wh-era-frame=%(t_era)d "
             "tooltip-zone-mismatch=%(t_zm)d tooltip-no-spawns=%(t_nosp)d" % tot)
    L.append("Patch candidates (open-world / no-spawn givers): %d" % len(result["_patch"]))
    L.append("Chain members (prereq-only): %d" % len(result["chain_members"]))
    return "\n".join(L) + "\n"


def tooltip_checker(db, wh):
    """entity_check callback backed by zone_audit.check_entity (zone_audit.init_env must have run)."""
    import zone_audit
    return lambda kind, eid: zone_audit.check_entity(db, wh, zone_audit.Z._TRANSFORMS, kind, eid)


def write_outputs(result):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "dungeons.json"), "w", encoding="utf8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False, default=str)
    txt = render_text(result)
    with open(os.path.join(OUT_DIR, "dungeons.txt"), "w", encoding="utf8") as f:
        f.write(txt)
    return txt


def main():
    import zone_audit
    import wh_tooltip
    db = qd.InstalledDB(QDB_DIR)
    fdj = fdjmod.load_fdj(FDJ_DIR)
    zone_audit.init_env(QDB_DIR)
    wh = wh_tooltip.WH(os.path.join(ROOT, "work", "wh"), offline="--online" not in sys.argv)
    result = audit(db, fdj, tooltip_checker(db, wh))
    txt = write_outputs(result)
    sys.stdout.reconfigure(encoding="utf8", errors="replace")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())

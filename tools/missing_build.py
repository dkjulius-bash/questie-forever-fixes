"""Step 2 of the missing-quest hunt: Wowhead page records (work/missing/pages/<id>.json) ->
work/missing/quests.json, each quest mapped into QuestieDB's row shape plus entity rows.

NOTE: JSON object keys are strings, so questieRow.startedBy/finishedBy/objectives use "1"/"2"/"3";
the Lua emitter must turn them into integer keys.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from qdb_decode import InstalledDB, spawn_points  # noqa: E402
from wh_tooltip import WH, points  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
ALLIANCE, HORDE = 4294967373, 8589934770
A_BITS, H_BITS = 1 | 4 | 8 | 64, 2 | 16 | 32 | 128
KIND = {"npc": "Npc", "object": "Object", "item": "Item"}


def ref_ids(refs, kind):
    out = []
    for r in refs or []:
        m = re.fullmatch(r"%s=(\d+)" % kind, str(r))
        if m and int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def faction_of(side, race=0):
    f = "Alliance" if side == 1 else "Horde" if side == 2 else "Both"
    r = (race or 0) & 255
    if r and r & ~A_BITS == 0:
        return "Alliance"
    if r and r & ~H_BITS == 0:
        return "Horde"
    return f


def db_faction(mask):
    """Classify a QuestieDB requiredRaces mask (None/absent = neutral)."""
    return faction_of(0, mask if isinstance(mask, int) else 0)


def required_races(race, faction):
    r = (race or 0) & 255
    if not r:
        return ALLIANCE if faction == "Alliance" else HORDE if faction == "Horde" else None
    if r == 77:
        return ALLIANCE
    if r == 178:
        return HORDE
    return None if r == 255 else r


def load_blacklist():
    path = os.path.join(ROOT, "data", "blacklist_forever.csv")
    with open(path, encoding="utf-8", newline="") as f:
        return {int(r["id"]): (r.get("comment") or "blacklisted") for r in csv.DictReader(f)
                if r["value"] == "true"}


def parse_objectives(p):
    obj = {"creature": [], "object": [], "item": []}
    source, unlinked = None, []
    for row in p.get("ol") or []:
        qty, text, refs = (list(row) + [None, None, None])[:3]
        refs = refs or []
        if not refs:  # Wowhead shows unknown items as "Item #226720" without a link
            refs = ["item=%s" % m for m in re.findall(r"Item #(\d+)", text or "")]
        if "(Provided)" in (text or ""):
            ids = ref_ids(refs, "item")
            source = source or (ids[0] if ids else None)
            continue
        if not refs:
            unlinked.append(text)
            continue
        m = re.match(r"\d+", str(qty or ""))
        cnt = int(m.group()) if m else 1
        for kind, key in (("npc", "creature"), ("object", "object"), ("item", "item")):
            for i in ref_ids(refs, kind):
                if all(i != o[0] for o in obj[key]):
                    obj[key].append([i, cnt])
    return obj, source, unlinked


def parse_series(ser):
    """-> (pre, next); only meaningful when "self" is in the series."""
    ser = [str(s) for s in ser or []]
    if "self" not in ser:
        return None, None
    k = ser.index("self")
    m = re.fullmatch(r"quest=(\d+)", ser[k - 1]) if k > 0 else None
    pre = int(m.group(1)) if m else None
    m = re.fullmatch(r"quest=(\d+)", ser[k + 1]) if k + 1 < len(ser) else None
    return pre, (int(m.group(1)) if m else None)


def build_quest(p, db, names, blacklist):
    q = {"id": p["id"], "name": p.get("name")}
    side = p.get("side") or p.get("gside") or 0
    fac = faction_of(side, p.get("race"))
    q.update(level=p.get("lvl"), requiredLevel=p.get("req"), wowheadSide=side, faction=fac,
             reqraceWowhead=p.get("race") or 0, requiredRaces=required_races(p.get("race"), fac),
             requiredClasses=p.get("cls") or None)
    q["starters"] = {k: ref_ids(p.get("start"), k) for k in ("npc", "object", "item")}
    q["enders"] = {k: ref_ids(p.get("end"), k) for k in ("npc", "object")}
    obj, source, unlinked = parse_objectives(p)
    q.update(objectives=obj, sourceItemId=source, unlinkedObjectives=unlinked)
    pre, nxt = parse_series(p.get("ser"))
    q.update(preQuestSingle=pre, nextQuestInChain=nxt, zoneOrSort=p.get("cat"), category2=p.get("cat2"))
    q["isDungeon"] = p.get("cat2") == 2 or p.get("type") == 81
    q["isRaid"] = p.get("cat2") == 3 or p.get("type") == 62
    env = p.get("env") or []
    q.update(patch=p.get("patch"), envChanges=env,
             forever=str(p.get("patch") or "").startswith("1.60") or bool(env))
    q["blacklisted"] = blacklist.get(p["id"])
    same = set(names.get((p.get("name") or "").strip().lower(), []))
    for lv in p.get("lv") or []:
        if lv[1] == "see-also":
            same |= {i for i in lv[2] if i in db.ids("Quest")}
    same = sorted(same)
    sides = {str(i): db_faction((db.get("Quest", i) or {}).get("requiredRaces")) for i in same}
    q["sameNameInQuestieDB"], q["sameNameSides"] = same, sides
    nogiver = not any(q["starters"].values()) and not any(q["enders"].values()) and source is None
    if p.get("nf"):
        cls = "not-found"
    elif any(is_dup(q, nogiver, int(i), f, fac, db) for i, f in sides.items()):
        cls = "duplicate"  # checked before blacklisted: 908/909/5383 are blacklisted AND duplicates
    elif q["blacklisted"]:
        cls = "blacklisted"
    elif nogiver:
        cls = "no-giver-data"
    else:
        # same name but different objectives (e.g. per-class T0.5 quest variants) -> distinct quest
        cls = "variant" if same else "real"
    q["classification"] = cls
    q["gaps"] = gaps(q, p, db)
    q["questieRow"] = questie_row(q, p)
    q["includeCandidate"] = cls in ("real", "variant")
    return q


def _db_objective_ids(row):
    ids = set()
    for g, rows in groups_raw((row or {}).get("objectives")).items():
        if g in (1, 2, 3):
            for r in rows or []:
                if isinstance(r, (list, tuple)) and r and isinstance(r[0], int):
                    ids.add((g, r[0]))
    return ids


def groups_raw(v):
    if isinstance(v, list):
        return {i + 1: y for i, y in enumerate(v) if y is not None}
    if isinstance(v, dict):
        return {int(k): y for k, y in v.items() if str(k).isdigit() and y is not None}
    return {}


def is_dup(q, nogiver, other_id, other_fac, fac, db):
    """Same-name QuestieDB quest counts as the same quest when factions are compatible and either this
    record is a giverless legacy copy, or both carry the same objective entities (and source item)."""
    if not (other_fac == fac or "Both" in (other_fac, fac)):
        return False
    if nogiver:
        return True
    row = db.get("Quest", other_id) or {}
    mine = {(g, i) for g, key in ((1, "creature"), (2, "object"), (3, "item")) for i, _ in q["objectives"][key]}
    if mine != _db_objective_ids(row) or q["sourceItemId"] != row.get("sourceItemId"):
        return False
    # Forever re-issued some quests under new ids with new givers (e.g. T0.5 quests: Deliana 16013 ->
    # 230319); same objectives but a different giver set is a distinct quest.
    st = {(g, i) for g, k in ((1, "npc"), (2, "object"), (3, "item")) for i in q["starters"][k]}
    if st:
        dbst = {(g, i) for g, ids in groups_raw(row.get("startedBy")).items() for i in (ids or [])
                if isinstance(i, int)}
        if st != dbst:
            return False
    return True


def gaps(q, p, db):
    g = []
    st, en, ob = q["starters"], q["enders"], q["objectives"]
    if not any(st.values()):
        g.append("no-starter")
    if st["item"]:
        g.append("item-started")
    if not any(en.values()):
        g.append("no-ender")
    for tag, group in (("starter", st), ("ender", en)):
        for kind, ids in group.items():
            g += ["%s-not-in-questiedb:%s=%d" % (tag, kind, i) for i in ids if i not in db.ids(KIND[kind])]
    for kind, key in (("npc", "creature"), ("object", "object"), ("item", "item")):
        g += ["objective-not-in-questiedb:%s=%d" % (kind, i) for i, _ in ob[key] if i not in db.ids(KIND[kind])]
    if q["unlinkedObjectives"]:
        g.append("unlinked-objective")
    if p.get("ser") and "self" not in p["ser"]:
        g.append("series-without-self")
    return g


def questie_row(q, p):
    st, en, ob = q["starters"], q["enders"], q["objectives"]
    row = {"name": q["name"], "questLevel": q["level"], "requiredLevel": q["requiredLevel"]}
    row["startedBy"] = {k: st[n] for k, n in (("1", "npc"), ("2", "object"), ("3", "item")) if st[n]}
    row["finishedBy"] = {k: en[n] for k, n in (("1", "npc"), ("2", "object")) if en[n]}
    row["requiredRaces"], row["requiredClasses"] = q["requiredRaces"], q["requiredClasses"]
    if p.get("obj"):
        row["objectivesText"] = [p["obj"]]
    # QuestieDB stores no counts: rows are [id], the DB pads the rest
    row["objectives"] = {k: [[i] for i, _ in ob[n]] for k, n in (("1", "creature"), ("2", "object"), ("3", "item"))
                         if ob[n]}
    row["sourceItemId"] = q["sourceItemId"]
    if q["preQuestSingle"]:
        row["preQuestSingle"] = [q["preQuestSingle"]]
    row["nextQuestInChain"] = q["nextQuestInChain"]
    row["zoneOrSort"] = q["zoneOrSort"]
    row["reputationReward"] = p.get("rep")
    repeatable = any("Repeatable" in (x if isinstance(x, str) else str(x[0])) for x in p.get("ib") or [])
    if p.get("daily") or p.get("wk") or repeatable:
        row["specialFlags"] = 1
    return {k: v for k, v in row.items() if v not in (None, [], {}, "")}


def build_entities(real, db, wh):
    ents = {"Npc": {}, "Object": {}, "Item": {}}

    def add(kind, i, q, role):
        e = ents[kind].setdefault(i, {"role": set(), "quests": set(), "starts": set(), "ends": set()})
        e["role"].add(role)
        e["quests"].add(q["id"])
        if role == "starter":
            e["starts"].add(q["id"])
        if role == "ender":
            e["ends"].add(q["id"])

    for q in real:
        for k, ids in q["starters"].items():
            for i in ids:
                add(KIND[k], i, q, "starter")
        for k, ids in q["enders"].items():
            for i in ids:
                add(KIND[k], i, q, "ender")
        for key, kind in (("creature", "Npc"), ("object", "Object"), ("item", "Item")):
            for i, _ in q["objectives"][key]:
                add(kind, i, q, "objective")
    out = {"Npc": {}, "Object": {}, "Item": {}}
    for kind, d in ents.items():
        for i in sorted(d):
            e = d[i]
            res = {"inQuestieDB": i in db.ids(kind), "role": sorted(e["role"]), "quests": sorted(e["quests"])}
            if kind == "Item":
                if not res["inQuestieDB"]:
                    res["name"] = (wh.get("item", i) or {}).get("name")
            elif res["inQuestieDB"]:
                sp = spawn_points((db.get(kind, i) or {}).get("spawns"))
                zs = sorted(z for z, pts in sp.items() if any(tuple(p[:2]) != (-1, -1) for p in pts))
                res.update(dbSpawnZones=zs, dbHasSpawns=bool(zs))
            else:
                t = wh.get(kind.lower(), i) or {}
                zone, pts, _ = points(t)
                row = {"name": t.get("name"), "spawns": {str(zone): [list(p) for p in pts]} if pts else {},
                       "zoneID": zone, "questStarts": sorted(e["starts"]), "questEnds": sorted(e["ends"])}
                res["questieRow"] = {k: v for k, v in row.items() if v not in (None, {}, [])}
                if "error" in t:
                    res["tooltipError"] = t["error"]
                if not pts:
                    res["noCoords"] = True
            out[kind][str(i)] = res
    return out


def summarize(n_pages, quests, ents):
    real = [q for q in quests if q["includeCandidate"]]
    gap_counts = Counter(g.split(":")[0] for q in real for g in q["gaps"])
    miss = {k: {i: e for i, e in v.items() if not e["inQuestieDB"]} for k, v in ents.items()}
    return {"pages": n_pages, "classification": dict(Counter(q["classification"] for q in quests)),
            "real": {"faction": dict(Counter(q["faction"] for q in real)),
                     "zoneOrSort": dict(Counter(q["zoneOrSort"] for q in real).most_common(30)),
                     "gaps": dict(gap_counts), "isDungeon": sum(q["isDungeon"] for q in real),
                     "isRaid": sum(q["isRaid"] for q in real), "forever": sum(q["forever"] for q in real)},
            "entities": {"missingNpc": len(miss["Npc"]), "missingObject": len(miss["Object"]),
                         "missingItem": len(miss["Item"]),
                         "missingNpcObjectWithCoords": sum(1 for k in ("Npc", "Object")
                                                           for e in miss[k].values() if not e.get("noCoords"))}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--pages", default=os.path.join(ROOT, "work", "missing", "pages"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "missing", "quests.json"))
    a = ap.parse_args()
    db = InstalledDB(QDB)
    names = {}
    for i in db.ids("Quest"):
        n = ((db.get("Quest", i) or {}).get("name") or "").strip().lower()
        names.setdefault(n, []).append(i)
    blacklist = load_blacklist()
    pages = []
    for f in glob.glob(os.path.join(a.pages, "*.json")):
        with open(f, encoding="utf-8") as fh:
            pages.append(json.load(fh))
    quests = sorted((build_quest(p, db, names, blacklist) for p in pages), key=lambda q: q["id"])
    wh = WH(os.path.join(ROOT, "work", "missing", "tooltip"), offline=a.offline)
    ents = build_entities([q for q in quests if q["includeCandidate"]], db, wh)
    summary = summarize(len(pages), quests, ents)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "quests": quests, "entities": ents}, f, indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

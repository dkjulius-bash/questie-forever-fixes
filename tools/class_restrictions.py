"""requiredClasses for WoW Forever's re-issued Tier 0.5 quest chains that QuestieDB leaves class-less
-> data/class_restrictions.json.  CLI: python -I tools/class_restrictions.py [--offline]
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zone_audit as ZA  # noqa: E402
from patch_policy import _db_obj_groups, _rows_list  # noqa: E402
from qdb_decode import InstalledDB  # noqa: E402
from zone_audit_all import quest_faction  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
CHAINS = {"An Earnest Proposition", "Just Compensation", "Anthion's Parting Words", "Saving the Best for Last"}
KEYWORDS = {"Magister": "Mage", "Devout": "Priest", "Dreadmist": "Warlock", "Shadowcraft": "Rogue",
            "Beaststalker": "Hunter", "Elements": "Shaman", "Lightforge": "Paladin", "Valor": "Warrior",
            "Wildheart": "Druid"}
MASKS = {"Warrior": 1, "Paladin": 2, "Hunter": 4, "Rogue": 8, "Priest": 16, "Shaman": 64, "Mage": 128,
         "Warlock": 256, "Druid": 1024}
COMMENT = ("requiredClasses for WoW Forever's re-issued Tier 0.5 quests that QuestieDB leaves class-less. "
           "Built by tools/class_restrictions.py; refresh.py applies an entry only where QuestieDB has no requiredClasses.")
OUT = os.path.join(ROOT, "data", "class_restrictions.json")


def keyword_classes(text):
    t = (text or "").lower()
    return {c: k for k, c in KEYWORDS.items() if k.lower() in t}


def item_ids(row):
    g = _db_obj_groups((row or {}).get("objectives"))
    rows = g.get(3, g.get("3"))
    out = []
    for r in _rows_list(rows):
        if isinstance(r, (list, tuple)) and r and isinstance(r[0], int):
            out.append(r[0])
        elif isinstance(r, int):
            out.append(r)
    return out


def load_sets(offline):
    rows = ZA.ensure_csv("ItemSet", offline)
    sets = []
    for r in rows:
        ids = {int(r["ItemID_%d" % i]) for i in range(17) if int(r.get("ItemID_%d" % i) or 0)}
        sets.append((int(r["ID"]), r["Name_lang"], ids))
    return sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    db = InstalledDB(QDB)
    sets = load_sets(a.offline)
    added = {}
    p = os.path.join(ROOT, "data", "added_quests.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            added = json.load(f).get("quests", {})

    pool = {}  # id -> dict(name,row,faction,inDB)
    for i in db.ids("Quest"):
        r = db.get("Quest", i)
        if r and (r.get("name") or "").strip() in CHAINS:
            pool[i] = {"name": r["name"].strip(), "row": r, "faction": quest_faction(r), "inDB": True}
    for k, e in added.items():
        row = dict(e["row"])
        for f, v in (e.get("overrides") or {}).items():
            if v is None:
                row.pop(f, None)
            else:
                row[f] = v
        if (row.get("name") or e["name"]).strip() in CHAINS:
            pool[int(k)] = {"name": (row.get("name") or e["name"]).strip(), "row": row, "faction": e["faction"],
                            "inDB": False}
    # corroboration index: class-bearing QuestieDB quests by (name, objective items)
    by_key = {}
    for i, q in pool.items():
        if q["inDB"] and q["row"].get("requiredClasses"):
            by_key.setdefault((q["name"], frozenset(item_ids(q["row"]))), []).append(i)

    quests, skipped = {}, {}
    for qid in sorted(pool):
        q = pool[qid]
        if qid < 80000:
            continue
        rc = q["row"].get("requiredClasses")
        if rc:
            skipped[str(qid)] = {"name": q["name"], "reason": "questiedb-has-class" if q["inDB"] else "row-has-class",
                                 "requiredClasses": rc}
            continue
        items = item_ids(q["row"])
        cls, method, ev = {}, None, None
        hits = [(sid, sn, sorted(ids & set(items))) for sid, sn, ids in sets if ids & set(items)]
        for sid, sn, m in hits:
            for c in keyword_classes(sn):
                cls.setdefault(c, []).append((sid, sn, m))
        if len(cls) == 1:
            method = "itemset"
            ev = "; ".join("ItemSet %d '%s': items %s" % (sid, sn, ", ".join(map(str, m)))
                           for v in cls.values() for sid, sn, m in v)
        elif len(cls) > 1:
            skipped[str(qid)] = {"name": q["name"], "reason": "ambiguous: " + ", ".join(sorted(cls))}
            continue
        else:
            text = " ".join(q["row"].get("objectivesText") or [])
            kc = keyword_classes(text)
            if len(kc) == 1:
                (cls_name, kw), = kc.items()
                cls = {cls_name: []}
                method, ev = "objectives-text", "objectivesText: '%s'" % kw
            else:
                skipped[str(qid)] = {"name": q["name"],
                                     "reason": "no-class-evidence" if not kc else "ambiguous: " + ", ".join(sorted(kc))}
                continue
        cname = next(iter(cls))
        mask = MASKS[cname]
        corr = sorted(i for i in by_key.get((q["name"], frozenset(items)), []) if i != qid)
        bad = [i for i in corr if pool[i]["row"]["requiredClasses"] != mask]
        if bad:
            skipped[str(qid)] = {"name": q["name"], "reason": "conflict with QuestieDB quest %d (requiredClasses %d)"
                                 % (bad[0], pool[bad[0]]["row"]["requiredClasses"])}
            continue
        quests[str(qid)] = {"name": q["name"], "faction": q["faction"], "class": cname, "requiredClasses": mask,
                            "method": method, "evidence": ev, "corroboratedBy": corr, "inQuestieDB": q["inDB"]}

    out = {"_comment": COMMENT,
           "source": {"itemSet": "wago.tools DB2 ItemSet, product wowf (work/db2/ItemSet.csv)",
                      "allowableClass": "not available: the wowf ItemSparse table lacks these items and Dungeon Set "
                                        "items carry no class restriction",
                      "classKeywords": KEYWORDS, "classMasks": MASKS, "chains": sorted(CHAINS),
                      "generated": datetime.date.today().isoformat()},
           "quests": quests, "skipped": skipped}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    print("%-7s %-30s %-9s %-8s %s" % ("id", "name", "faction", "class", "method"))
    for k, v in quests.items():
        print("%-7s %-30s %-9s %-8s %s%s" % (k, v["name"], v["faction"], v["class"], v["method"],
                                             "" if v["corroboratedBy"] else "  (uncorroborated)"))
    print("derived %d, skipped %d" % (len(quests), len(skipped)))
    for k, v in skipped.items():
        print("  skipped %s %s: %s" % (k, v["name"], v["reason"]))


if __name__ == "__main__":
    main()

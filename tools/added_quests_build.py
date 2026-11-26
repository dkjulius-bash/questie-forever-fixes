"""work/missing/quests.json -> data/added_quests.json (quests QuestieDB lacks, curated from Wowhead Forever pages).

Rebuild keeps any existing 'overrides' blocks. Offline; reads only cached inputs.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qdb_decode import InstalledDB  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
COLLECTED = "2026-11-26"
OUT = os.path.join(ROOT, "data", "added_quests.json")

INCLUDE_NO_GIVER = {97414, 97449, 97450, 95818, 99366, 99367}
NO_ITEM_START = {95821}  # no starter on Wowhead; never treat an item as its starter
FACTION_FIX = {95818: "Alliance"}  # page carries no side; Ironforge turn-in, Alliance counterpart of Horde 95821
NO_GIVER_NOTE = ("No giver on Wowhead; shipped without startedBy/finishedBy (never guess giver ids) so Questie can "
                 "track the objectives once the quest is in the log. Suggested givers: work/audit-all/review_quests.md")
REVIEW_OUT = os.path.join(ROOT, "work", "audit-all", "review_quests.md")
SUGGESTED_GIVERS = {  # qid -> (starter npc id|name|None, ender npc id|name|None, evidence)
    97414: (230317, 230317, "Horde siblings 84203/84208/84210 use Mokvar"),
    97449: (16016, 230319, "like 84185 (Anthion Harmon -> Deliana)"),
    97450: (230319, 230319, "Alliance siblings 84195/84196/84200 use Deliana"),
    95821: (3365, None, "Karolek is the ender of the preceding quest 95820, which leads into this one"),
    96265: (None, "Thera Duskwhisper", "named in objectivesText; not in QuestieDB"),
    98830: (None, "Shen'dralar Ancient", "named in objectivesText; not in QuestieDB"),
    95818: (None, None, "Alliance counterpart of Horde 95821 (pre-quest 95817, Rotgath Stonebeard, Ironforge); giver unknown"),
    99366: (None, None, "objectives differ from QuestieDB siblings 99210-99215; givers unknown"),
    99367: (None, None, "objectives differ from QuestieDB siblings 99210-99215; givers unknown"),
}
EXCLUDE = {
    93689: "uncertain: giverless; QuestieDB 92459 with the same name is Alliance with a different zone; may be the Horde counterpart",
    98447: "uncertain: giverless; objective npc 272450 differs from QuestieDB 96139",
    93451: "duplicate of QuestieDB 93450",
    96915: "duplicate of QuestieDB 96912, 96913, 96914",
    92454: "No usable starter or ender: starter item 251900 (Thendal Grove Gift Voucher; client ItemSparse "
                  "StartQuestID=92454) has no drop/vendor source in QuestieDB, and the ender Dalia Windbreeze is not "
                  "in QuestieDB and not linked on the Wowhead page.",
}
MANUAL_ITEM_NAMES = {
    221346: ("Scapula of the Fallen Avatar", "objectivesText of quest 82081; Wowhead page env: 'Objectives: no longer Scapula of the Fallen Avatar'"),
    228690: ("The Light and How to Swing It", "Wowhead page env of quest 84551 ('Objectives: no longer The Light and How to Swing It'); classic item 18359 has this name"),
    226720: ("Beaststalker's Cap", "objectivesText of quest 84204"),
    226723: ("Beaststalker's Tunic", "objectivesText of quest 84204"),
    284660: ("Tortheldrin's Broken Glaive", "objectivesText of quest 98830 (the page's objective line only reads 'Item #284660 (Provided)')"),
}
COMMENT = ("Quests missing from QuestieDB, curated from Wowhead Forever quest pages. Built by tools/added_quests_build.py "
           "from work/missing/quests.json; refresh.py ships them as new rows and retires any id QuestieDB has since added. "
           "Edit only 'overrides' (field -> value, null deletes the field); a rebuild keeps them.")


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def sparse_names():
    path = os.path.join(ROOT, "work", "db2", "ItemSparse.csv")
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("Display_lang"):
                    out[int(r["ID"])] = r["Display_lang"]
    return out


def tooltip_name(i):
    for d in ("missing/tooltip", "wh"):
        p = os.path.join(ROOT, "work", *d.split("/"), "item_%d.json" % i)
        if os.path.exists(p):
            t = load(p, {})
            if "error" not in t and t.get("name"):
                return t["name"], "Wowhead tooltip cache (%s)" % d
    return None, None


def npc_label(db, v):
    if v is None:
        return "unknown"
    if isinstance(v, str):
        return "%s (not in QuestieDB)" % v
    return "%s (%d)" % ((db.get("Npc", v) or {}).get("name") or "?", v)


def write_review(db, quests):
    lines = ["# Quest givers to confirm", "",
             "If confirmed in game, these get added as startedBy/finishedBy in data/added_quests.json overrides.", "",
             "## Suggested givers to confirm in game", ""]
    for qid in sorted(SUGGESTED_GIVERS):
        q = quests.get(str(qid))
        if not q:
            continue
        st, en, ev = SUGGESTED_GIVERS[qid]
        lines.append("- **%s** (%d, %s) — starter: %s; ender: %s. Evidence: %s." % (
            q["name"], qid, q["faction"], npc_label(db, st), npc_label(db, en), ev))
    with open(REVIEW_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    db = InstalledDB(QDB)
    src = load(os.path.join(ROOT, "work", "missing", "quests.json"), None)
    old = load(OUT, {})
    old_q, old_i = old.get("quests", {}), old.get("items", {})
    sparse = sparse_names()
    quests, items, excluded = {}, {}, {}

    def add_item(i, qid, role, row, extra_q=None):
        e = items.setdefault(str(i), {"quests": [], "role": role, "provenance": {"source": "wh-page"}, "row": {}})
        if qid not in e["quests"]:
            e["quests"].append(qid)
        e["row"].update(row)
        if role == "starter":
            e["role"] = "starter"

    skipped_other = 0
    for q in sorted(src["quests"], key=lambda x: x["id"]):
        qid = q["id"]
        if qid in EXCLUDE:
            excluded[str(qid)] = {"name": q["name"], "reason": EXCLUDE[qid]}
            continue
        if not (q["includeCandidate"] or qid in INCLUDE_NO_GIVER):
            skipped_other += 1
            continue
        row = json.loads(json.dumps(q["questieRow"]))
        notes = []
        if qid in INCLUDE_NO_GIVER:
            row.pop("startedBy", None)
            row.pop("finishedBy", None)
            notes.append(NO_GIVER_NOTE)
        txt = row.get("objectivesText")
        if txt and any("{" in t for t in txt):
            row["objectivesText"] = [t.split("{", 1)[0].strip() if "{" in t else t for t in txt]
            notes.append("objectivesText trimmed at stray Wowhead template JSON")
        if not row.get("startedBy") and q.get("sourceItemId") and qid not in NO_ITEM_START                 and qid not in INCLUDE_NO_GIVER:
            it = q["sourceItemId"]
            row["startedBy"] = {"3": [it]}
            notes.append("Wowhead lists item %d as (Provided) and no starter; treated as item-started "
                         "(same shape as QuestieDB quest 7501)" % it)
            add_item(it, qid, "starter", {"startQuest": qid})
        for r in (row.get("objectives") or {}).get("3", []):
            if db.get("Item", r[0]) is None:
                add_item(r[0], qid, "objective", {})
        fac = FACTION_FIX.get(qid, q["faction"])
        if fac != q["faction"]:
            notes.append("faction set to %s by hand: the Wowhead page carries no side; pre-quest 95817 (Rotgath Stonebeard, Ironforge) is Alliance-only in QuestieDB, so overrides.requiredRaces is set to the Alliance mask" % fac)
        quests[str(qid)] = {
            "name": q["name"], "faction": fac,
            "provenance": {"source": "wh-page", "url": "https://www.wowhead.com/forever/quest=%d" % qid,
                           "collected": COLLECTED, "patch": q["patch"], "classification": q["classification"],
                           "gaps": q["gaps"], "notes": notes},
            "row": row,
            "overrides": (old_q.get(str(qid)) or {}).get("overrides", {}),
        }

    for k in sorted(items, key=int):
        i, e = int(k), items[k]
        e["quests"].sort()
        ov = dict((old_i.get(k) or {}).get("overrides", {}))
        name = (db.get("Item", i) or {}).get("name"), "QuestieDB"
        if not name[0] and i in sparse:
            name = sparse[i], "work/db2/ItemSparse.csv"
        if not name[0]:
            name = tooltip_name(i)
        if name[0] and name[1] == "QuestieDB":
            e["provenance"]["nameSource"] = "QuestieDB (entry only adds startQuest)"
        elif name[0]:
            e["row"]["name"] = name[0]
            e["provenance"]["nameSource"] = name[1]
        elif i in MANUAL_ITEM_NAMES:
            n, note = MANUAL_ITEM_NAMES[i]
            e["provenance"]["nameSource"] = note
            ov.setdefault("name", n)
        else:
            print("WARNING: no name for item %d" % i)
        e["overrides"] = ov
    out = {"_comment": COMMENT, "quests": quests, "items": {k: items[k] for k in sorted(items, key=int)},
           "excluded": excluded}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    fac = {}
    for v in quests.values():
        fac[v["faction"]] = fac.get(v["faction"], 0) + 1
    print("quests %d %s; excluded %d; not selected %d; items %d" % (len(quests), fac, len(excluded), skipped_other,
                                                                   len(items)))
    write_review(db, quests)


if __name__ == "__main__":
    main()

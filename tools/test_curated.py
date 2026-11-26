"""Headless tests for the curated layers (added quests, class restrictions, gap-fill helpers)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curated  # noqa: E402
import zone_audit  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" -- {detail}" if detail and not cond else ""))


FTYPES = {
    "Quest": {"name": "string", "startedBy": "table", "finishedBy": "table", "objectives": "table",
              "objectivesText": "table", "preQuestSingle": "table", "reputationReward": "table",
              "questLevel": "number", "requiredLevel": "number", "requiredRaces": "number",
              "requiredClasses": "number", "sourceItemId": "number", "zoneOrSort": "number",
              "nextQuestInChain": "number", "specialFlags": "number"},
    "Npc": {"name": "string", "questStarts": "table", "questEnds": "table", "spawns": "table", "zoneID": "number"},
    "Object": {"name": "string", "questStarts": "table", "questEnds": "table", "spawns": "table", "zoneID": "number"},
    "Item": {"name": "string", "startQuest": "number", "npcDrops": "table", "objectDrops": "table"},
}


class FakeDB:
    ftypes = FTYPES

    def __init__(self, **rows):
        self.rows = {k: dict(rows.get(k, {})) for k in FTYPES}

    def get(self, kind, eid):
        return self.rows[kind].get(eid)

    def ids(self, kind):
        return set(self.rows[kind])


def fresh():
    patch = {k: {} for k in FTYPES}
    sources = {k: {} for k in FTYPES}
    return patch, sources, []


def quest_entry(**row_over):
    row = {"name": "Q", "questLevel": 60, "requiredLevel": 58, "startedBy": {"1": [100]}, "finishedBy": {"1": [100]},
           "objectives": {"3": [[16686], [16688]]}, "zoneOrSort": 1537}
    row.update(row_over)
    return {"name": row["name"], "faction": "Alliance", "row": row, "overrides": {}}


# 1
db = FakeDB(Npc={100: {"name": "Giver"}})
patch, sources, reasons = fresh()
log = curated.apply_added_quests(patch, sources, reasons, db, {"quests": {"500": quest_entry()}})
q = patch["Quest"].get(500, {})
check("1 new quest: int group keys, reason new-quest, source wh-page",
      q.get("startedBy") == {1: [100]} and q.get("objectives") == {3: [[16686], [16688]]}
      and ("Quest", 500, "name", "new-quest") in reasons and sources["Quest"][500] == "wh-page"
      and any(l.startswith("added 500 Alliance Q") for l in log), str((q, log)))

# 2
db = FakeDB(Quest={500: {"name": "Q"}}, Npc={100: {"name": "Giver"}}, Item={7: {"name": "I"}})
patch, sources, reasons = fresh()
data = {"quests": {"500": quest_entry()},
        "items": {"7": {"quests": [500], "role": "starter", "row": {"startQuest": 500}, "overrides": {}}}}
log = curated.apply_added_quests(patch, sources, reasons, db, data)
check("2 quest in DB retired, nothing emitted",
      all(not patch[k] for k in patch) and any(l.startswith("retired 500") for l in log), str((patch, log)))

# 3
db = FakeDB(Npc={100: {"name": "Giver", "questStarts": [1]}, 101: {"name": "G2", "questStarts": [500], "questEnds": []}})
patch, sources, reasons = fresh()
patch["Npc"][100] = {"questStarts_add": [9]}
sources["Npc"][100] = "trace"
entry = quest_entry(startedBy={"1": [100, 101]}, finishedBy={"1": [101, 999]})
log = curated.apply_added_quests(patch, sources, reasons, db, {"quests": {"500": entry}})
check("3 giver adds only for missing ids, union with trace row, source trace+wh-page",
      patch["Npc"][100]["questStarts_add"] == [9, 500] and "questEnds_add" not in patch["Npc"][100]
      and "questStarts_add" not in patch["Npc"].get(101, {}) and patch["Npc"][101]["questEnds_add"] == [500]
      and sources["Npc"][100] == "trace+wh-page" and 999 not in patch["Npc"]
      and any("999" in l and "warning" in l for l in log), str((patch["Npc"], sources["Npc"], log)))

# 4
db = FakeDB(Item={8: {"name": "Have", "startQuest": 0}, 9: {"name": "Full", "startQuest": 5}})
patch, sources, reasons = fresh()
data = {"quests": {},
        "items": {"7": {"quests": [1], "role": "starter", "row": {"startQuest": 1}, "overrides": {"name": "New Item"}},
                  "8": {"quests": [1], "role": "starter", "row": {"startQuest": 1}, "overrides": {"name": "Ignored"}},
                  "9": {"quests": [1], "role": "starter", "row": {"startQuest": 1}, "overrides": {}}}}
log = curated.apply_added_quests(patch, sources, reasons, db, data)
check("4 items: new -> full row w/ override, DB-empty -> only startQuest, complete -> nothing",
      patch["Item"].get(7) == {"startQuest": 1, "name": "New Item"} and patch["Item"].get(8) == {"startQuest": 1}
      and 9 not in patch["Item"] and ("Item", 7, "name", "new-quest-item") in reasons
      and ("Item", 8, "startQuest", "fill-missing") in reasons and any("item 9 already complete" in l for l in log)
      and sources["Item"][7] == "wh-page", str((patch["Item"], log)))

# 5
db = FakeDB(Npc={100: {"name": "Giver"}})
patch, sources, reasons = fresh()
entry = quest_entry(zoneOrSort=1537, questLevel=60)
entry["overrides"] = {"zoneOrSort": None, "questLevel": 55}
curated.apply_added_quests(patch, sources, reasons, db, {"quests": {"500": entry}})
check("5 override null deletes, value replaces", "zoneOrSort" not in patch["Quest"][500] and patch["Quest"][500]["questLevel"] == 55)

# 6
db = FakeDB(Quest={1: {"name": "a"}, 2: {"name": "b", "requiredClasses": 4}, 3: {"name": "c", "requiredClasses": 0}},
            Npc={100: {"name": "Giver"}})
patch, sources, reasons = fresh()
curated.apply_added_quests(patch, sources, reasons, db, {"quests": {"500": quest_entry(), "501": quest_entry(requiredClasses=7)}})
cr = {"quests": {str(q): {"name": "n%d" % q, "faction": "Alliance", "class": "Druid", "requiredClasses": 1024, "method": "itemset"}
                 for q in (1, 2, 3, 500, 501, 77)}}
log = curated.apply_class_restrictions(patch, sources, reasons, db, cr)
check("6 class restriction: DB-empty applied, never over DB value, added quest filled, existing kept, unknown skipped",
      patch["Quest"][1]["requiredClasses"] == 1024 and sources["Quest"][1] == "class-map"
      and 2 not in patch["Quest"] and patch["Quest"][3]["requiredClasses"] == 1024
      and patch["Quest"][500]["requiredClasses"] == 1024 and sources["Quest"][500] == "wh-page+class-map"
      and patch["Quest"][501]["requiredClasses"] == 7
      and any(l.startswith("skip 2:") for l in log) and any(l.startswith("skip 77: quest not found") for l in log)
      and ("Quest", 1, "requiredClasses", "class-restriction") in reasons, str((patch["Quest"], log)))

# 7
db = FakeDB(Npc={100: {"name": "Giver"}})
patch, sources, reasons = fresh()
entry = quest_entry(questLevel="sixty")
log = curated.apply_added_quests(patch, sources, reasons, db, {"quests": {"500": entry}})
check("7 invalid field type dropped", "questLevel" not in patch["Quest"][500]
      and ("Quest", 500, "questLevel", "invalid-dropped") in reasons and any("questLevel" in l for l in log), str(log))

# 8
check("8a all-(0,0) -> [[-1,-1]]", zone_audit._instance_points([[0, 0], [0.0, 0.0]]) == [[-1, -1]])
check("8b mixed -> (0,0) dropped", zone_audit._instance_points([[0, 0], [12.5, 30.1]]) == [[12.5, 30.1]])
check("8c normal points untouched", zone_audit._instance_points([[1, 2], [3, 4]]) == [[1, 2], [3, 4]])

# 9
s = {"Npc": {1: "wh-tooltip"}}
curated.add_source(s, "Npc", 1, "trace")
curated.add_source(s, "Npc", 2, "class-map")
curated.add_source(s, "Npc", 2, "trace")
curated.add_source(s, "Npc", 2, "wh-page")
check("9 add_source ordering", s["Npc"][1] == "trace+wh-tooltip" and s["Npc"][2] == "trace+wh-page+class-map", str(s))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)

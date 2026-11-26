"""work/audit-all/candidates.json (action == fill-gap) -> data/gap_fills.json. Offline."""
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "work", "audit-all", "candidates.json")
OUT = os.path.join(ROOT, "data", "gap_fills.json")
SCOURGE_INVASION = {14697, 16141, 16298, 16299, 16379, 16380, 16383}
REDRAWN = {44, 139, 215, 1519}
EVENT_HINTS = ("Necropolis", "Shadow of Doom", "Pallid Horror", "Patchwork Terror", "Cultist Engineer",
               "Necrotic Shard", "Flameshocker", "Spectral", "Skeletal Shocktrooper", "Ghoul Berserker",
               "Bone Witch", "Lumbering Horror", "Spirit of the Damned")
COMMENT = ("Entities QuestieDB has no spawns for, filled from Wowhead Forever tooltip coordinates. Built by "
           "tools/gap_fill_select.py from the all-zones audit; refresh.py re-checks each one (ships only while "
           "QuestieDB still has no spawns, through the wh-tooltip rules) and never ships anything else from that audit.")


def main():
    with open(SRC, encoding="utf-8") as f:
        cands = json.load(f)
    ship, excluded = [], []
    for c in sorted((c for c in cands if c["action"] == "fill-gap"), key=lambda c: (c["kind"], c["id"])):
        base = {"kind": c["kind"], "id": c["id"], "name": c["name"], "whZone": c["wh_zone"]}
        reason = None
        if c["kind"] == "Npc" and c["id"] in SCOURGE_INVASION:
            reason = "scourge-invasion: event-only mob (Argent Dawn Scourge Invasion), not a permanent spawn"
        elif c["wh_zone"] in REDRAWN:
            reason = ("redrawn-map: Wowhead tooltip coordinates are never used on map %s (stale Era frame)"
                      % c["wh_zone"])
        if reason:
            excluded.append({**base, "quests": len(c["quests"]), "reason": reason})
            continue
        if any(h.lower() in c["name"].lower() for h in EVENT_HINTS):
            print("NOTE: possible invasion-event mob kept: %s %d %s" % (c["kind"], c["id"], c["name"]))
        ship.append({**base, "zones": c["zones"], "roles": c["roles"], "quests": len(c["quests"]),
                     "factions": c["factions"]})
    date = datetime.date.fromtimestamp(os.path.getmtime(SRC)).isoformat()
    out = {"_comment": COMMENT,
           "source": {"audit": "work/audit-all/candidates.json", "auditDate": date,
                      "rule": "action == fill-gap: questie-no-spawns, and the Wowhead tooltip zone is one of the "
                              "zones of the entity's quests"},
           "ship": ship, "excluded": excluded}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    print("ship %d, excluded %d" % (len(ship), len(excluded)))
    for e in excluded:
        print("  excluded %s %d %s: %s" % (e["kind"], e["id"], e["name"], e["reason"][:40]))


if __name__ == "__main__":
    main()

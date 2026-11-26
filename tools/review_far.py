"""work/audit-all/candidates.json (status == far) -> work/audit-all/review_far.md (not shipped; verify in game)."""
import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qdb_decode import InstalledDB  # noqa: E402
from zone_audit_all import quest_faction  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDB = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB"
SRC = os.path.join(ROOT, "work", "audit-all", "candidates.json")
OUT = os.path.join(ROOT, "work", "audit-all", "review_far.md")


def nearest(pts, others, n=3):
    def d(p):
        return min(math.hypot(p[0] - o[0], p[1] - o[1]) for o in others) if others else 0
    return sorted(pts, key=lambda p: (d(p), p[0], p[1]))[:n]


def fmt(pts, total):
    s = ", ".join("(%.1f, %.1f)" % (p[0], p[1]) for p in pts)
    return s + (" +%d" % (total - len(pts)) if total > len(pts) else "")


def main():
    with open(SRC, encoding="utf-8") as f:
        cands = [c for c in json.load(f) if c["status"] == "far"]
    db = InstalledDB(QDB)
    patch = {}
    pp = os.path.join(ROOT, "work", "patch.json")
    if os.path.exists(pp):
        with open(pp, encoding="utf-8") as f:
            patch = json.load(f).get("patch", {})
    zones = {}
    for c in cands:
        zones.setdefault(" / ".join(c["zones"]) or "(unknown zone)", []).append(c)
    zq = {z: {q for c in cs for q in c["quests"]} for z, cs in zones.items()}
    order = sorted(zones, key=lambda z: (-len(zq[z]), z))
    lines = ["# Far-spawn review", "",
             "Entities whose QuestieDB spawns are more than 3 map units from every Wowhead Forever tooltip point. "
             "Check in game which is right; nothing here is shipped.", "",
             "Generated %s. %d entities, %d zones, %d distinct quests." % (
                 datetime.date.today().isoformat(), len(cands), len(zones), len(set().union(*zq.values())) if zq else 0),
             ""]
    for z in order:
        lines += ["## %s \u2014 %d quests, %d entities" % (z, len(zq[z]), len(zones[z])), ""]
        for c in sorted(zones[z], key=lambda c: (-len(c["quests"]), c["kind"], c["id"])):
            qp = [p[:2] for p in c["questie_points"]]
            wp = [p[:2] for p in c["wh_points"]]
            ships = "spawns" in ((patch.get(c["kind"], {}) or {}).get(str(c["id"])) or {})
            lines.append("- **%s** (%s %d) \u2014 %s \u2014 dist %.1f%s" % (
                c["name"], c["kind"], c["id"], ", ".join(c["roles"]), c["distance"] or 0,
                " \u2014 QFF already ships spawns for it" if ships else ""))
            lines.append("  Questie: %s | Wowhead: %s" % (fmt(nearest(qp, wp), len(qp)), fmt(nearest(wp, qp), len(wp))))
            qs = []
            for q in c["quests"]:
                r = db.get("Quest", q) or {}
                qs.append(((r.get("name") or "?"), q, quest_faction(r) if r else "?"))
            lines.append("  Quests: " + "; ".join("%s (%d, %s)" % t for t in sorted(qs)))
        lines.append("")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    print("review_far: %d entities in %d zones -> %s" % (len(cands), len(zones), OUT))


if __name__ == "__main__":
    main()

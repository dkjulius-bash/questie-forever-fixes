"""Curated data layers merged into the patch: added quests (data/added_quests.json),
class restrictions (data/class_restrictions.json) and Wowhead gap fills (data/gap_fills.json)."""
import json
import os

import patch_policy
from qdb_decode import groups, id_list

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

SOURCE_ORDER = ("trace", "wh-tooltip", "wh-page", "class-map")
GROUP_FIELDS = ("startedBy", "finishedBy", "objectives")


def load(name):
    """Parsed data/<name> or None if the file is missing."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf8") as f:
        return json.load(f)


def add_source(sources, kind, eid, tag):
    cur = sources[kind].get(eid)
    tags = set(cur.split("+")) if cur else set()
    tags.add(tag)
    sources[kind][eid] = "+".join(t for t in SOURCE_ORDER if t in tags)


def _empty(v):
    return v is None or v is False or v == 0 or v == "" or (isinstance(v, (list, dict)) and len(v) == 0)


def _intkeys(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out[int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k] = x
        return out
    return v


def effective_row(entry):
    """row with overrides applied (override null deletes the field); group keys -> int."""
    row = dict(entry.get("row") or {})
    for f, v in (entry.get("overrides") or {}).items():
        if v is None:
            row.pop(f, None)
        else:
            row[f] = v
    for f in GROUP_FIELDS:
        if f in row:
            row[f] = _intkeys(row[f])
    return row


def _union(a, b):
    out = list(a)
    for x in b:
        if x not in out:
            out.append(x)
    return out


def _drop_reasons(reasons, kind, eid, fields):
    reasons[:] = [r for r in reasons if not (r[0] == kind and r[1] == eid and r[2] in fields)]


def _ids_str(row, f):
    ids = []
    for g in sorted(groups(row.get(f))):
        ids += groups(row.get(f))[g]
    return ",".join(str(i) for i in ids) or "-"


def apply_added_quests(patch, sources, reasons, db, data):
    log = []
    quests = data.get("quests") or {}
    retired = set()
    for qid in sorted(int(k) for k in quests):
        entry = quests[str(qid)]
        row = effective_row(entry)
        name = entry.get("name") or row.get("name") or "?"
        if db.get("Quest", qid) is not None:
            retired.add(qid)
            log.append("retired %d %s: now in QuestieDB" % (qid, name))
            continue
        base = dict(patch["Quest"].get(qid) or {})
        base.update(row)
        tmp = []
        out = patch_policy.validate_row("Quest", qid, base, db, tmp)
        for _k, _e, f, _r in tmp:
            log.append("quest %d: dropped invalid field %s" % (qid, f))
        _drop_reasons(reasons, "Quest", qid, set(row))
        for f in out:
            if f in row:
                reasons.append(("Quest", qid, f, "new-quest"))
        patch["Quest"][qid] = out
        add_source(sources, "Quest", qid, "wh-page")
        for _k, _e, f, _r in tmp:
            reasons.append(("Quest", qid, f, "invalid-dropped"))
        # givers
        for field, add_field in (("startedBy", "questStarts"), ("finishedBy", "questEnds")):
            g = groups(row.get(field))
            for grp, kind in ((1, "Npc"), (2, "Object")):
                for gid in g.get(grp, []):
                    drow = db.get(kind, gid)
                    if drow is None:
                        log.append("warning: quest %d %s %s %d not in QuestieDB; giver skipped" % (qid, field, kind, gid))
                        continue
                    if qid in id_list(drow.get(add_field)):
                        continue
                    key = add_field + "_add"
                    prow = patch[kind].setdefault(gid, {})
                    prow[key] = _union(prow.get(key, []), [qid])
                    r = (kind, gid, key, "new-quest-giver")
                    if r not in reasons:
                        reasons.append(r)
                    add_source(sources, kind, gid, "wh-page")
        log.append("added %d %s %s (starter: %s, ender: %s)" % (
            qid, entry.get("faction", "?"), name, _ids_str(row, "startedBy"), _ids_str(row, "finishedBy")))
    # items
    for iid in sorted(int(k) for k in (data.get("items") or {})):
        entry = data["items"][str(iid)]
        qs = entry.get("quests") or []
        if qs and all(q in retired for q in qs):
            continue
        row = effective_row(entry)
        dbrow = db.get("Item", iid)
        existing = dict(patch["Item"].get(iid) or {})
        if dbrow is None:
            emit = dict(existing)
            emit.update(row)
            why = "new-quest-item"
            fields = set(row)
        else:
            fields = {f for f, v in row.items() if _empty(dbrow.get(f)) and f not in existing}
            emit = dict(existing)
            for f in fields:
                emit[f] = row[f]
            why = "fill-missing"
        if not fields:
            log.append("item %d already complete in QuestieDB" % iid if dbrow is not None else "item %d: no data to emit" % iid)
            continue
        tmp = []
        out = patch_policy.validate_row("Item", iid, emit, db, tmp)
        for _k, _e, f, _r in tmp:
            log.append("item %d: dropped invalid field %s" % (iid, f))
            reasons.append(("Item", iid, f, "invalid-dropped"))
        _drop_reasons(reasons, "Item", iid, fields)
        for f in out:
            if f in fields:
                reasons.append(("Item", iid, f, why))
        patch["Item"][iid] = out
        add_source(sources, "Item", iid, "wh-page")
    return log


def apply_class_restrictions(patch, sources, reasons, db, data):
    log = []
    quests = data.get("quests") or {}
    for qid in sorted(int(k) for k in quests):
        e = quests[str(qid)]
        mask = e.get("requiredClasses")
        dbrow = db.get("Quest", qid)
        if dbrow is not None:
            cur = dbrow.get("requiredClasses")
            if not _empty(cur):
                log.append("skip %d: QuestieDB already sets requiredClasses %s" % (qid, cur))
                continue
            patch["Quest"].setdefault(qid, {})["requiredClasses"] = mask
        elif qid in patch["Quest"]:
            if "requiredClasses" in patch["Quest"][qid]:
                continue
            patch["Quest"][qid]["requiredClasses"] = mask
        else:
            log.append("skip %d: quest not found" % qid)
            continue
        reasons.append(("Quest", qid, "requiredClasses", "class-restriction"))
        add_source(sources, "Quest", qid, "class-map")
        log.append("%d %s %s -> %s (%s) via %s" % (qid, e.get("faction", "?"), e.get("name", "?"), e.get("class", "?"), mask, e.get("method", "?")))
    return log


def gap_fill_entities(data):
    return [(e["kind"], int(e["id"])) for e in (data.get("ship") or [])]

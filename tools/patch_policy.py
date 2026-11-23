"""Policy: diff extractor output against the installed QuestieDB, keep only useful rows/fields."""
import math

from qdb_decode import groups, id_list, spawn_points, is_sentinel, _isint, _collect_ints

GIVER_MATCH_DIST = 1.5
MOB_NEW_POINT_DIST = 3.0

GROUP_ADD = {("Quest", "startedBy_add"), ("Quest", "finishedBy_add")}
FLAT_ADD = {("Npc", "questStarts_add"), ("Npc", "questEnds_add"),
            ("Object", "questStarts_add"), ("Object", "questEnds_add"),
            ("Item", "npcDrops_add"), ("Item", "objectDrops_add")}


def _empty(v):
    if v is None or v is False or v == 0 or v == "":
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def _base(field):
    for suf in ("_add", "_remove"):
        if field.endswith(suf):
            return field[: -len(suf)]
    return field


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _round_pt(p):
    return [round(c, 4) if isinstance(c, float) else c for c in p]


def _row_ids(rows):
    """First element (the entity id) of each objectives row."""
    out = []
    if isinstance(rows, dict):
        rows = [rows[k] for k in sorted(rows, key=lambda z: (isinstance(z, str), z))]
    if not isinstance(rows, list):
        return out
    for r in rows:
        if _isint(r):
            out.append(r)
        elif isinstance(r, (list, tuple)) and r and _isint(r[0]):
            out.append(r[0])
        elif isinstance(r, dict) and _isint(r.get(1)):
            out.append(r[1])
    return out


def _db_obj_groups(v):
    """DB objectives -> {group: raw rows list}."""
    out = {}
    if isinstance(v, list):
        items = [(i + 1, y) for i, y in enumerate(v)]
    elif isinstance(v, dict):
        items = [(k if _isint(k) else (int(k) if isinstance(k, str) and k.isdigit() else None), y) for k, y in v.items()]
    else:
        return out
    for g, rows in items:
        if g is None or rows is None: continue
        out[g] = rows
    return out


def _rows_list(rows):
    if isinstance(rows, dict):
        return [rows[k] for k in sorted(rows, key=lambda z: (isinstance(z, str), z))]
    return rows if isinstance(rows, list) else []


def _is_giver(kind, eid, ext_row, dbrow, extracted):
    for f in ("questStarts", "questEnds"):
        if dbrow and not _empty(dbrow.get(f)): return True
        if not _empty(ext_row.get(f + "_add")): return True
    grp = 1 if kind == "Npc" else 2
    for q in extracted.get("Quest", {}).values():
        for f in ("startedBy_add", "finishedBy_add"):
            if eid in groups(q.get(f)).get(grp, []):
                return True
    return False


def _spawn_patch(kind, eid, ext_row, dbrow, extracted):
    """Returns (full merged spawns table or None, set(reason codes))."""
    obs = {z: [p for p in pts if not is_sentinel(p)] for z, pts in spawn_points(ext_row.get("spawns")).items()}
    obs = {z: p for z, p in obs.items() if p}
    dbsp = spawn_points(dbrow.get("spawns")) if dbrow else {}
    giver = None
    merged = {z: [tuple(p) for p in pts] for z, pts in dbsp.items()}
    reasons = set()
    for z, opts in obs.items():
        dpts = dbsp.get(z, [])
        usable = [p for p in dpts if not is_sentinel(p)]
        if not usable:
            merged[z] = [tuple(p) for p in dpts] + [tuple(p) for p in opts]
            reasons.add("spawn-new-zone")
            continue
        near = [any(_dist(o, d) <= GIVER_MATCH_DIST for d in usable) for o in opts]
        if all(near):
            continue
        if giver is None:
            giver = _is_giver(kind, eid, ext_row, dbrow, extracted)
        if giver and not any(near):
            merged[z] = [tuple(p) for p in opts]
            reasons.add("spawn-moved")
            continue
        cur = list(usable)
        added = []
        for o in opts:
            if all(_dist(o, d) > MOB_NEW_POINT_DIST for d in cur):
                added.append(tuple(o))
                cur.append(o)
        if added:
            merged[z] = [tuple(p) for p in dpts] + added
            reasons.add("spawn-extra-points")
    if not reasons:
        return None, reasons
    out = {z: [_round_pt(p) for p in pts] for z, pts in merged.items()}
    return out, reasons


def build_patch(extracted, db):
    patch = {k: {} for k in ("Quest", "Npc", "Object", "Item")}
    reasons = []
    for kind in patch:
        for eid, row in sorted(extracted.get(kind, {}).items()):
            dbrow = db.get(kind, eid)
            out = {}
            if dbrow is None:
                out = dict(row)
                for f in out:
                    reasons.append((kind, eid, f, "new-entity"))
            else:
                _existing(kind, eid, row, dbrow, extracted, out, reasons)
            out = _validate(kind, eid, out, db, reasons)
            if out:
                patch[kind][eid] = out
    # reasons for dropped rows/fields are filtered to what survives (invalid-dropped kept)
    keep = []
    for kind, eid, f, r in reasons:
        if r == "invalid-dropped" or f in patch[kind].get(eid, {}):
            keep.append((kind, eid, f, r))
    return patch, keep


def _existing(kind, eid, row, dbrow, extracted, out, reasons):
    def emit(f, v, why):
        out[f] = v
        reasons.append((kind, eid, f, why))

    spawn_done = False
    for f, v in row.items():
        if (kind, f) in GROUP_ADD:
            dbg = groups(dbrow.get(_base(f)))
            new = {}
            for g, ids in groups(v).items():
                have = set(dbg.get(g, []))
                nids = [i for i in dict.fromkeys(ids) if i not in have]
                if nids: new[g] = nids
            if new: emit(f, new, "add-ids")
        elif (kind, f) in FLAT_ADD:
            have = set(id_list(dbrow.get(_base(f))))
            nids = [i for i in dict.fromkeys(id_list(v)) if i not in have]
            if nids: emit(f, nids, "add-ids")
        elif kind == "Quest" and f == "objectives":
            _objectives(eid, v, dbrow, emit)
        elif kind == "Quest" and f == "questLevel":
            if _empty(dbrow.get(f)) or dbrow.get(f) != v:
                emit(f, v, "questLevel")
        elif f == "spawns" and kind in ("Npc", "Object"):
            sp, rs = _spawn_patch(kind, eid, row, dbrow, extracted)
            if sp is not None:
                for r in sorted(rs):
                    reasons.append((kind, eid, f, r))
                out[f] = sp
        else:
            if _empty(dbrow.get(f)) and not _empty(v):
                emit(f, v, "fill-missing")


def _objectives(eid, v, dbrow, emit):
    obs = groups(v)
    obs_ids = set()
    for g, ids in obs.items():
        obs_ids.update(ids)
    dbo = _db_obj_groups(dbrow.get("objectives"))
    dbids = set()
    for g in (1, 2, 3):
        if g in dbo: dbids.update(_row_ids(dbo[g]))
    if 5 in dbo:
        tmp = []
        _collect_ints(dbo[5], tmp)
        dbids.update(tmp)
    if obs_ids <= dbids:
        return
    # Group-preserving: keep every DB group as-is and only rewrite the observed groups
    # that hold an id the DB doesn't know. (A full replacement dropped valid DB objectives,
    # e.g. quest 2994's object objective when only its item objective was observed.)
    new = {g: rows for g, rows in dbo.items()}
    for g in sorted(obs):
        if set(obs[g]) <= dbids:
            continue
        rows = []
        dbrows = _rows_list(dbo.get(g))
        for i in dict.fromkeys(obs[g]):
            match = None
            for r in dbrows:
                if (isinstance(r, (list, tuple)) and r and r[0] == i) or r == i:
                    match = r
                    break
            rows.append(list(match) if isinstance(match, tuple) else (match if match is not None else [i]))
        new[g] = rows
    emit("objectives", new, "objectives-replaced")


def _validate(kind, eid, out, db, reasons):
    res = {}
    for f, v in out.items():
        base = _base(f)
        ftype = db.ftypes[kind].get(base)
        ok = ftype is not None
        if ok and f.endswith("_add") and ftype != "table":
            ok = False
        if ok and not (f.endswith("_add") or f.endswith("_remove")):
            if ftype == "number": ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            elif ftype == "string": ok = isinstance(v, str)
            elif ftype == "table": ok = isinstance(v, (list, dict))
        elif ok:
            ok = isinstance(v, (list, dict))
        if ok:
            res[f] = v
        else:
            reasons.append((kind, eid, f, "invalid-dropped"))
    return res

"""Human-readable report of the generated patch."""
from collections import Counter, defaultdict

from qdb_decode import groups, spawn_points, is_sentinel

RG_AREAS = {16591, 16685} | set(range(16723, 16732))


def _starter_ids(db, qid, extra=None):
    row = db.get("Quest", qid) or {}
    g = groups(row.get("startedBy"))
    npcs = set(g.get(1, []))
    objs = set(g.get(2, []))
    items = set(g.get(3, []))
    if extra:
        eg = groups(extra)
        npcs.update(eg.get(1, [])); objs.update(eg.get(2, [])); items.update(eg.get(3, []))
    return npcs, objs, items


def _zones(db, kind, eid):
    row = db.get(kind, eid)
    if not row: return None
    sp = spawn_points(row.get("spawns"))
    return {z for z, pts in sp.items() if any(not is_sentinel(p) for p in pts)}


def rg_quests(db):
    by_zone = set()
    by_spawn = set()
    for qid in db.ids("Quest"):
        row = db.get("Quest", qid)
        if row.get("zoneOrSort") in RG_AREAS:
            by_zone.add(qid)
        npcs, objs, _ = _starter_ids(db, qid)
        hit = False
        for n in npcs:
            z = _zones(db, "Npc", n)
            if z and z & RG_AREAS: hit = True; break
        if not hit:
            for o in objs:
                z = _zones(db, "Object", o)
                if z and z & RG_AREAS: hit = True; break
        if hit: by_spawn.add(qid)
    return by_zone, by_spawn


def build_report(patch, reasons, extracted, db, meta, sources=None):
    L = []
    P = L.append
    P("QuestieForeverFixes patch report")
    P("=" * 34)
    P("Sessions: %s   Characters: %s   Extractor commit: %s" % (meta.get("sessionCount"), meta.get("characters"), meta.get("extractorCommit")))
    P("QuestieDB %s   Questie %s" % (meta.get("questieDBVersion"), meta.get("questieVersion")))
    P("")
    P("(a) Patched entities")
    for kind in ("Quest", "Npc", "Object", "Item"):
        P("  %-7s extracted=%-5d patched=%d" % (kind, len(extracted.get(kind, {})), len(patch[kind])))
    P("")
    P("Per-field / per-reason counts")
    cnt = Counter((k, f, r) for k, _, f, r in reasons)
    for (k, f, r), n in sorted(cnt.items()):
        P("  %-7s %-20s %-20s %d" % (k, f, r, n))
    invalid = sum(n for (k, f, r), n in cnt.items() if r == "invalid-dropped")
    P("  invalid fields dropped: %d" % invalid)
    P("")

    if sources is not None:
        P("Patch rows by source")
        for kind in ("Quest", "Npc", "Object", "Item"):
            c = Counter(sources[kind].values())
            P("  %-7s trace=%-5d wh-tooltip=%-5d trace+wh-tooltip=%d" % (
                kind, c["trace"], c["wh-tooltip"], c["trace+wh-tooltip"]))
        whr = Counter((k, f, r) for k, _, f, r in reasons if r.startswith("wh-"))
        P("  wh-tooltip reasons per field:")
        for (k, f, r), n in sorted(whr.items()):
            P("    %-7s %-10s %-16s %d" % (k, f, r, n))
        if not whr:
            P("    (none)")
        P("")

    # ---- Riverglades
    by_zone, by_spawn = rg_quests(db)
    rg = sorted(by_zone | by_spawn)
    P("(c) Riverglades")
    P("  RG area ids: %s" % sorted(RG_AREAS))
    P("  RG quests (DB): %d   [zoneOrSort in RG: %d, starter spawns in RG: %d, both: %d]" % (
        len(rg), len(by_zone), len(by_spawn), len(by_zone & by_spawn)))

    pq = patch["Quest"]
    pn = patch["Npc"]
    po = patch["Object"]
    pi = patch["Item"]
    kinds = defaultdict(set)
    diag = Counter()
    for q in rg:
        row = db.get("Quest", q)
        prow = pq.get(q, {})
        npcs, objs, items = _starter_ids(db, q, prow.get("startedBy_add"))
        if "startedBy_add" in prow:
            kinds[q].add("new-starter")
        if any("spawns" in pn.get(n, {}) for n in npcs) or any("spawns" in po.get(o, {}) for o in objs):
            kinds[q].add("starter-spawn")
        fg = groups(row.get("finishedBy"))
        fg2 = groups(prow.get("finishedBy_add"))
        fn = set(fg.get(1, [])) | set(fg2.get(1, []))
        fo = set(fg.get(2, [])) | set(fg2.get(2, []))
        if "finishedBy_add" in prow or any("spawns" in pn.get(n, {}) for n in fn) or any("spawns" in po.get(o, {}) for o in fo):
            kinds[q].add("finisher")
        og = groups(row.get("objectives"))
        og2 = groups(prow.get("objectives"))
        on = set(og.get(1, [])) | set(og2.get(1, []))
        oo = set(og.get(2, [])) | set(og2.get(2, []))
        oi = set(og.get(3, [])) | set(og2.get(3, []))
        if "objectives" in prow or any("spawns" in pn.get(n, {}) for n in on) or any("spawns" in po.get(o, {}) for o in oo) \
                or any(("npcDrops_add" in pi.get(i, {}) or "objectDrops_add" in pi.get(i, {})) for i in oi):
            kinds[q].add("objectives")
        # DB diagnostics
        if not (npcs or objs or items):
            diag["no startedBy in DB"] += 1
        else:
            dnpcs, dobjs, _ = _starter_ids(db, q)
            zs = set()
            have_any = False
            for n in dnpcs:
                z = _zones(db, "Npc", n)
                if z: have_any = True; zs |= z
            for o in dobjs:
                z = _zones(db, "Object", o)
                if z: have_any = True; zs |= z
            if dnpcs or dobjs:
                if not have_any: diag["starter has no spawns in DB"] += 1
                elif not (zs & RG_AREAS): diag["starter has spawns, all outside RG"] += 1

    fixed = [q for q in rg if kinds[q]]
    observed = [q for q in rg if q in extracted.get("Quest", {})]
    obs_nofix = [q for q in observed if not kinds[q]]
    unobs = [q for q in rg if q not in extracted.get("Quest", {}) and not kinds[q]]
    kc = Counter(k for q in rg for k in kinds[q])
    P("  Fix kinds (quests):")
    for k in ("new-starter", "starter-spawn", "finisher", "objectives"):
        P("    %-14s %d" % (k, kc[k]))
    P("    %-14s 0   (the extractor has no prerequisite observer; prereqs are never inferred)" % "prereq")
    P("  RG quests with >=1 fix: %d" % len(fixed))
    P("  Observed but nothing to fix (DB already agrees): %d" % len(obs_nofix))
    P("  Unobserved (traces cannot fix): %d" % len(unobs))
    P("  DB-side diagnostics for RG quests:")
    for k in ("no startedBy in DB", "starter has no spawns in DB", "starter has spawns, all outside RG"):
        P("    %-38s %d" % (k, diag[k]))
    P("  Fixed RG quests:")
    for q in fixed:
        P("    %d  %s  [%s]" % (q, (db.get("Quest", q) or {}).get("name", "?"), ", ".join(sorted(kinds[q]))))
    P("")
    return "\n".join(L)

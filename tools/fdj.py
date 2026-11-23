"""Loader for the ForeverDungeonJournal addon data (executed with lupa, not line-parsed)."""
import csv
import os
import re

try:
    from lupa import lua51
except ImportError:  # pragma: no cover
    from lupa import LuaRuntime as _LR
    lua51 = None

_HERE = os.path.dirname(os.path.abspath(__file__))
AREA_CSV = os.path.join(_HERE, "..", "vendor", "QuestieTrace", "tools", "corrections-extractor",
                        "src", "extract", "resources", "AreaTable.1.60.1.70009.csv")

_NS_LUA = r"""
local function viv(t)
  return setmetatable(t, { __index = function(tbl, k)
    local n = viv({}); rawset(tbl, k, n); return n end })
end
local stub = function() return setmetatable({}, { __index = function() return function() end end }) end
CreateFrame = CreateFrame or stub
C_Timer = C_Timer or { After = function() end }
local ns = viv({})
ns.Constants = setmetatable({}, { __index = function(_, k) return k end })
return ns
"""


def _py(v, lua):
    t = lua.eval('type')(v) if not isinstance(v, (str, int, float, bool, type(None))) else None
    if t is None:
        return v
    if t != 'table':
        return None  # functions etc.
    items = [(k, v[k]) for k in v.keys()]
    n = len(items)
    if n and all(isinstance(k, (int, float)) and not isinstance(k, bool) and k == int(k) for k, _ in items):
        keys = sorted(int(k) for k, _ in items)
        if keys == list(range(1, n + 1)):
            return [_py(v[i], lua) for i in range(1, n + 1)]
    out = {}
    for k, x in items:
        if isinstance(k, float) and k == int(k):
            k = int(k)
        out[k] = _py(x, lua)
    return out


def _level_range(s):
    m = re.match(r'\s*(\d+)\s*(?:-\s*(\d+))?', str(s or ''))
    if not m:
        return (0, 0)
    a = int(m.group(1))
    return (a, int(m.group(2) or a))


def _scan_tags(src):
    tags = {}
    cur = None
    for line in src.splitlines():
        m = re.match(r'\s*--\s*BEGIN\s+(\S+)', line)
        if m:
            cur = m.group(1)
            continue
        if re.match(r'\s*--\s*END\s+', line):
            cur = None
            continue
        if cur:
            m = re.match(r'\s*FDJ\.QUEST_PREREQ_(?:CHAINS|DETAILS)\[(\d+)\]\s*=', line)
            if m:
                tags[int(m.group(1))] = cur
    return tags


def load_fdj(addon_dir):
    data_dir = os.path.join(addon_dir, "Data")
    L = lua51.LuaRuntime(unpack_returned_tuples=True)
    ns = L.execute(_NS_LUA)
    tags = {}
    for fn in ("Dungeons.lua", "QuestChains.lua", "QuestUpdates.lua"):
        with open(os.path.join(data_dir, fn), encoding='utf8') as f:
            src = f.read()
        r = L.eval('loadstring')(src, '@' + fn)
        if isinstance(r, tuple):
            raise RuntimeError("loadstring failed for %s: %s" % (fn, r[1] if len(r) > 1 else r))
        r('ForeverDungeonJournal', ns)
        if fn == "QuestUpdates.lua":
            tags = _scan_tags(src)
    dungeons = {}
    db = _py(ns.DB, L)
    for name, d in db.items():
        if not isinstance(d, dict):
            continue
        qs = d.get('quests') or []
        if isinstance(qs, dict):
            qs = [qs[k] for k in sorted(qs)]
        dungeons[name] = {"level": _level_range(d.get('level')), "location": d.get('location') or "",
                          "quests": [q for q in qs if isinstance(q, dict)]}
    chains = {}
    for qid, lst in (_py(ns.QUEST_PREREQ_CHAINS, L) or {}).items():
        if isinstance(lst, dict):
            lst = [lst[k] for k in sorted(lst, key=str)]
        chains[qid] = [e['id'] for e in lst if isinstance(e, dict) and isinstance(e.get('id'), int)]
    details = {k: v for k, v in (_py(ns.QUEST_PREREQ_DETAILS, L) or {}).items() if isinstance(v, dict)}
    return {"dungeons": dungeons, "chains": chains, "details": details, "tags": tags}


_AREAS = None


def _areas():
    global _AREAS
    if _AREAS is None:
        by_name = {}
        with open(AREA_CSV, encoding='utf8', newline='') as f:
            for row in csv.DictReader(f):
                try:
                    aid = int(row['ID'])
                    parent = int(row.get('ParentAreaID') or 0)
                except ValueError:
                    continue
                for nm in {row.get('AreaName_lang') or '', row.get('ZoneName') or ''}:
                    nm = nm.strip().lower()
                    if nm:
                        by_name.setdefault(nm, []).append((parent != 0, aid))
        _AREAS = {k: min(v)[1] for k, v in by_name.items()}  # top-level (parent 0) first, then lowest id
    return _AREAS


_COORD = re.compile(r'\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)')


def parse_place(text):
    text = text or ""
    coords = None
    m = _COORD.search(text)
    if m:
        coords = (float(m.group(1)), float(m.group(2)))
        text = text[:m.start()] + text[m.end():]
    segs = [s.strip() for s in text.split(',')]
    npc = segs[0] if segs else ""
    areas = _areas()
    zone = None
    for s in segs[1:]:
        s2 = re.sub(r'^(?:in|at|near|outside|inside)\s+(?:the\s+)?', '', s.strip().rstrip('.'), flags=re.I).lower()
        for cand in (s.strip().rstrip('.').lower(), s2):
            if cand in areas:
                zone = areas[cand]
                break
        if zone is not None:
            break
    return {"npc": npc, "zone": zone, "coords": coords}

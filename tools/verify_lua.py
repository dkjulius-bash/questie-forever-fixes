"""Static verification harness for QuestieForeverFixes (Data.lua + Core.lua) under Lua 5.1 via lupa."""
import argparse
import re
import sys
from pathlib import Path

from lupa import lua51

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "addon" / "QuestieForeverFixes"
FIXTURE = ROOT / "tools" / "fixtures" / "Data.lua"
LOCAL_FIXTURE = ROOT / "tools" / "fixtures" / "LocalData.lua"
META_DIR = Path(r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB\src\meta")
KINDS = [("Quest", "quest"), ("Npc", "npc"), ("Object", "object"), ("Item", "item")]
ADDON_NAME = "QuestieForeverFixes"

PAIR = re.compile(r"\[(\d+)\]='([^']*)'")


def parse_meta(kind):
    """Return (names, types) dicts index->str from the first two `[1]='...'` lines."""
    lines = [l for l in (META_DIR / f"{kind}Meta.lua").read_text(encoding="utf-8").splitlines() if l.startswith("[1]=")]
    names = {int(i): v for i, v in PAIR.findall(lines[0])}
    types = {int(i): v for i, v in PAIR.findall(lines[1])}
    return names, types


STUB_TEMPLATE = r'''
__out, __frames, __registry, __applied, __registered = {}, {}, {}, {}, {}
__opts = ...
local function addline(s) __out[#__out + 1] = s end
print = addline
DEFAULT_CHAT_FRAME = { AddMessage = function(_, s) addline(s) end }
SlashCmdList = {}
C_AddOns = { GetAddOnMetadata = function(a, k) if a == "QuestieDB" and k == "Version" then return "1.1.5" end end }
function CreateFrame()
    local f = { events = {} }
    function f:RegisterEvent(e) self.events[e] = true end
    function f:UnregisterEvent(e) self.events[e] = nil end
    function f:SetScript(n, fn) if n == "OnEvent" then self.onevent = fn end end
    __frames[#__frames + 1] = f
    return f
end
function __fire(ev, arg)
    for _, f in ipairs(__frames) do
        if f.events[ev] and f.onevent then f.onevent(f, ev, arg) end
    end
end
local META = { Quest = __META_Quest, Npc = __META_Npc, Object = __META_Object, Item = __META_Item }
local KEYSNAME = { Quest = "questKeys", Npc = "npcKeys", Object = "objectKeys", Item = "itemKeys" }
local function keysFor(dt)
    local k = {}
    for i, n in pairs(META[dt].names) do k[n] = i; k[n .. "_add"] = i + 1000; k[n .. "_remove"] = i - 1000 end
    return k
end
local function validate(dt, rows)
    local m = META[dt]
    if type(rows) ~= "table" then error(dt .. ": rows not a table", 0) end
    for id, row in pairs(rows) do
        if type(id) ~= "number" or id < 1 or id % 1 ~= 0 then error(dt .. ": bad id " .. tostring(id), 0) end
        if type(row) ~= "table" then error(dt .. "[" .. id .. "]: row not a table", 0) end
        for key, v in pairs(row) do
            if type(key) ~= "number" then error(dt .. "[" .. id .. "]: non-numeric key " .. tostring(key), 0) end
            local idx, op = key, "set"
            if key > 1000 then idx, op = key - 1000, "add" elseif key < 0 then idx, op = key + 1000, "remove" end
            if not m.names[idx] then error(dt .. "[" .. id .. "]: unknown field key " .. key, 0) end
            if v == nil then error(dt .. "[" .. id .. "]: nil value", 0) end
            if op == "add" and m.types[idx] ~= "table" then
                error(dt .. "[" .. id .. "]: _add on non-table field " .. m.names[idx], 0)
            end
        end
    end
end
if not __opts.nolib then
    local lib = { contractVersion = 4, minSupportedContract = 1, Enum = {}, Corrections = {} }
    for dt, kn in pairs(KEYSNAME) do lib.Enum[kn] = keysFor(dt) end
    function lib.RequireContract(n)
        if __opts.contract_fail then return false, "too old" end
        return n >= 1 and n <= 4, "contract " .. tostring(n)
    end
    function lib.RegisterRuntimeCorrection(owner, dt, name, func, order)
        for i = #__registry, 1, -1 do
            local e = __registry[i]
            if e.owner == owner and e.datatype == dt and e.name == name then table.remove(__registry, i) end
        end
        __registry[#__registry + 1] = { owner = owner, datatype = dt, name = name, func = func, loadOrder = order }
    end
    function lib.ApplyRegisteredCorrections(owner)
        for _, e in ipairs(__registry) do
            if e.owner == owner then
                if __opts.fail_on == e.datatype then error("simulated failure for " .. e.datatype, 0) end
                local rows = e.func()
                validate(e.datatype, rows)
                local n = 0
                for _ in pairs(rows) do n = n + 1 end
                __applied[e.datatype] = n
                __registered[e.datatype] = rows
            end
        end
    end
    function lib.Corrections.UnregisterCorrection(owner, dt, name)
        for i = #__registry, 1, -1 do
            local e = __registry[i]
            if e.owner == owner and e.datatype == dt and e.name == name then table.remove(__registry, i) end
        end
        __applied[dt] = nil
        __registered[dt] = nil
    end
    LibQuestieDB = lib
end
if __opts.sv_disabled then QuestieForeverFixesDB = { disabled = true } end
function __serialize(v)
    if type(v) ~= "table" then return type(v) == "string" and string.format("%q", v) or tostring(v) end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b)
        if type(a) == type(b) then return a < b end
        return type(a) == "number"
    end)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = "[" .. __serialize(k) .. "]=" .. __serialize(v[k]) end
    return "{" .. table.concat(parts, ",") .. "}"
end
function __count_data()
    local d, c = ns_global.data(), {}
    for _, dt in ipairs({ "Quest", "Npc", "Object", "Item" }) do
        local n = 0
        for _ in pairs(d[dt] or {}) do n = n + 1 end
        c[dt] = n
    end
    return c
end
'''


class Scenario:
    def __init__(self, data_path, local_data=None, **opts):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        assert self.lua.eval("_VERSION") == "Lua 5.1", "not Lua 5.1"
        lua = self.lua
        stub = STUB_TEMPLATE
        for dt, kind in KINDS:
            names, types = parse_meta(kind)
            lit = "{names=%s,types=%s}" % (
                "{" + ",".join(f'[{i}]="{n}"' for i, n in names.items()) + "}",
                "{" + ",".join(f'[{i}]="{n}"' for i, n in types.items()) + "}",
            )
            stub = stub.replace(f"__META_{dt}", lit)
        o = lua.table()
        for k, v in opts.items():
            o[k] = v
        self.load("stub", stub, o)
        self.ns = lua.table()
        lua.globals().ns_global = self.ns
        if local_data is not None:
            src = Path(local_data).read_text(encoding="utf-8") if isinstance(local_data, Path) else local_data
            self.load("LocalData.lua", src)
        self.load("Data.lua", Path(data_path).read_text(encoding="utf-8"), ADDON_NAME, self.ns)
        self.load("Core.lua", (ADDON / "Core.lua").read_text(encoding="utf-8"), ADDON_NAME, self.ns)

    def load(self, name, src, *args):
        res = self.lua.eval("loadstring")(src, "@" + name)
        fn, err = res if isinstance(res, tuple) else (res, None)
        if fn is None:
            raise RuntimeError(f"compile error in {name}: {err}")
        fn(*args)

    def fire(self):
        self.lua.globals()["__fire"]("ADDON_LOADED", ADDON_NAME)

    def out(self):
        g = self.lua.globals()
        return [str(g["__out"][i]) for i in range(1, len(g["__out"]) + 1)]

    def registry(self):
        g = self.lua.globals()
        return [(str(e["owner"]), str(e["datatype"]), str(e["name"]), e["loadOrder"])
                for e in (g["__registry"][i] for i in range(1, len(g["__registry"]) + 1))]

    def applied(self):
        return {str(k): v for k, v in self.lua.globals()["__applied"].items()}

    def slash(self, msg):
        before = len(self.out())
        self.lua.globals().SlashCmdList.QUESTIEFOREVERFIXES(msg)
        return self.out()[before:]

    def data_counts(self):
        return {str(k): v for k, v in self.lua.globals()["__count_data"]().items()}

    def meta_counts(self):
        return {str(k): v for k, v in self.ns.meta.counts.items()}

    def sv(self):
        return self.lua.globals().QuestieForeverFixesDB


results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'}: {name}" + (f" -- {detail}" if detail and not cond else ""))


def scenario_a(data):
    print("[a] normal")
    s = Scenario(data)
    check("Data.lua + Core.lua load", True)
    s.fire()
    reg = s.registry()
    dc, mc = s.data_counts(), s.meta_counts()
    expect = sorted(dt for dt, n in dc.items() if n > 0)
    check("registered exactly non-empty datatypes", sorted(r[1] for r in reg) == expect, f"{reg} vs {expect}")
    check("owner/name correct", all(r[0] == ADDON_NAME and r[2] == "traces" for r in reg))
    ap = s.applied()
    check("applied counts == data entity counts", ap == {k: v for k, v in dc.items() if v > 0}, f"{ap} vs {dc}")
    check("data counts == ns.meta.counts", dc == mc, f"{dc} vs {mc}")
    check("no warning printed", s.out() == [], str(s.out()))
    lines = s.slash("")
    txt = "\n".join(lines)
    check("/qff shows counts", all(f"{dt} {n}" in txt for dt, n in dc.items()), txt)
    check("/qff shows contract 4 and QuestieDB version", "contract 4" in txt and "QuestieDB 1.1.5" in txt, txt)
    check("/qff zero skipped fields", "skipped fields 0" in txt, txt)
    print("  /qff output:")
    for l in lines:
        print("    " + l)
    print("  registered tables:")
    g = s.lua.globals()
    for dt, _ in KINDS:
        rows = g.__registered[dt]
        if rows is None:
            print(f"    {dt}: (none)")
            continue
        print(f"    {dt}: {ap[dt]} rows")
        ids = sorted(k for k in rows.keys())[:3]
        for i in ids:
            print(f"      [{i}] = {g.__serialize(rows[i])}")


def scenario_b(data):
    print("[b] /qff off")
    s = Scenario(data)
    s.fire()
    s.slash("off")
    check("disabled == true", s.sv()["disabled"] is True)
    s2 = Scenario(data, sv_disabled=True)
    s2.fire()
    check("disabled runtime registers nothing", s2.registry() == [])
    check("exactly one line printed", len(s2.out()) == 1, str(s2.out()))
    s2.slash("on")
    check("/qff on clears disabled", s2.sv()["disabled"] is None)


def scenario_c(data):
    print("[c] LibQuestieDB absent")
    s = Scenario(data, nolib=True)
    try:
        s.fire()
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    check("no Lua error", ok)
    check("exactly one warning line", len(s.out()) == 1, str(s.out()))
    check("nothing registered", s.registry() == [])
    s.slash("")  # must not crash


def scenario_d(data):
    print("[d] RequireContract false")
    s = Scenario(data, contract_fail=True)
    s.fire()
    check("one warning line containing message", len(s.out()) == 1 and "too old" in s.out()[0], str(s.out()))
    check("nothing registered", s.registry() == [])


def scenario_e(data):
    print("[e] isolation (Npc fails)")
    s = Scenario(data, fail_on="Npc")
    s.fire()
    dc = s.data_counts()
    exp = {k: v for k, v in dc.items() if v > 0 and k != "Npc"}
    check("other datatypes applied", s.applied() == exp, f"{s.applied()} vs {exp}")
    check("Npc unregistered", all(r[1] != "Npc" for r in s.registry()))
    check("one warning line naming Npc", len(s.out()) == 1 and "Npc" in s.out()[0], str(s.out()))
    txt = "\n".join(s.slash(""))
    check("/qff shows Npc error", "error Npc" in txt and "simulated failure" in txt, txt)


def scenario_f(data):
    print("[f] static checks")
    lua = lua51.LuaRuntime()
    check("lupa is Lua 5.1", lua.eval("_VERSION") == "Lua 5.1")
    for p in (Path(data), ADDON / "Core.lua"):
        src = p.read_text(encoding="utf-8")
        check(f"{p.name}: no goto", re.search(r"\bgoto\b", src) is None)
        check(f"{p.name}: no //", "//" not in src)
        res = lua.eval("loadstring")(src, "@" + p.name)
        fn, err = res if isinstance(res, tuple) else (res, None)
        check(f"{p.name}: compiles", fn is not None, str(err))


SRC_TAGS = ("trace", "wh-tooltip", "wh-page", "class-map")
SRC_RE = re.compile(r"-- src: ([a-z-]+(?:\+[a-z-]+)*)\s*$")


def _src_ok(m):
    return m is not None and all(t in SRC_TAGS for t in m.group(1).split("+"))
ROW_RE = re.compile(r"^\s+\[\d+\] = \{")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def scenario_g(data):
    print("[g] row source comments")
    lines = [l for l in Path(data).read_text(encoding="utf-8").splitlines() if ROW_RE.match(l)]
    bad = [l[:80] for l in lines if not _src_ok(SRC_RE.search(l))]
    check("every row line carries a -- src comment (%d rows)" % len(lines), lines and not bad, str(bad[:3]))


def spawns_bad(d):
    """Check spawns shape on a data() table; return (rows_checked, [bad row labels])."""
    bad = []
    n = 0
    for dt in ("Npc", "Object"):
        rows = d[dt]
        if rows is None:
            continue
        for eid, row in rows.items():
            sp = row["spawns"]
            if sp is None:
                continue
            n += 1
            ok = True
            for z, pts in sp.items():
                if not (_num(z) and z >= 1 and z == int(z)): ok = False; break
                items = list(pts.values()) if pts is not None else []
                if not items: ok = False; break
                for pt in items:
                    x, y = pt[1], pt[2]
                    if not (_num(x) and _num(y)): ok = False; break
                    if not ((0 <= x <= 100 and 0 <= y <= 100) or (x == -1 and y == -1)): ok = False; break
                    if pt[3] is not None and not _num(pt[3]): ok = False; break
                if not ok: break
            if not ok:
                bad.append("%s[%s]" % (dt, eid))
    return n, bad


def scenario_h(data):
    print("[h] spawns shape")
    s = Scenario(data)
    n, bad = spawns_bad(s.ns.data())
    check("all spawns values well-formed (%d checked)" % n, not bad, str(bad[:5]))


def scenario_i(data):
    print("[i] meta.sources vs comments")
    text = Path(data).read_text(encoding="utf-8")
    cnt = {}
    for l in text.splitlines():
        if ROW_RE.match(l):
            m = SRC_RE.search(l)
            if _src_ok(m): cnt[m.group(1)] = cnt.get(m.group(1), 0) + 1
    s = Scenario(data)
    src = s.ns.meta.sources
    check("meta.sources present", src is not None)
    if src is not None:
        got = {str(k): v for k, v in src.items()}
        check("meta.sources == comment counts", got == cnt, "%s vs %s" % (got, cnt))


def lua_ids(tbl):
    out = {}
    for dt, _ in KINDS:
        rows = tbl[dt]
        out[dt] = set(rows.keys()) if rows is not None else set()
    return out


def scenario_j(data, local_path):
    print("[j] local data")
    local_path = Path(local_path)
    text = local_path.read_text(encoding="utf-8")
    check("LocalData: no goto", re.search(r"\bgoto\b", text) is None)
    check("LocalData: no //", "//" not in text)
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    res = lua.eval("loadstring")(text, "@" + local_path.name)
    fn, err = res if isinstance(res, tuple) else (res, None)
    check("LocalData: compiles", fn is not None, str(err))
    if fn is None:
        return
    fn()
    g = lua.globals().QuestieForeverFixes_LocalData
    check("defines table QuestieForeverFixes_LocalData with meta table and data function",
          g is not None and lua.eval("type")(g.meta) == "table" and lua.eval("type")(g.data) == "function")
    d = g.data()
    counts = {dt: len(list(d[dt].keys())) for dt, _ in KINDS}
    meta_counts = {str(k): v for k, v in g.meta.counts.items()}
    check("meta.counts == data() row counts", counts == meta_counts, f"{counts} vs {meta_counts}")
    rows = [l for l in text.splitlines() if ROW_RE.match(l)]
    bad = [l[:60] for l in rows if "-- src:" not in l]
    check("every row line carries a -- src: comment (%d rows)" % len(rows), rows and not bad, str(bad[:3]))
    n, badsp = spawns_bad(d)
    check("local spawns well-formed (%d checked)" % n, not badsp, str(badsp[:5]))
    s = Scenario(data, local_data=local_path)
    s.fire()
    check("no lines printed at load", s.out() == [], str(s.out()))
    sh_ids, lo_ids = lua_ids(s.ns.data()), lua_ids(d)
    union = {dt: len(sh_ids[dt] | lo_ids[dt]) for dt, _ in KINDS}
    expect = {k: v for k, v in union.items() if v > 0}
    check("every non-empty kind registered", sorted(r[1] for r in s.registry()) == sorted(expect), str(s.registry()))
    check("applied counts == union of shipped and local ids", s.applied() == expect, f"{s.applied()} vs {expect}")


NEWQUEST_FIXTURE = ROOT / "tools" / "fixtures" / "DataNewQuest.lua"
QDB_SRC = META_DIR.parent
K_FILES = ["meta/questMeta.lua", "meta/normalize.lua", "corrections/tablePatch.lua",
           "corrections/registry.lua", "read/shared.lua"]

K_SETUP = r"""
function(L)
  local base = {
    [84195] = { [1] = "Saving the Best for Last", [6] = 4294967373, [10] = { nil, nil, { { 16720 }, { 16706 } } } },
    [9001] = { [1] = "Other Class Quest", [7] = 128 },
  }
  local list, map = { 9001, 84195 }, { [9001] = true, [84195] = true }
  local backend = {
    hasScalarRows = false,
    getAllIds = function() return list, map end,
    readField = function(id, idx) local r = base[id]; return r and r[idx] end,
  }
  L.Quest = L.shared.CreateEntity(L.Meta.Quest, backend)
  L.RequireContract = function(n) return true end
  L.contractVersion = 4
  L.minSupportedContract = 1
  local keys = {}
  for name, idx in pairs(L.Meta.Quest.keys) do
    keys[name] = idx; keys[name .. "_add"] = idx + 1000; keys[name .. "_remove"] = idx - 1000
  end
  L.Enum = { questKeys = keys, npcKeys = {}, objectKeys = {}, itemKeys = {} }
  L.RegisterRuntimeCorrection = L.Corrections.RegisterRuntimeCorrection
  L.ApplyRegisteredCorrections = L.Corrections.ApplyRegisteredCorrections
  LibQuestieDB = L
  __out, __frames = {}, {}
  DEFAULT_CHAT_FRAME = { AddMessage = function(_, s) __out[#__out + 1] = s end }
  SlashCmdList = {}
  C_AddOns = { GetAddOnMetadata = function(a, k) if a == "QuestieDB" and k == "Version" then return "1.1.5" end end }
  function CreateFrame()
    local f = { events = {} }
    function f:RegisterEvent(e) self.events[e] = true end
    function f:UnregisterEvent(e) self.events[e] = nil end
    function f:SetScript(n, fn) if n == "OnEvent" then self.onevent = fn end end
    __frames[#__frames + 1] = f
    return f
  end
end
"""

K_LOADER = """
function(name, src, lib)
  local fn = assert(loadstring(src, "@" .. name))
  return fn("QuestieDB", lib)
end
"""

K_LIB = """{
  config = { entityTypes = {{name="Quest"}}, expansionOrder = { Classic = 1, Forever = 1 } },
  flavor = { expansion = "Forever", rules = "Classic", name = "Forever" },
}"""

K_READ = """
R = {}
local Q = LibQuestieDB.Quest
R.e1, R.e2 = Q.Exists(84197), Q.Exists(82081)
R.all = Q.GetAllIds(true)[84197]
R.name = Q.Get(84197, "name")
R.rc = Q.Get(84197, "requiredClasses")
local ob = Q.Get(84197, "objectives")
R.ob = ob and ob[3] and ob[3][1] and ob[3][1][1]
local sb = Q.Get(84197, "startedBy")
R.sb = sb and sb[1] and sb[1][1]
local sb2 = Q.Get(82081, "startedBy")
R.sb2 = sb2 and sb2[3] and sb2[3][1]
R.rc2 = Q.Get(84195, "requiredClasses")
R.name2 = Q.Get(84195, "name")
local ob2 = Q.Get(84195, "objectives")
R.ob2 = ob2 and ob2[3] and ob2[3][2] and ob2[3][2][1]
R.rc3 = Q.Get(9001, "requiredClasses")
"""


def scenario_k(_data):
    print("[k] new quest + class override through the real QuestieDB registry")
    lua = lua51.LuaRuntime(unpack_returned_tuples=False)
    loader = lua.eval(K_LOADER)
    lib = lua.eval(K_LIB)
    for f in K_FILES:
        loader(f, (QDB_SRC / f).read_text(encoding="utf-8"), lib)
    lua.eval(K_SETUP)(lib)
    ns = lua.table()
    for name, path in (("Data.lua", NEWQUEST_FIXTURE), ("Core.lua", ADDON / "Core.lua")):
        fn = lua.eval("loadstring")(path.read_text(encoding="utf-8"), "@" + name)
        if fn is None:
            raise RuntimeError("compile error in " + name)
        fn(ADDON_NAME, ns)
    g = lua.globals()
    for i in range(1, len(g.__frames) + 1):
        f = g.__frames[i]
        if f.events["ADDON_LOADED"] and f.onevent:
            f.onevent(f, "ADDON_LOADED", ADDON_NAME)

    def out():
        return [str(g.__out[i]) for i in range(1, len(g.__out) + 1)]

    check("no chat lines printed at load", out() == [], str(out()))
    lua.execute(K_READ)
    R = g.R
    check("Quest.Exists(84197) and (82081)", R["e1"] is True and R["e2"] is True)
    check("GetAllIds(true)[84197]", R["all"] is True)
    check("Get name", R["name"] == "Saving the Best for Last", str(R["name"]))
    check("Get requiredClasses == 128", R["rc"] == 128, str(R["rc"]))
    check("objectives[3][1][1] == 16686", R["ob"] == 16686, str(R["ob"]))
    check("startedBy[1][1] == 230319", R["sb"] == 230319, str(R["sb"]))
    check("item-started quest startedBy[3][1] == 221346", R["sb2"] == 221346, str(R["sb2"]))
    check("84195 requiredClasses == 1024", R["rc2"] == 1024, str(R["rc2"]))
    check("84195 base name kept", R["name2"] == "Saving the Best for Last", str(R["name2"]))
    check("84195 base objectives still readable", R["ob2"] == 16706, str(R["ob2"]))
    check("9001 requiredClasses unchanged (128)", R["rc3"] == 128, str(R["rc3"]))
    before = len(out())
    g.SlashCmdList.QUESTIEFOREVERFIXES("")
    txt = "\n".join(out()[before:])
    check("/qff shows Quest 3", "Quest 3" in txt, txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--local-data", default=str(LOCAL_FIXTURE))
    a = ap.parse_args()
    default = ADDON / "Data.lua"
    data = Path(a.data) if a.data else (default if default.exists() else FIXTURE)
    print(f"data: {data}")
    fns = [scenario_a, scenario_b, scenario_c, scenario_d, scenario_e, scenario_f]
    if Path(data) == default:
        fns += [scenario_g, scenario_h, scenario_i]
    else:
        print("(fixture data: scenarios g/h/i skipped)")
    for fn in fns:
        try:
            fn(data)
        except Exception as e:
            check(f"{fn.__name__} raised", False, repr(e))
    try:
        scenario_k(data)
    except Exception as e:
        check("scenario_k raised", False, repr(e))
    try:
        scenario_j(data, a.local_data)
    except Exception as e:
        check("scenario_j raised", False, repr(e))
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()

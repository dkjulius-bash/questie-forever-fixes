"""Static verification harness for QuestieForeverFixes (Data.lua + Core.lua) under Lua 5.1 via lupa."""
import argparse
import re
import sys
from pathlib import Path

from lupa import lua51

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "addon" / "QuestieForeverFixes"
FIXTURE = ROOT / "tools" / "fixtures" / "Data.lua"
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
    def __init__(self, data_path, **opts):
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


SRC_RE = re.compile(r"-- src: (trace\+wh-tooltip|trace|wh-tooltip)\s*$")
ROW_RE = re.compile(r"^\s+\[\d+\] = \{")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def scenario_g(data):
    print("[g] row source comments")
    lines = [l for l in Path(data).read_text(encoding="utf-8").splitlines() if ROW_RE.match(l)]
    bad = [l[:80] for l in lines if not SRC_RE.search(l)]
    check("every row line carries a -- src comment (%d rows)" % len(lines), lines and not bad, str(bad[:3]))


def scenario_h(data):
    print("[h] spawns shape")
    s = Scenario(data)
    d = s.ns.data()
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
    check("all spawns values well-formed (%d checked)" % n, not bad, str(bad[:5]))


def scenario_i(data):
    print("[i] meta.sources vs comments")
    text = Path(data).read_text(encoding="utf-8")
    cnt = {"trace": 0, "wh-tooltip": 0, "trace+wh-tooltip": 0}
    for l in text.splitlines():
        if ROW_RE.match(l):
            m = SRC_RE.search(l)
            if m: cnt[m.group(1)] += 1
    s = Scenario(data)
    src = s.ns.meta.sources
    check("meta.sources present", src is not None)
    if src is not None:
        got = {"trace": src.trace, "wh-tooltip": src.wh, "trace+wh-tooltip": src.both}
        check("meta.sources == comment counts", got == cnt, "%s vs %s" % (got, cnt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
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
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()

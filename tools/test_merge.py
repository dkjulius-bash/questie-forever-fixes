"""Headless tests for the local-fixes merge in Core.lua (Lua 5.1 via lupa)."""
import sys
from pathlib import Path

from lupa import lua51

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_lua as vl  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" -- {detail}" if detail and not cond else ""))


STUB = r'''
SlashCmdList = {}
__lines = {}
DEFAULT_CHAT_FRAME = { AddMessage = function(_, s) __lines[#__lines + 1] = s end }
function CreateFrame()
    local f = {}
    function f:RegisterEvent() end
    function f:UnregisterEvent() end
    function f:SetScript() end
    return f
end
function ser(v)
    if type(v) ~= "table" then return type(v) == "string" and string.format("%q", v) or tostring(v) end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b)
        if type(a) == type(b) then return a < b end
        return type(a) == "number"
    end)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = "[" .. ser(k) .. "]=" .. ser(v[k]) end
    return "{" .. table.concat(parts, ",") .. "}"
end
'''

lua = lua51.LuaRuntime(unpack_returned_tuples=True)
lua.execute(STUB)
ns = lua.table()
src = (vl.ADDON / "Core.lua").read_text(encoding="utf-8")
fn = lua.eval("loadstring")(src, "@Core.lua")
fn = fn[0] if isinstance(fn, tuple) else fn
fn("QuestieForeverFixes", ns)
merge_fn = ns.mergeData
ser = lua.globals().ser


def L(code):
    return lua.eval(code)


def merge(shipped, loc):
    """Return (serialized merged, stats) for Lua table literals; also checks inputs via serialization."""
    s, l = L(shipped), L(loc)
    m, st = merge_fn(s, l)
    return m, st


def same(tbl, expected_lua):
    return str(ser(tbl)) == str(ser(L(expected_lua)))


# 1
m, st = merge("{Npc={}}", "{Npc={[7]={name='x'}}}")
check("1 local-only entity present, new=1", same(m.Npc, "{[7]={name='x'}}") and st.Npc.new == 1 and st.Npc.total == 1)
# 2
m, st = merge("{Npc={[1]={spawns={[440]={{10,10},{20,20}}}}}}",
              "{Npc={[1]={spawns={[440]={{10,10},{10.3,10.2},{30,30}}}}}}")
check("2 overlapping spawns deduped", same(m.Npc[1].spawns, "{[440]={{10,10},{20,20},{30,30}}}") and st.Npc.merged == 1)
# 3
m, _ = merge("{Npc={[1]={spawns={[440]={{10,10}}}}}}", "{Npc={[1]={spawns={[490]={{1,1}}}}}}")
check("3 new zone added, 440 unchanged", same(m.Npc[1].spawns, "{[440]={{10,10}},[490]={{1,1}}}"))
# 4
m, _ = merge("{Npc={[1]={spawns={[440]={{1,1},{2,2},{3,3}}}}}}", "{Npc={[1]={spawns={[440]={{2,2}}}}}}")
check("4 local never deletes shipped points", same(m.Npc[1].spawns, "{[440]={{1,1},{2,2},{3,3}}}"))
# 5
m, _ = merge("{Item={[1]={npcDrops_add={1,2}}}}", "{Item={[1]={npcDrops_add={2,3},objectDrops_add={9}}}}")
check("5 drop list union + local-only field taken",
      same(m.Item[1].npcDrops_add, "{1,2,3}") and same(m.Item[1].objectDrops_add, "{9}"))
# 6
m, _ = merge("{Quest={[1]={startedBy_add={[1]={5}}}}}", "{Quest={[1]={startedBy_add={[1]={5,6},[2]={7}}}}}")
check("6 grouped _add union", same(m.Quest[1].startedBy_add, "{[1]={5,6},[2]={7}}"))
# 7
m, _ = merge("{Npc={[1]={zoneID=440}}}", "{Npc={[1]={zoneID=490,name='n'}}}")
check("7 scalar: shipped wins, local-only taken", m.Npc[1].zoneID == 440 and m.Npc[1].name == "n")
# 8
m, _ = merge("{Quest={[1]={objectives={[1]={{1}}}},[2]={}}}",
             "{Quest={[1]={objectives={[1]={{2}}}},[2]={objectives={[1]={{3}}}}}}")
check("8 objectives: shipped wins, local fills gap",
      same(m.Quest[1].objectives, "{[1]={{1}}}") and same(m.Quest[2].objectives, "{[1]={{3}}}"))
# 9
m, _ = merge("{Npc={[1]={spawns={[440]={{-1,-1}}}}}}", "{Npc={[1]={spawns={[440]={{-1,-1}}}}}}")
check("9 sentinel appears once", same(m.Npc[1].spawns, "{[440]={{-1,-1}}}"))
# 10
s = L("{Npc={[1]={spawns={[440]={{1,1}}},npcDrops_add={1}}}}")
l = L("{Npc={[1]={spawns={[440]={{50,50}}},npcDrops_add={2}}}}")
s0, l0 = str(ser(s)), str(ser(l))
merge_fn(s, l)
check("10 inputs not mutated", str(ser(s)) == s0 and str(ser(l)) == l0 and len(s.Npc[1].spawns[440]) == 1
      and len(s.Npc[1].npcDrops_add) == 1)
# 11
shipped = "{Quest={[1]={name='a'}},Npc={[2]={name='b'}},Object={},Item={[3]={name='c'}}}"
ok = True
for loc in ("{}", "{Npc={}}", "{Quest={}}"):
    try:
        m, st = merge(shipped, loc)
        ok = ok and all(same(m[k], f"({shipped}).{k}") for k in ("Quest", "Npc", "Object", "Item"))
    except Exception as e:
        ok = False
        print("   ", e)
check("11 empty / partial local -> merged == shipped", ok)


# End-to-end
def txt(sc, msg=""):
    return "\n".join(sc.slash(msg))


data = vl.ADDON / "Data.lua"
local_fix = vl.LOCAL_FIXTURE

# 12
s = vl.Scenario(data)
s.fire()
silent12 = s.out() == []
check("12 absent local: applied == shipped counts, 'local none', silent",
      s.applied() == {k: v for k, v in s.data_counts().items() if v > 0} and silent12 and "local none" in txt(s),
      str(s.out()))

# 13
s = vl.Scenario(data, local_data=local_fix)
s.fire()
silent = s.out() == []
sh_ids, lo_ids = vl.lua_ids(s.ns.data()), None
lua2 = lua51.LuaRuntime()
lua2.execute(local_fix.read_text(encoding="utf-8"))
ld = lua2.globals().QuestieForeverFixes_LocalData.data()
lo_ids = vl.lua_ids(ld)
expect = {k: len(sh_ids[k] | lo_ids[k]) for k, _ in vl.KINDS if sh_ids[k] | lo_ids[k]}
t = txt(s)
g = s.lua.globals()
spawns_key = g.LibQuestieDB.Enum.npcKeys.spawns
row = g.__registered["Npc"][4196]
shipped_pts = len(s.ns.data().Npc[4196].spawns[440])
check("13a fixture local: silent load, applied == union", silent and s.applied() == expect, f"{s.out()} {s.applied()} {expect}")
check("13b /qff text", "local " in t and "Npc 3 (1 new)" in t and "built " in t, t)
check("13c global cleared", g.QuestieForeverFixes_LocalData is None)
check("13d Npc 4196 zone 440 has shipped+1 points", len(row[spawns_key][440]) == shipped_pts + 1,
      f"{len(row[spawns_key][440])} vs {shipped_pts}+1")

# 14
broken = "QuestieForeverFixes_LocalData = { meta = {}, data = function() error('boom', 0) end }"
s = vl.Scenario(data, local_data=broken)
s.fire()
out = s.out()
check("14 broken local: shipped applied, one line, /qff local error",
      s.applied() == {k: v for k, v in s.data_counts().items() if v > 0}
      and len(out) == 1 and "local fixes ignored" in out[0] and "local error" in txt(s), str(out))

# 15
stale = ("QuestieForeverFixes_LocalData = { meta = { generatedAt = 'x', questieDBVersion = '1.0.0', sessions = 1 }, "
         "data = function() return { Quest = {}, Npc = {}, Object = {}, Item = {} } end }")
s = vl.Scenario(data, local_data=stale)
s.fire()
check("15 stale QuestieDB version flags rebuild", "rebuild" in txt(s))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)

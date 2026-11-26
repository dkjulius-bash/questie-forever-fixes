"""Prototype: a Dynamic Correction adds a brand-new quest id, using QuestieDB's real Lua under lupa (lua51)."""
import sys
from pathlib import Path

from lupa import lua51

SRC = Path(r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB\src")
FILES = ["meta/questMeta.lua", "meta/normalize.lua", "corrections/tablePatch.lua",
         "corrections/registry.lua", "read/shared.lua"]

lua = lua51.LuaRuntime(unpack_returned_tuples=False)
loader = lua.eval("""
function(name, src, lib)
  local fn = assert(loadstring(src, "@" .. name))
  return fn("QuestieDB", lib)
end
""")
lib = lua.eval("""{
  config = { entityTypes = {{name="Quest"}}, expansionOrder = { Classic = 1, Forever = 1 } },
  flavor = { expansion = "Forever", rules = "Classic", name = "Forever" },
}""")
for f in FILES:
    loader(f, (SRC / f).read_text(encoding="utf-8"), lib)

lua.globals().LIB = lib
lua.execute("""
local L = LIB
local base = {
  [2] = { [1] = "Base Two", [5] = 10 },
  [7] = { [1] = "Base Seven", [5] = 1 },
}
local list, map = {2, 7}, {[2] = true, [7] = true}
local backend = {
  hasScalarRows = false,
  getAllIds = function() return list, map end,
  readField = function(id, idx) local r = base[id]; return r and r[idx] end,
}
L.Quest = L.shared.CreateEntity(L.Meta.Quest, backend)
""")

lua.execute(r"""
R = {}
local function check(name, cond) R[#R + 1] = { name, cond and true or false } end
local L = LIB
local Q, C = L.Quest, L.Corrections

check("1 Exists(99001)==false before", Q.Exists(99001) == false)
local before = Q.GetAllIds(true)
check("1 GetAllIds(true)[99001]==nil before", before[99001] == nil)

local rows = { [99001] = { [1]="Prototype Quest", [2]={{230319}}, [3]={{230319}}, [4]=58, [5]=60,
  [6]=4294967373, [8]={"Do the thing."}, [10]={nil,nil,{{16686},{16688}}}, [17]=1537 },
  [7] = { [5] = 3 } }
C.RegisterRuntimeCorrection("QuestieForeverFixes", "Quest", "traces", function() return rows end, 10)
C.ApplyRegisteredCorrections("QuestieForeverFixes")

check("3 Exists(99001) true", Q.Exists(99001) == true)
check("3 GetAllIds(true)[99001] true", Q.GetAllIds(true)[99001] == true)
local list = Q.GetAllIds()
local found, sorted = false, true
for i = 1, #list do
  if list[i] == 99001 then found = true end
  if i > 1 and list[i-1] >= list[i] then sorted = false end
end
check("3 list contains 99001 and sorted", found and sorted and #list == 3)
check("3 name", Q.Get(99001, "name") == "Prototype Quest")
local sb = Q.Get(99001, "startedBy")
check("3 startedBy[1][1]==230319", sb and sb[1] and sb[1][1] == 230319)
check("3 requiredRaces==4294967373", Q.Get(99001, "requiredRaces") == 4294967373)
local ob = Q.Get(99001, "objectives")
check("3 objectives[3][1][1]==16686", ob and ob[3] and ob[3][1] and ob[3][1][1] == 16686)
check("3 zoneOrSort==1537", Q.Get(99001, "zoneOrSort") == 1537)
local ga = Q.GetAll(99001, {"name", "questLevel"})
check("3 GetAll name,questLevel", ga and ga[1] == "Prototype Quest" and ga[2] == 60)
check("4 base quest 7 exists", Q.Exists(7) == true)
check("4 quest 7 questLevel==3 (override)", Q.Get(7, "questLevel") == 3)
check("4 quest 7 name kept", Q.Get(7, "name") == "Base Seven")
check("5 stale map before[99001]==nil", before[99001] == nil)
check("5 fresh map [99001]==true", Q.GetAllIds(true)[99001] == true)

C.UnregisterCorrection("QuestieForeverFixes", "Quest", "traces")
C.ApplyRegisteredCorrections("QuestieForeverFixes")
check("6 Exists(99001) false after withdraw", Q.Exists(99001) == false)
check("6 quest 7 reverted to 1", Q.Get(7, "questLevel") == 1)
""")

fails = 0
R = lua.globals().R
for i in range(1, len(R) + 1):
    name, ok = R[i][1], R[i][2]
    print(("PASS " if ok else "FAIL ") + name)
    fails += 0 if ok else 1
sys.exit(1 if fails else 0)

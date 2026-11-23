"""Load extractor output modules (foreverXTraces.lua) with lupa into Python data."""
from lupa.lua51 import LuaRuntime

_STUB = """
local K = setmetatable({}, {__index = function(t, k) return k end})
local created
QuestieLoader = {
  CreateModule = function(self, n) created = {} ; return created end,
  ImportModule = function(self, n)
    return {questKeys = K, npcKeys = K, objectKeys = K, itemKeys = K}
  end,
}
function __get_created() return created end
"""


def _conv(v, lua):
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v == int(v) and abs(v) < 2 ** 53:
            return int(v)
        return v
    # lua table
    d = {}
    for k, x in v.items():
        if isinstance(k, float) and k == int(k):
            k = int(k)
        d[k] = _conv(x, lua)
    n = len(d)
    if n and all(isinstance(k, int) and not isinstance(k, bool) for k in d) and set(d) == set(range(1, n + 1)):
        return [d[i] for i in range(1, n + 1)]
    return d


def load_module(path):
    """Returns {entityId:int -> {fieldName:str -> value}}. Contiguous 1..n Lua tables become lists,
    tables with holes/string keys become dicts."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(_STUB)
    with open(path, encoding="utf8") as f:
        src = f.read()
    lua.execute(src)
    mod = lua.eval("__get_created()")
    data = mod.Load(mod)
    out = {}
    for k, row in data.items():
        out[int(k)] = _conv(row, lua)
    return out

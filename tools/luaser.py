"""Deterministic Lua 5.1 literal serializer."""
import math

_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\0": "\\0"}


def lua_string(s):
    out = []
    for ch in s:
        if ch in _ESC:
            out.append(_ESC[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append("\\%03d" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def lua_number(x):
    if isinstance(x, bool):
        raise TypeError("bool is not a number")
    if isinstance(x, int):
        return str(x)
    if math.isnan(x) or math.isinf(x):
        raise ValueError("nan/inf not serializable")
    r = round(x, 4)
    if r == int(r) and abs(r) < 1e15:
        return str(int(r))
    return repr(r)


def _is_int(k):
    return isinstance(k, int) and not isinstance(k, bool)


def _norm(v):
    """Lists containing None -> dict form."""
    if isinstance(v, (list, tuple)):
        if any(x is None for x in v):
            return {i + 1: x for i, x in enumerate(v) if x is not None}
        return list(v)
    return v


def dumps(v, indent=None, _level=0):
    """indent=None -> compact single line; indent=int -> pretty at top levels."""
    v = _norm(v)
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return lua_number(v)
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, list):
        return "{" + ",".join(dumps(x, None) for x in v) + "}"
    if isinstance(v, dict):
        keys = list(v.keys())
        ikeys = sorted(k for k in keys if _is_int(k))
        skeys = sorted(k for k in keys if isinstance(k, str))
        if len(ikeys) + len(skeys) != len(keys):
            raise TypeError("unsupported key type")
        if not skeys and ikeys == list(range(1, len(ikeys) + 1)) and all(v[k] is not None for k in ikeys):
            return "{" + ",".join(dumps(v[k], None) for k in ikeys) + "}"
        parts = []
        for k in ikeys:
            if v[k] is None: continue
            parts.append("[%d]=%s" % (k, dumps(v[k], None)))
        for k in skeys:
            if v[k] is None: continue
            parts.append("[%s]=%s" % (lua_string(k), dumps(v[k], None)))
        return "{" + ",".join(parts) + "}"
    raise TypeError("unsupported type %s" % type(v))

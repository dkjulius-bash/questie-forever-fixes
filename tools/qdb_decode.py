"""Reader for the baked QuestieDB (CBOR values base64'd into TOC metadata lines)."""
import base64
import os
import re
import struct
from collections import defaultdict

KINDS = ("Quest", "Npc", "Object", "Item")


def cbor(b, i=0):
    ib = b[i]
    mt = ib >> 5
    ai = ib & 31
    i += 1
    if mt == 7:
        if ai == 20: return False, i
        if ai == 21: return True, i
        if ai in (22, 23): return None, i
        if ai == 25: return struct.unpack('>e', b[i:i + 2])[0], i + 2
        if ai == 26: return struct.unpack('>f', b[i:i + 4])[0], i + 4
        if ai == 27: return struct.unpack('>d', b[i:i + 8])[0], i + 8
        if ai == 31: return 'BREAK', i
        return ai, i
    if ai < 24: n = ai
    elif ai == 24: n = b[i]; i += 1
    elif ai == 25: n = int.from_bytes(b[i:i + 2], 'big'); i += 2
    elif ai == 26: n = int.from_bytes(b[i:i + 4], 'big'); i += 4
    elif ai == 27: n = int.from_bytes(b[i:i + 8], 'big'); i += 8
    elif ai == 31: n = None
    if mt == 0: return n, i
    if mt == 1: return -1 - n, i
    if mt in (2, 3):
        return b[i:i + n].decode('utf8', 'replace'), i + n
    if mt == 4:
        r = []
        if n is None:
            while True:
                v, i = cbor(b, i)
                if v == 'BREAK': break
                r.append(v)
        else:
            for _ in range(n):
                v, i = cbor(b, i)
                r.append(v)
        return r, i
    if mt == 5:
        r = {}
        cnt = 0
        while n is None or cnt < n:
            k, i = cbor(b, i)
            if k == 'BREAK': break
            v, i = cbor(b, i)
            r[k] = v
            cnt += 1
        return r, i
    if mt == 6:
        return cbor(b, i)


def b64(s):
    return base64.b64decode(s + '=' * (-len(s) % 4))


def _dec(s):
    return cbor(b64(s))[0]


def _isint(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _items(x):
    if x is None or x is False: return []
    if isinstance(x, list): return x
    if isinstance(x, dict):
        return [x[k] for k in sorted(x, key=lambda z: (isinstance(z, str), z))]
    return [x]


def _collect_ints(x, out):
    if _isint(x):
        out.append(x)
    elif isinstance(x, (list, dict)):
        for y in _items(x):
            _collect_ints(y, out)


def _toint(k):
    if _isint(k): return k
    if isinstance(k, str) and k.lstrip('-').isdigit(): return int(k)
    return None


def groups(v):
    """Positional group table (list or dict, int/str keys) -> {groupIdx: [ints]}."""
    out = {}
    if isinstance(v, list):
        pairs = [(i + 1, y) for i, y in enumerate(v)]
    elif isinstance(v, dict):
        pairs = []
        for k, y in v.items():
            ki = _toint(k)
            if ki is not None: pairs.append((ki, y))
    else:
        return out
    for k, y in pairs:
        if y is None: continue
        lst = []
        _collect_ints(y, lst)
        if lst: out[k] = lst
    return out


def id_list(v):
    out = []
    _collect_ints(v, out)
    return out


def _is_pt(p):
    return isinstance(p, (list, tuple)) and len(p) >= 2 and all(
        isinstance(c, (int, float)) and not isinstance(c, bool) for c in p[:2])


def spawn_points(v):
    """spawns table -> {zone:int: [(x,y,rest...)]} (raw tuples, incl. (-1,-1) sentinels)."""
    out = {}
    if isinstance(v, list):
        pairs = [(i + 1, y) for i, y in enumerate(v)]
    elif isinstance(v, dict):
        pairs = [(_toint(k), y) for k, y in v.items()]
    else:
        return out
    for z, pts in pairs:
        if z is None or pts is None: continue
        res = []
        if _is_pt(pts):
            pts = [pts]
        elif isinstance(pts, dict):
            pts = _items(pts)
        if isinstance(pts, list):
            for p in pts:
                if isinstance(p, dict): p = _items(p)
                if _is_pt(p): res.append(tuple(p))
        out[z] = res
    return out


def is_sentinel(p):
    return p[0] == -1 and p[1] == -1


class InstalledDB:
    def __init__(self, addon_dir):
        self.addon_dir = addon_dir
        toc = os.path.join(addon_dir, "QuestieDB_Forever.toc")
        self.raw = {}
        self.version = None
        with open(toc, encoding='utf8') as f:
            for line in f:
                line = line.rstrip('\r\n')
                if line.startswith('## Version:'):
                    self.version = line.split(':', 1)[1].strip()
                if not line.startswith('## X-'): continue
                k, _, v = line[5:].partition(': ')
                self.raw[k.strip()] = v.strip()
        self._ids = defaultdict(set)
        for k in self.raw:
            m = re.fullmatch(r'(Quest|Npc|Object|Item)-(\d+)-S', k)
            if m: self._ids[m.group(1)].add(int(m.group(2)))
        self.fields = {}
        self.ftypes = {}
        self._tidx = {}
        for kind in KINDS:
            self._load_meta(kind)
        self._cache = {}

    def _load_meta(self, kind):
        path = os.path.join(self.addon_dir, "src", "meta", kind.lower() + "Meta.lua")
        names = None
        types = None
        with open(path, encoding='utf8') as f:
            for line in f:
                if not line.startswith("[1]="): continue
                pairs = re.findall(r"\[(\d+)\]='([^']*)'", line)
                if names is None:
                    names = {int(a): b for a, b in pairs}
                elif types is None and all(b in ('string', 'number', 'table') for _, b in pairs):
                    types = {int(a): b for a, b in pairs}
        if not names or not types:
            raise RuntimeError("could not parse meta for " + kind)
        self.fields[kind] = names
        self._tidx[kind] = types
        self.ftypes[kind] = {names[i]: t for i, t in types.items() if i in names}

    def _getval(self, k):
        v = self.raw.get(k)
        if v is None: return None
        m = re.fullmatch(r'~(\d+)~', v)
        if m:
            parts = [self.raw[f"{k}-{j}"] for j in range(1, int(m.group(1)) + 1)]
            if any('=' in p[:-2] for p in parts):
                return cbor(b''.join(b64(p) for p in parts))[0]
            return _dec(''.join(parts))
        return _dec(v)

    def ids(self, kind):
        return self._ids[kind]

    def get(self, kind, eid):
        key = (kind, eid)
        if key in self._cache: return self._cache[key]
        if eid not in self._ids[kind]:
            self._cache[key] = None
            return None
        s = self._getval(f"{kind}-{eid}-S")
        s = s if isinstance(s, dict) else {}
        out = {}
        for idx, name in self.fields[kind].items():
            v = s.get(idx)
            if self._tidx[kind].get(idx) == 'table' or v is None:
                tv = self._getval(f"{kind}-{eid}-{idx}")
                if tv is not None: v = tv
            if v is not None: out[name] = v
        self._cache[key] = out
        return out

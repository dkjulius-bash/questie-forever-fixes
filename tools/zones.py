"""Zone sets, AreaID -> uiMap lookup and the Era -> Forever coordinate transforms (parsed from the installed QuestieDB)."""
import os
import re
from collections import OrderedDict

ZONES = OrderedDict([
    ("Riverglades", 16591),
    ("Un'Goro Crater", 490),
    ("Eastern Plaguelands", 139),
    ("Western Plaguelands", 28),
    ("Searing Gorge", 51),
    ("Burning Steppes", 46),
])
RIVERGLADES_EXTRA = [16591, 16685] + list(range(16723, 16732))

_A2U = {}
_TRANSFORMS = {}


def _strip_comments(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def load_area_uimap(questiedb_dir):
    """{AreaID: uiMapID}; override block wins over the base block. Also sets the module default."""
    path = os.path.join(questiedb_dir, "support", "Forever", "Zones", "areaIdToUiMapId.lua")
    with open(path, encoding="utf8") as f:
        text = f.read()
    out = {}
    for name in ("areaIdToUiMapId", "areaIdToUiMapIdOverride"):  # base first, override overwrites
        m = re.search(r"ZoneDB\.private\.%s\s*=\s*\[\[(.*?)\]\]" % name, text, re.S)
        if not m:
            raise RuntimeError("block %s not found in %s" % (name, path))
        for a, u in re.findall(r"\[(\d+)\]\s*=\s*(\d+)", _strip_comments(m.group(1))):
            out[int(a)] = int(u)
    _A2U.clear()
    _A2U.update(out)
    return out


def load_transforms(questiedb_dir):
    """{AreaID: (scaleX, offsetX, scaleY, offsetY)} from eraToForever.lua. Also sets the module default."""
    path = os.path.join(questiedb_dir, "src", "support", "eraToForever.lua")
    with open(path, encoding="utf8") as f:
        text = f.read()
    m = re.search(r"local transforms = \{(.*?)\n\}", text, re.S)
    if not m:
        raise RuntimeError("transforms table not found in " + path)
    num = r"(-?[0-9.]+(?:[eE][-+]?\d+)?)"
    out = {}
    for a, *v in re.findall(r"\[(\d+)\]\s*=\s*\{\s*%s\s*,\s*%s\s*,\s*%s\s*,\s*%s\s*\}" % ((num,) * 4), _strip_comments(m.group(1))):
        out[int(a)] = tuple(float(x) for x in v)
    if not out:
        raise RuntimeError("no transforms parsed")
    _TRANSFORMS.clear()
    _TRANSFORMS.update(out)
    return out


def zone_sets(a2u=None, zones=None):
    """name -> set(AreaIDs mapping to the same uiMap as the zone's main AreaID); Riverglades adds its explicit list."""
    a2u = _A2U if a2u is None else a2u
    zones = ZONES if zones is None else zones
    out = OrderedDict()
    for name, main in zones.items():
        u = a2u.get(main)
        s = {main}
        if u:
            s |= {a for a, v in a2u.items() if v == u}
        if name == "Riverglades":
            s |= set(RIVERGLADES_EXTRA)
        out[name] = s
    return out


def uimap_of(area, a2u=None):
    a2u = _A2U if a2u is None else a2u
    return a2u.get(area)


def uimap_group(uimap, a2u=None):
    """All AreaIDs mapping to a uiMap."""
    a2u = _A2U if a2u is None else a2u
    return {a for a, v in a2u.items() if v == uimap}


def era_to_forever(area, x, y, transforms=None):
    t = (_TRANSFORMS if transforms is None else transforms).get(area)
    if not t:
        return x, y
    return x * t[0] + t[1], y * t[2] + t[3]


def forever_to_era(area, x, y, transforms=None):
    t = (_TRANSFORMS if transforms is None else transforms).get(area)
    if not t:
        return x, y
    return (x - t[1]) / t[0], (y - t[3]) / t[2]

"""InstalledDB + the shipped Data.lua rows, as QuestieDB would see them after the shipped corrections."""
import patch_policy
from qdb_decode import groups, id_list


class OverlayDB:
    def __init__(self, db, shipped):
        self._db = db
        self._shipped = shipped
        self._cache = {}

    def __getattr__(self, name):
        return getattr(self._db, name)

    def ids(self, kind):
        return set(self._db.ids(kind)) | set(self._shipped.get(kind, {}))

    def get(self, kind, eid):
        srow = self._shipped.get(kind, {}).get(eid)
        if srow is None:
            return self._db.get(kind, eid)
        key = (kind, eid)
        if key in self._cache:
            return self._cache[key]
        base = dict(self._db.get(kind, eid) or {})
        for f, v in srow.items():
            if f.endswith("_add"):
                b = f[:-4]
                if (kind, f) in patch_policy.GROUP_ADD:
                    g = {k: list(x) for k, x in groups(base.get(b)).items()}
                    for gk, ids in groups(v).items():
                        cur = g.setdefault(gk, [])
                        cur.extend(i for i in ids if i not in cur)
                    base[b] = g
                else:
                    cur = id_list(base.get(b))
                    cur.extend(i for i in id_list(v) if i not in cur)
                    base[b] = cur
            elif f.endswith("_remove"):
                continue
            else:
                base[f] = v
        self._cache[key] = base
        return base

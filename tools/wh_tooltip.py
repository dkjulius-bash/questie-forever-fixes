"""Wowhead tooltip API client with an on-disk cache (nether.wowhead.com/tooltip, dataEnv=16)."""
import datetime
import json
import math
import os
import time
import urllib.request

import zones

SLEEP = 0.34
ERROR_RETRY_DAYS = 1.0
STALE_ERA_DIST = 1.0


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _age_days(d):
    ts = d.get("fetchedAt") if isinstance(d, dict) else None
    if not ts:
        return 0.0  # old cache files without fetchedAt count as fresh
    try:
        t = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return 0.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return (_now() - t).total_seconds() / 86400.0


class WH:
    def __init__(self, cache_dir, offline=False, refresh_days=30):
        self.cache_dir = cache_dir
        self.offline = offline
        self.refresh_days = refresh_days
        self.fetched = 0
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, kind, eid):
        return os.path.join(self.cache_dir, "%s_%d.json" % (kind, eid))

    def _fetch(self, kind, eid):
        url = "https://nether.wowhead.com/tooltip/%s/%d?dataEnv=16&locale=0" % (kind, eid)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, dict):
                d = {"error": "unexpected payload"}
        except Exception as e:  # noqa: BLE001
            d = {"error": str(e)}
        finally:
            time.sleep(SLEEP)
        self.fetched += 1
        d["fetchedAt"] = _now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return d

    def get(self, kind, eid):
        kind = kind.lower()
        path = self._path(kind, eid)
        cached = None
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    cached = json.load(f)
            except (OSError, ValueError):
                cached = None
        if cached is not None:
            limit = ERROR_RETRY_DAYS if "error" in cached else self.refresh_days
            if self.offline or _age_days(cached) <= limit:
                return cached
        if self.offline:
            return None
        d = self._fetch(kind, eid)
        if "error" in d and cached is not None and "error" not in cached:
            return cached  # keep the older good data rather than overwrite it with a transient error
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return d


def points(d, transforms=None):
    """-> (zone, [(x, y)...] deduped over all floors, stale_era_dropped_count)."""
    m = (d or {}).get("map") or {}
    zone = m.get("zone")
    seen = []
    for _fl, pts in sorted((m.get("coords") or {}).items()):
        for p in pts or []:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                t = (float(p[0]), float(p[1]))
                if t not in seen:
                    seen.append(t)
    tr = zones._TRANSFORMS if transforms is None else transforms
    if zone not in tr:
        return zone, seen, 0
    keep = []
    dropped = 0
    for i, p in enumerate(seen):
        q = zones.era_to_forever(zone, p[0], p[1], tr)
        if any(j != i and math.dist(q, o) <= STALE_ERA_DIST for j, o in enumerate(seen)):
            dropped += 1
        else:
            keep.append(p)
    return zone, keep, dropped

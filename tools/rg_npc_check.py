"""Compare Questie spawns of Riverglades quest givers/finishers with Wowhead Forever tooltip coords."""
import sys, os, json, time, math, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from qdb_decode import InstalledDB, groups, spawn_points, is_sentinel
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'work', 'wh')
db = InstalledDB(r'C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB')
rg = [int(x) for x in open(os.path.join(ROOT, 'work', 'rg_ids.txt')).read().split(',')]
ALLY = (1 << 32) | 77

def wh(kind, eid):
    p = os.path.join(CACHE, f'{kind}_{eid}.json')
    if os.path.exists(p): return json.load(open(p, encoding='utf-8'))
    url = f'https://nether.wowhead.com/tooltip/{kind}/{eid}?dataEnv=16&locale=0'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try: d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e: d = {'error': str(e)}
    json.dump(d, open(p, 'w', encoding='utf-8')); time.sleep(0.4)
    return d

def whpts(d):
    m = d.get('map') or {}
    out = []
    for fl, pts in (m.get('coords') or {}).items(): out += [tuple(p) for p in pts]
    return m.get('zone'), out

rows = []
for q in rg:
    row = db.get('Quest', q)
    rr = row.get('requiredRaces') or 0
    if rr and not (rr & ALLY): continue
    for role, field in (('start', 'startedBy'), ('end', 'finishedBy')):
        g = groups(row.get(field))
        for kind, key in (('npc', 1), ('object', 2)):
            for eid in g.get(key, []):
                ent = db.get('Npc' if kind == 'npc' else 'Object', eid) or {}
                sp = spawn_points(ent.get('spawns'))
                d = wh(kind, eid); wz, wp = whpts(d)
                qp = [p for p in sp.get(wz, []) if not is_sentinel(p)] if wz else []
                dist = min((math.dist(a, b) for a in wp for b in qp), default=None)
                status = ('no-wh-coords' if not wp else 'questie-no-spawns' if not sp else
                          'zone-mismatch' if not qp else 'far' if dist > 3 else 'ok')
                rows.append(dict(q=q, qname=row.get('name'), role=role, kind=kind, id=eid, name=ent.get('name') or d.get('name'),
                                 status=status, dist=None if dist is None else round(dist, 2), whzone=wz, wh=wp[:3],
                                 qzones=sorted(sp.keys()), qpts={z: v[:3] for z, v in sp.items()}))
json.dump(rows, open(os.path.join(ROOT, 'work', 'rg_npc_check.json'), 'w'), indent=1, default=str)
from collections import Counter
print(Counter(r['status'] for r in rows))
for r in rows:
    if r['status'] != 'ok':
        print(r['status'], r['role'], r['q'], r['qname'], '|', r['kind'], r['id'], r['name'], 'dist', r['dist'], 'wh', r['whzone'], r['wh'][:1], 'qz', r['qzones'], str(list(r['qpts'].values())[:1])[:40])

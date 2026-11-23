"""Compare Riverglades quest prereqs / starters / objectives in installed QuestieDB with Wowhead quest-page data.
Input work/rg_wh.txt: one record per line: id|prev|se|obj   (prev = series predecessor or 0; se = Sn123/En456; obj = n123@16591:4;o55@16591:2)"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from qdb_decode import InstalledDB, groups, id_list
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = InstalledDB(r'C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB')

def ints(v):
    out = []
    def walk(x):
        if isinstance(x, bool) or x is None: return
        if isinstance(x, (int, float)): out.append(int(x)); return
        if isinstance(x, dict): [walk(v) for v in x.values()]
        elif isinstance(x, (list, tuple)): [walk(v) for v in x]
    walk(v); return out

def obj_entities(row):
    g = groups(row.get('objectives'))  # 1 creature 2 object 3 item 5 killcredit
    n = set(); o = set(); it = set()
    for t in g.get(1, []) if isinstance(g.get(1), list) else []: pass
    raw = row.get('objectives')
    # positional: [creatures, objects, items, rep, killcredit, spell]
    seq = raw if isinstance(raw, list) else [raw.get(k) if isinstance(raw, dict) else None for k in (1, 2, 3, 4, 5, 6)] if raw else []
    def firsts(lst):
        r = set()
        for e in lst or []:
            if isinstance(e, (list, tuple)) and e:
                h = e[0]
                if isinstance(h, (list, tuple)): r.update(int(x) for x in h if isinstance(x, (int, float)))
                elif isinstance(h, (int, float)): r.add(int(h))
            elif isinstance(e, dict) and e:
                h = e.get(1); 
                if isinstance(h, (int, float)): r.add(int(h))
        return r
    if seq:
        seq = list(seq) + [None] * 6
        n |= firsts(seq[0]); o |= firsts(seq[1]); it |= firsts(seq[2]); n |= firsts(seq[4])
    for i in list(it):  # item objective -> its sources
        irow = db.get('Item', i) or {}
        n |= set(ints(irow.get('npcDrops'))); o |= set(ints(irow.get('objectDrops')))
    return n, o, it

res = []
for line in open(os.path.join(ROOT, 'work', 'rg_wh.txt')):
    line = line.strip()
    if not line: continue
    qid, prev, se, obj = (line.split('|') + ['', '', ''])[:4]
    qid = int(qid); prev = int(prev or 0)
    row = db.get('Quest', qid) or {}
    pre = set(ints(row.get('preQuestSingle'))) | set(ints(row.get('preQuestGroup')))
    issues = []
    if prev and prev not in pre: issues.append(f'prereq-missing:{prev} (questie has {sorted(pre) or "none"})')
    if not prev and pre: issues.append(f'questie-extra-prereq:{sorted(pre)} (wowhead series has none)')
    sb = groups(row.get('startedBy')); fb = groups(row.get('finishedBy'))
    for tok in filter(None, se.split('/')):
        role, kind, eid = tok[0], tok[1], int(tok[2:])
        g = sb if role == 'S' else fb
        key = {'n': 1, 'o': 2, 'i': 3}[kind]
        if eid not in (g.get(key) or []): issues.append(f'{"starter" if role=="S" else "finisher"}-mismatch:{kind}{eid} (questie {dict(g)})')
    qn, qo, qi = obj_entities(row)
    whn = set(); who = set()
    for tok in filter(None, obj.split(';')):
        ent = tok.split('@')[0]
        if ent.startswith('n'): whn.add(int(ent[1:]))
        elif ent.startswith('o'): who.add(int(ent[1:]))
    miss_n = whn - qn; miss_o = who - qo
    if (whn or who) and not (qn or qo): issues.append(f'questie-no-objective-locations (wowhead: npcs {sorted(whn)} objs {sorted(who)})')
    elif miss_n or miss_o: issues.append(f'objective-entities-missing: npcs {sorted(miss_n)} objs {sorted(miss_o)}')
    res.append(dict(id=qid, name=row.get('name'), level=row.get('questLevel'), issues=issues))
json.dump(res, open(os.path.join(ROOT, 'work', 'rg_quest_check.json'), 'w'), indent=1)
from collections import Counter
c = Counter(i.split(':')[0].split(' ')[0] for r in res for i in r['issues'])
print('quests', len(res), 'with issues', sum(1 for r in res if r['issues']), dict(c))
for r in res:
    for i in r['issues']: print(r['id'], r['name'], '->', i)

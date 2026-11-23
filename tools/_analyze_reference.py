import base64, struct, json, csv, re, sys, os
from collections import Counter, defaultdict
TOC = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\QuestieDB\QuestieDB_Forever.toc"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis")


def cbor(b, i=0):
    ib = b[i]; mt = ib >> 5; ai = ib & 31; i += 1
    if mt == 7:
        if ai == 20: return False, i
        if ai == 21: return True, i
        if ai in (22, 23): return None, i
        if ai == 25: return struct.unpack('>e', b[i:i+2])[0], i+2
        if ai == 26: return struct.unpack('>f', b[i:i+4])[0], i+4
        if ai == 27: return struct.unpack('>d', b[i:i+8])[0], i+8
        if ai == 31: return 'BREAK', i
        return ai, i
    if ai < 24: n = ai
    elif ai == 24: n = b[i]; i += 1
    elif ai == 25: n = int.from_bytes(b[i:i+2], 'big'); i += 2
    elif ai == 26: n = int.from_bytes(b[i:i+4], 'big'); i += 4
    elif ai == 27: n = int.from_bytes(b[i:i+8], 'big'); i += 8
    elif ai == 31: n = None
    if mt == 0: return n, i
    if mt == 1: return -1-n, i
    if mt in (2, 3):
        s = b[i:i+n]
        return s.decode('utf8', 'replace'), i+n
    if mt == 4:
        r = []
        if n is None:
            while True:
                v, i = cbor(b, i)
                if v == 'BREAK': break
                r.append(v)
        else:
            for _ in range(n):
                v, i = cbor(b, i); r.append(v)
        return r, i
    if mt == 5:
        r = {}; cnt = 0
        while n is None or cnt < n:
            k, i = cbor(b, i)
            if k == 'BREAK': break
            v, i = cbor(b, i); r[k] = v; cnt += 1
        return r, i
    if mt == 6:
        return cbor(b, i)


def b64(s): return base64.b64decode(s + '=' * (-len(s) % 4))
def dec(s): return cbor(b64(s))[0]


raw = {}
with open(TOC, encoding='utf8') as f:
    for line in f:
        if not line.startswith('## X-'): continue
        k, _, v = line[5:].partition(': ')
        raw[k.strip()] = v.strip()


def getval(k):
    v = raw.get(k)
    if v is None: return None
    m = re.fullmatch(r'~(\d+)~', v)
    if m:
        parts = [raw[f"{k}-{j}"] for j in range(1, int(m.group(1)) + 1)]
        if any('=' in p[:-2] for p in parts):
            return cbor(b''.join(b64(p) for p in parts))[0]
        return dec(''.join(parts))
    return dec(v)


ids = defaultdict(set)
for k in raw:
    m = re.fullmatch(r'(Quest|Npc|Object|Item)-(\d+)-S', k)
    if m: ids[m.group(1)].add(int(m.group(2)))


def row(t, i):
    s = getval(f"{t}-{i}-S")
    return s if isinstance(s, dict) else {}


def field(t, i, fi, s):
    v = getval(f"{t}-{i}-{fi}")
    return v if v is not None else s.get(fi)


def items(x):
    if x is None or x is False: return []
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x[k] for k in sorted(x, key=lambda z: (isinstance(z, str), z))]
    return [x]


def sub(x, idx, name):
    if isinstance(x, dict):
        v = x.get(idx, x.get(name))
    elif isinstance(x, list):
        v = x[idx-1] if idx-1 < len(x) else None
    else:
        v = None
    return [y for y in items(v) if isinstance(y, int) and not isinstance(y, bool)]


def sub_list(x): return [y for y in items(x) if isinstance(y, int)]


cache = {}
def ent(t, i):
    k = (t, i)
    if k in cache: return cache[k]
    if i not in ids[t]:
        cache[k] = None; return None
    s = row(t, i)
    d = {'s': s, 'name': s.get(1) if isinstance(s.get(1), str) else None}
    d['spawns'] = field(t, i, 7 if t == 'Npc' else 4, s) if t in ('Npc', 'Object') else None
    if t == 'Item':
        d['npcDrops'] = sub_list(field(t, i, 2, s)); d['objDrops'] = sub_list(field(t, i, 3, s)); d['vendors'] = sub_list(field(t, i, 14, s))
    cache[k] = d
    return d


def spawn_class(sp):
    valid = inst = 0
    if isinstance(sp, list): sp = {i+1: v for i, v in enumerate(sp)}
    if not isinstance(sp, dict): return 0, 0
    for z, pts in sp.items():
        for p in items(pts):
            if isinstance(p, (list, dict)):
                pp = items(p)
                if len(pp) >= 2 and pp[0] == -1 and pp[1] == -1: inst += 1
                else: valid += 1
    return valid, inst


def ent_spawn(t, i):
    e = ent(t, i)
    if not e: return None
    return spawn_class(e['spawns'])


def zones_of(sp):
    if isinstance(sp, dict): return [str(z) for z in sp]
    return []


def starter_eval(sb):
    cs = sub(sb, 1, 'creatureStart'); os_ = sub(sb, 2, 'objectStart'); is_ = sub(sb, 3, 'itemStart')
    res = {'valid': 0, 'inst': 0, 'exist': 0, 'total': len(cs) + len(os_) + len(is_)}
    names = []; zones = []
    def acc(t, i):
        r = ent_spawn(t, i)
        if r is None: return
        res['exist'] += 1; res['valid'] += r[0]; res['inst'] += r[1]
    for n in cs:
        acc('Npc', n); e = ent('Npc', n)
        if e: names.append(e['name'] or ''); zones += zones_of(e['spawns'])
    for o in os_:
        acc('Object', o); e = ent('Object', o)
        if e: names.append(e['name'] or ''); zones += zones_of(e['spawns'])
    for it in is_:
        e = ent('Item', it)
        if not e: continue
        res['exist'] += 1; names.append(e['name'] or '')
        for n in e['npcDrops'] + e['vendors']:
            r = ent_spawn('Npc', n)
            if r: res['valid'] += r[0]; res['inst'] += r[1]
        for o in e['objDrops']:
            r = ent_spawn('Object', o)
            if r: res['valid'] += r[0]; res['inst'] += r[1]
    return res, names, sorted(set(zones))


def b36(n):
    d = '0123456789abcdefghijklmnopqrstuvwxyz'
    if n == 0: return '0'
    s = ''
    while n:
        n, r = divmod(n, 36); s = d[r] + s
    return s


def rle(l):
    l = sorted(l); out = []; prev = 0; i = 0
    while i < len(l):
        j = i
        while j+1 < len(l) and l[j+1] == l[j] + 1: j += 1
        run = j - i + 1
        out.append(b36(l[i] - prev) + ('.' + b36(run) if run > 1 else ''))
        prev = l[j]; i = j + 1
    return ','.join(out)


rows = []; hist = Counter(); reasons = Counter(); split = {'<90000': Counter(), '>=90000': Counter()}
examples = defaultdict(list); drawable = []; undraw = []; excluded = Counter()
for qid in sorted(ids['Quest']):
    s = row('Quest', qid)
    g = lambda fi: field('Quest', qid, fi, s)
    name = s.get(1) if isinstance(s.get(1), str) else g(1)
    sb = g(2); fb = g(3)
    rr = s.get(6) or 0
    if not isinstance(rr, int): rr = 0
    hist[rr] += 1
    if not (rr == 0 or rr & 77):
        excluded['unknown-race-only' if (rr >> 8) and not (rr & 255) else 'horde-only'] += 1
        continue
    classes = s.get(7) or 0
    res, names, zones = starter_eval(sb)
    if res['valid'] > 0: reason = ''
    elif res['total'] == 0: reason = 'no-startedBy'
    elif res['exist'] == 0: reason = 'starter-missing-entity'
    elif res['inst'] > 0: reason = 'instance-only'
    else: reason = 'starter-no-spawns'
    ok = reason == ''
    flags = []
    ce = sub(fb, 1, 'creatureEnd'); oe = sub(fb, 2, 'objectEnd')
    if not ce and not oe: flags.append('no-finishedBy')
    else:
        fv = sum((ent_spawn('Npc', n) or (0, 0))[0] for n in ce) + sum((ent_spawn('Object', n) or (0, 0))[0] for n in oe)
        if fv == 0: flags.append('finisher-no-spawns')
    if items(g(12)) or items(g(13)): flags.append('has-prereq')
    if g(18): flags.append('requiredSkill')
    if g(19): flags.append('requiredMinRep')
    if g(30): flags.append('requiredSpell')
    if classes: flags.append('class-restricted')
    rows.append([qid, name, s.get(5), s.get(4), rr, classes, s.get(17), json.dumps(sb, separators=(',', ':')), json.dumps(fb, separators=(',', ':')), ok, reason, ';'.join(flags), '|'.join(names), '|'.join(zones)])
    if ok: drawable.append(qid)
    else:
        undraw.append(qid); reasons[reason] += 1
        split['<90000' if qid < 90000 else '>=90000'][reason] += 1
        examples[reason].append((qid, name, s.get(5)))

with open(os.path.join(OUT, 'questie_quests.csv'), 'w', newline='', encoding='utf8') as f:
    w = csv.writer(f)
    w.writerow('id name questLevel requiredLevel requiredRaces requiredClasses zoneOrSort startedBy finishedBy drawable reason flags starterNames starterZones'.split())
    w.writerows(rows)
open(os.path.join(OUT, 'undrawable_rle.txt'), 'w').write(rle(undraw))
open(os.path.join(OUT, 'drawable_rle.txt'), 'w').write(rle(drawable))
L = [f"all quests: {len(ids['Quest'])}", f"excluded non-Alliance: {sum(excluded.values())} {dict(excluded)}",
     f"Alliance-eligible: {len(rows)}", f"drawable: {len(drawable)}", f"undrawable: {len(undraw)}",
     "per reason: " + str(dict(reasons))]
for k, v in split.items(): L.append(f"  id {k}: {dict(v)}")
L.append("requiredRaces histogram (value: count):")
for k, v in sorted(hist.items()): L.append(f"  {k}: {v}")
for r, e in examples.items():
    L.append(f"examples [{r}]:")
    for x in e[:25]: L.append(f"  {x[0]} | {x[1]} | L{x[2]}")
open(os.path.join(OUT, 'summary.txt'), 'w', encoding='utf8').write('\n'.join(L))
print(row('Quest', 5)); print(getval('Quest-5-2'))
e = ent('Npc', 288); print('npc288', e and e['name'], e and str(e['spawns'])[:80])
print(row('Quest', 6).get(1))
print('\n'.join(L[:60]))

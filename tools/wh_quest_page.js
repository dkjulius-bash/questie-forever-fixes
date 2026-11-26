// In-page extractor for Wowhead Forever quest pages (run via Claude-in-Chrome javascript_tool on a
// www.wowhead.com/forever tab). Defines window.qffParse(html, id) and window.qffRun(ids, gapMs).
// qffRun fetches strictly one page at a time with a gap, stores compact JSON per quest in
// localStorage 'qffm:<id>', and stops on any non-200 / verification page (window.qffState.stopped).
window.qffParse = function (html, id) {
  const out = { id: id };
  const strip = s => (s || '').replace(/https?:\/\/[^\s"\]]*/g, '').replace(/\?[^\]\s"']*/g, '');
  const idsIn = s => [...(s || '').matchAll(/\/(npc|object|item|quest|zone|faction|spell)=(\d+)/g)].map(m => m[1] + '=' + m[2]);
  const titleM = html.match(/<title>([^<]*)<\/title>/i);
  out.title = titleM ? titleM[1] : null;
  if (/human verification|verify you are human|captcha|just a moment/i.test(out.title || '')) { out.verify = true; return out; }
  // g_quests extend + Gatherer quest entry
  const ext = html.match(new RegExp('\\$\\.extend\\(g_quests\\[' + id + '\\],\\s*(\\{.*?\\})\\);\\s*\\n'));
  if (ext) { try { out.q = JSON.parse(ext[1]); } catch (e) { out.qErr = String(e); } }
  const gat = html.match(new RegExp('WH\\.Gatherer\\.addData\\(5,\\s*16,\\s*(\\{"' + id + '".*?\\})\\);'));
  if (gat) { try { out.g = JSON.parse(gat[1])[id]; } catch (e) { out.gErr = String(e); } }
  // infobox markup
  const ib = html.match(/printHtml\(("(?:[^"\\]|\\.)*"),\s*"infobox-contents-0"/);
  if (ib) {
    let mk = '';
    try { mk = JSON.parse(ib[1]); } catch (e) { out.ibErr = String(e); }
    out.infobox = mk.split('[li]').slice(1).map(x => {
      const raw = x.replace(/\[\/li\][\s\S]*/, '');
      return { t: strip(raw.replace(/\[[^\]]*\]/g, '')).replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200), ids: idsIn(raw) };
    });
  }
  // mapper
  const mp = html.match(/var g_mapperData = (\{.*?\});\s*\n/);
  if (mp) {
    try {
      const md = JSON.parse(mp[1]); const pins = [];
      for (const z in md) for (const fl in md[z]) for (const c of (md[z][fl].coords || [])) {
        const o = c[2] || {}; pins.push({ zone: +z, floor: +fl, x: c[0], y: c[1], type: o.type, who: (o.menu || []).map(m => [m[0], m[1], idsIn(m[2]).join(',')]) });
      }
      out.pins = pins.slice(0, 40);
    } catch (e) { out.mapErr = String(e); }
  }
  // DOM-ish parts
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const h1 = doc.querySelector('h1.heading-size-1');
  const text = h1 ? (h1.closest('.text') || h1.parentElement) : null;
  if (text) {
    // objective text = text nodes between h1 and the first table/h2
    let obj = ''; let n = h1.nextSibling;
    while (n && !(n.nodeType === 1 && /^(H2|TABLE|DIV)$/.test(n.tagName))) { obj += n.textContent || ''; n = n.nextSibling; }
    out.objText = obj.replace(/\s+/g, ' ').trim().slice(0, 400);
    // objectives table = the first icon-list table before any H2 (later ones are rewards)
    let objTable = null;
    for (let m = h1.nextSibling; m; m = m.nextSibling) {
      if (m.nodeType !== 1) continue;
      if (m.tagName === 'H2') break;
      if (m.tagName === 'TABLE' && m.classList.contains('icon-list')) { objTable = m; break; }
    }
    out.iconlist = [...(objTable ? objTable.querySelectorAll('tr') : [])].map(tr => ({ q: tr.getAttribute('data-icon-list-quantity'), t: tr.textContent.replace(/\s+/g, ' ').trim().slice(0, 120), ids: idsIn([...tr.querySelectorAll('a')].map(a => a.getAttribute('href')).join(' ')) })).slice(0, 30);
    const desc = [...text.querySelectorAll('h2')].find(h => /^Description/.test(h.textContent));
    out.hasDescription = !!desc;
  }
  out.series = [...doc.querySelectorAll('table.series tr')].map(tr => { const a = tr.querySelector('a'); return a ? idsIn(a.getAttribute('href'))[0] : 'self'; });
  // listviews (quest/npc/object/item templates)
  out.listviews = [...html.matchAll(/new Listview\(\{template: '(\w+)', id: '([\w-]+)'[^\n]*?data: (\[.*?\])\}\);/g)].map(m => {
    let ids = []; try { ids = JSON.parse(m[3]).map(r => r.id); } catch (e) { ids = ['parseErr']; }
    return { template: m[1], id: m[2], ids: ids.slice(0, 40), n: ids.length };
  });
  return out;
};

window.qffState = window.qffState || { done: 0, stopped: null, running: false, log: [] };
window.qffRun = async function (ids, gapMs) {
  const st = window.qffState; st.running = true; st.stopped = null;
  for (const id of ids) {
    if (localStorage.getItem('qffm:' + id)) continue;
    let rec;
    try {
      const r = await fetch('/forever/quest=' + id, { credentials: 'same-origin' });
      const html = await r.text();
      if (r.status === 404) { rec = { id: id, status: 404, notFound: true }; }
      else if (r.status !== 200) { st.stopped = { id: id, status: r.status, title: (html.match(/<title>([^<]*)/) || [])[1] }; break; }
      else {
        rec = window.qffParse(html, id);
        rec.status = r.status; rec.url = r.url.replace(/\?.*/, '');
      }
      if (rec.verify) { st.stopped = { id: id, verify: true, title: rec.title }; break; }
    } catch (e) { st.stopped = { id: id, error: String(e) }; break; }
    localStorage.setItem('qffm:' + id, JSON.stringify(rec));
    st.done++;
    await new Promise(res => setTimeout(res, gapMs));
  }
  st.running = false;
  return st;
};
// Compact form of one stored record (what gets exported to work/missing/pages/<id>.json).
window.qffCompact = function (r) {
  if (!r || r.notFound) return { id: r && r.id, nf: 1 };
  const q = r.q || {}, g = r.g || {};
  const ib = r.infobox || [];
  const pick = re => { const x = ib.find(i => re.test(i.t)); return x ? x.ids : []; };
  const skip = /^(Level|Requires level|Side|Difficulty|Sharable|Not sharable|Start|End|Added in patch)\b/;
  const lv = (r.listviews || []).map(l => [l.template, l.id, l.ids, l.n]);
  const patch = (ib.find(i => /^Added in patch/.test(i.t)) || {}).t;
  return {
    id: r.id, name: q.name || g.name_enus, lvl: q.level, req: q.reqlevel, side: q.side, gside: g._side,
    race: g.reqrace, cls: g.reqclass, cat: q.category, cat2: q.category2, type: q.type,
    daily: q.daily, wk: q.weekly, rep: q.reprewards,
    start: pick(/^Start\b/), end: pick(/^End\b/),
    obj: r.objText, ol: (r.iconlist || []).map(o => [o.q, o.t, o.ids]),
    ser: r.series, lv: lv, env: (q.envChange && q.envChange.lines) || [],
    ib: ib.filter(i => !skip.test(i.t)).map(i => i.ids.length ? [i.t, i.ids] : i.t),
    patch: patch ? patch.replace(/^Added in patch\s*/, '') : null,
    pins: (r.pins || []).map(p => [p.zone, p.x, p.y, p.type, p.who.map(w => w[2]).filter(Boolean)]),
    err: r.qErr || r.gErr || r.ibErr || r.mapErr || undefined
  };
};
// Export ids [from, from+n) of the sorted stored list as NDJSON split into <=800-char chunks, with a checksum.
window.qffExport = function (from, n) {
  const ids = Object.keys(localStorage).filter(k => k.startsWith('qffm:')).map(k => +k.slice(5)).sort((a, b) => a - b);
  const sel = ids.slice(from, from + n);
  const s = sel.map(id => JSON.stringify(window.qffCompact(JSON.parse(localStorage.getItem('qffm:' + id))))).join('\n');
  let sum = 0; for (let i = 0; i < s.length; i++) sum = (sum + s.charCodeAt(i) * (i % 97 + 1)) % 1000000007;
  const chunks = []; for (let i = 0; i < s.length; i += 800) chunks.push(s.slice(i, i + 800));
  return { total: ids.length, from: from, ids: sel, len: s.length, sum: sum, chunks: chunks };
};
'qff loaded';

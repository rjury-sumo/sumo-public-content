#!/usr/bin/env python3
"""
build_webview.py — Generate a self-contained HTML browser for the query library.

Reads query_library.json and writes query_library.html with the data embedded
inline (no server / no external fetch — double-click to open from disk).

Usage:
  python3 build_webview.py [--out DIR]
"""
import argparse
import json
import os

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sumo Logic Query Library</title>
<style>
  :root {
    --bg:#0f1419; --panel:#171d26; --panel2:#1e2632; --border:#2a3441;
    --text:#d7dee8; --muted:#8b98a9; --accent:#4aa3ff; --accent2:#7c5cff;
    --logs:#4aa3ff; --metrics:#39c07a; --traces:#e0a33e; --saved:#c678dd;
  }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  header { padding:14px 20px; border-bottom:1px solid var(--border); background:var(--panel);
           display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .stats { color:var(--muted); font-size:12px; }
  header .spacer { flex:1; }
  button { background:var(--panel2); color:var(--text); border:1px solid var(--border);
           border-radius:6px; padding:6px 12px; cursor:pointer; font-size:13px; }
  button:hover { border-color:var(--accent); }
  .layout { display:flex; height:calc(100vh - 53px); }
  .sidebar { width:260px; border-right:1px solid var(--border); background:var(--panel);
             overflow-y:auto; padding:14px; flex-shrink:0; }
  .sidebar h3 { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
                margin:18px 0 8px; display:flex; align-items:center; justify-content:space-between; }
  .facet { display:flex; align-items:center; justify-content:space-between; padding:3px 0;
           cursor:pointer; font-size:13px; }
  .facet:hover { color:var(--accent); }
  .facet input { margin-right:8px; }
  .facet .cnt { color:var(--muted); font-size:11px; }
  .facet label { cursor:pointer; display:flex; align-items:center; flex:1; }
  .sb-head { display:flex; gap:8px; margin-bottom:6px; }
  #clearAll { flex:1; }
  #clearAll:disabled { opacity:.4; cursor:default; }
  .clr { cursor:pointer; color:var(--accent); font-size:10px; font-weight:500;
         text-transform:none; letter-spacing:0; }
  .clr:hover { text-decoration:underline; }
  .chips { display:flex; flex-wrap:wrap; gap:4px; margin:0 0 6px; }
  .fchip { background:rgba(74,163,255,.16); color:var(--accent); border-radius:20px;
           padding:2px 8px; font-size:11px; cursor:pointer; }
  .fchip:hover { background:rgba(74,163,255,.28); }
  .fsearch { width:100%; padding:5px 8px; margin-bottom:6px; box-sizing:border-box;
             background:var(--panel2); border:1px solid var(--border); border-radius:5px;
             color:var(--text); font-size:12px; }
  .morehint { color:var(--muted); font-size:11px; font-style:italic; padding:3px 0 0; }
  .main { flex:1; overflow-y:auto; padding:14px 18px; }
  .searchbar { display:flex; gap:10px; margin-bottom:12px; }
  .searchbar input { flex:1; padding:9px 12px; background:var(--panel2); border:1px solid var(--border);
                     border-radius:6px; color:var(--text); font-size:14px; }
  .resultcount { color:var(--muted); font-size:12px; margin-bottom:10px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:8px;
          padding:12px 14px; margin-bottom:10px; cursor:pointer; }
  .card:hover { border-color:var(--accent); }
  .card .top { display:flex; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap; }
  .card .title { font-weight:600; }
  .card .ctx { color:var(--muted); font-size:12px; margin-bottom:6px; }
  .desc { color:#b6c2d2; font-size:12.5px; margin-bottom:8px; font-style:italic; }
  .modal .desc { font-style:normal; color:var(--text); }
  .card pre { margin:0; background:var(--panel2); border-radius:6px; padding:8px 10px;
              font:12px/1.45 "SF Mono",Menlo,Consolas,monospace; color:#c8d3e0;
              white-space:pre-wrap; max-height:88px; overflow:hidden; }
  .badge { font-size:10.5px; padding:2px 7px; border-radius:20px; font-weight:600;
           text-transform:uppercase; letter-spacing:.03em; }
  .b-Logs { background:rgba(74,163,255,.16); color:var(--logs); }
  .b-Metrics { background:rgba(57,192,122,.16); color:var(--metrics); }
  .b-Traces { background:rgba(224,163,62,.16); color:var(--traces); }
  .b-mode { background:var(--panel2); color:var(--muted); }
  .b-src { background:var(--panel2); color:var(--muted); }
  .chip { font-size:11px; background:var(--panel2); border:1px solid var(--border);
          padding:1px 7px; border-radius:4px; color:var(--accent); }
  /* modal */
  .overlay { position:fixed; inset:0; background:rgba(0,0,0,.6); display:none; z-index:10; }
  .overlay.open { display:flex; align-items:flex-start; justify-content:center; padding:40px 20px; }
  .modal { background:var(--panel); border:1px solid var(--border); border-radius:10px;
           width:min(900px,100%); max-height:calc(100vh - 80px); overflow-y:auto; }
  .modal .mhead { padding:16px 20px; border-bottom:1px solid var(--border); display:flex;
                  align-items:center; gap:10px; position:sticky; top:0; background:var(--panel); }
  .modal .mhead .title { font-weight:600; font-size:15px; flex:1; }
  .modal .mbody { padding:16px 20px; }
  .modal pre { background:var(--panel2); border:1px solid var(--border); border-radius:6px;
               padding:12px 14px; font:12.5px/1.5 "SF Mono",Menlo,Consolas,monospace;
               color:#c8d3e0; white-space:pre-wrap; overflow-x:auto; }
  .modal h4 { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
              margin:18px 0 8px; }
  .kv { display:flex; gap:8px; flex-wrap:wrap; }
  .src { background:var(--panel2); border:1px solid var(--border); border-radius:6px;
         padding:10px 12px; margin-bottom:8px; font-size:12.5px; }
  .src .sline { color:var(--muted); }
  .src .sline b { color:var(--text); font-weight:600; }
  a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<header>
  <h1>Sumo Logic Query Library</h1>
  <span class="stats" id="stats"></span>
  <span class="spacer"></span>
  <button id="exportJson">Export JSON</button>
  <button id="exportCsv">Export CSV</button>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar"></aside>
  <main class="main">
    <div class="searchbar">
      <input id="search" type="text" placeholder="Search query text, panel title, dashboard, folder, operator…" autofocus>
    </div>
    <div class="resultcount" id="resultcount"></div>
    <div id="results"></div>
  </main>
</div>
<div class="overlay" id="overlay"><div class="modal" id="modal"></div></div>

<script id="data" type="application/json">__DATA__</script>
<script>
const DB = JSON.parse(document.getElementById('data').textContent);
const QUERIES = DB.queries;

// derive "app" (top-level apps/<X>) from the first source file
function appOf(rec){
  const f = (rec.sources[0]||{}).file || '';
  const m = f.match(/apps\/([^\/]+)/);
  return m ? m[1] : '(other)';
}
QUERIES.forEach(q => { q._app = appOf(q); q._text = [
  q.query, (q.description||''), (q.tags||[]).join(' '),
  q.operators.join(' '), (q.metadataFields||[]).join(' '), q.parameters.join(' '),
  ...q.sources.map(s => [s.dashboardName,s.panelTitle,s.folder].join(' '))
].join(' ').toLowerCase(); });

// facet definitions: accessor returns a scalar or an array of values
const FACETS = [
  ['Query type','type', q=>q.queryType],
  ['Query mode','mode', q=>q.queryMode],
  ['App / source','app', q=>q._app],
  ['Tags','tags', q=>q.tags||[]],
  ['Operators','operators', q=>q.operators||[]],
  ['Metadata fields','fields', q=>q.metadataFields||[]],
];
const filters = {}; FACETS.forEach(([,k])=>filters[k]=new Set());
const facetSearch = {}; FACETS.forEach(([,k])=>facetSearch[k]='');
const TOP_N = 20, MAX_SHOWN = 80;
let search = '';
function accFor(key){ return FACETS.find(f=>f[1]===key)[2]; }
function anyFilter(){ return search || FACETS.some(([,k])=>filters[k].size); }

function valsOf(q, acc){ const v = acc(q); return v==null ? [] : (Array.isArray(v)?v:[v]); }

// Does q pass all active filters + search? Skip the facet named exceptKey
// (so a facet's own options aren't narrowed by its own selections).
function passesFilters(q, exceptKey){
  for (const [,key,acc] of FACETS){
    if (key===exceptKey) continue;
    if (filters[key].size){
      const vs = valsOf(q,acc);
      if (!vs.some(v=>filters[key].has(v))) return false;
    }
  }
  if (search && !q._text.includes(search)) return false;
  return true;
}
function matches(q){ return passesFilters(q, null); }

// Faceted counts: options + counts scoped to records passing every OTHER
// active filter, so the menu progressively narrows to valid results.
function scopedCounts(key){
  const acc = accFor(key);
  const m = new Map();
  for (const q of QUERIES){
    if (!passesFilters(q, key)) continue;
    for (const v of valsOf(q,acc)) m.set(v,(m.get(v)||0)+1);
  }
  return [...m.entries()].sort((a,b)=>b[1]-a[1]);
}

const SB = document.getElementById('sidebar');

function renderChips(key){
  return [...filters[key]].map(v =>
    `<span class="fchip" data-k="${key}" data-v="${encodeURIComponent(v)}">${esc(String(v))} ✕</span>`
  ).join('');
}

function renderOptions(key, counts){
  const q = (facetSearch[key]||'').toLowerCase();
  const matched = q ? counts.filter(([v])=>String(v).toLowerCase().includes(q)) : counts;
  const shown = (q ? matched : counts.slice(0, TOP_N)).slice(0, MAX_SHOWN);
  let h = shown.map(([val,cnt])=>{
    const on = filters[key].has(val);
    return `<div class="facet"><label><input type="checkbox" data-k="${key}" data-v="${encodeURIComponent(val)}" ${on?'checked':''}>${esc(String(val))}</label><span class="cnt">${cnt}</span></div>`;
  }).join('');
  if (q) h += `<div class="morehint">${matched.length} match${matched.length===1?'':'es'}${matched.length>MAX_SHOWN?` (showing ${MAX_SHOWN})`:''}</div>`;
  else if (counts.length > TOP_N) h += `<div class="morehint">top ${TOP_N} of ${counts.length} — type to search all</div>`;
  else if (!counts.length) h += `<div class="morehint">no matching values in current results</div>`;
  return h;
}

function groupHTML(label, key, counts){
  const large = counts.length > TOP_N;
  const active = filters[key].size;
  return `<h3>${esc(label)}${active?`<span class="clr" data-clr="${key}">clear (${active})</span>`:''}</h3>
    <div class="chips">${renderChips(key)}</div>
    ${large?`<input class="fsearch" data-fs="${key}" placeholder="filter ${esc(label.toLowerCase())}…" value="${esc(facetSearch[key]||'')}">`:''}
    <div class="opts">${renderOptions(key,counts)}</div>`;
}

// re-render only this group's options (used on in-section search — keeps input focused)
function refreshOptions(key){
  const g = SB.querySelector(`.facet-group[data-key="${key}"]`);
  if (g) g.querySelector('.opts').innerHTML = renderOptions(key, scopedCounts(key));
}
function updateClearAll(){
  const b = document.getElementById('clearAll');
  if (b) b.disabled = !anyFilter();
}

// A filter change rescopes EVERY facet, so rebuild the whole sidebar.
function renderSidebar(){
  let html = `<div class="sb-head"><button id="clearAll">Clear all filters</button></div>`;
  for (const [label,key] of FACETS){
    const counts = scopedCounts(key);
    if (!counts.length && !filters[key].size) continue;   // hide facets with no valid options
    html += `<div class="facet-group" data-key="${key}">${groupHTML(label,key,counts)}</div>`;
  }
  SB.innerHTML = html;
  updateClearAll();
}

// delegated events (bound once)
SB.addEventListener('input', e => {
  if (e.target.classList.contains('fsearch')){
    facetSearch[e.target.dataset.fs] = e.target.value;
    refreshOptions(e.target.dataset.fs);   // input element untouched → keeps focus
  }
});
SB.addEventListener('change', e => {
  const cb = e.target;
  if (cb.matches('.opts input[type=checkbox]')){
    const k=cb.dataset.k, v=decodeURIComponent(cb.dataset.v);
    if (cb.checked) filters[k].add(v); else filters[k].delete(v);
    renderSidebar(); render();   // rescope all facets to the new result set
  }
});
SB.addEventListener('click', e => {
  if (e.target.id === 'clearAll'){
    FACETS.forEach(([,k])=>{ filters[k].clear(); facetSearch[k]=''; });
    search=''; document.getElementById('search').value='';
    renderSidebar(); render(); return;
  }
  if (e.target.dataset.clr){
    const k=e.target.dataset.clr; filters[k].clear(); facetSearch[k]='';
    renderSidebar(); render(); return;
  }
  const chip = e.target.closest('.fchip');
  if (chip){
    filters[chip.dataset.k].delete(decodeURIComponent(chip.dataset.v));
    renderSidebar(); render();
  }
});

function esc(s){ return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

let current = [];
function render(){
  current = QUERIES.filter(matches);
  document.getElementById('resultcount').textContent =
    `${current.length} of ${QUERIES.length} unique queries`;
  const res = document.getElementById('results');
  res.innerHTML = current.slice(0,500).map((q,i)=>{
    const s0 = q.sources[0]||{};
    const ctx = [s0.dashboardName, s0.folder && '· '+s0.folder, (s0.rowContext&&s0.rowContext[0])].filter(Boolean).join(' ');
    const title = s0.panelTitle || s0.dashboardName || '(untitled)';
    const tags = (q.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('');
    return `<div class="card" data-i="${QUERIES.indexOf(q)}">
      <div class="top"><span class="badge b-${q.queryType}">${q.queryType}</span>
        <span class="badge b-mode">${q.queryMode}</span>
        <span class="title">${esc(title)}</span>
        ${q.parameters.length?`<span class="badge b-src">${q.parameters.length} params</span>`:''}
        ${q.sourceCount>1?`<span class="badge b-src">${q.sourceCount} sources</span>`:''}</div>
      <div class="ctx">${esc(ctx)}</div>
      ${q.description?`<div class="desc">${esc(q.description)}</div>`:''}
      <pre>${esc(q.query || '(structured query — open to view detail)')}</pre>
      ${tags?`<div class="kv" style="margin-top:8px">${tags}</div>`:''}
    </div>`;
  }).join('') + (current.length>500?`<div class="resultcount">…showing first 500. Refine filters/search.</div>`:'');
  res.querySelectorAll('.card').forEach(c => c.onclick = ()=>openModal(QUERIES[+c.dataset.i]));
}

function openModal(q){
  const body = q.query || '(structured query — see detail file)';
  const srcs = q.sources.map(s=>`<div class="src">
    <div class="sline"><b>${esc(s.panelTitle||s.dashboardName)}</b> — ${s.objectType}${s.visualization?` · ${s.visualization}`:''}</div>
    <div class="sline">dashboard: ${esc(s.dashboardName)}${s.folder?` &nbsp;|&nbsp; folder: ${esc(s.folder)}`:''}</div>
    <div class="sline">file: ${esc(s.file)}</div>
  </div>`).join('');
  const params = q.queryParameters||[];
  document.getElementById('modal').innerHTML = `
    <div class="mhead">
      <span class="badge b-${q.queryType}">${q.queryType}</span>
      <span class="title">${esc(q.id)} · ${esc((q.sources[0]||{}).panelTitle||'')}</span>
      <button id="copyBtn">Copy query</button>
      ${q.detailFile?`<a href="${esc(q.detailFile)}" target="_blank"><button>Full detail ↗</button></a>`:''}
      <button id="closeBtn">✕</button>
    </div>
    <div class="mbody">
      ${q.description?`<h4>Description</h4><div class="desc">${esc(q.description)}</div>`:''}
      ${(q.tags&&q.tags.length)?`<h4>Tags</h4><div class="kv">${q.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join('')}</div>`:''}
      <h4>Query <span style="color:var(--muted);font-weight:400;text-transform:none">· ${esc(q.queryMode)} · viewerType: ${esc(q.viewerType)}</span></h4>
      <pre id="qtext">${esc(body)}</pre>
      ${params.length?`<h4>Upload parameters (logSearches API · dataType ANY)</h4><pre>${esc(JSON.stringify(params,null,2))}</pre>`:''}
      ${q.scopes.length?`<h4>Scope</h4><div class="kv">${q.scopes.map(s=>`<span class="chip">${esc(s)}</span>`).join('')}</div>`:''}
      ${q.operators.length?`<h4>Operators</h4><div class="kv">${q.operators.map(o=>`<span class="chip">${esc(o)}</span>`).join('')}</div>`:''}
      ${(q.metadataFields&&q.metadataFields.length)?`<h4>Metadata fields</h4><div class="kv">${q.metadataFields.map(o=>`<span class="chip">${esc(o)}</span>`).join('')}</div>`:''}
      <h4>Sources (${q.sourceCount})</h4>${srcs}
      ${q.detailFile?`<p style="color:var(--muted);font-size:12px">Full visual settings, template-variable definitions, row context and structured metrics/traces data are in <a href="${esc(q.detailFile)}" target="_blank">${esc(q.detailFile)}</a>.</p>`:''}
    </div>`;
  document.getElementById('overlay').classList.add('open');
  document.getElementById('closeBtn').onclick = closeModal;
  document.getElementById('copyBtn').onclick = ()=>navigator.clipboard.writeText(body);
}
function closeModal(){ document.getElementById('overlay').classList.remove('open'); }
document.getElementById('overlay').onclick = e=>{ if(e.target.id==='overlay') closeModal(); };
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeModal(); });

document.getElementById('search').oninput = e=>{
  search=e.target.value.trim().toLowerCase();
  renderSidebar();   // rescope facets to the text-search results (#search keeps focus)
  render();
};

function download(name, text, type){
  const b=new Blob([text],{type}); const u=URL.createObjectURL(b);
  const a=document.createElement('a'); a.href=u; a.download=name; a.click(); URL.revokeObjectURL(u);
}
document.getElementById('exportJson').onclick = ()=>
  download('query_library_filtered.json', JSON.stringify(current,null,2),'application/json');
document.getElementById('exportCsv').onclick = ()=>{
  const rows=[['id','queryType','queryMode','sourceCount','app','dashboard','panel','folder','tags','description','parameters','operators','metadataFields','query']];
  for(const q of current){ const s=q.sources[0]||{};
    rows.push([q.id,q.queryType,q.queryMode,q.sourceCount,q._app,s.dashboardName,s.panelTitle,s.folder||'',(q.tags||[]).join('|'),q.description||'',q.parameters.join('|'),q.operators.join('|'),(q.metadataFields||[]).join('|'),q.query]); }
  const csv=rows.map(r=>r.map(c=>`"${String(c==null?'':c).replace(/"/g,'""')}"`).join(',')).join('\n');
  download('query_library_filtered.csv', csv,'text/csv');
};

document.getElementById('stats').textContent =
  `${DB.meta.uniqueQueries} unique · ${Object.entries(DB.meta.byQueryType).map(([k,v])=>k+' '+v).join(' · ')}` +
  (DB.meta.enrichedQueries ? ` · ${DB.meta.enrichedQueries} described` : '');
renderSidebar(); render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)
    lib_path = os.path.join(out_dir, "query_library.json")
    with open(lib_path, "r", encoding="utf-8") as fh:
        library = json.load(fh)

    # Merge AI enrichment (description + tags), matched by hash (preferred) or id.
    # Sources: per-record files in enrichment/*.json AND/OR a consolidated
    # enrichment.json (a JSON array, or {"enrichments"|"queries": [...]}).
    by_hash, by_id = {}, {}

    def index(e):
        if not isinstance(e, dict):
            return
        if e.get("hash"):
            by_hash[e["hash"]] = e
        if e.get("id"):
            by_id[e["id"]] = e

    enrich_dir = os.path.join(out_dir, "enrichment")
    if os.path.isdir(enrich_dir):
        for fn in sorted(os.listdir(enrich_dir)):
            if fn.endswith(".json"):
                try:
                    index(json.load(open(os.path.join(enrich_dir, fn), encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    continue

    consolidated = os.path.join(out_dir, "enrichment.json")
    if os.path.isfile(consolidated):
        try:
            data = json.load(open(consolidated, encoding="utf-8"))
            items = data if isinstance(data, list) else (
                data.get("enrichments") or data.get("queries") or [])
            for e in items:
                index(e)
        except (json.JSONDecodeError, OSError):
            pass

    enriched = 0
    for rec in library["queries"]:
        e = by_hash.get(rec["hash"]) or by_id.get(rec["id"])
        if e:
            rec["description"] = e.get("description")
            rec["tags"] = e.get("tags", [])
            enriched += 1
    library["meta"]["enrichedQueries"] = enriched

    data = json.dumps(library, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA__", data)
    html_path = os.path.join(out_dir, "query_library.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {html_path} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()

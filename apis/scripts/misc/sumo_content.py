#!/usr/bin/env python3
"""
sumo_content.py — Standalone Sumo Logic content library browser and exporter.

No external dependencies — stdlib only. Requires Python 3.10+.

CREDENTIALS
    export SUMO_ACCESS_ID=your_access_id
    export SUMO_ACCESS_KEY=your_access_key
    export SUMO_ENDPOINT=https://api.us2.sumologic.com   # adjust region

    Or pass --access-id / --access-key / --endpoint.

    Region endpoints:
        US1  https://api.sumologic.com
        US2  https://api.us2.sumologic.com
        EU   https://api.eu.sumologic.com
        AU   https://api.au.sumologic.com

SUBCOMMANDS
    ls <target>         List direct children of a folder
    get <target>        Show a content item or folder and its children
    search <target>     Filter children by name, type, or date
    export <target>     Export a content item/folder to JSON (async API)
    path <id>           Resolve a content ID to its library path

TARGETS
    personal            Your Personal folder
    global              Global Library  (async job)
    admin-recommended   Admin Recommended content  (async job)
    installed-apps      Installed Apps  (async job)
    /Library/path       Path-based lookup (any path starting with /)
    <ID>                Content ID (hex or decimal)

USAGE
    python sumo_content.py ls personal
    python sumo_content.py ls global --admin
    python sumo_content.py get "/Library/Admin Recommended"
    python sumo_content.py search personal --name "*CloudTrail*" --type Dashboard
    python sumo_content.py search global --name "*error*" --recurse --max-depth 3
    python sumo_content.py search personal --scheduled
    python sumo_content.py export 0000000000000005 --output /tmp/dashboard.json
    python sumo_content.py path 0000000000000005

    # JSON output (for piping)
    python sumo_content.py ls personal --json | jq '.children[] | .name'

    # Interactive table in browser
    python sumo_content.py search global --name "*Kubernetes*" --recurse --webview

    # Save output to file
    python sumo_content.py ls personal --json --output result.json
"""

import argparse
import base64
import fnmatch
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT  = "https://api.au.sumologic.com"
POLL_TIMEOUT      = 120   # seconds
POLL_INTERVAL     = 2     # seconds
API_MIN_INTERVAL  = 0.25  # 4 req/s per key
MAX_RETRIES       = 3

_SPECIAL_TARGETS = {
    "personal":          "personal",
    "global":            "global",
    "admin-recommended": "admin-recommended",
    "adminrecommended":  "admin-recommended",
    "installed-apps":    "installed-apps",
    "installedapps":     "installed-apps",
}

_TYPE_COLOR = {
    "Folder":        "\033[34m",
    "Dashboard":     "\033[32m",
    "Search":        "\033[33m",
    "MetricsSearch": "\033[35m",
    "Lookups":       "\033[36m",
    "Report":        "\033[90m",
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    access_id  = getattr(args, "access_id",  None) or os.environ.get("SUMO_ACCESS_ID",  "")
    access_key = getattr(args, "access_key", None) or os.environ.get("SUMO_ACCESS_KEY", "")
    endpoint   = getattr(args, "endpoint_url", None) or os.environ.get("SUMO_ENDPOINT", DEFAULT_ENDPOINT)

    if not access_id or not access_key:
        _die(
            "ERROR: Sumo Logic credentials not found.\n"
            "Set SUMO_ACCESS_ID and SUMO_ACCESS_KEY, or use --access-id / --access-key."
        )
    if not endpoint.startswith("https://"):
        _die(f"ERROR: endpoint must use https://. Got: {endpoint!r}")

    return access_id, access_key, endpoint.rstrip("/")

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)

def _err(msg: str) -> None:
    print(msg, file=sys.stderr)

_PROG_WIDTH = 78
def _progress(msg: str) -> None:
    if sys.stderr.isatty():
        line = f"  {msg}"[:_PROG_WIDTH]
        print(f"\r{line:<{_PROG_WIDTH}}", end="", flush=True, file=sys.stderr)

def _clear_progress() -> None:
    if sys.stderr.isatty():
        print(f"\r{' ' * _PROG_WIDTH}\r", end="", flush=True, file=sys.stderr)

def _c(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text

def _fmt_dt(s: str) -> str:
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:16]

# ---------------------------------------------------------------------------
# API error
# ---------------------------------------------------------------------------

class ContentAPIError(Exception):
    def __init__(self, status_code: int, message: str, suggestions: list[str] | None = None):
        self.status_code  = status_code
        self.message      = message
        self.suggestions  = suggestions or []
        super().__init__(message)

def _suggestions_for(status: int) -> list[str]:
    if status == 401:
        return ["Check SUMO_ACCESS_ID / SUMO_ACCESS_KEY environment variables"]
    if status == 403:
        return [
            "Credential may lack content library access",
            "Try --admin for shared/global content",
        ]
    if status == 404:
        return [
            "Check that the path or ID exists",
            "Try --admin if the item is in a shared space",
        ]
    return []

# ---------------------------------------------------------------------------
# HTTP client (stdlib urllib)
# ---------------------------------------------------------------------------

class ContentClient:
    def __init__(self, access_id: str, access_key: str, base_url: str, admin_mode: bool = False):
        self._base   = base_url
        token        = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
        self._headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        if admin_mode:
            self._headers["isAdminMode"] = "true"
        self._last_call: float = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        gap = now - self._last_call
        if gap < API_MIN_INTERVAL:
            time.sleep(API_MIN_INTERVAL - gap)
        self._last_call = time.monotonic()

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        data = json.dumps(body).encode() if body else None
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < MAX_RETRIES:
                    retry_after = exc.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else 2.0 ** attempt
                    _clear_progress()
                    _err(f"  Rate limited (429); retrying in {wait:.0f}s… (attempt {attempt+1}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    detail = json.loads(raw)
                    msg = detail.get("message") or ""
                    if not msg and detail.get("errors"):
                        msg = detail["errors"][0].get("message", "")
                    msg = f"HTTP {exc.code}: {msg}" if msg else f"HTTP {exc.code}"
                except Exception:
                    msg = f"HTTP {exc.code}: {raw[:200]}"
                raise ContentAPIError(exc.code, msg, _suggestions_for(exc.code)) from exc
        raise ContentAPIError(429, "Rate limit exceeded after retries")

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._request("POST", path, body=body)

    # ── Sync endpoints ────────────────────────────────────────────────────────

    def personal(self) -> dict:
        return self.get("/api/v2/content/folders/personal")

    def folder(self, folder_id: str) -> dict:
        return self.get(f"/api/v2/content/folders/{folder_id}")

    def item_by_path(self, path: str) -> dict:
        return self.get("/api/v2/content/path", params={"path": path})

    def item_path(self, content_id: str) -> str:
        return self.get(f"/api/v2/content/{content_id}/path").get("path", "")

    # ── Async folder endpoints ────────────────────────────────────────────────

    def global_folder(self) -> dict:
        job  = self.get("/api/v2/content/folders/global")
        data = self._poll_folder("/api/v2/content/folders/global", job["id"])
        if "data" in data and "children" not in data:
            data["children"] = data.pop("data")
        return data

    def admin_recommended(self) -> dict:
        job = self.get("/api/v2/content/folders/adminRecommended")
        return self._poll_folder("/api/v2/content/folders/adminRecommended", job["id"])

    def installed_apps(self) -> dict:
        job = self.get("/api/v2/content/folders/installedApps")
        return self._poll_folder("/api/v2/content/folders/installedApps", job["id"])

    def _poll_folder(self, base: str, job_id: str) -> dict:
        deadline = time.monotonic() + POLL_TIMEOUT
        while time.monotonic() < deadline:
            data   = self.get(f"{base}/{job_id}/status")
            status = data.get("status", "")
            _err(f"  [folder] status={status}")
            if status == "Success":
                return self.get(f"{base}/{job_id}/result")
            if status in ("Failed", "Cancelled"):
                _die(f"Folder job {status.lower()}")
            time.sleep(POLL_INTERVAL)
        _die(f"Timed out after {POLL_TIMEOUT}s waiting for folder job")

    # ── Async export ──────────────────────────────────────────────────────────

    def export_item(self, content_id: str) -> dict:
        job    = self.post(f"/api/v2/content/{content_id}/export")
        job_id = job["id"]
        deadline = time.monotonic() + POLL_TIMEOUT
        while time.monotonic() < deadline:
            data   = self.get(f"/api/v2/content/{content_id}/export/{job_id}/status")
            status = data.get("status", "")
            _err(f"  [export] status={status}")
            if status == "Success":
                return self.get(f"/api/v2/content/{content_id}/export/{job_id}/result")
            if status in ("Failed", "Cancelled"):
                _die(f"Export job {status.lower()}")
            time.sleep(POLL_INTERVAL)
        _die(f"Timed out after {POLL_TIMEOUT}s waiting for export job")

# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def resolve_target(client: ContentClient, target: str) -> dict:
    key     = target.lower().strip()
    special = _SPECIAL_TARGETS.get(key)

    if special == "personal":
        _err("  Fetching personal folder…")
        return client.personal()
    if special == "global":
        _err("  Fetching global library (async)…")
        return client.global_folder()
    if special == "admin-recommended":
        _err("  Fetching Admin Recommended (async)…")
        return client.admin_recommended()
    if special == "installed-apps":
        _err("  Fetching Installed Apps (async)…")
        return client.installed_apps()

    if target.startswith("/"):
        _err(f"  Resolving path: {target}")
        item = client.item_by_path(target)
        if item.get("itemType") == "Folder":
            return client.folder(item["id"])
        return item

    _err(f"  Fetching by ID: {target}")
    try:
        return client.folder(target)
    except ContentAPIError as e:
        if e.status_code == 400:
            return {"id": target, "itemType": "unknown", "name": target}
        raise

# ---------------------------------------------------------------------------
# Recursive search
# ---------------------------------------------------------------------------

def _parse_modified_after(value: str) -> datetime:
    m = re.match(r"^-(\d+)([dhw])$", value.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        secs = {"d": 86400, "h": 3600, "w": 604800}[unit]
        return datetime.now(timezone.utc) - timedelta(seconds=n * secs)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        _die(f"Cannot parse --modified-after value: {value!r}  (use ISO date or -Nd/-Nh/-Nw)")


def search_folder(
    client: ContentClient,
    folder: dict,
    name_glob: str | None,
    type_filter: str | None,
    modified_after: datetime | None,
    is_scheduled: bool | None,
    recurse: bool,
    max_depth: int,
    _depth: int = 0,
    _results: list | None = None,
    _fetched: list | None = None,
    _errors: list | None = None,
    _path_prefix: str = "",
) -> tuple[list[dict], list[dict]]:
    if _results is None: _results = []
    if _fetched is None: _fetched = [0]
    if _errors  is None: _errors  = []

    children     = folder.get("children", [])
    _fetched[0] += len(children)
    if _fetched[0] > 500:
        _err(f"  Warning: fetched {_fetched[0]} items — large tree, this may be slow")

    folder_name  = folder.get("name", "")
    current_path = f"{_path_prefix}/{folder_name}".lstrip("/")

    for child in children:
        name       = child.get("name",     "") or ""
        itype      = child.get("itemType", "") or ""
        mod        = child.get("modifiedAt","") or ""
        child_path = f"{current_path}/{name}"

        matches = True
        if name_glob and not fnmatch.fnmatch(name.lower(), name_glob.lower()):
            matches = False
        if type_filter and itype.lower() != type_filter.lower():
            matches = False
        if modified_after and mod:
            try:
                if datetime.fromisoformat(mod.replace("Z", "+00:00")) < modified_after:
                    matches = False
            except ValueError:
                pass
        if is_scheduled is not None and "isScheduled" in child:
            if child["isScheduled"] != is_scheduled:
                matches = False

        if matches:
            _results.append({**child, "_path": child_path})

        if recurse and itype == "Folder" and _depth < max_depth:
            _progress(f"Searching {child_path[:65]}… ({len(_results)} found)")
            try:
                subfolder = client.folder(child["id"])
                search_folder(
                    client, subfolder, name_glob, type_filter, modified_after,
                    is_scheduled, recurse, max_depth,
                    _depth + 1, _results, _fetched, _errors, current_path,
                )
            except Exception as exc:
                _clear_progress()
                _err(f"  Warning: could not fetch folder '{name}': {exc}")
                _errors.append({"path": child_path, "error": str(exc)})

    return _results, _errors

# ---------------------------------------------------------------------------
# Tabular display
# ---------------------------------------------------------------------------

def _print_item_detail(item: dict, use_color: bool) -> None:
    itype = item.get("itemType", "")
    color = _TYPE_COLOR.get(itype, "")
    print(f"  {'Name':<15} {_c(item.get('name', ''), _BOLD, use_color)}")
    print(f"  {'Type':<15} {_c(itype, color, use_color)}")
    print(f"  {'ID':<15} {_c(item.get('id', ''), _DIM, use_color)}")
    if item.get("description"):
        print(f"  {'Description':<15} {item['description']}")
    if item.get("modifiedAt"):
        print(f"  {'Modified':<15} {_fmt_dt(item['modifiedAt'])}")
    if item.get("createdBy"):
        print(f"  {'Created by':<15} {item['createdBy']}")


def _print_children_table(children: list[dict], use_color: bool, show_path: bool = False) -> None:
    if not children:
        print("  (empty)")
        return

    nw = min(50, max(20, max(len(c.get("name", "") or "") for c in children)))
    tw = min(18, max(10, max(len(c.get("itemType","") or "") for c in children)))
    iw = min(26, max(10, max(len(str(c.get("id","") or "")) for c in children)))
    show_sched = any("isScheduled" in c for c in children)

    hdr = f"  {'Name':<{nw}}  {'Type':<{tw}}  {'ID':<{iw}}  {'Modified':<16}"
    if show_sched:
        hdr += "  Sched"
    if show_path:
        hdr += "  Path"
    print(_c(hdr, _BOLD, use_color))
    print("  " + "─" * (len(hdr) - 2))

    for c in children:
        name  = (c.get("name", "") or "")[:nw]
        itype = (c.get("itemType", "") or "")
        cid   = str(c.get("id", "") or "")[:iw]
        mod   = _fmt_dt(c.get("modifiedAt", ""))
        color = _TYPE_COLOR.get(itype, "")

        type_cell = f"{itype:<{tw}}"
        if use_color and color:
            type_cell = f"{color}{type_cell}{_RESET}"

        row = f"  {name:<{nw}}  {type_cell}  {_c(cid, _DIM, use_color):<{iw}}  {mod:<16}"
        if show_sched:
            sched = c.get("isScheduled")
            if use_color:
                cell = (f"\033[32mY{_RESET}" if sched else f"\033[2mN{_RESET}") if sched is not None else " "
            else:
                cell = ("Y" if sched else "N") if sched is not None else " "
            row += f"  {cell}"
        if show_path:
            row += f"  {c.get('_path', '')}"
        print(row)

# ---------------------------------------------------------------------------
# Output / save helpers
# ---------------------------------------------------------------------------

def _write_output(data: dict, output_path: str | None, pretty: bool) -> None:
    """Write JSON to stdout or a file."""
    text = json.dumps(data, indent=2 if pretty else None)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        _err(f"  Saved to: {output_path}")
    else:
        print(text)


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", s)[:40].strip("-")

# ---------------------------------------------------------------------------
# Webview
# ---------------------------------------------------------------------------

_WEBVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>%%TITLE%%</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: ui-monospace, monospace; font-size: 13px; }
    th   { cursor: pointer; user-select: none; }
    th:hover { background: #d1d5db; }
    .badge-yes { color: #16a34a; font-weight: bold; }
    .badge-no  { color: #dc2626; }
    tr:hover td { background: #eff6ff; }
    .type-Folder        { color: #2563eb; }
    .type-Dashboard     { color: #16a34a; }
    .type-Search        { color: #d97706; }
    .type-MetricsSearch { color: #9333ea; }
    .type-Lookups       { color: #0891b2; }
    .type-Report        { color: #6b7280; }
  </style>
</head>
<body class="bg-gray-50 p-4">
<div class="max-w-full">
  <h1 class="text-base font-bold text-blue-700 mb-1">%%TITLE%%</h1>
  <div id="meta" class="text-xs text-gray-500 mb-2"></div>
  <div class="flex gap-2 mb-2 flex-wrap">
    <input id="q" type="text" placeholder="Filter all columns…"
           class="border rounded px-2 py-1 text-xs w-64" oninput="applyFilter()">
    <select id="type-sel" class="border rounded px-2 py-1 text-xs" onchange="applyFilter()">
      <option value="">All types</option>
    </select>
    <span id="count" class="text-xs text-gray-500 self-center"></span>
  </div>
  <div class="overflow-auto">
    <table class="text-xs border-collapse w-full bg-white border border-gray-200">
      <thead id="thead" class="bg-gray-200 sticky top-0"></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</div>
<script>
const PAYLOAD = %%DATA_JSON%%;
const rows    = PAYLOAD.rows || [];
const COLS    = %%COLS_JSON%%;
let sortCol = null, sortDir = 1, filtered = rows;

function e(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function renderCell(v, col) {
  if (v == null) return '<span class="text-gray-300">—</span>';
  if (typeof v === 'boolean') return v ? '<span class="badge-yes">✓</span>' : '<span class="badge-no">✗</span>';
  if (col === 'itemType') return `<span class="type-${e(v)} font-semibold">${e(v)}</span>`;
  if (col === 'modifiedAt' || col === 'createdAt') {
    try { return new Date(v).toISOString().slice(0,16).replace('T',' '); } catch(x) {}
  }
  if (typeof v === 'object') {
    const lbl = Array.isArray(v) ? '['+v.length+']' : '{'+Object.keys(v).length+'}';
    return `<span class="text-blue-400" title="${e(JSON.stringify(v,null,2))}">${lbl}</span>`;
  }
  return e(String(v));
}

function buildHeader() {
  document.getElementById('thead').innerHTML = '<tr>' + COLS.map(c => {
    const arr = sortCol===c?(sortDir===1?' ↑':' ↓'):'';
    return `<th class="px-2 py-1 text-left border-r border-gray-300 whitespace-nowrap"
                onclick="sortBy('${c.replace(/'/g,"\\'")}')">` + e(c) + arr + '</th>';
  }).join('') + '</tr>';
}

function buildRows() {
  if (!filtered.length) {
    document.getElementById('tbody').innerHTML='<tr><td class="p-4 text-gray-400 italic" colspan="99">No results</td></tr>';
    document.getElementById('count').textContent='0 rows';
    return;
  }
  document.getElementById('count').textContent = filtered.length+' of '+rows.length+' rows';
  document.getElementById('tbody').innerHTML = filtered.map(row =>
    '<tr class="border-b border-gray-100">' +
    COLS.map(c => '<td class="px-2 py-1 border-r border-gray-100 whitespace-nowrap max-w-xs overflow-hidden text-ellipsis">'+renderCell(row[c],c)+'</td>').join('') +
    '</tr>'
  ).join('');
}

function applyFilter() {
  const q    = (document.getElementById('q').value||'').toLowerCase();
  const type = document.getElementById('type-sel').value;
  filtered = rows.filter(r => {
    if (type && r.itemType !== type) return false;
    if (q && !Object.values(r).some(v=>String(v??'').toLowerCase().includes(q))) return false;
    return true;
  });
  if (sortCol) doSort();
  buildRows();
}

function sortBy(col) {
  sortDir = sortCol===col?-sortDir:1; sortCol=col;
  doSort(); buildHeader(); buildRows();
}

function doSort() {
  const col=sortCol,dir=sortDir;
  filtered=[...filtered].sort((a,b)=>{
    const av=String(a[col]??''),bv=String(b[col]??'');
    const an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn)) return (an-bn)*dir;
    return (av<bv?-1:av>bv?1:0)*dir;
  });
}

document.addEventListener('DOMContentLoaded',()=>{
  const m=PAYLOAD.meta||{};
  document.getElementById('meta').textContent=
    [m.subcommand,m.target,m.fetched_at,m.count!=null?m.count+' items':''].filter(Boolean).join('  ·  ');

  // Populate type filter
  const types=[...new Set(rows.map(r=>r.itemType).filter(Boolean))].sort();
  const sel=document.getElementById('type-sel');
  types.forEach(t=>{ const o=document.createElement('option'); o.value=t; o.textContent=t; sel.appendChild(o); });

  buildHeader();
  applyFilter();
});
</script>
</body>
</html>"""


def _open_webview(rows: list[dict], title: str, meta: dict) -> None:
    if not rows:
        _err("  (no rows to display in webview)")
        return

    # Collect columns: id first, name second, then rest
    seen: set[str] = set()
    cols: list[str] = []
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                cols.append(k)

    for pin in ["name", "id"]:
        idx = cols.index(pin) if pin in cols else -1
        if idx > 0:
            cols.insert(0, cols.pop(idx))

    payload_json = json.dumps({"rows": rows, "meta": meta}).replace("</", "<\\/")
    cols_json    = json.dumps(cols)
    ts           = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug         = _slug(title)

    html = (
        _WEBVIEW_TEMPLATE
        .replace("%%TITLE%%", title)
        .replace("%%DATA_JSON%%", payload_json)
        .replace("%%COLS_JSON%%", cols_json)
    )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{slug}.html", prefix=f"{ts}_",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8",
    )
    tmp.write(html)
    tmp.close()
    _err(f"  webview: {tmp.name}")
    webbrowser.open(f"file://{tmp.name}")

# ---------------------------------------------------------------------------
# Shared arg helpers
# ---------------------------------------------------------------------------

def _add_cred_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--admin",       action="store_true", help="Use admin mode (isAdminMode: true)")
    p.add_argument("--access-id",   default=None, metavar="ID",  dest="access_id",
                   help="Sumo Logic access ID (default: $SUMO_ACCESS_ID)")
    p.add_argument("--access-key",  default=None, metavar="KEY", dest="access_key",
                   help="Sumo Logic access key (default: $SUMO_ACCESS_KEY)")
    p.add_argument("--endpoint",    default=None, metavar="URL", dest="endpoint_url",
                   help=f"API base URL (default: $SUMO_ENDPOINT or {DEFAULT_ENDPOINT})")
    p.add_argument("--json",        dest="json_mode", action="store_true",
                   help="Output raw JSON to stdout (or --output file)")
    p.add_argument("--output", "-o",metavar="FILE", default=None,
                   help="Save JSON output to this file instead of stdout")
    p.add_argument("--webview",     action="store_true",
                   help="Open results as an interactive HTML table in the browser")


def _make_client(args: argparse.Namespace) -> ContentClient:
    access_id, access_key, endpoint = resolve_credentials(args)
    return ContentClient(access_id, access_key, endpoint, getattr(args, "admin", False))


def _pretty(args: argparse.Namespace) -> bool:
    return sys.stdout.isatty() and not getattr(args, "output", None)

# ---------------------------------------------------------------------------
# Subcommand: ls
# ---------------------------------------------------------------------------

def cmd_ls(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="sumo_content.py ls",
        description="List direct children of a content folder.")
    p.add_argument("target", help="personal | global | admin-recommended | installed-apps | /path | ID")
    _add_cred_args(p)
    args = p.parse_args(argv)

    client = _make_client(args)
    try:
        item = resolve_target(client, args.target)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        for s in e.suggestions:
            _err(f"  • {s}")
        sys.exit(1)

    children = item.get("children", [])
    use_color = sys.stdout.isatty() and not args.json_mode

    if args.webview:
        _open_webview(children, f"ls · {args.target}", {
            "subcommand": "ls", "target": args.target,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(children),
        })
        return

    if args.json_mode or args.output:
        _write_output({
            "status": "success", "subcommand": "ls", "target": args.target,
            "item": item, "children": children, "count": len(children),
        }, args.output, _pretty(args))
        return

    print(f"\n  {item.get('name', args.target)}  ({len(children)} children)\n")
    _print_children_table(children, use_color)
    print()


# ---------------------------------------------------------------------------
# Subcommand: get
# ---------------------------------------------------------------------------

def cmd_get(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="sumo_content.py get",
        description="Show a content item or folder.")
    p.add_argument("target", help="personal | global | admin-recommended | installed-apps | /path | ID")
    _add_cred_args(p)
    args = p.parse_args(argv)

    client = _make_client(args)
    try:
        item = resolve_target(client, args.target)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        for s in e.suggestions:
            _err(f"  • {s}")
        sys.exit(1)

    children  = item.get("children", [])
    use_color = sys.stdout.isatty() and not args.json_mode

    if args.webview:
        rows = children if children else [item]
        _open_webview(rows, f"get · {args.target}", {
            "subcommand": "get", "target": args.target,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(rows),
        })
        return

    if args.json_mode or args.output:
        _write_output({
            "status": "success", "subcommand": "get", "target": args.target,
            "item": item, "children": children, "count": len(children),
        }, args.output, _pretty(args))
        return

    print()
    _print_item_detail(item, use_color)
    if children:
        print(f"\n  Children ({len(children)}):")
        _print_children_table(children, use_color)
    print()


# ---------------------------------------------------------------------------
# Subcommand: search
# ---------------------------------------------------------------------------

def cmd_search(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="sumo_content.py search",
        description="Filter children of a folder by name, type, or date.")
    p.add_argument("target", help="personal | global | admin-recommended | installed-apps | /path | ID")
    p.add_argument("--name",           metavar="GLOB",
                   help="fnmatch pattern on item name, e.g. '*CloudTrail*'")
    p.add_argument("--type",           metavar="TYPE", dest="type_filter",
                   help="itemType: Folder|Dashboard|Search|Lookups|MetricsSearch|Report")
    p.add_argument("--modified-after", metavar="DATE",
                   help="ISO date or relative: -30d, -12h, -1w")
    sched = p.add_mutually_exclusive_group()
    sched.add_argument("--scheduled",   dest="is_scheduled", action="store_const", const=True,  default=None)
    sched.add_argument("--unscheduled", dest="is_scheduled", action="store_const", const=False)
    p.add_argument("--recurse",        action="store_true",
                   help="Walk into sub-folders (BFS)")
    p.add_argument("--max-depth",      type=int, default=5, metavar="N",
                   help="Max recursion depth (default: 5)")
    _add_cred_args(p)
    args = p.parse_args(argv)

    modified_after = _parse_modified_after(args.modified_after) if args.modified_after else None

    client = _make_client(args)
    try:
        folder = resolve_target(client, args.target)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        for s in e.suggestions:
            _err(f"  • {s}")
        sys.exit(1)

    results, fetch_errors = search_folder(
        client, folder,
        name_glob=args.name,
        type_filter=args.type_filter,
        modified_after=modified_after,
        is_scheduled=args.is_scheduled,
        recurse=args.recurse,
        max_depth=args.max_depth,
    )
    _clear_progress()

    use_color = sys.stdout.isatty() and not args.json_mode

    if args.webview:
        _open_webview(results, f"search · {args.target}", {
            "subcommand": "search", "target": args.target,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "count": len(results),
        })
        return

    if args.json_mode or args.output:
        _write_output({
            "status": "success", "subcommand": "search", "target": args.target,
            "folder": {"id": folder.get("id"), "name": folder.get("name")},
            "results": results, "count": len(results),
            "fetch_errors": fetch_errors,
        }, args.output, _pretty(args))
        return

    print(f"\n  Found {len(results)} match(es) in '{folder.get('name', args.target)}'")
    if not results:
        print("  Try broadening filters or add --recurse to search sub-folders.")
    else:
        print()
        _print_children_table(results, use_color, show_path=args.recurse)
    if fetch_errors:
        print(f"\n  Folders not accessible ({len(fetch_errors)}):")
        for fe in fetch_errors:
            print(f"    • {fe['path']}: {fe['error']}")
    print()


# ---------------------------------------------------------------------------
# Subcommand: export
# ---------------------------------------------------------------------------

def cmd_export(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="sumo_content.py export",
        description="Export a content item or folder to JSON (async API).")
    p.add_argument("target", help="Content ID, /path, or keyword")
    _add_cred_args(p)
    args = p.parse_args(argv)

    client = _make_client(args)
    try:
        item = resolve_target(client, args.target)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        sys.exit(1)

    content_id = item.get("id", args.target)
    item_name  = item.get("name", _slug(args.target))
    _err(f"  Exporting '{item_name}' (id={content_id})…")

    try:
        export_data = client.export_item(content_id)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        sys.exit(1)

    if args.output:
        out_path = args.output
    else:
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        tmp      = tempfile.mktemp(suffix=".json", prefix=f"sumo-export-{_slug(item_name)}-{ts}-")
        out_path = tmp

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)
    _err(f"  Saved to: {out_path}")

    if args.json_mode:
        _write_output({
            "status": "success", "subcommand": "export", "target": args.target,
            "item": item, "output_file": out_path, "content": export_data,
        }, None, _pretty(args))
    else:
        print(f"Exported '{item_name}' → {out_path}")


# ---------------------------------------------------------------------------
# Subcommand: path
# ---------------------------------------------------------------------------

def cmd_path(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="sumo_content.py path",
        description="Resolve a content ID to its library path.")
    p.add_argument("content_id", help="Content ID (hex or decimal)")
    _add_cred_args(p)
    args = p.parse_args(argv)

    client = _make_client(args)
    try:
        path = client.item_path(args.content_id)
    except ContentAPIError as e:
        _err(f"Error: {e.message}")
        sys.exit(1)

    if args.json_mode or args.output:
        _write_output({
            "status": "success", "content_id": args.content_id, "path": path,
        }, args.output, _pretty(args))
    else:
        print(path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {
    "ls":     cmd_ls,
    "get":    cmd_get,
    "search": cmd_search,
    "export": cmd_export,
    "path":   cmd_path,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    sub = sys.argv[1].lower()
    if sub not in _SUBCOMMANDS:
        _err(
            f"Unknown subcommand: {sys.argv[1]!r}\n"
            f"Available: {', '.join(_SUBCOMMANDS)}\n"
            f"Run:  python sumo_content.py --help"
        )
        sys.exit(1)

    _SUBCOMMANDS[sub](sys.argv[2:])


if __name__ == "__main__":
    main()

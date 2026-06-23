#!/usr/bin/env python3
"""
sumo_api.py — Standalone read-only GET access to Sumo Logic REST APIs.

No dependencies beyond the Python standard library. Requires Python 3.10+.

CREDENTIALS
    Set environment variables before running:

        export SUMO_ACCESS_ID=your_access_id
        export SUMO_ACCESS_KEY=your_access_key
        export SUMO_ENDPOINT=https://api.us2.sumologic.com   # adjust region

    Or pass --access-id / --access-key / --endpoint on the command line.

    Region endpoints:
        US1  https://api.sumologic.com
        US2  https://api.us2.sumologic.com
        EU   https://api.eu.sumologic.com
        AU   https://api.au.sumologic.com

USAGE
    python sumo_api.py <endpoint> [options]

    # List saved log searches (API default page size)
    python sumo_api.py logSearches

    # Fetch up to 500 searches, auto-paginating in chunks of 100
    python sumo_api.py logSearches --limit 500

    # Pipe to jq for filtering
    python sumo_api.py logSearches | jq '.data[] | select(.name | contains("prod"))'

    # Open interactive HTML table in browser
    python sumo_api.py connections --webview

    # Extra query parameters
    python sumo_api.py healthEvents --param type=Collector

    # Get a single resource by ID
    python sumo_api.py logSearches --id abc123

    # Auto-paginate all pages
    python sumo_api.py accessKeys --all

KNOWN ENDPOINT ALIASES (case-insensitive)

  Resources (sumo r equivalents):
    collectors            /v1/collectors                Installed collectors  [offset paging]
    partitions            /v1/partitions                Log partitions
    scheduledViews        /v1/scheduledViews            Scheduled views
    extractionRules       /v1/extractionRules           Field extraction rules (FERs)
    fields                /v1/fields                    Schema fields
    users                 /v1/users                     Users
    roles                 /v2/roles                     Roles
    dashboards            /v2/dashboards                Dashboards
    monitors              /v1/monitors/search           Monitors (all, via search endpoint)

    Aliases:  fer/fers → extractionRules  |  scheduled-view(s) → scheduledViews
              collector/partition/field/user/role/dashboard/monitor → plural form
    Note:     Sources are not in the OpenAPI spec; use /v1/collectors/{id}/sources as a raw path

  Org config:
    logSearches           /v1/logSearches               Saved log searches
    accessKeys            /v1/accessKeys                Access keys
    connections           /v1/connections               Notification connections
    tokens                /v1/tokens                    API tokens
    healthEvents          /v1/healthEvents              Platform health events
    lookupTables          /v1/lookupTables              Lookup table definitions
    metricsSearches       /v2/metricsSearches           Saved metrics searches
    apps                  /v1/apps                      App Catalog
    ingestBudgets         /v2/ingestBudgets             Ingest budget definitions
    scanBudgets           /v1/budgets                   Scan budget definitions
    dynamicParsingRules   /v1/dynamicParsingRules       Dynamic parsing rules
    transformationRules   /v1/transformationRules       Log transformation rules
    dataMaskingRules      /v1/dataMaskingRules          Data masking rules
    dataForwardingDests   /v1/logsDataForwarding/destinations
    dataForwardingRules   /v1/logsDataForwarding/rules
    serviceAccounts       /v1/serviceAccounts           Service accounts
    oauthClients          /v1/oauth/clients             OAuth clients
    macros                /v2/macros                    Saved macros

    You can also pass a raw path:  /v1/logSearches  or  v1/logSearches

OUTPUT
    Always a JSON object with a "data" array, suitable for piping to jq:
        python sumo_api.py logSearches | jq '.data | length'
        python sumo_api.py logSearches | jq '.data[] | .name'

    Output is indented when stdout is a terminal, compact when piped.
    --webview opens an interactive HTML table in your browser.
"""

import argparse
import base64
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
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = "https://api.au.sumologic.com"
MAX_PAGES = 50

# ---------------------------------------------------------------------------
# Endpoint catalog
# ---------------------------------------------------------------------------

CATALOG: dict[str, dict] = {
    "logSearches": {
        "path": "/v1/logSearches",
        "array_key": "logSearches",
        "next_key": "token",
        "max_limit": 100,
        "description": "Saved log searches",
    },
    "accessKeys": {
        "path": "/v1/accessKeys",
        "array_key": "data",
        "next_key": "next",
        "description": "Access keys for the org",
    },
    "connections": {
        "path": "/v1/connections",
        "array_key": "data",
        "next_key": "next",
        "description": "Notification connections (webhooks, PagerDuty, etc.)",
    },
    "tokens": {
        "path": "/v1/tokens",
        "array_key": "data",
        "next_key": None,
        "description": "API tokens",
    },
    "healthEvents": {
        "path": "/v1/healthEvents",
        "array_key": "data",
        "next_key": "next",
        "description": "Platform health events",
    },
    "lookupTables": {
        "path": "/v1/lookupTables",
        "array_key": "data",
        "next_key": "next",
        "description": "Lookup table definitions",
    },
    "metricsSearches": {
        "path": "/v2/metricsSearches",
        "array_key": "metricsSearches",
        "next_key": "next",
        "description": "Saved metrics searches",
    },
    "apps": {
        "path": "/v1/apps",
        "array_key": "apps",
        "next_key": None,
        "description": "App Catalog",
    },
    "ingestBudgets": {
        "path": "/v2/ingestBudgets",
        "array_key": "data",
        "next_key": "next",
        "description": "Ingest budget definitions",
    },
    "scanBudgets": {
        "path": "/v1/budgets",
        "array_key": "data",
        "next_key": "next",
        "description": "Scan budget definitions",
    },
    "dynamicParsingRules": {
        "path": "/v1/dynamicParsingRules",
        "array_key": "data",
        "next_key": "next",
        "description": "Dynamic parsing rules",
    },
    "transformationRules": {
        "path": "/v1/transformationRules",
        "array_key": "data",
        "next_key": "next",
        "description": "Log transformation rules",
    },
    "dataMaskingRules": {
        "path": "/v1/dataMaskingRules",
        "array_key": "data",
        "next_key": "next",
        "description": "Data masking rules",
    },
    "dataForwardingDests": {
        "path": "/v1/logsDataForwarding/destinations",
        "array_key": "data",
        "next_key": None,
        "description": "Data forwarding destinations",
    },
    "dataForwardingRules": {
        "path": "/v1/logsDataForwarding/rules",
        "array_key": "data",
        "next_key": None,
        "description": "Data forwarding rules",
    },
    "serviceAccounts": {
        "path": "/v1/serviceAccounts",
        "array_key": "data",
        "next_key": None,
        "description": "Service accounts",
    },
    "oauthClients": {
        "path": "/v1/oauth/clients",
        "array_key": "data",
        "next_key": "next",
        "description": "OAuth clients",
    },
    "macros": {
        "path": "/v2/macros",
        "array_key": "data",
        "next_key": "next",
        "description": "Saved macros",
    },
    # ── Resources (sumo r equivalents) ─────────────────────────────────────
    # Note: collectors/sources are not in the Sumo Logic OpenAPI spec but the
    # REST API is documented at https://help.sumologic.com/docs/api/collector-management/
    "collectors": {
        "path": "/v1/collectors",
        "array_key": "collectors",
        "next_key": None,
        "pagination_style": "offset",
        "page_size": 300,
        "description": "Installed collectors (offset-based pagination)",
    },
    "partitions": {
        "path": "/v1/partitions",
        "array_key": "data",
        "next_key": "next",
        "description": "Log partitions",
    },
    "scheduledViews": {
        "path": "/v1/scheduledViews",
        "array_key": "data",
        "next_key": "next",
        "description": "Scheduled views",
    },
    "extractionRules": {
        "path": "/v1/extractionRules",
        "array_key": "data",
        "next_key": "next",
        "description": "Field extraction rules (FERs)",
    },
    "fields": {
        "path": "/v1/fields",
        "array_key": "data",
        "next_key": None,
        "description": "Schema fields (all returned in one call)",
    },
    "users": {
        "path": "/v1/users",
        "array_key": "data",
        "next_key": "next",
        "description": "Users",
    },
    "roles": {
        "path": "/v2/roles",
        "array_key": "data",
        "next_key": "next",
        "description": "Roles",
    },
    "dashboards": {
        "path": "/v2/dashboards",
        "array_key": "dashboards",
        "next_key": "next",
        "description": "Dashboards (v2 API)",
    },
    "monitors": {
        "path": "/v1/monitors/search",
        "array_key": None,       # endpoint returns a bare JSON array
        "next_key": None,
        "pagination_style": "none",
        "list_params": {"query": ""},   # required; empty = return all monitors
        "list_transform": "item",       # each element is {item: {...}, path: "..."}
        "description": "Monitors (all, via /monitors/search?query=)",
    },
}

# Extra case-insensitive aliases for resource types (sumo-CLI-style names)
_RESOURCE_ALIASES: dict[str, str] = {
    "collector":       "collectors",
    "partition":       "partitions",
    "scheduledview":   "scheduledViews",
    "scheduled-view":  "scheduledViews",
    "scheduled-views": "scheduledViews",
    "fer":             "extractionRules",
    "fers":            "extractionRules",
    "extractionrule":  "extractionRules",
    "field":           "fields",
    "user":            "users",
    "role":            "roles",
    "dashboard":       "dashboards",
    "monitor":         "monitors",
}

_CATALOG_LOWER: dict[str, str] = {k.lower(): k for k in CATALOG}
_SKIP_ARRAY_KEYS = frozenset({"warnings", "errors", "permissions", "pathItems"})

# ---------------------------------------------------------------------------
# Progress (always stderr so stdout stays clean for piping)
# ---------------------------------------------------------------------------

def _progress(msg: str) -> None:
    print(msg, file=sys.stderr)

# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    access_id  = args.access_id  or os.environ.get("SUMO_ACCESS_ID",  "")
    access_key = args.access_key or os.environ.get("SUMO_ACCESS_KEY", "")
    endpoint   = args.endpoint_url or os.environ.get("SUMO_ENDPOINT", DEFAULT_ENDPOINT)

    if not access_id or not access_key:
        print(
            "ERROR: Sumo Logic credentials not found.\n"
            "Set SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables, or use\n"
            "--access-id / --access-key flags.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not endpoint.startswith("https://"):
        print(f"ERROR: endpoint must use https://. Got: {endpoint!r}", file=sys.stderr)
        sys.exit(1)

    return access_id, access_key, endpoint.rstrip("/")

# ---------------------------------------------------------------------------
# Endpoint resolution
# ---------------------------------------------------------------------------

def resolve_endpoint(raw: str) -> tuple[str, dict | None]:
    lower = raw.lower()
    # Direct catalog match (case-insensitive), then friendly resource alias
    canonical = _CATALOG_LOWER.get(lower) or _CATALOG_LOWER.get(_RESOURCE_ALIASES.get(lower, "").lower())
    if canonical:
        return CATALOG[canonical]["path"], CATALOG[canonical]

    if raw.startswith("/"):
        return raw, None

    if raw.startswith("v1/") or raw.startswith("v2/"):
        return "/" + raw, None

    raise ValueError(
        f"Unknown endpoint '{raw}'.\n"
        f"Known aliases: {', '.join(CATALOG)}\n"
        f"Or use a path like /v1/logSearches or v1/logSearches"
    )

# ---------------------------------------------------------------------------
# HTTP client (stdlib urllib — no third-party packages needed)
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class ApiClient:
    _MAX_RETRIES = 3

    def __init__(self, access_id: str, access_key: str, base_url: str):
        self._base = base_url
        token = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self._base}/api{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers=self._headers)

        for attempt in range(self._MAX_RETRIES):
            try:
                with urllib.request.urlopen(req) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if body.strip() else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = 5 * (attempt + 1)
                    _progress(f"  [rate-limited] retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                body = exc.read().decode("utf-8", errors="replace")
                raise ApiError(exc.code, body) from exc

        raise ApiError(429, "Rate limit exceeded after retries")

# ---------------------------------------------------------------------------
# Array key / pagination helpers
# ---------------------------------------------------------------------------

def _detect_array_key(resp: dict) -> tuple[str, list]:
    if "data" in resp and isinstance(resp["data"], list):
        return "data", resp["data"]
    for k, v in resp.items():
        if isinstance(v, list) and k not in _SKIP_ARRAY_KEYS:
            return k, v
    return "", []


def _detect_next_token(resp: dict, catalog_next_key: str | None) -> str | None:
    keys: list[str] = []
    if catalog_next_key:
        keys.append(catalog_next_key)
    for fallback in ("next", "token"):
        if fallback not in keys:
            keys.append(fallback)
    for key in keys:
        val = resp.get(key)
        if val:
            return str(val)
    return None

# ---------------------------------------------------------------------------
# Paginated fetch
# ---------------------------------------------------------------------------

def _apply_transform(items: list, transform: str) -> list:
    """Unwrap a nested key from each item (e.g. monitors return {item:{...}, path:"..."})."""
    if not transform:
        return items
    return [i[transform] for i in items if isinstance(i, dict) and transform in i]


def fetch(
    client: ApiClient,
    path: str,
    params: dict,
    catalog_entry: dict | None,
    fetch_all: bool,
    initial_token: str | None,
    total_limit: int | None = None,
) -> tuple[list, str | None]:
    ce               = catalog_entry or {}
    pagination_style = ce.get("pagination_style", "token")
    list_transform   = ce.get("list_transform", "")
    page_size        = ce.get("page_size", 300)

    # ── Offset pagination (collectors) ─────────────────────────────────────
    if pagination_style == "offset":
        all_items: list = []
        array_key = ce.get("array_key")
        effective_limit = params.get("limit", page_size)
        offset = 0
        page   = 0

        while True:
            page_params = {**params, "limit": effective_limit, "offset": offset}
            resp = client.get(path, page_params)

            if isinstance(resp, list):
                items = resp
            elif array_key:
                items = resp.get(array_key, [])
            else:
                _, items = _detect_array_key(resp)

            items = _apply_transform(items, list_transform)

            if not items:
                return all_items, None

            all_items.extend(items)
            page += 1

            if total_limit and not fetch_all and len(all_items) >= total_limit:
                return all_items[:total_limit], None

            if len(items) < effective_limit:
                return all_items, None  # last page — fewer items than requested

            if not fetch_all and total_limit is None:
                _progress(f"  {len(all_items)} items fetched (one page); use --all for all pages")
                return all_items, f"offset={offset + len(items)}"

            if page >= MAX_PAGES:
                _progress(f"  [pagination] reached {MAX_PAGES}-page limit")
                return all_items, f"offset={offset + len(items)}"

            offset += len(items)
            _progress(f"  fetched {len(all_items)} items (page {page})...")

    # ── No pagination / raw list (monitors, fields, apps, …) ───────────────
    if pagination_style == "none":
        resp  = client.get(path, params or None)
        items = resp if isinstance(resp, list) else resp.get(ce.get("array_key") or "", resp)
        if not isinstance(items, list):
            _, items = _detect_array_key(resp) if isinstance(resp, dict) else ("", [resp])
        items = _apply_transform(items, list_transform)
        if total_limit and not fetch_all:
            items = items[:total_limit]
        return items, None

    # ── Token pagination (default) ──────────────────────────────────────────
    all_items = []
    token     = initial_token
    array_key = ce.get("array_key")
    next_key  = ce.get("next_key")
    page      = 0

    while True:
        page_params = dict(params)
        if token:
            page_params["token"] = token

        resp = client.get(path, page_params)

        if isinstance(resp, list):
            items = _apply_transform(resp, list_transform)
            all_items.extend(items)
            return all_items, None

        if array_key is not None:
            items = resp.get(array_key, [])
        else:
            detected, items = _detect_array_key(resp)
            if detected:
                array_key = detected
            else:
                return [resp], None

        items = _apply_transform(items, list_transform)
        all_items.extend(items)
        page += 1

        next_token = _detect_next_token(resp, next_key)

        if not next_token:
            return all_items, None

        if fetch_all:
            pass
        elif total_limit is not None and len(all_items) < total_limit:
            pass
        else:
            return all_items, next_token

        if page >= MAX_PAGES:
            _progress(f"  [pagination] reached {MAX_PAGES}-page limit; use --token to continue")
            if total_limit and not fetch_all:
                all_items = all_items[:total_limit]
            return all_items, next_token

        token = next_token
        _progress(f"  fetched {len(all_items)} items (page {page})...")

    return all_items, None  # unreachable

# ---------------------------------------------------------------------------
# Webview (self-contained HTML, no external dependencies)
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
    th { cursor: pointer; user-select: none; }
    th:hover { background: #d1d5db; }
    .badge-yes { color: #16a34a; font-weight: bold; }
    .badge-no  { color: #dc2626; font-weight: bold; }
    tr:hover td { background: #eff6ff; }
  </style>
</head>
<body class="bg-gray-50 p-4">
<div class="max-w-full">
  <h1 class="text-base font-bold text-blue-700 mb-1">%%TITLE%%</h1>
  <div id="meta" class="text-xs text-gray-500 mb-2"></div>
  <div class="flex gap-2 mb-2">
    <input id="q" type="text" placeholder="Filter all columns…"
           class="border rounded px-2 py-1 text-xs w-64"
           oninput="applyFilter()">
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
const rows    = PAYLOAD.data || [];
let cols = [], sortCol = null, sortDir = 1, filtered = rows;

function getCols() {
  const seen = new Set(), out = [];
  for (const row of rows)
    for (const k of Object.keys(row))
      if (!seen.has(k)) { seen.add(k); out.push(k); }
  for (const pin of ['name', 'id'].reverse()) {
    const i = out.indexOf(pin);
    if (i > 0) { out.splice(i, 1); out.unshift(pin); }
  }
  return out;
}

function e(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function renderCell(v) {
  if (v == null) return '<span class="text-gray-300">—</span>';
  if (typeof v === 'boolean') return v ? '<span class="badge-yes">✓</span>' : '<span class="badge-no">✗</span>';
  if (typeof v === 'object') {
    const lbl = Array.isArray(v) ? '['+v.length+']' : '{'+Object.keys(v).length+'}';
    return `<span class="text-blue-500" title="${e(JSON.stringify(v,null,2))}">${lbl}</span>`;
  }
  return e(String(v));
}

function buildHeader() {
  document.getElementById('thead').innerHTML = '<tr>' + cols.map(c => {
    const arr = sortCol===c ? (sortDir===1?' ↑':' ↓') : '';
    return `<th class="px-2 py-1 text-left border-r border-gray-300 whitespace-nowrap"
                onclick="sortBy('${c.replace(/'/g,"\\'")}')">` + e(c) + arr + '</th>';
  }).join('') + '</tr>';
}

function buildRows() {
  if (!filtered.length) {
    document.getElementById('tbody').innerHTML = '<tr><td class="p-4 text-gray-400 italic" colspan="99">No results</td></tr>';
    document.getElementById('count').textContent = '0 rows';
    return;
  }
  document.getElementById('count').textContent = filtered.length + ' of ' + rows.length + ' rows';
  document.getElementById('tbody').innerHTML = filtered.map(row =>
    '<tr class="border-b border-gray-100">' +
    cols.map(c => '<td class="px-2 py-1 border-r border-gray-100 whitespace-nowrap">' + renderCell(row[c]) + '</td>').join('') +
    '</tr>'
  ).join('');
}

function applyFilter() {
  const q = (document.getElementById('q').value || '').toLowerCase();
  filtered = q ? rows.filter(r => Object.values(r).some(v => String(v??'').toLowerCase().includes(q))) : rows;
  if (sortCol) doSort();
  buildRows();
}

function sortBy(col) {
  sortDir = sortCol === col ? -sortDir : 1; sortCol = col;
  doSort(); buildHeader(); buildRows();
}

function doSort() {
  const col = sortCol, dir = sortDir;
  filtered = [...filtered].sort((a, b) => {
    const av = String(a[col]??''), bv = String(b[col]??'');
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return (an-bn)*dir;
    return (av<bv?-1:av>bv?1:0)*dir;
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const m = PAYLOAD.meta || {};
  document.getElementById('meta').textContent =
    [m.endpoint, m.fetched_at, m.count!=null?m.count+' items':''].filter(Boolean).join('  ·  ');
  cols = getCols();
  buildHeader();
  applyFilter();
});
</script>
</body>
</html>"""


def open_webview(items: list, api_path: str, command: str, next_token: str | None) -> None:
    slug = re.sub(r"_+", "_", re.sub(r"[^a-zA-Z0-9]", "_", api_path.strip("/"))).strip("_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    meta = {
        "endpoint": api_path,
        "count": len(items),
        "command": command,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if next_token:
        meta["next_token"] = next_token
        meta["note"] = "More pages available — re-run with --all to fetch everything"

    payload_json = json.dumps({"data": items, "meta": meta}).replace("</", "<\\/")
    html = _WEBVIEW_TEMPLATE.replace("%%TITLE%%", f"sumo api · {api_path}").replace("%%DATA_JSON%%", payload_json)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{slug}.html", prefix=f"{ts}_",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8",
    )
    tmp.write(html)
    tmp.close()
    _progress(f"  webview: {tmp.name}")
    webbrowser.open(f"file://{tmp.name}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sumo_api.py",
        description="Read-only GET access to Sumo Logic REST APIs. No external dependencies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("endpoint", nargs="?", default=None,
        help="Catalog alias (e.g. logSearches) or path like /v1/logSearches. "
             "Omit to list available aliases.")
    parser.add_argument("--id", dest="resource_id", metavar="ID",
        help="Append /{ID} for get-by-id (skips pagination)")
    parser.add_argument("--param", dest="params", metavar="key=value",
        action="append", default=[],
        help="Extra query parameters (repeatable)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
        help="Max items to return. Auto-paginates for endpoints with per-page caps.")
    parser.add_argument("--token", metavar="TOKEN",
        help="Resume pagination from a continuation token")
    parser.add_argument("--all", dest="fetch_all", action="store_true",
        help=f"Auto-paginate all pages (stops at {MAX_PAGES} pages)")
    parser.add_argument("--pretty", action="store_true",
        help="Indent JSON output (default when stdout is a terminal)")
    parser.add_argument("--webview", action="store_true",
        help="Open results as an interactive HTML table in the browser")
    parser.add_argument("--access-id", default=None, metavar="ID",
        help="Sumo Logic access ID (default: $SUMO_ACCESS_ID)")
    parser.add_argument("--access-key", default=None, metavar="KEY",
        help="Sumo Logic access key (default: $SUMO_ACCESS_KEY)")
    parser.add_argument("--endpoint", dest="endpoint_url", default=None, metavar="URL",
        help=f"API base URL (default: $SUMO_ENDPOINT or {DEFAULT_ENDPOINT})")

    args = parser.parse_args(argv)
    pretty = args.pretty or sys.stdout.isatty()

    if args.endpoint is None:
        print("Available endpoint aliases (case-insensitive):\n")
        for name, entry in CATALOG.items():
            print(f"  {name:<24} {entry['path']:<40}  {entry['description']}")
        print("\nUsage: python sumo_api.py <endpoint> [--limit N] [--all] [--webview]")
        sys.exit(0)

    try:
        api_path, catalog_entry = resolve_endpoint(args.endpoint)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if args.resource_id:
        api_path = f"{api_path}/{args.resource_id}"

    access_id, access_key, base_url = resolve_credentials(args)
    client = ApiClient(access_id, access_key, base_url)

    # Seed query_params with any catalog-level defaults (e.g. monitors need ?query=)
    query_params: dict[str, str | int] = dict((catalog_entry or {}).get("list_params", {}))
    total_limit: int | None = None
    if not args.resource_id and args.limit is not None:
        max_limit = catalog_entry.get("max_limit") if catalog_entry else None
        if max_limit and args.limit > max_limit:
            _progress(f"  [pagination] {args.endpoint} page max is {max_limit}; "
                      f"will auto-paginate to fetch up to {args.limit}")
            query_params["limit"] = max_limit
            total_limit = args.limit
        else:
            query_params["limit"] = args.limit

    for kv in args.params:
        if "=" not in kv:
            print(f"--param must be key=value, got: {kv!r}", file=sys.stderr)
            sys.exit(1)
        k, _, v = kv.partition("=")
        query_params[k.strip()] = v.strip()

    _progress(f"GET {api_path}")

    try:
        if args.resource_id:
            resp = client.get(api_path, query_params or None)
            items: list = resp if isinstance(resp, list) else [resp]
            next_token: str | None = None
        else:
            items, next_token = fetch(
                client=client,
                path=api_path,
                params=query_params,
                catalog_entry=catalog_entry,
                fetch_all=args.fetch_all,
                initial_token=args.token,
                total_limit=total_limit,
            )
    except ApiError as exc:
        print(json.dumps({
            "status": "error",
            "error_code": exc.status_code,
            "error_message": exc.message,
            "endpoint": api_path,
        }, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.webview:
        cmd = f"sumo_api.py {args.endpoint}"
        if args.resource_id:
            cmd += f" --id {args.resource_id}"
        if args.fetch_all:
            cmd += " --all"
        open_webview(items, api_path, cmd, next_token)

    envelope: dict = {
        "status": "success",
        "endpoint": api_path,
        "count": len(items),
        "next_token": next_token,
        "data": items,
    }
    print(json.dumps(envelope, indent=2 if pretty else None))


if __name__ == "__main__":
    main()

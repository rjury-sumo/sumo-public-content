# Sumo Logic Query Library — Extraction & Webview Plan

## Goal

Scrape every Sumo Logic query embedded in the dashboard/content exports under `apps/`
into a single JSON query database, then generate a self-contained, browsable webview
(search / filter / inspect / export). The result is a portable library of admin and
power-user searches (logs + metrics) applicable to any Sumo Logic instance.

## Source data model (from inspection of `apps/`)

72 JSON files. Top-level `type` values observed:

| Top-level type | Count | Handling |
|---|---|---|
| `DashboardV2SyncDefinition` | 57 | Single dashboard. Extract panel queries. |
| `FolderSyncDefinition` | 8 | Folder export. Recurse `children[]`; extract from nested dashboards & saved searches. |
| `SavedSearchWithScheduleSyncDefinition` | 3 (top-level) + 68 (nested) | Saved/scheduled search. Extract `search.queryText`. |
| `LookupTableSyncDefinition` | 3 | No query — skip (count in stats). |

### Object shapes

**Dashboard** (`DashboardV2SyncDefinition`)
- `name`, `title`, `description` — dashboard-level context.
- `panels[]` — each has `key`, `title`, `description`, `panelType`, `visualSettings` (JSON string).
  - `panelType: SumoSearchPanel` → `queries[]` (usually 1). Each query: `queryString`, `queryType` (`Logs`|`Metrics`|`Traces`), `queryKey`, `metricsQueryMode` (`Advanced`|`Basic`|null), `metricsQueryData` (structured, ~non-null for Basic metrics).
  - `panelType: TextPanel` → `text` (markdown). No query — used as **context** (row headers / notes).
  - `panelType: TracesListPanel` → traces query.
- `variables[]` — template variables (`name`, `defaultValue`, `sourceDefinition.values`, `allowMultiSelect`, `includeAllOption`). Appear in queries as `{{name}}`.
- `layout.layoutStructures[]` — grid position per panel `key`: `structure` is a JSON string `{height,width,x,y}`. Used to derive spatial context (which text panel heads a row of search panels).

**Folder** (`FolderSyncDefinition`)
- `name`, `children[]` — children may be folders (nested, up to 3+ levels), dashboards, or saved searches.
- **Context rule (per user):** use the *immediate* parent folder name as context, not the full ancestor chain.

**Saved search** (`SavedSearchWithScheduleSyncDefinition`)
- `name`, `description`, `search.queryText`, `search.defaultTimeRange`, `search.queryParameters[]`.
- Treated as a single Logs query with the object name as its title/context.

### Query type / mode inventory (whole `apps/` tree)
- Panels: `SumoSearchPanel` 2427, `TextPanel` 446, `TracesListPanel` 2.
- Queries: Logs 1791, Metrics 996, Traces 2.
- Metrics with structured `metricsQueryData` (Basic mode): 28.
- Nested saved searches: 68.

## Extracted record schema

Records are **deduplicated by `(queryType, normalized query text)`** — byte-identical
queries collapse into one record whose `sources[]` lists every place it appears.

```jsonc
{
  "id": "q0001",
  "hash": "<sha1 of queryType + '\\n' + query>",
  "queryType": "Logs | Metrics | Traces",
  "queryMode": "Logs | Metrics-Advanced | Metrics-Basic | Traces | SavedSearch",
  "query": "<raw queryString / search.queryText>",
  "parameters": ["user", "expected_asn_geo_regex"],   // distinct {{...}} tokens in query
  "scopes": ["_index=sumologic_audit_events", "_view=..."], // parsed index/view scope (best-effort)
  "operators": ["json", "geoip", "lookup", "where", "count"], // parsed pipe operators (best-effort)
  "metricsQueryData": { ... } | null,                  // preserved for Basic-mode metrics
  "sourceCount": 2,
  "sources": [
    {
      "file": "apps/audit/sumologic_login_api_activity.json",
      "objectType": "Dashboard | SavedSearch",
      "folder": null,                     // immediate parent folder (folder exports only)
      "dashboardName": "Sumo Logic Login and API Activity",
      "dashboardDescription": "...",
      "panelTitle": "Access Key Changes: ...",
      "panelType": "SumoSearchPanel",
      "panelKey": "panelPANE-...",
      "visualization": "table",           // visualSettings general.type
      "rowContext": ["API Access Activity and Configuration Changes"], // nearest text-panel header above + same-row text
      "variables": [ {"name":"user","defaultValue":"*","values":""} ] // dashboard template vars
    }
  ]
}
```

### Context derivation from `layout`
1. Parse each `layoutStructures[].structure` (JSON string) → `{x,y,w,h}` keyed by panel key.
2. For each search panel, find text panels where `text_y <= panel_y` (above/at) — the one with
   the **largest** such `y` is the nearest **header**; also capture text panels whose y-range
   overlaps the panel (same row). Store their `title`+`text` in `rowContext`.
3. Fallback: if no layout entry, attach all dashboard text-panel titles as weak context.

## Outputs (all under `ask_rick/`)

```
ask_rick/
├── docs/dev/extraction-plan.md      # this file
├── scripts/extract_queries.py        # the scraper (stdlib only)
├── scripts/build_webview.py          # embeds slim library into the HTML
├── output/
│   ├── query_library.json            # SLIM deduped query DB (browse index + upload fields)
│   ├── query_library.html            # webview (slim JSON embedded; links out to details/)
│   ├── details/q0001.json …          # one file per record: heavy/extended data
│   └── extraction_log.json           # stats + warnings + errors
```

### Slim main vs. detail split (size control)
To keep the embedded webview payload small, the main `query_library.json` carries only
lightweight, always-needed fields; verbose data lives in per-record `details/<id>.json`
files reached by a click-through link in the webview.

- **Main (embedded):** `id, hash, queryType, queryMode, query, parameters, scopes,
  operators, viewerType, queryParameters, sourceCount, detailFile`, and slim `sources[]`
  (`file, objectType, folder, dashboardName, panelTitle, panelType, visualization`).
- **Detail (`details/<id>.json`):** full `sources[]` incl. `dashboardDescription`,
  `rowContext`, dashboard `variables`, raw `visualSettingsRaw`, plus `metricsQueryData`
  and `tracesQueryData`.

The query text itself stays in the main JSON (it is the searchable payload and is what
you asked to keep inline). A record only gets a detail file when it actually has extended
data (`detailFile: null` otherwise).

## Upload target — logSearches (Saved Searches) API

A planned extension pushes this library into a Sumo instance as saved searches. Reference
export samples were pulled to a gitignored `tmp/` (`sumo api logSearches --json` for the
default and `--instance demo`) and inspected. Mapping from a dashboard panel query → a
logSearches API object:

| Saved-search field | Source in extraction | Notes |
|---|---|---|
| `queryString` | record `query` | verbatim |
| `queryParameters[]` | record `queryParameters` (pre-built) | each `{{param}}` → `{name, dataType:"ANY", value:<dashboard default>, description, autoComplete:SKIP_AUTOCOMPLETE}` |
| `properties.aggregateViewerType` | record `viewerType` | mapped from panel `visualSettings.general.type` (table/bar/line/…); defaults to `table` |
| `properties.logsQueryMode` | record `queryMode` | `Advanced` for logs/advanced-metrics |
| `name` / `description` | source `panelTitle` / dashboard name+desc | for library placement |

**Parameter type decision (confirmed):** params are emitted as `dataType: "ANY"` — this is
the closest match to dashboard `{{param}}` substitution (raw text insert, no added quoting),
even though `ANY` is not the API default.

**Visual settings:** dashboard panel `visualSettings` is a canvas.js JSON blob and is *similar
but not identical* to what a saved search stores. The raw `visualSettingsRaw` is preserved in
each detail record so a future uploader can attempt conversion (or at minimum map
`general.type` → `aggregateViewerType`). Full conversion is deferred — flagged as tricky.

### Webview (single self-contained HTML)
- JSON DB embedded inline (double-click to open from disk; no server / CORS issues).
- Left: full-text search box + facet filters (queryType, queryMode, operator, parameter presence, source app/folder).
- Center: results list (query title context + snippet + type badge + source count).
- Right / modal: inspect view — full query (monospace, copy button), parameters, scopes,
  operators, all sources with dashboard/folder/panel context and viz type.
- Export: selected/filtered results → JSON and CSV download (client-side Blob).

### Stats & logging (`extraction_log.json`)
- `filesScanned`, `filesParsedOk`, `filesFailed[]{file,error}`.
- `objectsProcessed` by type; `panelsProcessed`; `queriesExtracted`; `uniqueQueries`; `byQueryType`.
- `warnings[]{file,context,message}` (e.g. empty query, unparseable visualSettings/layout, panel with no query).
- `errors[]` (parse failures — e.g. the known 0-byte `apps/nginx-ingress-logs-only/logs-only.json`).

## Operators, metadata fields & AI enrichment

**Operators** (`operators`): distinct Sumo operators/functions used in a query, matched
against the canonical vocabulary lifted from the VS Code Sumo syntax highlighter
(`Hajime/syntaxes/sumo.tmLanguage.json`) — the pure boolean keywords (`and/or/not/in/name`)
are excluded to avoid false positives. Matching runs on a comment-stripped copy of the query.

**Metadata fields** (`metadataFields`): distinct Sumo special/metadata fields (the `_`-prefixed
tokens such as `_index`, `_sourceCategory`, `_timeslice`, `_raw`, `_count`), normalized to
lowercase since Sumo metadata fields are case-insensitive.

**AI enrichment** (optional, one-time): `scripts/enrich_queries.py` calls Claude
(default `claude-haiku-4-5` for cost; `--model claude-opus-4-8` for higher quality; structured
outputs) to generate a plain-English `description` and semantic
`tags` for each query, written to `output/enrichment/<id>.json` keyed by query **hash** (so it
survives re-extraction while the query text is unchanged). The script is idempotent/resumable
(skips queries that already have a matching-hash enrichment file) and takes `--limit`, `--model`,
`--force`. `build_webview.py` merges enrichment by hash at build time — the canonical
`query_library.json` stays pure extraction. A small **authored demo set** (10 queries) ships in
`output/enrichment/` so the webview shows the feature before a full API run.

The webview exposes **tags**, **operators**, and **metadata fields** as additional facets
(top 40 each), shows the description on each card and in the modal, and includes all of them in
the CSV/JSON export.

## Approach / phasing
1. **Plan** (this doc). ✅
2. **Test run** — script runs against an explicit file list of 5 diverse objects:
   - `apps/audit/sumologic_login_api_activity.json` (logs, template vars, text-panel context)
   - `apps/metrics/metric_discovery_and_guided_search.json` (Metrics — Advanced mode, many params)
   - `apps/kubernetes/kubernetes_collection_app_versions/kubernetes_app_4.6.json` (Metrics — Basic mode, `metricsQueryData`)
   - `apps/Tracing and Spans/tracing errors - span details.json` (Traces panel)
   - `apps/_sumoAdmin_all_the_admin_apps/_SumoAdmin.json` (nested folders + saved searches; immediate-parent-folder context)
3. **Evaluate** the test JSON + webview together, then iterate.
4. **Full run** — glob `apps/**/*.json`; same script, whole-tree input.

## Decisions (confirmed)
- **Scope:** include both dashboard panel queries and nested SavedSearch queries.
- **Delivery:** single self-contained HTML (JSON embedded inline).
- **Dedup:** collapse byte-identical queries into one record with a merged `sources[]`.
- Metrics **Basic** mode: keep `queryString` if present; always preserve `metricsQueryData`.
- Folder context: **immediate** parent folder only.

## Open items / edge cases tracked
- Empty/corrupt files (0-byte) → logged as errors, not crash.
- `metricsQueryData` (Basic) has no `queryString` — the searchable "query" text is derived from
  the structured object; preserve raw structure for inspection.
- Non-breaking spaces / trailing whitespace in names → normalize for display, keep raw.
- Traces queries (`tracesQueryData`/`spansQueryData`) — minimal volume (2); capture raw.
```

# Sumo Logic Query Library

A searchable, browsable library of **2,418 unique Sumo Logic queries** scraped from the
dashboard, folder, and saved-search exports in this repository — with plain-English
descriptions, semantic tags, and a self-contained web UI to search, filter, inspect, and
export them.

**▶ Live library:**
<https://rjury-sumo.github.io/sumo-public-content/ask_rick/output/query_library.html>

The goal: turn the custom admin and power-user searches scattered across many dashboards into
one reusable reference that applies to any Sumo Logic instance — a starting point for building,
adapting, or uploading queries.

---

## Use cases covered

The library is extracted from real dashboards, so it clusters around the domains those
dashboards address. Browse by tag/facet in the web UI; the major themes:

| Domain | What you'll find | Example sources |
|---|---|---|
| **Sumo administration & enterprise audit** | Account, content, user/role, security, collector & data-forwarding audit; login/API activity; access-key and configuration change tracking | `_sumoAdmin`, `audit`, `search_audit` |
| **Cost, credits & data tiers** | Data-volume analysis, credit/capacity utilization, Flex & Infrequent tier scan volume, ingest spikes | `data-tiers`, `credits`, `credits_usage_summary` |
| **Kubernetes & infrastructure** | Node/pod/container/deployment metrics, CPU/memory/disk, collection health, capacity planning | `kubernetes`, `host metrics`, `AWS-EC2` |
| **Cloud SIEM & SOC** | Insights, signals, records analysis, SOC KPIs/KRIs, rule & mapping health | `CSIEM` |
| **Distributed tracing** | Trace/span error analysis, service & operation breakdowns | `Tracing and Spans`, `RUM` |
| **Cloud & app logs** | AWS CloudTrail, EC2, nginx access/ingress, generic log exploration | `aws`, `cloudtrail`, `nginx-*`, `log_explorers` |
| **Search governance & automation** | Search-usage-per-query analysis, scheduled searches, SOAR automation, monitors | `search_audit`, `scheduled_search`, `SOAR Automation Services`, `monitors` |

**Query techniques represented** (also facetable): `json-parsing`, `timeslice`, `transpose`,
`geoip`, `lookup`, `topk`, `quantize`, `compare-with-timeshift`, plus `anomaly-detection`,
`capacity-planning`, `troubleshooting`, and `alerting` intents.

**Typical ways to use it:**
- **Find a query** for a task ("how do I audit access-key changes?", "top CPU nodes", "search
  usage by user") and copy it into Search.
- **Learn patterns** — filter by operator (e.g. `geoip`, `transpose`) or metadata field (e.g.
  `_index=sumologic_audit_events`) to see real examples of a technique.
- **Seed a new dashboard or instance** — export a filtered set (JSON/CSV) and adapt.
- **Bulk-upload** curated searches into an instance as saved searches (the library records
  logSearches-API-ready parameters — see *Reusing queries* below).

---

## The library at a glance

| | |
|---|---|
| Source files scanned | 81 (dashboards, folders, saved searches, lookups) |
| Objects | 221 dashboards · 41 folders · 68 saved searches |
| Unique queries | **2,418** (deduplicated from 2,926 occurrences) |
| By type | Logs 1,928 · Metrics 996 · Traces 2 |
| Descriptions + tags | 2,418 / 2,418 (AI-enriched) |

---

## The web UI

`output/query_library.html` is self-contained (query data embedded inline — opens from disk or
GitHub Pages, no server needed):

- **Full-text search** across query text, description, tags, operators, fields, and dashboard context.
- **Progressive faceted filtering** — Query type, mode, source app, tags, operators, metadata
  fields. Facets rescope to the current result set (selecting `Metrics` collapses the operator
  list to operators actually used in metrics queries); top-20 + in-section search + removable
  chips; "Clear all" / per-section clear.
- **Inspect modal** — full query with copy button, description, tags, template parameters,
  scope, operators, source dashboards/panels, and upload-ready logSearches parameters.
- **Export** the filtered set to JSON or CSV.

---

## Command-line browser (`scripts/querylib.py`)

A terminal companion to the web UI — same data (`query_library.json` + `enrichment.json`
merged by hash), tabular or `--json` output, no API calls. Three commands:

```
# list queries (filterable) or facet values
python3 scripts/querylib.py list                         # first N queries (table)
python3 scripts/querylib.py list tags                    # tag values + counts
python3 scripts/querylib.py list apps --json

# multi-criteria search (OR within a repeatable flag, AND across flags)
python3 scripts/querylib.py filter --text "access key" --type Logs
python3 scripts/querylib.py filter --tag geoip --tag security --operator lookup -n 30
python3 scripts/querylib.py filter --app kubernetes --field _sourcecategory --json

# full detail for one query (by id or hash)
python3 scripts/querylib.py show q0404
python3 scripts/querylib.py show q0404 --json
```

Filters: `--text`, `--type`, `--mode`, `--app`, `--tag`, `--operator`, `--field`, `--param`,
`--scope` (repeatable flags are OR within, AND across). Every command takes `--json`,
`--no-color`, and `-n/--limit` (`-n 0` = all). `--json` emits a `{status, ...}` envelope for
scripting/piping.

## Folder structure

```
ask_rick/
├── readme.md                       # this file
├── docs/dev/
│   ├── extraction-plan.md          # design: data model, schema, approach
│   └── enrichment-prompt.md        # bring-your-own-model enrichment guide
├── scripts/
│   ├── extract_queries.py          # scrape exports → query_library.json + details/
│   ├── querylib.py                 # CLI: list / filter / show (tabular or --json)
│   ├── build_webview.py            # build the self-contained HTML (merges enrichment)
│   ├── make_enrichment_input.py    # slim, dashboard-grouped input for enrichment
│   ├── enrich_queries.py           # optional: AI enrichment via Anthropic API
│   └── repair_enrichment.py        # re-key enrichment.json to the library by hash
└── output/
    ├── query_library.json          # the query DB (browse index + upload fields)
    ├── query_library.html          # the web UI
    ├── enrichment.json             # descriptions + tags (keyed by query hash)
    ├── enrichment_input.json       # dashboard-grouped input for an enrichment run
    ├── extraction_log.json         # run stats, warnings, errors
    └── details/<id>.json           # per-query heavy data (visual settings, sources, etc.)
```

---

## How it's built

1. **Extract** — walk the repo for Sumo exports, dedupe queries by `(type, text)`, capture
   operators, metadata fields, template params, layout-derived context, and logSearches-API
   upload fields:
   ```
   python3 scripts/extract_queries.py --tree
   ```
2. **Enrich** (optional but recommended) — generate a plain-English description + tags per query.
   Either run the API script, or use the bring-your-own-model Claude Desktop flow in
   `docs/dev/enrichment-prompt.md`:
   ```
   python3 scripts/make_enrichment_input.py            # full input (grouped by dashboard)
   python3 scripts/make_enrichment_input.py --missing-only   # only un-described queries
   # ... produce enrichment.json ...
   python3 scripts/repair_enrichment.py                # re-key ids to the current library
   ```
3. **Build the UI** — merges enrichment (by hash) and embeds everything:
   ```
   python3 scripts/build_webview.py
   ```

Enrichment is matched by **query hash**, so it survives re-extraction: after adding dashboards,
re-run `--tree`, enrich only the new queries with `--missing-only`, `repair_enrichment.py`, and
rebuild.

---

## Reusing queries

Each record carries fields that map onto the Sumo **logSearches (Saved Searches) API**, so a
filtered export can be turned into saved searches in any instance:

- `queryParameters` — one per `{{param}}`, emitted as `dataType: "ANY"` with the dashboard
  default as `value` (closest match to dashboard template substitution).
- `viewerType` — the panel visualization mapped to `properties.aggregateViewerType`.

See `docs/dev/extraction-plan.md` for the full record schema and the API mapping.

---

## Notes

- The web UI is ~4.9 MB (all query data embedded). It loads fine from GitHub Pages or disk;
  via `htmlpreview.github.io` it works but loads slowly and detail-file links won't resolve.
- Descriptions/tags are AI-generated — accurate for browsing and clustering, but verify a query
  against your own data before relying on it operationally.
- Regenerated artifacts under `output/` are reproducible from the scripts.

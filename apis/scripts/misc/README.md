# Sumo Logic Standalone Python Tools

Two single-file Python scripts for read-only access to your Sumo Logic org.
No external dependencies — stdlib only. Requires **Python 3.10+**.

---

## Setup

### Credentials

Set environment variables before running either script:

```bash
export SUMO_ACCESS_ID=your_access_id
export SUMO_ACCESS_KEY=your_access_key
export SUMO_ENDPOINT=https://api.us2.sumologic.com   # see regions below
```

Or pass them inline with `--access-id`, `--access-key`, `--endpoint`.

**Region endpoints:**

| Region | Endpoint |
|--------|----------|
| US1 | `https://api.sumologic.com` |
| US2 | `https://api.us2.sumologic.com` |
| EU | `https://api.eu.sumologic.com` |
| AU | `https://api.au.sumologic.com` |

### Quick check

```bash
python sumo_api.py               # lists available endpoint aliases
python sumo_content.py --help    # shows subcommand reference
```

---

## sumo_api.py — REST API browser

Generic read-only GET access to Sumo Logic REST API endpoints. Handles
pagination automatically and outputs a consistent JSON envelope.

### Output format

Always outputs a JSON object with a `data` array — safe to pipe to `jq`:

```json
{
  "status": "success",
  "endpoint": "/v1/logSearches",
  "count": 50,
  "next_token": "VEZuRU4v...",
  "data": [ ... ]
}
```

Output is indented when stdout is a terminal, compact when piped.

### Endpoint aliases

All aliases are **case-insensitive** (`logsearches`, `logSearches`, and `LOGSEARCHES` all work).

**Resources:**

| Alias | API path | Notes |
|-------|----------|-------|
| `collectors` | `/v1/collectors` | Offset-paged (300/page). Use `--all` for large orgs. |
| `partitions` | `/v1/partitions` | |
| `scheduledViews` | `/v1/scheduledViews` | Also: `scheduled-view`, `scheduled-views` |
| `extractionRules` | `/v1/extractionRules` | Also: `fer`, `fers` |
| `fields` | `/v1/fields` | All returned in one call |
| `users` | `/v1/users` | |
| `roles` | `/v2/roles` | |
| `dashboards` | `/v2/dashboards` | |
| `monitors` | `/v1/monitors/search` | All monitors via search endpoint |

**Org config:**

| Alias | API path |
|-------|----------|
| `logSearches` | `/v1/logSearches` |
| `accessKeys` | `/v1/accessKeys` |
| `connections` | `/v1/connections` |
| `tokens` | `/v1/tokens` |
| `healthEvents` | `/v1/healthEvents` |
| `lookupTables` | `/v1/lookupTables` |
| `metricsSearches` | `/v2/metricsSearches` |
| `apps` | `/v1/apps` |
| `ingestBudgets` | `/v2/ingestBudgets` |
| `scanBudgets` | `/v1/budgets` |
| `dynamicParsingRules` | `/v1/dynamicParsingRules` |
| `transformationRules` | `/v1/transformationRules` |
| `dataMaskingRules` | `/v1/dataMaskingRules` |
| `dataForwardingDests` | `/v1/logsDataForwarding/destinations` |
| `dataForwardingRules` | `/v1/logsDataForwarding/rules` |
| `serviceAccounts` | `/v1/serviceAccounts` |
| `oauthClients` | `/v1/oauth/clients` |
| `macros` | `/v2/macros` |

> **Sources** are not in the OpenAPI spec. Access them via raw path:
> `python sumo_api.py /v1/collectors/12345/sources`

### Options

```
sumo_api.py <endpoint> [options]

  --id ID             Get a single item by ID (skips pagination)
  --param key=value   Extra query parameters (repeatable)
  --limit N           Max items to return; auto-paginates for endpoints with per-page caps
  --all               Fetch all pages (up to 50-page safety cap)
  --token TOKEN       Resume token-based pagination from a specific page
  --pretty            Indent JSON output (default when stdout is a terminal)
  --webview           Open results as an interactive HTML table in the browser
  --access-id ID      Override $SUMO_ACCESS_ID
  --access-key KEY    Override $SUMO_ACCESS_KEY
  --endpoint URL      Override $SUMO_ENDPOINT
```

### Examples

**List resources:**

```bash
# All collectors (one page, API default)
python sumo_api.py collectors

# All collectors across all pages
python sumo_api.py collectors --all

# All FERs, open in browser table
python sumo_api.py fer --webview

# All monitors
python sumo_api.py monitors

# Partitions as compact JSON (piped)
python sumo_api.py partitions | jq '.data[] | {name, analyticsTier, retentionPeriod}'
```

**Filter with jq:**

```bash
# Find saved searches containing "error"
python sumo_api.py logSearches --all | jq '.data[] | select(.name | ascii_downcase | contains("error")) | .name'

# List all alive collectors
python sumo_api.py collectors --all | jq '.data[] | select(.alive == true) | .name'

# Count users by role (requires role IDs to name mapping)
python sumo_api.py users --all | jq '[.data[].roleIds[]] | length'

# FERs that are disabled
python sumo_api.py fer --all | jq '.data[] | select(.enabled == false) | {name, scope}'

# Monitors by type
python sumo_api.py monitors | jq 'group_by(.monitorType) | map({type: .[0].monitorType, count: length})'
```

**Pagination:**

```bash
# logSearches API caps at 100/page — --limit 500 auto-paginates 5 pages
python sumo_api.py logSearches --limit 500

# Resume from a token printed in a previous run
python sumo_api.py logSearches --token VEZuRU4v...

# Fetch everything
python sumo_api.py logSearches --all
```

**Get a single item by ID:**

```bash
python sumo_api.py partitions --id my_partition_name
python sumo_api.py users --id 000000000ABC1234
python sumo_api.py dashboards --id abc123def456
```

**Raw paths (for endpoints not in the alias list):**

```bash
# Sources for a specific collector
python sumo_api.py /v1/collectors/12345/sources

# Archive jobs for a source
python sumo_api.py /v1/archive/12345/jobs

# Any v1/v2 path works
python sumo_api.py v2/dashboards
```

**Extra query parameters:**

```bash
# Filter users by email domain
python sumo_api.py users --param email=@example.com

# Health events for a specific type
python sumo_api.py healthEvents --param type=Collector

# Lookup tables with a name filter
python sumo_api.py lookupTables --param name=my_table
```

**Webview (interactive HTML table):**

```bash
# Opens in your default browser — sortable, filterable, with hover tooltips on nested objects
python sumo_api.py collectors --webview
python sumo_api.py monitors --webview
python sumo_api.py fer --all --webview
```

---

## sumo_content.py — Content library browser

Navigate, search, filter, and export items from the Sumo Logic content library.

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `ls <target>` | List direct children of a folder |
| `get <target>` | Show a content item/folder and its children |
| `search <target>` | Filter children by name, type, or date |
| `export <target>` | Export a content item/folder to JSON |
| `path <id>` | Resolve a content ID to its library path |

### Targets

| Target | Description |
|--------|-------------|
| `personal` | Your Personal folder |
| `global` | Global Library *(async job)* |
| `admin-recommended` | Admin Recommended content *(async job)* |
| `installed-apps` | Installed Apps *(async job)* |
| `/Library/path/...` | Path-based lookup |
| `<ID>` | Content ID (hex or decimal) |

### Common options (all subcommands)

```
  --admin             Use admin mode (isAdminMode: true) for shared/global content
  --json              Output raw JSON to stdout
  --output FILE       Save JSON output to a file
  --webview           Open results as an interactive HTML table in the browser
  --access-id ID      Override $SUMO_ACCESS_ID
  --access-key KEY    Override $SUMO_ACCESS_KEY
  --endpoint URL      Override $SUMO_ENDPOINT
```

### Examples

**Browse folders:**

```bash
# List your personal folder
python sumo_content.py ls personal

# List global library (requires async job — takes a few seconds)
python sumo_content.py ls global --admin

# List admin recommended content
python sumo_content.py ls admin-recommended --admin

# List a subfolder by path
python sumo_content.py ls "/Library/Admin Recommended"

# List a folder by ID
python sumo_content.py ls 0000000000ABC123
```

**Get item detail:**

```bash
# Show a folder's metadata and all children
python sumo_content.py get personal

# Show a specific item
python sumo_content.py get "/Library/Admin Recommended/AWS/CloudTrail"
```

**Search and filter:**

```bash
# Find all dashboards in your personal folder
python sumo_content.py search personal --type Dashboard

# Find items matching a name pattern
python sumo_content.py search personal --name "*CloudTrail*"

# Find items modified in the last 30 days
python sumo_content.py search personal --modified-after -30d

# Combine filters
python sumo_content.py search personal --type Search --name "*error*"

# Recursively search all sub-folders (BFS)
python sumo_content.py search personal --recurse

# Limit recursion depth
python sumo_content.py search global --name "*Kubernetes*" --recurse --max-depth 3 --admin

# Find only scheduled searches
python sumo_content.py search personal --type Search --scheduled

# Find unscheduled searches
python sumo_content.py search personal --type Search --unscheduled
```

**Export:**

```bash
# Export a dashboard to a temp file (path printed to stderr)
python sumo_content.py export 0000000000ABC123

# Export to a specific file
python sumo_content.py export 0000000000ABC123 --output /tmp/my_dashboard.json

# Export by path
python sumo_content.py export "/Library/Admin Recommended/AWS/CloudTrail" --admin --output cloudtrail.json
```

**Resolve a path:**

```bash
python sumo_content.py path 0000000000ABC123
# → /Library/Users/myuser@example.com/My Dashboards/My Dashboard
```

**JSON output for scripting:**

```bash
# List personal folder as JSON, pipe to jq
python sumo_content.py ls personal --json | jq '.children[] | select(.itemType == "Dashboard") | {name, id}'

# Find all saved searches recursively, save to file
python sumo_content.py search personal --type Search --recurse --json --output searches.json

# Count items by type
python sumo_content.py ls global --admin --json | jq '[.children[] | .itemType] | group_by(.) | map({type: .[0], count: length})'

# Get all dashboard IDs
python sumo_content.py search personal --type Dashboard --recurse --json | jq '[.results[] | .id]'
```

**Webview (interactive HTML table):**

```bash
# Opens in browser with type-filter dropdown, text search, and sortable columns
python sumo_content.py search personal --recurse --webview
python sumo_content.py search global --name "*error*" --recurse --admin --webview
python sumo_content.py ls personal --webview
```

---

## Tips

**Checking what's in an org quickly:**

```bash
python sumo_api.py collectors --all | jq '.count'
python sumo_api.py monitors | jq '.count'
python sumo_api.py partitions | jq '[.data[] | {name, analyticsTier}]'
python sumo_content.py ls personal
```

**Finding a specific item across the whole library:**

```bash
python sumo_content.py search global --name "*CloudTrail*" --recurse --admin
```

**Exporting all dashboards from a folder:**

```bash
# First find their IDs
python sumo_content.py search personal --type Dashboard --json | jq -r '.results[].id'

# Then export each one
python sumo_content.py export <id> --output dashboard_<id>.json
```

**Using a different Sumo Logic org:**

```bash
# Inline credentials for a one-off call
python sumo_api.py collectors \
  --access-id $PROD_ID \
  --access-key $PROD_KEY \
  --endpoint https://api.us2.sumologic.com

# Or export per-org vars before running
export SUMO_ACCESS_ID=$PROD_ID
export SUMO_ACCESS_KEY=$PROD_KEY
export SUMO_ENDPOINT=https://api.us2.sumologic.com
```

**Rate limiting:** Both scripts automatically retry on HTTP 429 with exponential backoff (up to 3 retries). The content script also enforces ≤4 API calls/second to stay within Sumo Logic per-key limits.

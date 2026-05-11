---
name: sumo-search-job
description: Execute a single Sumo Logic search job and retrieve results (records or raw messages). Use when the user wants to run a Sumo Logic query, fetch log data, or get aggregated analytics results for a defined time range.
---

# Execute a Sumo Logic Search Job

Use `execute_search_job.py` to run a search and retrieve results. Follow every step in order.

---

## Step 1 — Determine credentials and region

Credentials come from environment variables or user-supplied values. **Never hardcode secrets.**

```bash
# Check whether env vars are already set
echo "SUMO_ACCESS_ID=${SUMO_ACCESS_ID:-(not set)}"
echo "SUMO_ACCESS_KEY=${SUMO_ACCESS_KEY:-(not set)}"
```

If unset, ask the user for `access_id`, `access_key`, and `region`. Valid regions: `us1 us2 eu au de jp ca in`.

---

## Step 2 — Create a YAML config for the query

Create a `.yaml` file in `apis/scripts/search_job/config_examples/` (or a temp file). Required fields: `name`, `query`, `from`, `to`.

```yaml
# Minimal working config
name: "my_search"
query: "_sourceCategory=prod/app | count by _sourceHost"
from: "-1h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
```

**Multiline queries** use the YAML pipe literal:
```yaml
query: |
  _sourceCategory=prod/app
  | where status >= 400
  | count by _sourceHost, status
  | sort by _count desc
```

**Time format options:**
```yaml
from: "-1h"                    # 1 hour ago
from: "-30m"                   # 30 minutes ago
from: "2024-01-01T00:00:00Z"  # ISO 8601
from: 1704067200000            # epoch milliseconds
to: "now"
```

---

## Step 3 — Choose the right mode

| Goal | Mode flag | requiresRawMessages |
|---|---|---|
| Aggregate/analytics results | `--mode records` | False (faster) |
| Raw log lines | `--mode messages` | True |
| Just create the job, no results | `--mode create-only` | — |

**Use `records` mode by default** unless raw log lines are explicitly needed. It is faster because `requiresRawMessages=False`.

---

## Step 4 — Choose an output format

| Flag | Best for |
|---|---|
| `--output json` | Single structured document |
| `--output jsonl` | Streaming / line-by-line processing |
| `--output csv` | Spreadsheet / pandas ingestion |
| `--output table` | Human-readable terminal display |
| `--output sumo-https` | Re-ingesting results into Sumo Logic |

---

## Step 5 — Run the command

```bash
cd apis/scripts/search_job

python execute_search_job.py \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/my_search.yaml \
  --mode records \
  --output csv \
  --output-file results.csv \
  --log-level INFO
```

**With explicit output directory:**
```bash
python execute_search_job.py \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/my_search.yaml \
  --mode records \
  --output jsonl \
  --output-directory ./output/ \
  --log-level INFO
```

**Tune polling** if queries are slow or the default 300 s timeout is too short:
```bash
  --poll-interval 10    # seconds between status checks (default: 5)
  --max-wait 600        # maximum seconds to wait (default: 300)
```

---

## Step 6 — Validate results

Check the output file exists and is non-empty before proceeding:

```bash
wc -l results.csv
head -5 results.csv
```

For JSONL:
```bash
head -1 output/my_search_records.jsonl | python -m json.tool
```

---

## Hard limits to respect

- **Aggregate records:** max 10,000 per job. If `recordCount` hits 10,000, the query likely needs a narrower time range or more selective filter.
- **Raw messages:** max 100,000 per job. For larger exports use the [sumo-bulk-messages](sumo-bulk-messages.md) skill.
- Both limits are API-enforced — the script will not silently truncate; it returns whatever the API delivers.

---

## Common errors and fixes

| Error | Likely cause | Fix |
|---|---|---|
| `HTTP 401 Unauthorized` | Wrong credentials or region | Verify `SUMO_ACCESS_ID`/`SUMO_ACCESS_KEY` and `--region` |
| `HTTP 400 Bad Request` | Malformed query or time range | Check YAML `query`, `from`, `to` fields |
| `FORCE PAUSED` state | Query timed out server-side | Narrow time range or add more selective filters |
| Empty output file | Query returned 0 results | Verify the query logic and time range manually in the Sumo UI |
| Timeout (`max-wait` exceeded) | Long-running query | Increase `--max-wait` or narrow the query |

---

## Example — Error rate by service (last 24 hours)

```yaml
# config_examples/error_rate.yaml
name: "error_rate_24h"
query: |
  _sourceCategory=prod/*
  | where status >= 500
  | timeslice 1h
  | count by _timeslice, service
  | sort by _timeslice asc
from: "-24h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
```

```bash
python execute_search_job.py \
  --region us1 \
  --access-id "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/error_rate.yaml \
  --mode records \
  --output csv \
  --output-file error_rate_24h.csv
```

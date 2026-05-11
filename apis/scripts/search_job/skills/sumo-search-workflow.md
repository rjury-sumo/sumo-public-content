---
name: sumo-search-workflow
description: Integrate Sumo Logic search results into agent analysis workflows. Use when the agent needs to query Sumo Logic as a data source for investigation, anomaly detection, reporting, or feeding results into downstream tools (pandas, databases, re-ingestion pipelines, etc.).
---

# Integrating Sumo Logic Search into Agent Workflows

This skill describes patterns for using `execute_search_job.py` as a data retrieval step inside a larger agentic or scripted workflow.

---

## Core pattern: query → retrieve → process

```
1. Write YAML config for the query
2. Run execute_search_job.py, capture output to file
3. Read and process the output file
4. Act on results (alert, report, store, re-ingest)
```

Always write results to a file first — do not rely on stdout for structured data.

---

## Pattern 1 — Investigation workflow

When investigating an incident or anomaly, chain queries from broad to narrow:

**Step 1: Broad error count across all services**
```yaml
# /tmp/step1_error_overview.yaml
name: "error_overview"
query: |
  _sourceCategory=prod/*
  | where status >= 500
  | count by service, status
  | sort by _count desc
from: "-2h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
```

```bash
python execute_search_job.py \
  --region us1 \
  --access-id "$SUMO_ACCESS_ID" --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config /tmp/step1_error_overview.yaml \
  --mode records --output jsonl --output-file /tmp/step1_results.jsonl
```

**Step 2: Read results and identify the worst service**
```python
import json

services = []
with open("/tmp/step1_results.jsonl") as f:
    for line in f:
        r = json.loads(line)["map"]
        services.append((r["service"], int(r["_count"])))

services.sort(key=lambda x: x[1], reverse=True)
worst_service = services[0][0]
print(f"Worst service: {worst_service} with {services[0][1]} errors")
```

**Step 3: Drill into that service for raw messages**
```yaml
# /tmp/step2_drill.yaml  (write programmatically)
name: "drill_into_service"
query: |
  _sourceCategory=prod/{{ worst_service }}
  | where status >= 500
from: "-2h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
```

---

## Pattern 2 — Scheduled report generation

Run a batch export on a schedule (cron or CI/CD) and post results to Sumo Logic:

```bash
#!/bin/bash
set -euo pipefail

DATE=$(date -u +%Y%m%d)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python "${SCRIPT_DIR}/execute_search_job.py" \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config "${SCRIPT_DIR}/config_examples/daily_summary.yaml" \
  --batch-mode \
  --batch-start "-1d" --batch-end "now" --batch-interval "1h" \
  --mode records \
  --output sumo-https \
  --sumo-https-url "$SUMO_HTTPS_ENDPOINT" \
  --sumo-timestamp add \
  --log-level WARNING   # suppress INFO noise in cron logs
```

---

## Pattern 3 — Anomaly detection feed

Query a metric-like aggregate, load into pandas, run a statistical check:

```python
import subprocess, json, tempfile, os, pandas as pd
from pathlib import Path

# 1. Write config dynamically
config = """
name: request_latency
query: |
  _sourceCategory=prod/api
  | timeslice 5m
  | avg(latency_ms) as avg_latency, p95(latency_ms) as p95_latency by _timeslice
from: "-4h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
"""
config_path = Path(tempfile.mktemp(suffix=".yaml"))
config_path.write_text(config)
output_path = Path(tempfile.mktemp(suffix=".jsonl"))

# 2. Run search
result = subprocess.run(
    [
        "python", "execute_search_job.py",
        "--region", os.environ["SUMO_REGION"],
        "--access-id",  os.environ["SUMO_ACCESS_ID"],
        "--access-key", os.environ["SUMO_ACCESS_KEY"],
        "--yaml-config", str(config_path),
        "--mode", "records",
        "--output", "jsonl",
        "--output-file", str(output_path),
        "--log-level", "WARNING",
    ],
    cwd="apis/scripts/search_job",
    check=True,
)

# 3. Load into pandas
rows = [json.loads(line)["map"] for line in output_path.read_text().splitlines()]
df = pd.DataFrame(rows)
df["avg_latency"] = pd.to_numeric(df["avg_latency"])
df["p95_latency"] = pd.to_numeric(df["p95_latency"])

# 4. Detect anomaly
baseline = df["p95_latency"].mean()
latest = df["p95_latency"].iloc[-1]
if latest > baseline * 1.5:
    print(f"ALERT: p95 latency {latest:.0f}ms is {latest/baseline:.1f}x above baseline {baseline:.0f}ms")
```

---

## Pattern 4 — Data pipeline (query → transform → store)

```python
import subprocess, json, os
from pathlib import Path

def run_sumo_query(config_yaml: str, output_path: str) -> list[dict]:
    """Run a search job and return records as a list of dicts."""
    config_path = Path("/tmp/sumo_query.yaml")
    config_path.write_text(config_yaml)

    subprocess.run(
        [
            "python", "execute_search_job.py",
            "--region",     os.environ["SUMO_REGION"],
            "--access-id",  os.environ["SUMO_ACCESS_ID"],
            "--access-key", os.environ["SUMO_ACCESS_KEY"],
            "--yaml-config", str(config_path),
            "--mode", "records",
            "--output", "jsonl",
            "--output-file", output_path,
            "--log-level", "WARNING",
        ],
        cwd="apis/scripts/search_job",
        check=True,
    )

    records = []
    with open(output_path) as f:
        for line in f:
            records.append(json.loads(line)["map"])
    return records


# Example use
records = run_sumo_query(
    config_yaml="""
name: "top_errors"
query: |
  _sourceCategory=prod/* | where status >= 500 | count by url | sort by _count desc | limit 20
from: "-1h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
""",
    output_path="/tmp/top_errors.jsonl",
)

for r in records[:5]:
    print(r["url"], r["_count"])
```

---

## Choosing records vs messages in a workflow context

| You need | Mode |
|---|---|
| Aggregated metrics, counts, statistics | `--mode records` |
| Raw log lines for parsing/regex | `--mode messages` |
| Feed a search result into another Sumo query | Export records as JSONL, re-ingest via `sumo-https` |
| Debug why a query returns unexpected results | `--mode messages` to see raw logs |

---

## Error handling in automated workflows

Always check the exit code. The script exits with code `1` on any error:

```bash
if ! python execute_search_job.py ... ; then
  echo "Search job failed — check logs" >&2
  exit 1
fi
```

In Python:
```python
import subprocess
try:
    subprocess.run([...], check=True, capture_output=True, text=True)
except subprocess.CalledProcessError as e:
    print(f"Search failed:\n{e.stderr}")
    raise
```

---

## Environment variable conventions

Set these before running any workflow:

```bash
export SUMO_ACCESS_ID="your_access_id"
export SUMO_ACCESS_KEY="your_access_key"
export SUMO_REGION="us1"            # or us2, eu, au, de, jp, ca, in
export SUMO_HTTPS_ENDPOINT="https://endpoint1.collection.us1.sumologic.com/receiver/v1/http/TOKEN"
```

Use a `.env` file with `direnv` or load via `source .env` for local development. **Never commit credentials to git.**

---

## Performance guidance for workflows

| Tip | Reason |
|---|---|
| Use `--mode records` over messages when possible | `requiresRawMessages=False` reduces job resource cost |
| Add selective filters early in the query pipeline | Reduces scan cost and improves speed |
| Use `byReceiptTime: false` unless you need ingest-time ordering | Receipt-time queries have higher overhead |
| Batch large time ranges rather than one massive job | Stays under API limits and allows incremental progress |
| Set `--log-level WARNING` in automated scripts | Keeps logs clean; errors still surface |
| Write output to `/tmp` for ephemeral pipeline steps | Avoids accumulating stale data files |

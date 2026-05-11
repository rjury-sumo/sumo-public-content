---
name: sumo-bulk-messages
description: Export large volumes of raw Sumo Logic log messages (potentially >100,000 events) using adaptive time bucketing. Use when the user needs raw log lines (not aggregates) across a large time range, when event volume per window may exceed 100,000, or when a CloudTrail/audit/compliance bulk export is required.
---

# Sumo Logic Bulk Raw Messages Export (Adaptive Bucketing)

The `--batch-messages-export` mode solves the 100,000-message-per-job API limit by automatically subdividing time windows until each bucket fits within the limit. It then paginates through messages (10,000 per page) within each bucket.

---

## How adaptive bucketing works

1. Runs a `timeslice | count` query to measure event density across the full time range.
2. Recursively splits any bucket that exceeds `--max-events-per-bucket` into halves.
3. Executes a messages job for each resulting optimal bucket.
4. Paginates within each job (10k messages per page, up to 100k per job).
5. Writes one output file per bucket, named with precise timestamps.

This ensures **no data is dropped** even when event rates vary significantly across the time window.

---

## Step 1 — Prepare config

```yaml
# config_examples/cloudtrail_export.yaml
name: "cloudtrail_export"
query: |
  _sourceCategory=aws/cloudtrail
  | where eventName != "AssumeRole"
from: "-1d"       # overridden by --batch-start
to: "now"         # overridden by --batch-end
timeZone: "UTC"
byReceiptTime: false
```

**Important:** Keep the query as selective as possible. Every message retrieved counts against your account's scan cost.

---

## Step 2 — Estimate volume first (recommended)

Before a large export, run a quick aggregate to understand event volume:

```bash
# Create a temporary count config
cat > /tmp/count_check.yaml <<'EOF'
name: "volume_check"
query: "_sourceCategory=aws/cloudtrail | count"
from: "-7d"
to: "now"
timeZone: "UTC"
byReceiptTime: false
EOF

python execute_search_job.py \
  --region us1 \
  --access-id "$SUMO_ACCESS_ID" --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config /tmp/count_check.yaml \
  --mode records --output table
```

Use the result to set `--max-events-per-bucket` appropriately.

---

## Step 3 — Run the bulk messages export

```bash
cd apis/scripts/search_job

python execute_search_job.py \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/cloudtrail_export.yaml \
  --batch-messages-export \
  --batch-start "-7d" \
  --batch-end   "now" \
  --batch-interval "1d" \
  --max-events-per-bucket 100000 \
  --confirm-export \
  --output jsonl \
  --output-directory ./output/ \
  --log-level INFO
```

**`--confirm-export`** prints the planned bucket list and asks for confirmation before starting — always use this for large exports so you can review the plan.

**`--max-events-per-bucket`** (default 100,000) — set lower (e.g., 50,000) for more conservative subdivision, or when you want smaller output files:
```bash
  --max-events-per-bucket 50000
```

---

## Step 4 — Monitor progress

The script prints a live progress bar to stderr showing:
- Current bucket index / total buckets
- Events retrieved so far
- Elapsed time and ETA

At completion it prints an export summary:
```
Export Summary:
  Total buckets processed: 42
  Total messages retrieved: 3,847,291
  Total output files: 42
  Output directory: ./output/
```

---

## Step 5 — Output files

Each bucket produces one file:

```
cloudtrail_export_messages_batch_000_20240101000000.000_20240102000000.000.jsonl
cloudtrail_export_messages_batch_001_20240101120000.000_20240102000000.000.jsonl  # subdivided
...
```

Note: subdivided buckets break the sequential index pattern — this is expected. Sort by the embedded timestamp, not the index.

**Each message record has the structure:**
```json
{"map": {"_raw": "...", "_messagetime": "...", "_sourceCategory": "...", ...}}
```

---

## Step 6 — Process the output

**Extract `_raw` field from all JSONL files:**
```python
import json, glob

for path in sorted(glob.glob("output/cloudtrail_export_messages_batch_*.jsonl")):
    with open(path) as f:
        for line in f:
            record = json.loads(line)
            raw_log = record["map"]["_raw"]
            # process raw_log ...
```

**Count total messages:**
```bash
wc -l output/cloudtrail_export_messages_batch_*.jsonl | tail -1
```

---

## Choosing parameters for different scenarios

| Scenario | `--batch-interval` | `--max-events-per-bucket` |
|---|---|---|
| Low-volume logs (< 10k/day) | `1d` | `100000` |
| Medium-volume (10k–500k/day) | `6h` or `1d` | `100000` |
| High-volume (> 500k/day) | `1h` or `6h` | `50000` |
| Compliance / audit (complete) | `1h` | `50000` |

---

## Hard limits

| Limit | Value |
|---|---|
| Messages per job | 100,000 (API hard cap) |
| Messages per page | 10,000 or 100 MB |
| Concurrent search jobs | Account-dependent |

If a bucket still hits 100,000 messages after subdivision, the bucket's time window is too wide. Reduce `--batch-interval` or `--max-events-per-bucket` and re-run.

---

## Resuming a failed export

If the export fails mid-way, check which bucket files were already written:

```bash
ls -la output/cloudtrail_export_messages_batch_*.jsonl | tail -5
```

The script does not currently support automatic resume — re-run the full export and use `--batch-start` set to the last successfully completed bucket's end time to continue from where it stopped.

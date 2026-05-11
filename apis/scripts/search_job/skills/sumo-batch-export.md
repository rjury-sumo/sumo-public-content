---
name: sumo-batch-export
description: Export Sumo Logic search results across a large time range by splitting it into sequential batch intervals. Use when the query spans days or weeks, when a single job would exceed the 10,000 record or 100,000 message limit, or when the user wants one output file per time window.
---

# Sumo Logic Batch Export

Batch mode runs the same query repeatedly over sub-intervals of a large time window, writing one output file per interval. Each file is named with the batch index and precise timestamps so they sort correctly.

---

## When to use batch mode vs single job

| Scenario | Use |
|---|---|
| < 10,000 aggregate records total | Single job (`--mode records`) |
| < 100,000 raw messages total | Single job (`--mode messages`) |
| Large time range, aggregate results | Batch mode (this skill) |
| Large time range, raw messages, possibly >100k/window | [sumo-bulk-messages](sumo-bulk-messages.md) |

---

## Step 1 — Prepare config

Same YAML format as a single job. The `from`/`to` fields in the YAML are **overridden** by `--batch-start` / `--batch-end` on the CLI, so you can leave them as placeholders.

```yaml
# config_examples/weekly_errors.yaml
name: "weekly_errors"
query: |
  _sourceCategory=prod/*
  | where status >= 500
  | count by _sourceHost, status
  | sort by _count desc
from: "-1h"       # overridden by --batch-start
to: "now"         # overridden by --batch-end
timeZone: "UTC"
byReceiptTime: false
```

---

## Step 2 — Choose a batch interval

Match the interval to expected data volume so no single job exceeds API limits.

| Data volume (per window) | Suggested interval |
|---|---|
| Low (< 1k records) | `1d` or larger |
| Medium (1k–8k records) | `6h` or `12h` |
| High (8k–10k records) | `1h` or `2h` |

Valid interval formats: `1h`, `6h`, `12h`, `1d`, `7d` (hours and days only).

---

## Step 3 — Run batch export

```bash
cd apis/scripts/search_job

python execute_search_job.py \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/weekly_errors.yaml \
  --batch-mode \
  --batch-start "-7d" \
  --batch-end   "now" \
  --batch-interval "1d" \
  --mode records \
  --output jsonl \
  --output-directory ./output/ \
  --log-level INFO
```

**ISO date ranges** (explicit start/end):
```bash
  --batch-start "2024-01-01T00:00:00Z" \
  --batch-end   "2024-01-31T23:59:59Z" \
  --batch-interval "1d"
```

---

## Step 4 — Understand the output files

Files are written to `--output-directory` (default `./output/`). Each file follows this naming pattern:

```
{name}_{mode}_batch_{index}_{from_timestamp}_{to_timestamp}.{ext}
```

Example:
```
weekly_errors_records_batch_000_20240101000000.000_20240102000000.000.jsonl
weekly_errors_records_batch_001_20240102000000.000_20240103000000.000.jsonl
...
weekly_errors_records_batch_006_20240107000000.000_20240108000000.000.jsonl
```

Files sort lexicographically in chronological order because of the zero-padded index and timestamp.

---

## Step 5 — Merge or process batch files

**Concatenate all JSONL files:**
```bash
cat output/weekly_errors_records_batch_*.jsonl > weekly_errors_all.jsonl
```

**Load into pandas:**
```python
import pandas as pd, glob

files = sorted(glob.glob("output/weekly_errors_records_batch_*.jsonl"))
df = pd.concat([pd.read_json(f, lines=True) for f in files], ignore_index=True)
print(df.shape)
```

**Concatenate CSV files (keep one header):**
```bash
head -1 output/weekly_errors_records_batch_000_*.csv > merged.csv
tail -n +2 -q output/weekly_errors_records_batch_*.csv >> merged.csv
```

---

## Tuning tips

- If any batch returns exactly 10,000 records, the job hit the API cap — shrink `--batch-interval`.
- If batches are tiny (< 100 records), consider a larger interval to reduce API call overhead.
- Add `--poll-interval 10 --max-wait 600` for slow/large queries.
- Use `--log-level DEBUG` to see per-batch timing.

---

## Re-ingest batch results into Sumo Logic

Pipe each batch file to a Sumo Logic HTTPS endpoint after export:

```bash
python execute_search_job.py \
  --region us1 \
  --access-id  "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config config_examples/weekly_errors.yaml \
  --batch-mode \
  --batch-start "-7d" --batch-end "now" --batch-interval "1d" \
  --mode records \
  --output sumo-https \
  --sumo-https-url "https://endpoint1.collection.us1.sumologic.com/receiver/v1/http/TOKEN" \
  --sumo-timestamp add
```

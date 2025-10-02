# execute_search_job.py

A comprehensive Python script for executing Sumo Logic search jobs with support for YAML configuration, batch processing, multiple output formats, and direct integration with Sumo Logic HTTPS endpoints.

## Overview

This script provides a flexible interface to the Sumo Logic Search Job API, allowing you to:
- Execute search queries from YAML configuration files
- Process large time ranges in batches
- Output results in multiple formats (JSON, CSV, Table, Sumo HTTPS)
- Automatically handle authentication and polling
- Support relative time specifications for convenience

## Installation

### Prerequisites
- Python 3.6+
- PyYAML library

### Install Dependencies
```bash
pip install PyYAML
```

### Make Script Executable
```bash
chmod +x execute_search_job.py
```

## Basic Usage

### Simple Query Execution
```bash
./execute_search_job.py --region us1 --access-id YOUR_ACCESS_ID --access-key YOUR_ACCESS_KEY --yaml-config search.yaml
```

### Using Environment Variables and CSV Output
```bash
python3 ./execute_search_job.py --region au \
  --access-id=$SUMO_ACCESS_ID --access-key=$SUMO_ACCESS_KEY \
  --yaml-config=test_search_config.yaml --mode records --output=csv
```

### Retrieving Raw Messages
```bash
python3 ./execute_search_job.py --region au \
  --access-id=$SUMO_ACCESS_ID --access-key=$SUMO_ACCESS_KEY \
  --yaml-config=test_search_config.yaml --mode messages
```

## Configuration

### Authentication Parameters
- `--region` or `--endpoint`: Sumo Logic region (us1, us2, eu, au, de, jp, ca, in) or full API endpoint URL
- `--access-id`: Your Sumo Logic access ID
- `--access-key`: Your Sumo Logic access key

### YAML Configuration File
Create a YAML file with your search parameters:

```yaml
# Required fields
name: "webapp_analysis"  # Unique name for this query (used in logging and output filenames)
query: "_sourceCategory=webapp | count by _sourceHost"
from: "-1h"  # 1 hour ago
to: "now"    # current time

# Optional fields
timeZone: "UTC"
byReceiptTime: false
```

**Required Fields:**
- `name`: Unique identifier for the query, used in logging output and default filenames
- `query`: The Sumo Logic search query to execute
- `from`: Start time for the search
- `to`: End time for the search

#### Time Format Options
The script supports multiple time formats:

1. **Relative Times**: `-1h`, `-30m`, `-2d`, `-1w`, `now`
2. **ISO Format**: `"2024-01-01T00:00:00Z"`
3. **Epoch Milliseconds**: `1704067200000`

#### Relative Time Examples
- `-1s` = 1 second ago
- `-15m` = 15 minutes ago
- `-2h` = 2 hours ago
- `-1d` = 1 day ago
- `-1w` = 1 week ago
- `now` = current time

## Execution Modes

### 1. Create Only (`--mode create-only`)
Creates the search job and returns the job ID only.
- **Performance**: `requiresRawMessages=False`
- **Use Case**: Job scheduling, job ID collection

```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config search.yaml --mode create-only
```

### 2. Messages Mode (`--mode messages`)
Retrieves raw log messages from the search results.
- **Performance**: `requiresRawMessages=True`
- **Use Case**: Log analysis, debugging, raw data export
- **Output Formats**: Only `json` and `jsonl` are supported

```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config search.yaml --mode messages --output json
```

### 3. Records Mode (`--mode records`)
Retrieves aggregate query results and computed fields.
- **Performance**: `requiresRawMessages=False` (optimized)
- **Use Case**: Analytics, reporting, metrics

```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config search.yaml --mode records
```

## Output Formats

### JSON (`--output json`)
Standard JSON output with full metadata.
```bash
--output json
```

### JSON Lines (`--output jsonl`)
JSON Lines format - one JSON object per line, no metadata wrapper.
```bash
--output jsonl
```

### Table (`--output table`)
Human-readable formatted table (records mode only).
```bash
--output table
```

### CSV (`--output csv`)
Comma-separated values format (records mode only).
```bash
--output csv --output-file results.csv
```

### Sumo HTTPS (`--output sumo-https`)
POST each record to a Sumo Logic HTTPS collector endpoint (records mode only).
```bash
--output sumo-https --sumo-https-url https://endpoint1.collection.us1.sumologic.com/receiver/v1/http/YOUR_TOKEN
```

#### Timestamp Addition
Add timestamps to records when posting to Sumo Logic:
```bash
--sumo-timestamp add  # Adds current timestamp as 13-digit epoch milliseconds
--sumo-timestamp none # Default: no timestamp added
```

## File Output

### Default File Naming
When no `--output-file` is specified, the script automatically generates filenames using the query name and mode:

**Single Query Mode:**
- `{query_name}_{mode}.{extension}`
- Example: `webapp_analysis_records.csv`

**Batch Mode:**
- `{query_name}_{mode}_batch_{index}_{from_time}_{to_time}.{extension}`
- Example: `webapp_analysis_records_batch_000_20251003140000.000_20251003150000.000.csv`

### Output Directory
By default, files are written to `./output/` directory:
```bash
--output-file results.csv  # Creates ./output/results.csv
```

If no output file is specified, defaults to `./output/` for non-STDOUT modes.

### Custom Output Directory
```bash
--output-file results.csv --output-directory /path/to/directory/
```

### File Naming Behavior
- **Filename only**: Uses output directory
- **Relative path**: Combines with output directory
- **Absolute path**: Ignores output directory
- **No filename specified**: Auto-generates name based on query name and mode

## Batch Processing

Process large time ranges by splitting them into smaller intervals and executing queries sequentially.

### Batch Parameters
- `--batch-mode`: Enable batch processing
- `--batch-start`: Start time for batch (overrides YAML `from`)
- `--batch-end`: End time for batch (overrides YAML `to`)
- `--batch-interval`: Time interval for each batch (default: `1h`)

### Batch Examples

#### Process Last 24 Hours in 1-Hour Intervals
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config search.yaml --batch-mode \
  --batch-start="-24h" --batch-end="now" --batch-interval="1h" \
  --mode records --output csv --output-file hourly_data.csv
```

#### Process Specific Date Range
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config search.yaml --batch-mode \
  --batch-start="2024-01-01T00:00:00Z" --batch-end="2024-01-02T00:00:00Z" \
  --batch-interval="6h" --mode records --output table
```

#### Process Last 7 Days in Daily Intervals Using Environment Variables
```bash
python3 ./execute_search_job.py --region au \
  --access-id=$SUMO_ACCESS_ID --access-key=$SUMO_ACCESS_KEY \
  --yaml-config=example_search_config.yaml --batch-mode \
  --batch-start="-7d" --batch-end="now" --batch-interval="1d" \
  --mode records
```

### Batch File Naming
Files are automatically named with batch information using formatted timestamps:
- `hourly_data_batch_000_20240101020000.000_20240101030000.000.csv`
- `hourly_data_batch_001_20240101030000.000_20240101040000.000.csv`

Timestamp format: `YYYYMMddHHmmss.SSS`

## Logging

Control log verbosity with `--log-level`:

### Log Levels
- `DEBUG`: Detailed progress including job polling status
- `INFO`: Major operations and progress (default)
- `WARNING`: Non-fatal issues
- `ERROR`: Fatal errors only
- `CRITICAL`: Severe system issues

### Examples
```bash
# Quiet mode - errors only
--log-level ERROR

# Verbose mode - detailed progress
--log-level DEBUG
```

### Log Output Example
```
2025-09-22 14:16:48 - INFO - Single query: 2025-09-21 14:16:48 to 2025-09-22 14:16:48
2025-09-22 14:16:48 - INFO - [webapp_analysis] No output file specified, using default: webapp_analysis_records.csv in ./output/
2025-09-22 14:16:48 - INFO - [webapp_analysis] Creating search job with query: _sourceCategory=*
2025-09-22 14:16:49 - INFO - [webapp_analysis] Search job created with ID: ABC123
2025-09-22 14:16:49 - INFO - [webapp_analysis] Job ABC123 completed successfully
2025-09-22 14:16:49 - INFO - Output written to: ./output/webapp_analysis_records.csv
```

All log messages include the query name in brackets `[query_name]` for easy identification when running multiple queries.

## Advanced Examples

### 1. Analytics Workflow
Export hourly metrics to CSV files:
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config analytics.yaml --batch-mode \
  --batch-start="-7d" --batch-end="now" --batch-interval="1h" \
  --mode records --output csv --output-file metrics.csv \
  --output-directory ./reports/ --log-level INFO
```

### 2. Real-time Data Ingestion
Send query results directly to Sumo Logic with timestamps:
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config transform.yaml --mode records \
  --output sumo-https \
  --sumo-https-url https://endpoint1.collection.us1.sumologic.com/receiver/v1/http/TOKEN \
  --sumo-timestamp add
```

### 3. Debug Investigation
Get raw messages for troubleshooting:
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config debug.yaml --mode messages \
  --output json --output-file debug_messages.json \
  --log-level DEBUG
```

### 4. Scheduled Reporting
Generate daily reports:
```bash
./execute_search_job.py --region us1 --access-id ID --access-key KEY \
  --yaml-config daily_report.yaml --mode records \
  --output table --output-file daily_report.txt \
  --output-directory ./reports/$(date +%Y-%m-%d)/
```

## Error Handling

The script provides comprehensive error handling:

- **Authentication errors**: Clear messages for invalid credentials
- **API errors**: Detailed HTTP error information
- **Configuration errors**: Validation of required YAML fields
- **Network errors**: Timeout and connection issue handling
- **File errors**: Directory creation and write permission issues

## Performance Considerations

### requiresRawMessages Optimization
The script automatically optimizes the `requiresRawMessages` parameter:
- **Messages mode**: `true` (raw messages needed)
- **Records mode**: `false` (better performance for aggregates)
- **Create-only mode**: `false` (not retrieving results)

### Batch Processing Benefits
- **Large time ranges**: Avoid API timeouts
- **Memory efficiency**: Process data in chunks
- **Parallel analysis**: Separate files for each time interval
- **Fault tolerance**: Continue processing if individual batches fail

## Troubleshooting

### Common Issues

1. **PyYAML not found**
   ```bash
   pip install PyYAML
   ```

2. **Permission denied on output directory**
   ```bash
   mkdir -p ./output && chmod 755 ./output
   ```

3. **Invalid time format**
   - Use quotes for negative relative times: `--batch-start="-24h"`
   - Verify ISO format: `"2024-01-01T00:00:00Z"`

4. **sumo-https validation errors**
   - Only works with `--mode records`
   - URL must start with `https://`
   - `--sumo-https-url` parameter is required

5. **messages mode output format error**
   - Messages mode only supports `--output json` or `--output jsonl`
   - Table, CSV, and sumo-https outputs are not available for messages mode

### Debug Mode
Use `--log-level DEBUG` to see detailed execution information:
```bash
./execute_search_job.py --log-level DEBUG [other options]
```

## Integration Examples

### Cron Job Setup
```bash
# Daily report at 2 AM
0 2 * * * /path/to/execute_search_job.py --region us1 --access-id ID --access-key KEY --yaml-config daily.yaml --mode records --output csv --output-file daily.csv
```

### Shell Script Integration
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./execute_search_job.py \
  --region us1 \
  --access-id "$SUMO_ACCESS_ID" \
  --access-key "$SUMO_ACCESS_KEY" \
  --yaml-config "$1" \
  --mode records \
  --output csv \
  --output-file "report_$(date +%Y%m%d).csv" \
  --log-level INFO
```

## License

This script is provided as-is for use with Sumo Logic APIs. Please ensure compliance with your organization's data handling and API usage policies.
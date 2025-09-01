# flog_oltp.py as a flog wrapper

** DISCLAIMER: My buddy Claude wrote most of this - mileage may vary! **
He also wrote his [own readme file](readme.claudes.version.md) version as thought he could do better than me.

flog_otlp is a python wrapper to take STDOUT from [flog](https://github.com/mingrammer/flog) which can generate log file samples for formats like apache and json, then encode these in a OTLP compliant wrapper and forward to an OTLP endpoint. You can also provide custom attributes. I created this for testing sending OTLP log data to Sumo Logic but it could be applicable to any OTLP compliant receiver.

Mapping for flog payload:
- The flog event is encoded in a "log" json key.
- otlp-attributes: add resource-level attributes map to "fields" in sumologic. Fields are posted seperate to the log body and stored in the index with data but each named field must first be must be enabled or it's suppressed.
- telemetry-attributes: add log-level attributes that appear as json keys in the log event body in sumo logic.

Example standard body as it appears in sumo side:

```
{"log.source":"flog","log":"41.253.249.79 - rath4856 [27/Aug/2025:16:31:15 +1200] \"HEAD /empower HTTP/2.0\" 501 8873"}
```

### install flog

```bash
brew tap mingrammer/flog
brew install flog
```

# Executing flog-otlp
format options for -f are: apache_common,apache_combined,apache_error,rfc3164,rfc5424,common_log,json

## One time usage

```bash
python3 ./flog-otlp/flog_otlp.py                              # Default: 200 logs over 10 seconds
python3 ./flog-otlp/flog_otlp.py -n 100 -s 5s                 # 100 logs over 5 seconds  
python3 ./flog-otlp/flog_otlp.py -f apache_common -n 50       # 50 Apache common format logs
python3 ./flog-otlp/flog_otlp.py -f json -n 100 --no-loop     # 100 JSON logs, no infinite loop
python3 ./flog-otlp/flog_otlp.py --otlp-endpoint https://collector:4318/v1/logs  # Custom endpoint
python3 ./flog-otlp/flog_otlp.py --otlp-attributes environment=production --otlp-attributes region=us-east-1
python3 ./flog-otlp/flog_otlp.py --telemetry-attributes app=web-server --telemetry-attributes debug=true
python3 ./flog-otlp/flog_otlp.py --otlp-header "Authorization=Bearer token123" --otlp-header "X-Custom=value"
```

## Recurring Executions
This enables powerful use cases like continuous log generation for testing, scheduled batch processing, and long-running observability scenarios

### Smart Mode Detection
Single mode: When wait-time=0 and max-executions=1 (default)
Recurring mode: When wait-time>0 OR max-executions=1

The wrapper can call your flog command and forward logs on a configurable interval.

- --wait-time (seconds): Default: 0 (single execution),  > 0: Time to wait between flog executions
Examples: --wait-time 30, --wait-time 120.5
- --max-executions (count): Default: 1 (single execution), 0: Run forever until manually stopped (Ctrl+C), > 1: Run specified number of times
Examples: --max-executions 10, --max-executions 0

### Graceful Interruption:
Ctrl+C stops gracefully with summary report
Current execution completes before stopping
No data loss during interruption

```bash
# Run 10 times with 30 second intervals
python3 otlp_log_sender.py --wait-time 30 --max-executions 10

# Run forever with 1 minute intervals  
python3 otlp_log_sender.py --wait-time 60 --max-executions 0

# Generate 100 logs every 2 minutes, run 24 times (48 hours)
python3 otlp_log_sender.py -n 100 -s 5s --wait-time 120 --max-executions 24

# High-frequency: 50 logs every 10 seconds, run until stopped
python3 otlp_log_sender.py -n 50 -s 2s --wait-time 10 --max-executions 0

# JSON logs with custom attributes, 5 executions
python3 otlp_log_sender.py -f json -n 200 \
  --otlp-attributes environment=production \
  --wait-time 45 --max-executions 5

```

### Detailed Logging

```
Execution #3 started at 14:30:15 UTC
Executing: flog -f apache_common -n 100 -s 5s
[... processing logs ...]
Execution #3 completed in 7.2s (100 logs)
Waiting 30s before next execution...
Comprehensive Summary:
EXECUTION SUMMARY:
  Total executions: 5
  Total logs processed: 1,000  
  Total runtime: 187.3s
  Average logs per execution: 200.0
  Started: 2025-09-01 14:25:00 UTC
  Ended: 2025-09-01 14:28:07 UTC
```

## Parameters Reference

### OTLP Configuration
| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `--otlp-endpoint` | OTLP logs endpoint URL | `http://localhost:4318/v1/logs` | `https://collector:4318/v1/logs` |
| `--service-name` | Service name in resource attributes | `flog-generator` | `web-server` |
| `--otlp-attributes` | Resource-level attributes (repeatable) | None | `--otlp-attributes env=prod` |
| `--telemetry-attributes` | Log-level attributes (repeatable) | None | `--telemetry-attributes app=nginx` |
| `--otlp-header` | Custom HTTP headers (repeatable) | None | `--otlp-header "Auth=Bearer xyz"` |

### Log Generation (flog)
| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `-f, --format` | Log format | `apache_common` | `json`, `rfc5424`, `apache_combined` |
| `-n, --number` | Number of logs to generate | `200` | `1000` |
| `-s, --sleep` | Duration to generate logs over | `10s` | `5s`, `2m`, `1h` |
| `-r, --rate` | Rate limit (logs/second) | None | `50` |
| `-p, --bytes` | Bytes limit per second | None | `1024` |
| `-d, --delay-flog` | Delay between log generation | None | `100ms` |
| `--no-loop` | Disable infinite loop mode | False | N/A |

### Execution Control
| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `--wait-time` | Seconds between executions | `0` (single) | `30`, `120.5` |
| `--max-executions` | Number of executions (0=infinite) | `1` | `10`, `0` |
| `--delay` | Delay between individual log sends | `0.1` | `0.05`, `0` |
| `--verbose` | Enable verbose output | False | N/A |

### Supported Log Formats
- `apache_common` - Apache Common Log Format
- `apache_combined` - Apache Combined Log Format  
- `apache_error` - Apache Error Log Format
- `rfc3164` - RFC3164 (Legacy Syslog)
- `rfc5424` - RFC5424 (Modern Syslog)
- `common_log` - Common Log Format
- `json` - JSON structured logs
# OTLP Log Sender for flog

A Python utility that generates realistic log data using [flog](https://github.com/mingrammer/flog) and sends it to OpenTelemetry Protocol (OTLP) endpoints. Perfect for testing log pipelines, observability systems, and OTLP collectors.

## Features

- 🚀 **Multiple log formats**: Apache, RFC3164, RFC5424, JSON, and more
- 🔄 **Recurring executions**: Schedule log generation at regular intervals
- 🎯 **OTLP compliant**: Full OpenTelemetry Logs specification support
- ⚙️ **Highly configurable**: Custom attributes, headers, and metadata
- 📊 **Rich monitoring**: Real-time progress and execution summaries
- 🌍 **UTC timestamps**: Consistent timezone handling
- 🛡️ **Graceful interruption**: Clean shutdown with Ctrl+C

## Installation

### Prerequisites

1. **Python 3.7+** with `requests` library:
   ```bash
   pip install requests
   ```

2. **flog** log generator:
   ```bash
   go install github.com/mingrammer/flog@latest
   ```

### Download

```bash
wget https://raw.githubusercontent.com/your-repo/otlp_log_sender.py
chmod +x otlp_log_sender.py
```

## Use Cases

### 🧪 Testing & Development
- **OTLP collector testing**: Verify log ingestion pipelines
- **Observability platform testing**: Load test log processing systems  
- **Schema validation**: Test log parsing and field extraction
- **Performance benchmarking**: Measure throughput and latency

### 🔄 Continuous Testing
- **Synthetic log generation**: Create realistic log traffic patterns
- **Long-running tests**: Generate logs over hours/days for stability testing
- **Scheduled load testing**: Peak-time simulation with recurring executions
- **Multi-tenant testing**: Different service names and attributes per execution

### 📈 Monitoring & Alerting
- **Alert testing**: Trigger monitoring alerts with specific log patterns
- **Dashboard validation**: Populate dashboards with test data
- **SLA testing**: Verify log processing within time windows
- **Failover testing**: Test collector redundancy and failover

### 🏗️ Development & Staging
- **Local development**: Generate logs for feature development
- **CI/CD testing**: Automated log pipeline validation
- **Staging environment**: Realistic data for pre-production testing
- **Demo environments**: Populate demo systems with sample logs

## Quick Start

### Basic Usage
```bash
# Generate 200 Apache logs over 10 seconds (default)
python3 otlp_log_sender.py

# Generate JSON logs
python3 otlp_log_sender.py -f json -n 500 -s 30s

# Custom OTLP endpoint
python3 otlp_log_sender.py --otlp-endpoint https://my-collector:4318/v1/logs
```

### Recurring Executions
```bash
# Run 10 times with 30-second intervals
python3 otlp_log_sender.py --wait-time 30 --max-executions 10

# Run forever with 1-minute intervals (until Ctrl+C)
python3 otlp_log_sender.py --wait-time 60 --max-executions 0

# High-frequency testing: 100 logs every 10 seconds
python3 otlp_log_sender.py -n 100 -s 2s --wait-time 10 --max-executions 0
```

### Custom Attributes & Headers
```bash
# Add resource-level attributes
python3 otlp_log_sender.py \
  --otlp-attributes environment=production \
  --otlp-attributes region=us-east-1 \
  --otlp-attributes replica_count=3

# Add log-level attributes  
python3 otlp_log_sender.py \
  --telemetry-attributes app=web-server \
  --telemetry-attributes version=2.1.0 \
  --telemetry-attributes debug=true

# Custom headers (authentication, routing, etc.)
python3 otlp_log_sender.py \
  --otlp-header "Authorization=Bearer token123" \
  --otlp-header "X-Tenant-ID=customer-456"
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

## Advanced Examples

### Load Testing
```bash
# High-volume load test: 1000 logs/minute for 1 hour
python3 otlp_log_sender.py \
  -n 1000 -s 60s \
  --wait-time 0 --max-executions 60 \
  --delay 0.001 \
  --otlp-attributes test=load-test

# Burst testing: 500 logs every 30 seconds
python3 otlp_log_sender.py \
  -n 500 -s 5s \
  --wait-time 30 --max-executions 0 \
  --telemetry-attributes pattern=burst
```

### Multi-Service Simulation
```bash
# Web server logs
python3 otlp_log_sender.py \
  -f apache_combined -n 200 \
  --service-name web-server \
  --otlp-attributes component=frontend \
  --telemetry-attributes service_type=web &

# API server logs  
python3 otlp_log_sender.py \
  -f json -n 150 \
  --service-name api-server \
  --otlp-attributes component=backend \
  --telemetry-attributes service_type=api &
```

### Authentication & Security
```bash
# Bearer token authentication
python3 otlp_log_sender.py \
  --otlp-endpoint https://secure-collector:4318/v1/logs \
  --otlp-header "Authorization=Bearer $(cat token.txt)" \
  --otlp-header "X-API-Version=v1"

# Mutual TLS with custom headers
python3 otlp_log_sender.py \
  --otlp-endpoint https://mtls-collector:4318/v1/logs \
  --otlp-header "X-Client-Cert-Subject=cn=test-client" \
  --otlp-header "X-Tenant-ID=prod-tenant-123"
```

### Development & Testing
```bash
# Local development with debug info
python3 otlp_log_sender.py \
  -f json -n 50 -s 5s \
  --service-name local-app \
  --telemetry-attributes environment=development \
  --telemetry-attributes debug=true \
  --verbose

# CI/CD pipeline testing
python3 otlp_log_sender.py \
  --otlp-endpoint ${OTLP_ENDPOINT} \
  --otlp-attributes build_id=${BUILD_ID} \
  --otlp-attributes commit_sha=${COMMIT_SHA} \
  --telemetry-attributes pipeline=ci-test
```

## Output Examples

### Single Execution
```
OTLP Log Sender for flog
==============================
Executing: flog -f apache_common -n 200 -s 10s
Sending logs to: http://localhost:4318/v1/logs
--------------------------------------------------
Processing line 1: 127.0.0.1 - - [01/Sep/2025:14:30:15 +0000] "GET /index.html HTTP/1.1" 200 1234
✓ Log sent successfully
Processing line 2: 192.168.1.100 - - [01/Sep/2025:14:30:16 +0000] "POST /api/users HTTP/1.1" 201 567
✓ Log sent successfully
...
✓ Completed processing 200 log lines
✓ All logs processed successfully
```

### Recurring Executions
```
Starting recurring flog executions:
  Wait time between executions: 30.0s
  Max executions: 5
  Started at: 2025-09-01 14:30:00 UTC
============================================================

🔄 Execution #1 started at 14:30:00 UTC
[... processing logs ...]
✅ Execution #1 completed in 12.3s (200 logs)
⏳ Waiting 30s before next execution...

🔄 Execution #2 started at 14:30:42 UTC
[... processing logs ...]
✅ Execution #2 completed in 11.8s (200 logs)
⏳ Waiting 30s before next execution...

============================================================
📊 EXECUTION SUMMARY:
  Total executions: 5
  Total logs processed: 1,000
  Total runtime: 187.3s
  Average logs per execution: 200.0
  Started: 2025-09-01 14:30:00 UTC
  Ended: 2025-09-01 14:33:07 UTC
```

## Troubleshooting

### Common Issues

**Connection refused**
```bash
# Check if OTLP collector is running on the specified port
curl -v http://localhost:4318/v1/logs
```

**SSL/TLS errors**
```bash
# For HTTPS endpoints with self-signed certificates, modify the script to disable SSL verification
# (Not recommended for production)
```

**flog command not found**
```bash
# Install flog
go install github.com/mingrammer/flog@latest

# Verify installation  
flog --version
```

**High memory usage**
```bash
# Reduce batch size and add delays
python3 otlp_log_sender.py -n 50 --delay 0.1
```

### Debugging

Enable verbose output:
```bash
python3 otlp_log_sender.py --verbose
```

Test OTLP endpoint connectivity:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"test": "connectivity"}' \
  http://localhost:4318/v1/logs
```

## Integration with OTLP Collectors

### OpenTelemetry Collector
```yaml
# collector.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  logging:
    loglevel: info
  
service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [logging]
```

### Jaeger
```bash
# Run Jaeger with OTLP support
docker run -d --name jaeger \
  -p 14268:14268 -p 4318:4318 \
  jaegertracing/jaeger:latest
```

### Grafana Loki
Use the OpenTelemetry Collector with Loki exporter as an intermediary.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality  
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Related Projects

- [flog](https://github.com/mingrammer/flog) - Fake log generator
- [telemetrygen](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/cmd/telemetrygen) - OTLP telemetry generator
- [OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector) - Telemetry processing pipeline
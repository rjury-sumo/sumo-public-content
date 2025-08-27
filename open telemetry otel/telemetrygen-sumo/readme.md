# Telemetry Generator Options for OTLP

# References
- [telemetrygen](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/cmd/telemetrygen) to stream data to sumologic
- [otelgen](https://github.com/krzko/otelgen)
- [flog](https://github.com/mingrammer/flog)

# Pre-req Setup
- setup env var ```SUMOLOGIC_INSTALLATION_TOKEN```
- pull any docker images you might need later:
```bash
docker pull sumologic/sumologic-otel-collector:latest-ubi
docker pull otel/opentelemetry-collector:latest
docker pull otel/opentelemetry-collector-contrib:latest
docker pull sumologic/sumologic-otel-collector:latest
docker pull ghcr.io/krzko/otelgen:latest
```

# Run a otelcol-sumo container with the sumogic extension to relay OTLP data
Using sumologic extension to relay local OLTP telemetry to your sumologic instance. Staring otelcol-sumo with config.yaml as a container will expose local OTLP ports for forwarding.
- make sure you have a otelcol-data directory and config.yaml in $PWD

Config.yaml in this repo:
- names collector:  sumo_temeletrygen_tester
- defaults sourcecategory e.g: ```(_collector="sumo_temeletrygen_tester") AND _sourceCategory="otel/telemetrygen/test"```
- includes otel metrics in the collection configuration metric search: ```_collector=sumo_temeletrygen_tester metric=otelcol*```
- persists credentials and file storage locally. You need a local otelcol-data folder to persist the collector credentials and state, or use clobber as per: [sumologic extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/sumologicextension)

```bash
docker run --rm -ti -p 4317:4317 -p 4318:4318 \
  --env SUMOLOGIC_INSTALLATION_TOKEN="$SUMOLOGIC_INSTALLATION_TOKEN" \
  --name sumologic-otel-collector \
  -v "$(pwd)/otelcol-data:/var/lib/otelcol-sumo" \
  -v "$(pwd)/config.yaml:/etc/otel/config.yaml"  \
  sumologic/sumologic-otel-collector:latest-ubi
```

# Using flog_otlp wrapper or curl to send logs 

## direct for basic testing
Use curl to send an example json file

```bash
curl -i http://localhost:4318/v1/logs -X POST -H "Content-Type: application/json" -d @log.json
```

## using flog_oltp.py as a flog wrapper
flog_otlp is a python wrapper to take STDOUT from [flog](https://github.com/mingrammer/flog) which can generate log file samples for formats like apache and json, then encode these in a OTLP compliant wrapper and forward to an OTLP endpoint. You can also provide custom attributes.

The flog event is encoded in a "log" json key.

Example standard body as it appears in sumo side:

```
{"log.source":"flog","log":"41.253.249.79 - rath4856 [27/Aug/2025:16:31:15 +1200] \"HEAD /empower HTTP/2.0\" 501 8873"}
```

- otlp-attributes map to "fields" in sumologic so must be enabled to be indexed.
- telemetry-attributes map to message body in sumo logic so will add more keys to json payload

### install flog

```bash
brew tap mingrammer/flog
brew install flog
```

Running the wrapper - needs python3.
format options for -f are: apache_common,apache_combined,apache_error,rfc3164,rfc5424,common_log,json

```bash
# Basic usage
python3 ./flog-otlp/  flog_otlp.py                              # Default: 200 logs over 10 seconds
python3 ./flog-otlp/  flog_otlp.py -n 100 -s 5s                 # 100 logs over 5 seconds  
python3 ./flog-otlp/  flog_otlp.py -f apache_common -n 50       # 50 Apache common format logs
python3 ./flog-otlp/  flog_otlp.py -f json -n 100 --no-loop     # 100 JSON logs, no infinite loop
python3 ./flog-otlp/  flog_otlp.py --otlp-endpoint https://collector:4318/v1/logs  # Custom endpoint
python3 ./flog-otlp/  flog_otlp.py --otlp-attributes environment=production --otlp-attributes region=us-east-1
python3 ./flog-otl  flog_otlp.py --telemetry-attributes app=web-server --telemetry-attributes debug=true
python3 ./flog-otlp/  flog_otlp.py --otlp-header "Authorization=Bearer token123" --otlp-header "X-Custom=value"
```

# Using otelgen
A tool to generate synthetic OpenTelemetry logs, metrics and traces - can produce a good cross section of randomized data see [support signals](https://github.com/krzko/otelgen?tab=readme-ov-file#supported-signals)

## Install
```
brew install krzko/tap/otelgen
```

### logs
```otelgen --otel-exporter-otlp-endpoint localhost:4317 --insecure logs m --duration 10```

sends variable logs for 10 seconds similar to:
```json
{"k8s.pod.name":"otelgen-pod-24c9d088","worker_id":"9","trace_id":"cf282f94f3b07f885189c28bab3682de","k8s.container.name":"otelgen","http.target":"/api/v1/resource/9","phase":"processing","k8s.namespace.name":"default","http.method":"POST","trace_flags":"01","span_id":"a2ef7ea8b6630b9d","http.status_code":500,"service.name":"otelgen","log":"Log 9: Fatal phase: processing"}
{"k8s.pod.name":"otelgen-pod-4c3f5b37","worker_id":"9","trace_id":"cf282f94f3b07f885189c28bab3682de","k8s.container.name":"otelgen","http.target":"/api/v1/resource/9","phase":"finish","k8s.namespace.name":"default","http.method":"POST","trace_flags":"01","span_id":"97763624c8cf864e","http.status_code":403,"service.name":"otelgen","log":"Log 9: Warn phase: finish"}
{"k8s.pod.name":"otelgen-pod-47f4fc6c","worker_id":"10","trace_id":"5fe9e2b4a2812354fed8755ed17b15a9","k8s.container.name":"otelgen","http.target":"/api/v1/resource/10","phase":"processing","k8s.namespace.name":"default","http.method":"GET","trace_flags":"01","span_id":"65e717d99c655c4a","http.status_code":200,"service.name":"otelgen","log":"Log 10: Info phase: processing"}
```

searchable with:

```
(_collector="sumo_temeletrygen_tester")
AND _sourceCategory="otel/telemetrygen/test"
```

### traces

- single trace: ```$ otelgen --otel-exporter-otlp-endpoint localhost:4317 --insecure traces single```
- multi mode: ```otelgen --otel-exporter-otlp-endpoint localhost:4317 --insecure --duration 10 --rate 1 traces multi```

```bash
otelgen --otel-exporter-otlp-endpoint localhost:4317 --insecure \
  --rate 50 \
  --service-name test-app \
  --insecure \
  t m -t 150
  ```

Traces appear in trace views as service=otelgen

View spans in search with:

```
_index=_trace_spans service=otelgen 
| (endtimestamp - starttimestamp) / 1000 as duration
| toLowerCase(tags) as lowerCaseTags
```

# Using telemetrygen

Part of the cmd otel contrib repo and can produce basic LMT telemetry with abiltiy to tweak fields and metadata.
Good for basic testing but won't populate most of explore or have any x-stack traces.

You can get help on options from the commandline e.g

```bash
~/go/bin/telemetrygen 
Telemetrygen simulates a client generating traces, metrics, and logs

Usage:
  telemetrygen [command]

Examples:
telemetrygen traces
telemetrygen metrics
telemetrygen logs

Available Commands:
  help        Help about any command
  logs        Simulates a client generating metrics. (Stability level: development)
  metrics     Simulates a client generating metrics. (Stability level: development)
  traces      Simulates a client generating traces. (Stability level: alpha)
  ```

## setup telemetry gen
1. a working go installation
2. install [telemetrygen](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/cmd/telemetrygen) (you need to install go if you haven't already!!). ```go install github.com/open-telemetry/opentelemetry-collector-contrib/cmd/telemetrygen@latest```
(Note you can run it as a container also!)

## Start telemetry generation
```
~/go/bin/telemetrygen logs --duration 5s --otlp-insecure
~/go/bin/telemetrygen traces --duration 5s --otlp-insecure
~/go/bin/telemetrygen metrics --duration 5s --otlp-insecure
```

### viewing spans
```
_index=_trace_spans service=telemetrygen
| (endtimestamp - starttimestamp) / 1000 as duration
| toLowerCase(tags) as lowerCaseTags
| json field=lowerCaseTags "['application']", "['deployment.environment']"
| where toLowerCase(service) = toLowerCase("telemetrygen") and toLowerCase(%"['application']") = toLowerCase("default") and toLowerCase(%"['deployment.environment']") = toLowerCase("default")
```


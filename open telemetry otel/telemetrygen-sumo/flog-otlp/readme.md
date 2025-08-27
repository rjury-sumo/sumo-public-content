# flog_oltp.py as a flog wrapper

** DISCLAIMER: My buddy Claude wrote most of this - mileage may vary! **

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
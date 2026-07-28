# Metric Sources and Types

Different ingestion paths attach different tag schemas to a metric — the same query pattern (say, `| avg by pod`) is meaningless for a metric whose entity dimension is `service` or `LoadBalancer` instead of `pod`. Before writing a query for an unfamiliar metric name, work out which source/type it came from so you know what tags to filter and group by. Source: internal Sumo Logic metrics training material, cross-referenced with the Metrics documentation.

## Table of contents

- [Kubernetes / OpenTelemetry infrastructure metrics](#kubernetes--opentelemetry-infrastructure-metrics)
- [Trace-derived metrics](#trace-derived-metrics)
- [AWS CloudWatch metrics](#aws-cloudwatch-metrics)
- [Host metrics](#host-metrics)
- [OTel application metrics](#otel-application-metrics)
- [How to tell them apart](#how-to-tell-them-apart)

---

## Kubernetes / OpenTelemetry infrastructure metrics

**Ingestion**: Kubernetes Collection (OpenTelemetry or Prometheus).
**Common tags**: `cluster`, `namespace`, `deployment`, `service`, `pod`, `container`.

These are the classic infra metrics — counters and gauges scoped to a specific pod/container/deployment. Restart-count example (also the canonical counter-handling pattern, see `best-practices.md#rates-and-counters`):

```
metric=kube_pod_container_status_restarts_total
| quantize using max | delta counter
| topk(100,max)
| sum by pod
```

## Trace-derived metrics

**Ingestion**: automatically derived from distributed traces (OpenTelemetry / APM) and stored as regular metrics — no separate metrics pipeline needed if you're already sending traces.
**Identifying tag**: `_contenttype=metricfromtrace` — check this field when a metric name looks trace-related (e.g. `*_requests`, `*_duration`) and you're not sure whether it's a "real" metric or trace-derived.
**Common tags**: `application`, `service`, `deployment.environment`, `operation` — notice these are **request/service-shaped tags, not infrastructure tags** (no `pod`/`node`/`cluster`). Grouping or filtering by infra dimensions on a trace-derived metric will silently return nothing useful.

```
application=myapp deployment.environment=prod
metric=service_operation_requests service=* _contenttype=metricfromtrace
| quantize using sum | sum by operation
```

Use this family when you want aggregate request-rate/count/duration behavior per service+operation without paying for a full trace search — it's the "monitoring system health trends" use case, versus reaching for trace search when you need to follow one specific request end-to-end.

## AWS CloudWatch metrics

**Ingestion**: AWS Observability app, CloudWatch polling, or Kinesis Firehose streaming (push).
**Common tags**: `namespace`, `statistic`, `account`, `region`, `availabilityzone`.

CloudWatch sends **multiple statistic variants of the same metric name** (Sum, Average, Maximum, ...) all sharing one metric name — so every CloudWatch query must pin down `statistic=<type>` explicitly, or you'll be silently mixing incompatible statistic variants together in the same result set. This also interacts with `quantize`: think about what rollup you want on top of a metric that's already a specific CloudWatch statistic.

```
Namespace=AWS/ELB metric=RequestCount Statistic=Sum account=prod region=* loadbalancername=*
| sum by loadbalancername, namespace, region, account
```

## Host metrics

**Ingestion**: sent by an agent — could be OpenTelemetry, an installed Collector, or Telegraf.
**Common tags**: `host.name`, `host.group`, `deployment.environment` (OTel-schema hosts) — classic infra tags for CPU/memory/disk/network on a machine.

```
sumo.datasource=mac deployment.environment=* host.group=* host.name=*
metric=system.cpu.load_average.1m
```

## OTel application metrics

**Ingestion**: OpenTelemetry agent plus a Sumo Logic app for a specific technology (nginx, SQL Server, etc.).
**Common tags**: schema is per-application — e.g. nginx uses `webengine.cluster.name`; SQL Server uses `sqlserver.database.name`, `db.node.name`, `db.cluster.name`. Don't assume a generic tag set carries over between application integrations; check the specific app's documentation or use metric/tag discovery on the actual data.

```
deployment.environment={{deployment.environment}} sumo.datasource=nginx metric=nginx.requests
webengine.cluster.name={{webengine.cluster.name}}
| quantize using sum | sum by webengine.cluster.name
```

---

## How to tell them apart

If you're handed a bare metric name and don't know its source:

1. Check `_contenttype` — values like `metricfromtrace` immediately tell you it's trace-derived, not infrastructure.
2. Look at what tags actually come back for the metric (raw, unaggregated query — see the `//`-comment trick in `best-practices.md#other-query-writing-tips`). Infra-shaped tags (`pod`, `node`, `cluster`, `host.name`) vs. request-shaped tags (`service`, `operation`, `application`) tell you which family you're in.
3. For anything named like an AWS namespace (`AWS/...`) or with a `statistic` tag, treat it as CloudWatch and always pin `statistic=<type>`.
4. If the tag schema doesn't match any pattern above, it's likely a technology-specific OTel application integration — the tag names themselves (e.g. `sqlserver.*`, `webengine.*`) usually reveal which one.

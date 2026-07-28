---
name: sumo-metrics-query
description: Write and troubleshoot Sumo Logic Metrics queries (the metrics query language used by the Sumo Logic Metrics Search API and metrics-backed monitors/dashboards) — selectors, pipe operators like avg/sum/quantize/rate/delta/topk/pct, multi-row math with #A/#B/along, and cardinality-aware query design. Use this whenever the user is building, fixing, or reviewing a Sumo Logic metric query, asking why a metrics query returns "too many timeseries," needs to compute a rate or percentage from two metrics, or is deciding on quantization/rollup settings — even if they just paste a raw query string and ask "what's wrong with this." Does not cover the Metrics Search UI, chart panel settings, or log queries (LogCompare/timeslice) — those are different query languages.
---

# Sumo Logic Metrics Query Language

Sumo Logic Metrics queries are built for the **Metrics Search API / query endpoint**, not the log search language — they look similar (selectors piped into operators) but the operators, semantics, and performance concerns are entirely different from log queries. This skill covers writing correct, efficient metrics queries.

## Query anatomy

A metrics query is: **selectors**, optionally piped (`|`) through one or more **operators**.

```
<selectors> | <operator> | <operator> | ...
```

### Selectors (scope the data)

Selectors are key-value pairs and/or keyword strings that narrow which time series a query matches. A space between terms is an implicit `AND`.

```
metric=CPU_User cluster=prod                     # multiple key=value selectors, ANDed
node=prod-*                                      # wildcard match (case-insensitive)
!node=prod-01   or   not node=prod-01            # negation
( host=us* or host=eu* ) metric=cpu_idle         # bracket OR groups explicitly
field=(123, 345, 567)                            # `in`-style shorthand for multiple OR values
namespace=*                                       # "field is present, any value"
```

Built-in metadata fields available in any selector: `_sourceCategory`, `_sourceHost`, `_sourceName`, `_source`, `_collector`, `_contentType`, `_metricId`.

**Always scope with selectors before reaching for a value-based filter operator** (`where`/`filter`) — selector-based scoping is evaluated far more efficiently than post-hoc filtering.

### Operators (transform/aggregate the scoped data)

Operators are chained with `|` and fall into a few families — see `references/operators.md` for full syntax and examples of every operator:

| Family | Operators | Purpose |
|---|---|---|
| Aggregation | `avg`, `sum`, `min`, `max`, `count`, `pct(n)`, `stddev` | Collapse many time series into fewer, optionally `by field[,field...]` |
| Ranking | `topk(N, fn)`, `bottomk(N, fn)` | Keep only the N highest/lowest-ranked series |
| Quantization/rollup | `quantize`, `fillmissing` | Control the time-bucket size and rollup type |
| Rate of change | `rate`, `delta`, `accum` | Turn counters/gauges into rates, deltas, or running totals |
| Math & reshaping | `eval`, `parse`, `timeshift` | Arithmetic on values, extract dimensions from strings, shift time |
| Filtering | `where` (preferred), `filter` (legacy) | Drop series or data points by value, after scoping |
| Multi-query join | `along`, `#A`/`#B`/`#C`... row references | Combine results from multiple query rows |

A minimal but complete example:

```
cluster=search metric=cpu_idle | avg by node
```

## The concept you can't skip: quantization

Every metric series is retained at multiple rollup granularities (`avg`, `min`, `max`, `sum`, `count` — `latest` at query time). Every query quantizes into time buckets whether you ask for it or not: if you don't specify `quantize`, Sumo picks a bucket size automatically and rolls up using **`avg`** by default. That default is silently wrong for a lot of use cases (counts of discrete states, cumulative counters, "how many things are alive right now").

Rule of thumb: **decide what rollup you actually want, and say so explicitly** with `quantize to <interval> using <rollup>`, rather than relying on the default. See `references/operators.md#quantize` for syntax and `references/best-practices.md#quantization` for the classic "counting pods" example of why `avg` + `sum` gives the wrong total but `max` + `sum` gives the right one.

## Rates and counters

Many metrics are ever-increasing counters (request totals, restart counts, bytes sent). Graphing the raw counter is rarely useful — you want the rate of change. Use `delta counter` (simplest, integer results, handles counter resets) or `rate counter [over <interval>]` (per-second rate, can produce fractions). Full guidance and the recommended pattern (`quantize using max` → `delta counter` → aggregate) is in `references/best-practices.md#rates-and-counters`.

## Combining multiple queries (#A, #B, #C / along)

Sumo Metrics Search lets you reference up to six query rows (`#A` through `#F`) and combine them with arithmetic in a later row:

```
#A: metric=Net_InBytes node=* cluster=*
#B: metric=Net_OutBytes node=* cluster=*
#C: #A + #B along cluster, node as bytes_total
```

Without `along <field,...>`, a multi-row expression computes a **cross-join** of every result in #A against every result in #B — usually not what you want and a common source of "way too many series" or nonsensical output. Whenever both referenced rows can return more than one series, add `along` naming the shared dimension(s). Full explanation, more examples, and troubleshooting (misaligned quantization buckets producing missing results) are in `references/best-practices.md#joins-and-along`.

## Cardinality and output limits

Metrics queries are optimized for **lower-cardinality, high-performance aggregate charting** — this is a hard architectural difference from log queries, which tolerate very high cardinality. Two practical consequences:

- A non-aggregated query is capped at 1000 input series; an aggregated query (one using `avg`/`sum`/`max`/etc.) supports up to 200,000 series (last 24h) or 50,000 (longer ranges). If you see "too many timeseries in the output," add a `by <field>` aggregation, a `topk(...)`, or a `where`/`filter` to cut the result set down — see `references/best-practices.md#output-limits` for the exact fixes.
- Every additional tag (dimension) and every additional value that tag can take multiplies the number of time series billed and queried (DPM = metrics × entities × cardinality of all tags, billed at roughly 3 credits per 1000 DPM). Avoid ever selecting on or grouping by fields with high-cardinality values (timestamps, user/customer IDs, full URLs/query strings) — queries against those are slow, expensive, and often rate-limited. Details in `references/best-practices.md#cardinality`.

## Metric sources and types

Where a metric came from determines its tag schema, and getting that wrong is a common source of broken or misleading queries. A few examples: AWS CloudWatch metrics require an explicit `statistic=<type>` selector because AWS reports several statistic variants of the same metric under one name; Kubernetes/OpenTelemetry metrics carry infrastructure tags (`cluster`, `namespace`, `pod`, `container`); and metrics **derived from distributed traces** (`_contenttype=metricfromtrace`) carry trace-shaped tags (`service`, `operation`, `deployment.environment`) instead of infrastructure tags, and typically need `quantize using sum` rather than the `avg` default. See `references/metric-types.md` for the full source-by-source tag reference and example queries, including trace-derived metrics.

## Reference files

- `references/operators.md` — full syntax + examples for every operator (`avg`, `sum`, `min`, `max`, `count`, `pct`, `stddev`, `topk`, `bottomk`, `quantize`, `fillmissing`, `rate`, `delta`, `accum`, `eval`, `parse`, `timeshift`, `where`, `filter`, `in`, `along`). Read this when you need exact syntax for a specific operator.
- `references/best-practices.md` — quantization deep-dive with worked example, the ABC/`along` pattern for computing a derived metric from two series, rate/counter patterns, cardinality & DPM management, and how to fix "too many timeseries" errors. Read this when designing a non-trivial query or debugging unexpected output.
- `references/metric-types.md` — tag schemas and example queries by metric source/type: Kubernetes & OpenTelemetry infrastructure metrics, trace-derived metrics, AWS CloudWatch, host metrics, and OTel application metrics (nginx, SQL Server, etc.). Read this when the user's metric name or tags don't look like generic infrastructure metrics, or they mention traces, APM, or a specific integration.

All reference files are drawn from Sumo Logic's official Metrics documentation and an internal metrics training deck, and cover the query language and API only — they intentionally omit Metrics Search UI mechanics (autocomplete, chart panel types, display overrides), since this skill is scoped to writing queries against the metrics API.

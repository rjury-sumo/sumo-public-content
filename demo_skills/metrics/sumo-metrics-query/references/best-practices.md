# Metrics Query Best Practices

Patterns and pitfalls for writing correct, efficient Sumo Logic metrics queries, distilled from Sumo Logic's Metric Query Best Practices documentation. This covers query-language and API concerns only, not the Metrics Search UI.

## Table of contents

- [Quantization](#quantization)
- [Rates and counters](#rates-and-counters)
- [Joins and along (the ABC pattern)](#joins-and-along)
- [Output limits](#output-limits)
- [Aggregation and monitors](#aggregation-and-monitors)
- [Cardinality](#cardinality)
- [Other query-writing tips](#other-query-writing-tips)

---

## Quantization

Every metric series has multiple stored rollup types (`min`, `max`, `avg`, `sum`, `count`; `latest` is computed at query time). **Every query is quantized into time buckets, whether or not you write `quantize`** — if you don't specify one, Sumo auto-picks a bucket size and rolls up using `avg` by default. That default silently changes your results in ways that are easy to miss.

### Worked example: counting things correctly

Say you want the total number of pods in a cluster, where each pod reports one time series per possible state (5 states, 0/1 value in each). If you sum the wrong rollup, you get a nonsensical number:

```
cluster=prod metric=kube_pod_status_phase
| quantize to 1m using max drop last | sum
```

Using `max` per series (each pod's "is it in this state" signal is a step function, so `max` over the bucket correctly reflects "was it in this state") then `sum` gives the correct total. Averaging the rollup, or summing the raw `count` of data points, gives a fractional or meaningless total instead.

**The general rule:** before you `sum`, `avg`, or otherwise aggregate across quantized data, ask what the *source* metric actually represents at each raw data point (a gauge? a monotonic counter? a boolean state?) and pick the rollup (`quantize using <rollup>`) that's meaningful for that shape of data — don't leave it on the `avg` default just because it's shortest to type.

Also note: for CloudWatch-sourced metrics, AWS sends multiple statistic variants of the same metric, so you must include `statistic=<type>` in the selector or you'll be silently mixing rollup types.

---

## Rates and counters

Many metrics arrive as an ever-increasing counter (`kube_pod_container_status_restarts_total`, request totals, bytes sent). Charting the raw counter is rarely the goal — you want the rate of change per interval.

Recommended pattern for a counter:

```
metric=kube_pod_container_status_restarts_total
| quantize using max | delta counter
| topk(100,max)
| sum by pod
```

Why this shape:
- `quantize using max` (not the default `avg`) — averaging a counter rollup produces odd fractional values.
- `delta counter` — the simplest way to turn a counter into "how much did this change", and it handles counter resets (e.g. pod restart zeroing the counter) correctly. `rate` is the alternative but tends to produce fractional results, which is harder to reason about for something like a restart count.
- `sum by pod` (after ranking/filtering) — aggregate the delta, not the raw cumulative counter; summing the raw counter over time gives a meaningless ever-growing total instead of a restart rate.

Use `rate counter over <interval>` instead of `delta` when you specifically want a normalized per-second rate rather than a per-bucket delta (e.g. comparing metrics reported at different intervals).

### Other ways to get a rate

`delta counter` is the recommended default, but you'll see a few other equivalent-ish patterns in the wild — useful to recognize when reading someone else's query:

- `| quantize using rate` — bakes the rate calculation into the quantization rollup itself.
- `| rate increasing over 1m` — legacy form of `rate`, restricted to positive (increasing) changes over a window.
- `| sum | eval 1000 * _value / _granularity` — manually turns a per-bucket total into a per-second rate by dividing by the bucket width (`_granularity`, in milliseconds). Useful when you need the rate of an already-aggregated value rather than a raw counter.

Whichever you use, `quantize using max` (not the default `avg`) before extracting a rate/delta from a counter — averaging a monotonically increasing counter's rollup produces odd fractional artifacts at the bucket boundaries.

---

## Joins and along

To compute a value from two (or more) separate metric queries — a percentage, a difference, a ratio — Sumo Metrics Search lets you write up to six labeled query rows (`#A` through `#F`) and reference them in a later row. This is often called the **ABC pattern**.

### Why `along` matters

If a referenced row can return more than one time series (e.g. per-account, per-node, per-pod), a plain row-to-row expression like `#A + #B` computes the **cross-join** of every result in #A against every result in #B — not the pairwise match you almost always want.

```
#A: metric=CPU_User account=* | avg by account,metric      // 3 series: dev, stage, prod
#B: metric=CPU_Sys account=* | avg by account,metric        // 3 series: dev, stage, prod
#C: #A + #B                                                  // 9 series — every account × every account
#C: #A + #B along account                                    // 3 series — matched by account, as intended
```

Add `along <field>[, <field>, ...]` naming the dimension(s) shared between the referenced rows to restrict the combination to only the matching pairs (equivalent to a SQL inner join on those fields).

### Worked examples

Simple sum-to-total, keeping node/cluster paired correctly:
```
#A: metric=bytes_in node=* cluster=*
#B: metric=bytes_out node=* cluster=*
#C: #A + #B along cluster, node as bytes_total
```

Percentage from two metrics:
```
#A: metric=DiskFree DevName=*
#B: metric=DiskUsed DevName=*
#C: (#B / (#A + #B)) * 100 as DiskUsedPercent along DevName
```

Kubernetes memory-vs-limit percentage:
```
A: metric=container_memory_working_set_bytes cluster=prod namespace=prod-otel001
   | quantize 1m | avg by container, pod | sum by pod
B: metric=kube_pod_container_resource_limits resource=memory cluster=prod namespace=prod-otel001
   | quantize 1m | sum by pod
C: #A / #B * 100 along pod | topk(50,max)
```

**Rule of thumb:** when a joined row uses an aggregation operator (`avg by ...`, `sum by ...`), include those same grouping dimensions in the `along` clause of the row that references it.

### Quantization must match across joined rows

A join computes results separately per quantization bucket, so if the referenced rows' data doesn't land in the same buckets (e.g. hosts reporting at different intervals, combined with a very small auto-picked bucket size), you can get sparse or missing results. Explicitly set the same `quantize to <interval>` on every row feeding into a join, rather than relying on auto-quantization, especially for short time ranges:

```
#A: metric=CPU_User _source="HostMetrics" | quantize to 15s
#B: metric=CPU_User _source="JBM Host Metrics" | quantize to 15s
```

### Filtering one row using another row's results

You can simulate "filter row B down to only the dimension values that also appear in row A" with a zero-multiply trick:

```
#B + 0 * #A along _sourceHost
```

This returns row B's values, but only for `_sourceHost` values and quantization buckets where row A also has data — useful for "top N by metric X, but show me metric Y for those same entities."

### Troubleshooting joins

- **Fewer results than expected, or none at all** → quantization buckets are probably misaligned between rows; widen the `quantize` interval and set it explicitly on every referenced row.
- **More results than expected, or you exceed max output cardinality** → you probably forgot `along`; add it and name the shared dimension(s).

---

## Output limits

A single query row is capped at **1000 input time series for non-aggregated queries**. Aggregated queries (anything using `avg`, `sum`, `max`, etc.) support far more: at least 200,000 series for time ranges within the last 24 hours, 50,000 otherwise. If a query returns "There were too many timeseries in the output, showing first 1000," it's not aggregated (or not aggregated enough) — fix it with one of:

- Add a final aggregation by a lower-cardinality dimension: `| sum by pod | sum`, or `| sum by namespace`.
- Rank and cut down first: `| topk(500,latest) | sum by pod`.
- Filter out series or data points you don't need: `| filter max > 0`, `| where _value > 0`, `| where max > 0`.

---

## Aggregation and monitors

Beyond keeping you under the output limit, aggregating in the query itself (rather than relying on chart-level formatting) is generally worth doing because it:

- gives you direct control over which time series come out of the query, instead of hoping the chart UI groups things usefully;
- scales to far more input series and data points (see the limits above);
- makes alert grouping straightforward when the query backs a monitor — aggregate `by cluster`, `by pod`, `by host`, etc. and the monitor can fire and group per value of that dimension automatically.

If you're writing a monitor and want to reference a query's grouping field in the alert text/payload, use `ResultsJson.<fieldname>` — e.g. a query aggregated `| sum by pod` lets a monitor payload reference `ResultsJson.pod` to say which pod triggered.

---

## Cardinality

Metrics are architecturally optimized for lower-cardinality, high-performance aggregate queries — this is the single biggest mental-model difference from log search, which tolerates arbitrarily high cardinality. Metrics are billed on **data points per minute (DPM)**, roughly 3 credits per 1000 DPM averaged over a 24-hour period, where `DPM = metrics × entities × cardinality of all tag names/values` — so cardinality growth is a cost problem as much as a query-performance one. Cardinality of a metric is the *product* of all its tag cardinalities, so it grows fast:

- `host` × 10 and `service` × 20 → up to 200 combinations.
- add `url_path` × 5000 → up to 10,000.
- add a per-request or per-customer ID, or an epoch-nanosecond timestamp as a tag → effectively unbounded, and very likely to be rate-limited or dropped outright.

Never select on or group by fields likely to have more than a few thousand distinct values: timestamps/epoch times, user or customer IDs, raw query strings, or per-customer URL paths. If you need that level of granularity, log search is the right tool — it's built for high-cardinality data; metrics are not. High cardinality on a single metric or tag can also trigger Sumo to throttle or disable that source outright, so this is a correctness and reliability concern, not just a cost one.

Higher data-point frequency multiplies cost the same way cardinality does — reporting every 15s instead of every 60s is a 4x multiplier on data points per minute (DPM) for the same entities and tags.

---

## Other query-writing tips

- **Scope with selectors, not `where`/`filter`.** `cluster=search metric=cpu_idle | avg by node` is faster than scoping loosely and filtering afterward — selectors are evaluated before the query even starts aggregating.
- **Wildcards are case-insensitive.** `cluster=prod*` and `namespace=*` (field present, any value) both work as expected in selectors.
- **Negation:** `!tag=value*`, `not tag=value*`, and `!(tag=value)` are all valid.
- **Bracket your boolean logic explicitly:** `( host=us* or host=eu* ) AND metric=cpu_idle` — always parenthesize an `OR` group; a bare `space` between terms is an implicit `AND`.
- **A single query row's raw (non-aggregated) time series can be inspected directly** by temporarily commenting out the aggregation part of a query with `//`, e.g. `... | quantize 1m // | avg by container, pod | sum by pod` — useful when debugging unexpectedly high cardinality or unexpected tag values, without needing the charting UI.

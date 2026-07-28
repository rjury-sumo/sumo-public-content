# Metrics Operator Reference

Full syntax and examples for every Sumo Logic metrics query operator, grouped by purpose. Source: Sumo Logic Metrics Operators documentation.

## Table of contents

- [Selector-level](#selector-level): `in`
- [Aggregation](#aggregation): `avg`, `sum`, `min`, `max`, `count`, `pct`, `stddev`
- [Ranking](#ranking): `topk`, `bottomk`
- [Quantization & gap-filling](#quantization--gap-filling): `quantize`, `fillmissing`
- [Rate of change](#rate-of-change): `rate`, `delta`, `accum`
- [Math & reshaping](#math--reshaping): `eval`, `parse`, `timeshift`
- [Filtering](#filtering): `where`, `filter` (legacy)
- [Multi-query join](#multi-query-join): `along`

---

## Selector-level

### `in`

Shorthand for multiple OR conditions on one field, used directly in the selector (before any `|`).

```
<selectors> <field>=(<value>[, <value>, ...])
```

Example:
```
metric=CPU_Total dimX=(123, 345, 567)
```

---

## Aggregation

All aggregation operators collapse multiple matching time series into fewer series. Add `by <field>[, <field>, ...]` to group instead of collapsing to a single series.

### `avg`

```
avg [by FIELD [, FIELD, ...]]
```
```
Namespace=AWS/ApplicationELB metric=RequestCount TargetGroup=* | avg by TargetGroup
```

### `sum`

```
sum [by FIELD [, FIELD, ...]]
```
Sums the values of matching time series (or per group).

### `min` / `max`

```
min [by FIELD [, FIELD, ...]]
max [by FIELD [, FIELD, ...]]
```
Smallest/largest value per timestamp across matching series (or per group).

### `count`

```
count [by FIELD [, FIELD, ...]]
```
Counts the number of matching time series (or per group) at each timestamp — not the number of data points in one series.

### `pct`

```
pct(DOUBLE) [by FIELD [, FIELD, ...]]
```
`DOUBLE` is 0.0–100.0. Calculates the nth percentile across input series at each timestamp.
```
metric=MemoryUsed | pct(95.0) by node
```

### `stddev`

Standard deviation across matching time series at each timestamp. Same `[by FIELD, ...]` grouping pattern as the others. Useful combined with `avg` to build confidence-band expressions, e.g. `avg + 3 * stddev`.

---

## Ranking

### `topk`

Applies an aggregation function to matching series and returns the N series with the **highest** evaluated value over the query time range.

```
topk (N, SCALAR_EXPRESSION) [by FIELD [, FIELD, ...]]
```
`SCALAR_EXPRESSION` is one of `min`, `max`, `avg`, `count`, `sum`, `pct(n)`, `latest`, or an arithmetic expression combining them (e.g. `max / avg * 2`).

```
metric=CPU_Sys | topk (10, max)
metric=CPU_Sys | topk (10, max / avg * 2)
```

### `bottomk`

Same syntax and scalar-expression options as `topk`, but returns the N **lowest**-ranked series.

```
bottomk (N, SCALAR_EXPRESSION) [by FIELD [, FIELD, ...]]
```
```
metric=CPU_Sys | bottomk (5, avg + 3 * stddev)
```

---

## Quantization & gap-filling

### `quantize`

Controls the time-bucket size and rollup type used to aggregate raw data points. If omitted, Sumo auto-picks a bucket size and defaults to `avg` rollup — see `best-practices.md#quantization` for why that default is often wrong.

```
quantize [to INTERVAL] [using ROLLUP] [drop last]
```
- `INTERVAL`: duration in `s`/`m`/`h`/`d`.
- `ROLLUP`: `avg`, `min`, `max`, `sum`, `count`, or `rate`.
- `drop last`: drops the final bucket if it extends past the query time range.
- At least one of `to INTERVAL` or `using ROLLUP` must be present.
- `quantize` must immediately follow the selector to quantize the raw selector output directly; placed later in the pipe, it operates on whatever the prior step produced.

```
metric=CPU_User cluster=kafka | quantize to 10m using max
metric=CPU_User cluster=kafka | quantize to 10m using max drop last
metric=CPU_User cluster=kafka | quantize using max        // let Sumo pick the interval
```

### `fillmissing`

Fills empty time slices (which otherwise render as a straight-line interpolation) with a derived value.

```
fillmissing [using] <policy>
```
`<policy>` is one of: `empty` (leave the gap, discontinuous line), `interpolation` (linear interpolation between neighbors), `last` (repeat the previous value), or a fixed numeric value (e.g. `0`).

```
metric=CPU_Idle | avg by _sourcename | fillmissing interpolation
```

---

## Rate of change

### `rate`

Per-second rate of change between data points.

```
rate [increasing | decreasing | counter] [[over] INTERVAL]
```
- No modifier: instant rate between consecutive points.
- `counter`: use for ever-increasing counters — accounts for counter resets, always non-negative. Recommended over plain `rate` for counter-type metrics.
- `over INTERVAL`: average rate over a time window instead of point-to-point.
- `increasing`/`decreasing`: legacy, rarely needed.

```
metric=Net_InBytes Interface=eth0 | rate
metric=apiserver_request_total | rate counter
metric=apiserver_request_total | rate counter over 5m
```

### `delta`

Backward difference between each data point and the previous one. Simpler and more predictable than `rate` for counters — produces integers, not fractions.

```
delta [increasing | decreasing | counter]
```
```
metric=apiserver_request_total | delta counter
```

### `accum`

Running total across a time series (cumulative sum from the first point onward). Useful for turning per-interval counts (e.g. failures per bucket) into a cumulative total.

```
accum
```
```
success.count | accum
```

---

## Math & reshaping

### `eval`

Arithmetic/mathematical transform of a time series.

```
eval expr([REDUCER BOOLEAN EXPRESSION | _value] [_granularity])
```
- `expr`: `+ - * / sin cos abs log round ceil floor tan exp sqrt min max`
- `_value`: placeholder for each raw data point.
- Reducer functions (operate on the whole series, not a point): `avg`, `min`, `max`, `sum`, `count`, `pct(n)`, `latest`, `stddev`.
- `_granularity`: length of the quantization bucket in milliseconds — handy for converting a per-bucket total into a per-second rate.

```
metric=CPU_Idle | eval _value * 100
metric=CPU_Idle | sum | eval 1000 * _value / _granularity
```

### `parse`

Extracts new fields from an existing field (or, for Graphite metrics with no field specified, from the metric name) using wildcard patterns. `*` is a lazy (shortest) match, `**` is greedy.

```
parse [field=FIELD] PATTERN as PARSED_FIELD [, PARSED_FIELD, ...]
```
```
metric=HTTPCode_Target_2XX_Count | parse field=LoadBalancer */*/* as type, name, id | avg by name
```

### `timeshift`

Shifts a query's time series back by a fixed interval — useful for comparing "now" against "N ago" in a joined row.

```
timeshift TIME_INTERVAL
```
`TIME_INTERVAL` is in `ms`/`s`/`m`/`h`/`d`.
```
#B: metric=CPU_Idle | timeshift 2h
```

---

## Filtering

### `where` (preferred)

Filters out entire time series, or individual data points within one, based on a value condition. Use this instead of `filter` — `filter` is being deprecated.

```
where [VALUE BOOLEAN EXPRESSION | REDUCER BOOLEAN EXPRESSION]
```
Point-level:
```
metric=CPU_Idle | where _value > 5
metric=CPU_Idle | where _value > min - 5
```
Series-level (reducer functions: `avg`, `min`, `max`, `sum`, `count`, `pct(n)`, `latest`):
```
metric=CPU_Idle | where avg > 3
```
Duration form — series must meet the condition for some portion of a time window:
```
where [VALUE BOOLEAN EXPRESSION] [all | atleast n] [first | any | last] [duration]
```
```
metric=CPU_Idle | where _value > 3 atleast 3 any 5m
```

### `filter` (legacy — prefer `where`)

Same two syntax forms as `where` (reducer-based, or point-value + duration). Still supported but scheduled for deprecation; only use if maintaining an existing query that already relies on it.

```
filter [REDUCER BOOLEAN EXPRESSION]
filter _value [VALUE BOOLEAN EXPRESSION] [all | atleast n] [first | any | last] [duration]
```

---

## Multi-query join

### `along`

Used in a row that references other query rows (`#A`, `#B`, ...) with arithmetic, to restrict the combination to results whose named dimensions match — otherwise you get a full cross-join of every #A series against every #B series.

```
<expression> [along <field>[, <field>, ...]]
```
```
#A: metric=CPU_User account=* | avg by account,metric
#B: metric=CPU_Sys account=* | avg by account,metric
#C: #A + #B along account
```
See `best-practices.md#joins-and-along` for the full explanation of why this matters and worked examples.

# Advanced Lab: Scheduled Views - Query Performance and Design

## Overview

This lab covers **Scheduled Views** - Sumo Logic's mechanism for pre-computing and storing aggregated log data on a rolling basis.  There are two sections:
- Part One: understand the basics of views and how to query them
- Part Two: read on for more advancec concepts if you are are power user or admin looking to build your own views.

By the end you will understand when views add value, how to design and create one, and how to query a view correctly. 

**Lab environment:** Training Org. Log in as `training+analyst###@sumologic.com`. Find this month's password via **Home > Certification** tab in the training portal.

---

## What is a Scheduled View?

A scheduled view is a **continuously running background query** that reads raw log events, aggregates them (e.g. `timeslice 1m | count by dimensions`), and writes the result into a small, indexed dataset. Dashboard and search queries can then read from this pre-aggregated dataset instead of re-scanning all raw logs.

The diagram below shows the data flow:

```
Raw logs arrive → Scheduled View runs its definition query every ~1 minute
                                    ↓
                     Aggregated rows stored in view index
                                    ↓
                     Dashboard / search queries _view=name
                     (reads tiny pre-aggregated set, not raw logs)
```

**Key properties:**

- Data is typically grouped in 1 minute 'timesliced' buckets
- Stores pre-computed statistics from a search for fast reuse
- Fixed schema - columns are set at creation time and cannot change
- Continuous backfill from a configurable start date at creation time
- Configurable retention per view

---

## Scheduled Views Lab 1: Review views in your account

The UI location of views in your account can very between UI versions.

For new UI either:

- Navigate to **Data Management →  Logs →  Scheduled Views** (the UI page might be called 'Views' if you have this preview enabled)
- open the "Go To" dialog and search for views then open a new tab

For legacy UI:
- **Manage Data → Logs → Scheduled Views**.

> Review what views exist in this org. Click on one to see it's defition and consider what use case it would be created for.

Highlight your cursor on the view name in the tablular view so the small 'Open in Search' button appears. Click this to open the view in a search window and review search results.

> How do view results vary from raw messages results in a typical log query?

---

## Key Use Cases For a View

### 1. Dashboard acceleration over long time ranges

Dashboards covering days or weeks re-scan the same raw logs on every auto-refresh. A 1-minute view collapses millions of raw events per day into a few thousand aggregated rows. A 30-day panel that took 60+ seconds on raw logs often completes in under 2 seconds from a view.

### 2. Caching expensive compute operations

Operations like `threatip`, `geoip`, `parse regex`, and `lookup` joins are expensive at query time because they run on every matching raw event. A scheduled view runs these once at ingest time and stores the enriched result. Benefits:
- Dramatically faster dashboard queries
- Enrichment is captured at event time - historical forensic accuracy is preserved even as threat intelligence feeds are updated

### 3. Long-range reporting

Weekly or monthly scheduled searches that summarise KPIs are much cheaper when run against a pre-aggregated view. The scan cost is near-zero regardless of the underlying raw log volume.

---

## Querying a Scheduled View

### The golden rule: `sum(_count)` not `| count`

The view already counted events in 1-minute buckets. If you use `| count` in your query, you count the number of pre-aggregated rows - not the number of original log events. Always use `sum(_count)`:

```text
// Wrong - counts view rows, not original events
_view=apache_status_v1 | count by status_code

// Correct - sums the pre-aggregated event counts
_view=apache_status_v1 | sum(_count) as requests by status_code
```

### Re-aggregating to longer time intervals

The view stores 1-minute buckets. To show hourly or daily charts, re-aggregate in your query:

```text
_view=apache_status_v1
| timeslice 1h
| sum(_count) as requests by status_code, _timeslice
```

### Indexed field filters belong in the scope line

Filtering before the first `|` uses the view's indexed fields and is much faster than a `| where` clause:

```text
// Fast - indexed field filter in scope
_view=apache_status_v1 status_code=500 | sum(_count) by host

// Slower - post-aggregation filter
_view=apache_status_v1 | where status_code = 500 | sum(_count) by host
```

---

##  Scheduled Views Lab 2: Compare Raw vs View Query Performance

As dashboards cover longer time ranges (days or weeks), raw queries scan large volumes of data and can become slow or time out.

**Scheduled views** solve this by pre-computing and storing aggregated results on a rolling basis. Dashboard queries then read from a small, pre-aggregated dataset instead of re-scanning all raw logs.

### Part A: Run the Raw Query and Record Performance

Run the following query in a **new Log Search tab** over the **last 30 days**. When the query completes, note the execution time and data scanned (shown in the search status bar).

```text
_sourcecategory = "Labs/AWS/WAF"
| json field=_raw "httpRequest.clientIp" as src_ip
| where (ispublicip(src_ip))
| json field=_raw "action"
| threatip src_ip | where !(isempty(malicious_confidence))
//| timeslice 1m
| "AWS" as vendor
| "WAF" as product
| malicious_confidence as threat
| json field=raw_threat "threat_types"
| count by vendor,product,_sourcecategory,_source,src_ip,action,threat,actor,threat_types
| lookup asn,organization from asn://default on ip=src_ip
| geoip src_ip
| fields -latitude,longitude,country_name,state
```

**What this query does - step by step:**

| Step | Operator | What it does |
| --- | --- | --- |
| 1 | `_sourcecategory = "Labs/AWS/WAF"` | **Scope** - restricts the scan to AWS WAF log data only |
| 2 | `json field=_raw "httpRequest.clientIp"` | **Parse** - extracts the client IP from the JSON log structure |
| 3 | `where ispublicip(src_ip)` | **Filter** - discards private/RFC-1918 IPs that cannot be geo-resolved or threat-checked |
| 4 | `json field=_raw "action"` | **Parse** - extracts whether WAF allowed or blocked the request |
| 5 | `threatip src_ip` | **Enrich** - looks up each IP against Sumo Logic's threat intelligence feed; adds `malicious_confidence`, `actor`, and threat metadata |
| 6 | `where !(isempty(malicious_confidence))` | **Filter** - keeps only IPs with a positive threat match |
| 7 | `count by ...` | **Aggregate** - counts matched threat events grouped by source, IP, action, and threat attributes |
| 8 | `lookup ... from asn://default` | **Enrich** - resolves each IP to its ASN and organisation name |
| 9 | `geoip src_ip` | **Enrich** - resolves each IP to country, region, city, latitude, and longitude |
| 10 | `fields -latitude,...` | **Format** - drops geo-coordinate fields not needed in the output |

> **Why this query is expensive over large time ranges:**
>
> This query performs three costly operations on **every matching raw log event** at search time:
>
> - **`threatip`** - each IP is checked against a threat intelligence feed. On high-traffic WAF data this can mean millions of lookups per query run.
> - **`geoip`** - similarly resolves every IP to a location, adding compute overhead proportional to event volume.
> - **JSON parsing** - extracting nested fields from raw JSON is more expensive than querying pre-indexed fields.
>
> Over 30 days of busy WAF traffic, all three operations compound to make this query slow and data-intensive. A scheduled view runs this **once per minute at ingest time** and stores only the IOC matches with enrichment already applied - so dashboard queries skip all of this work entirely.

Record your results:

| Metric | Raw Query result |
| --- | --- |
| Query execution time - in search result bar in UI | ___ seconds |
| Data scanned - click the meter icon just to the left of the run query button | ___ GB |

<img src="images/scan-estimate.png" width="300">

### Part B: Run the Equivalent View Query

Now run the equivalent query using a scheduled view. The view has already aggregated the AWS WAF data in 1-minute buckets - your query re-aggregates those pre-computed rows.

```text
// Use the pre-aggregated view instead
_view=threat_geo_asn_aws_waf_v1
| sum(_count) as matched_events by vendor,product,_sourcecategory,_source,src_ip,action,threat,actor,threat_types,asn,organization
```

> **`sum(_count)` not `count`** - the view query is subtly different from the raw query. Using `count` would count the number of pre-aggregated view rows, not the total number of original events. `sum(_count)` correctly sums the event count stored in each 1-minute bucket.

Record your results:

| Metric | View Query result |
| --- | --- |
| Query execution time | ___ seconds |
| Data scanned | ___ GB |

### Part C: Compare and Reflect

> How did the runtimes and scan volume compare for the raw vs the view version of the query?
>
> **Views in dashboards** - we can easily add a query like this to a dashboard using the **Add to Dashboard** button in the Aggregates tab.
>
> **Key takeaway:** Views are most valuable for dashboard panels covering days or weeks of data, queries that run repeatedly (dashboards auto-refresh, scheduled reports), and queries involving expensive operations like `geoip` or `threatip` - the view computes these once at ingest time and caches the result. Views are **not** suitable when you need raw message-level detail, or for one-off ad-hoc queries.

### Part D: Reflect on the View Design

Look at the view definition query from Part B and answer the following:

1. **Why does the view definition use `timeslice 1m | count by ...` instead of a larger timeslice?**
   *(Hint: smaller timeslices preserve more re-aggregation flexibility for downstream queries.)*

2. **Why are `geoip` and `lookup` included in the view definition rather than in the dashboard query?**
   *(Hint: think about when the computation happens and historical accuracy of threat feeds.)*

3. **What would happen if a new dimension (e.g. `country_code`) was needed that is not in the current view schema?**
   *(Hint: views have a fixed schema - a new view version would need to be created.)*

---



---

## Design Principles

### Write a good view definition query

The view definition query must:
1. **Scope tightly** - include `_sourceCategory=` or `_index=` to limit which partitions are scanned
2. **End with an aggregate** - `timeslice 1m | count by dimensions` (or `sum`, `avg`)
3. **Include all dimensions** you will ever need to filter or group by in downstream queries - schema cannot change after creation

#### Multi-layer (Base Camp) architecture

Advanced users might also make multiple layers of views for use cases targeting very long time ranges (90 days, 1 year), views can be stacked:

```
Raw data           → tens of millions of rows/day
↓ 1-minute view    → 1,440 rows/facet/day
↓ 1-hour view      → 24 rows/facet/day    (built via save-to-index scheduled search)
↓ 1-day view       →  1 row/facet/day     (built via save-to-index scheduled search)
```

### Validate cardinality before creating

The goal is to reduce row count vs raw event volume. Run this over a 1-minute sample before committing:

```text
// Append to your proposed view definition query and run over -15m to -14m:
| sum(_count) as event_count, count as view_rows
```

| Result | Interpretation |
|---|---|
| `event_count=1,000,000` → `view_rows=11` | Excellent - massive compression |
| `event_count=200,000` → `view_rows=150,000` | Poor - one row per transaction, marginal benefit |
| Any ratio with expensive compute (`threatip`, `geoip`) | Build it - cache value outweighs cardinality |

**Rule of thumb:** if `view_rows` per timeslice exceeds ~10K or approaches raw event count, query performance gains diminish. Exception: views caching heavy compute are worth building at any cardinality.

### Naming conventions

Use lowercase, descriptive names with a version suffix:

```
apache_status_v1
threat_geo_asn_aws_waf_v1
cloudtrail_admin_events_v2
```

Query with a wildcard to span versions: `_view=apache_status_v*`

---

## Creating a Scheduled View

1. Navigate to **Manage Data → Logs → Scheduled Views**
2. Click **+ Add** and enter a lowercase versioned name (e.g. `apache_status_v1`)
3. Paste the view definition query - must be an aggregate query ending with `timeslice 1m | count by ...`
4. Set **Start Time** - backfills from this point; further back means a longer initial backfill
5. Set **Retention Period** - set to match your longest dashboard time range (e.g. 90 days)
6. Ensure all required output fields are enabled under **Manage Data → Logs → Fields**


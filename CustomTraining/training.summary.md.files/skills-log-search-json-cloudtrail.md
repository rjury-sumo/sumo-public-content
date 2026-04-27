# Skills: Log Search with JSON Structured Logs (AWS CloudTrail)
## Sumo Logic — Knowledge Reference

---

## 1. Search Scope and Structure

- Always open a search with a **scope** before the first `|`: use `_sourcecategory=`, `_index=`, or both. This is the single most effective performance lever.
- Add **keyword terms** after the scope (e.g. `errorcode recipientaccountid`). Keywords use a bloom filter and reduce data scanned before any parsing occurs.
- Spaces between terms are implicit `AND`. Complex boolean logic (`(a OR b) AND c`) is supported.
- Use a **relative time expression** (e.g. `-6h`, `-24h`) typed directly in the time range box for precise control.
- Scope with `_sourcecategory` wildcard suffix (e.g. `Labs/AWS/CloudTrail*`) to capture sub-categories without listing each one.

### Query Structure Template

```sql
_index=<partition> _sourcecategory=<scope> keyword(s)
| parse / json operators
| where <filter condition>
| aggregation operators
| sort / top
```

---

## 2. JSON Log Handling

- JSON logs are **auto-parsed** at search time in Sumo Logic — every JSON key is immediately available as a field in the Field Browser without explicit parsing.
- Auto-parsed nested fields appear with dot-path notation: `%"useridentity.arn"`.
- **Explicit `json` operator parsing is faster** than auto-parse for high-volume searches and should be used in production queries.
- Right-click any JSON key or value in the Messages tab → **Parse the selected key** to generate the operator automatically.

---

## 3. Parse Operators

| Operator | Use Case | Notes |
| --- | --- | --- |
| `json field=_raw "key"` | Extract a named JSON key | Most readable; use for JSON logs |
| `parse "anchor*anchor" as field` | Simple text pattern with wildcard | Fast; requires known surrounding text |
| `parse regex field=f "(?<name>pat)"` | Complex or variable patterns | Slowest; use named capture groups |
| `nodrop` keyword | Optional fields | Without `nodrop`, parse acts as a filter and drops non-matching events |

- Use `nodrop` for any field that may not be present in all events.
- Parse operators can target any field (`field=arn`), not just `_raw`.
- Chain multiple parse operators in sequence to build up a rich field set.

---

## 4. Iterative Investigation Workflow

The recommended search workflow is iterative — start broad, then narrow:

1. **Scope** with `_sourcecategory` and keywords
2. **Explore** with Field Browser and Log Message Inspector
3. **Narrow** by clicking metadata badges, histogram bars, or field values
4. **Parse** fields explicitly as needed
5. **Aggregate** into counts, time series, or distributions
6. **Visualise** in the Aggregates tab or add to a dashboard

### Key UI Shortcuts

| UI Feature | How to Use | What It Does |
| --- | --- | --- |
| Field Browser | Click field name | Shows value distribution (top 100k) |
| Field Browser | Click **Top Values** | Opens new aggregate query tab |
| Field Browser | Click **Top Values Over Time** | Opens new time-series query tab |
| Field Browser | Click individual value | Opens new search filtered to that value |
| Messages tab | Click metadata badge | Appends scope filter to current query |
| Messages tab | Down-arrow on badge | Opens surrounding messages search |
| Log Message Inspector | Ellipsis → Filter Selected Value | Appends field=value filter to query |
| Histogram | Click a bar | Filters Messages tab to that time window |
| Histogram | `Shift + click` | Opens new search for that time range |
| Histogram | Click log level | Filters Messages to that `_loglevel` |

---

## 5. Aggregation Patterns

### Categorical (count by dimension)

```sql
_sourcecategory = Labs/AWS/CloudTrail* errorcode
| json field=_raw "errorCode"
| count errorCode
| top 10 errorCode by _count
```

- Use for: pie charts, bar charts, ranked tables.
- Output is in the **Aggregates tab**; toggle between table and chart with the chart icons.

### Time Series (count over time by dimension)

```sql
_sourcecategory = Labs/AWS/CloudTrail* errorcode
| json field=_raw "errorCode"
| timeslice 5m
| count _timeslice, errorCode
| transpose row _timeslice column errorCode
```

- `timeslice` buckets events into time windows (e.g. `5m`, `15m`, `1h`).
- `transpose` pivots a multi-value field into columns — required for multi-series charts.
- Use **Stacked** column chart type to show proportional distribution over time.

### Performance Rule: Keywords Before `where`

Use **keyword terms** in the scope line (before the first `|`) to pre-filter with the bloom filter. Reserve `| where` for conditions that require parsed fields. This prevents full scans of non-matching data.

```sql
// Fast: keyword pre-filter reduces data before parsing
_sourcecategory=... errorcode (*exceed* or *limit*)
| json field=_raw "errorCode"
| where errorcode matches "*Limit*"

// Slow: no pre-filter, where clause scans everything
_sourcecategory=...
| json field=_raw "errorCode"
| where errorcode matches "*Limit*"
```

---

## 6. Key Metadata Fields

| Field | Description |
| --- | --- |
| `_sourcecategory` | Most important scoping field; set at source config |
| `_index` / `_view` | Partition where logs are stored; same concept, different UI labels |
| `_messagetime` | Parsed event timestamp |
| `_receipttime` | Time Sumo received the log |
| `_raw` | Full original log message |
| `_loglevel` | Auto-detected log level (INFO, WARN, ERROR, etc.) |

---

## 7. AWS CloudTrail Specifics

- CloudTrail events include `errorCode` and `errorMessage` **only on failed API calls** — use these as keywords to filter to failures efficiently.
- `recipientAccountId` identifies the AWS account; useful for multi-account environments.
- `userIdentity.arn` identifies the calling principal (user, role, or service).
- `eventName` and `eventSource` identify the API operation and AWS service.
- Rate-limit errors (e.g. `ThrottlingException`, `RequestLimitExceeded`) indicate workloads needing AWS soft limit increases — filter with `(*exceed* or *limit*)` as keywords.
- To investigate a specific workload: group by `recipientAccountId`, `arn`, or `eventName` in the aggregation.

---

## 8. Reference Links

| Resource | URL |
| --- | --- |
| Getting Started With Search | https://help.sumologic.com/docs/search/get-started-with-search/ |
| Log Operators Cheat Sheet | https://help.sumologic.com/docs/search/search-cheat-sheets/log-operators/ |
| Search Best Practices | https://help.sumologic.com/docs/search/get-started-with-search/build-search/best-practices-search/ |
| Field Browser | https://help.sumologic.com/docs/search/get-started-with-search/search-page/field-browser/ |
| Log Message Inspector | https://help.sumologic.com/docs/search/get-started-with-search/search-page/log-message-inspector/ |
| View JSON Log Results | https://help.sumologic.com/docs/search/get-started-with-search/search-basics/view-search-results-json-logs/ |
| Surrounding Messages | https://help.sumologic.com/docs/search/get-started-with-search/search-basics/search-surrounding-messages/ |
| Search Modes | https://help.sumologic.com/docs/search/get-started-with-search/search-page/search-modes/ |
| Introduction to Search (video) | https://www.youtube.com/watch?v=VbFsfpmP6LY |

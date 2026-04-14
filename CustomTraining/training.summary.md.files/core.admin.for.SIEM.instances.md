# Skills: Core Platform Admin for Cloud SIEM Instances
## Sumo Logic — Knowledge Reference

---

## 1. Platform Overview

- Sumo Logic provides three security product tiers: **Cloud Security Analytics** (data lake, investigation), **Cloud SIEM** (real-time detection & enrichment), and **Cloud SOAR** (orchestration and response).
- The platform supports a **maturity journey**: start with Security Data Lake / Compliance, progress to real-time SIEM detection, then automate with SOAR.
- Two pricing models exist: **Legacy Credits** (mostly ingest-based) and **Flex** (mostly scan-based, $0 to ingest except CSIEM). Understanding which model applies affects how admins monitor usage and cost.
- The **Account page** shows overall credits consumption and tracking against plan. The **Data Volume index** is key for mapping ingest to cost and investigating spikes.
- Enable these **account policies** for all enterprise instances: audit index, data volume index, and search audit index.

---

## 2. Core Log Platform Administration

### Collectors and Sources
- **Installed Collectors** run on-premise; **Hosted Collectors** and **C2C (Cloud-to-Cloud) Sources** collect from SaaS/cloud APIs.
- C2C connectors are the simplest path to SIEM — most have a built-in "Forward to SIEM" checkbox.
- For non-C2C sources, set `_siemforward=true` and `_parser=<parser_path>` via source config or Field Extraction Rules (FERs).

### Field Extraction Rules (FERs)
- FERs extract and assign fields **at ingest time** — searches against FER fields are 3–5× faster than search-time parsing.
- FERs are the most common enterprise mechanism for controlling SIEM forwarding and partition routing.
- Example pattern: use a FER to set `tier=continuous` or `tier=infrequent` based on log content, then route to separate partitions accordingly.
- In tiered/licensed accounts, only **Continuous tier** logs can forward to SIEM. In Flex accounts, any log with `_siemforward=true` routes to SIEM.

### Partitions
- All logs land in **partitions** (also called indexes or `_view`). Partitions are scoped by routing expression (usually `_sourcecategory`).
- Normalized CSIEM data is **reflected** back to core platform in special partitions: `sec_record_*` (records), `sec_signal` (signals), and `sumologic_*_events` (insights/audit).
- Partition scoping in queries (`_index=`, `_view=`) is the single biggest lever for search performance.

### Timestamp & Lag Best Practices
- Ensure `_messagetime` is parsed correctly — sources with lag >15 minutes erode real-time detection value.
- Use `_receipttime - _messagetime` to detect lag or future-timestamped events (lag < 0 = invalid).
- Hidden field `_format` shows how the timestamp was parsed from `_raw` — useful for debugging.
- A common AWS bug: failing to set up **SNS notification for S3 sources**, causing polling delay.

### Processing Rules
- Applied at the source level; support include, exclude, masking, and hashing of log content.
- Use **masking/redaction** processing rules for PII in high-security instances.

### Users, Roles & SAML
- RBAC has two dimensions: **Capabilities** (what a user can do) and **Role Search Scope** (what data they can see, typically scoped by `_sourcecategory`).
- Recommended layered role structure: Admin (all capabilities, `*`), Power User (deploy collection, create content), User (search/view), Restricted User (very limited).
- **SAML is strongly recommended** — supports on-demand provisioning, role attribute mapping from IDP, and subdomain-based SP-initiated login.
- API automation uses **user access keys**, **install tokens** (for agents), and the **Terraform provider**.

### Apps, Library & Content Sharing
- Install apps via the **App Catalog** (left navigation). Each app has guided install and links to docs.
- Content lives in the **Library**: Personal folder (private by default), Installed Apps, Admin Recommended (curated team folders).
- Share high-value content broadly — permissions model is similar to Google Drive (view, manage, etc.).
- For CSIEM admin monitoring, install the **Enterprise Audit - Cloud SIEM** app (v2, auto-updating). It includes dashboards for records, signals, insights, and the **Insight Trainer**.

### Auditing Sumo Logic Itself
- Enable **audit index**, **data volume index**, and **search audit index** for all enterprise accounts.
- Create a `sumo_admin` folder in Admin Recommended and import the Sumo audit apps.
- Key apps: Legacy Audit, Data Volume (v2 recommended), Enterprise Audit, Search Audit, and reflected CSIEM data apps.

---

## 3. Cloud SIEM Pipeline

### Forwarding Logs to SIEM (Priority Order)
1. **C2C connector with "Forward to SIEM" checkbox** — simplest, preferred.
2. **Sumo Logic Source + Parser** — set `_siemforward=true` and `_parser=<path>` in source config or FER. Get parser path from Parsers UI → "Copy Path".
3. **Sumo Logic Source + Ingest Mapping** (legacy) — least recommended; requires manual field mapping.

### Normalization Pipeline
- Logs sent to SIEM must be **normalized**: a **Parser** extracts raw fields, a **Log Mapper** maps them to the CSIEM normalized schema.
- Normalized records are stored in `sec_record_*` partitions in core platform.
- Failed records land in `sec_record_failure` with a `reason` field explaining why they failed.

### Recommended Data Source Categories (in order of importance)
1. Detection & Response (EDR, HIDS, DLP)
2. OS & System Logs (Windows, Linux — especially critical servers)
3. SaaS Security (CASB, ZScaler, Proofpoint, Umbrella)
4. Network Security (IDS/FW, NTA, Corelight)
5. Identity & Access (SSO, MFA, Active Directory)
6. Cloud Infrastructure (AWS CloudTrail/GuardDuty, Azure, GCP)

Collect from **at least 4 of the 6 categories** for effective correlation.

### Tuning Stages
- **Stage 1 — Foundations**: Normalisation quality, entity coverage, log mapper/parser health, collection domain coverage, network blocks, inventory, threat intel/record enrichments.
- **Stage 2 — Entity Config**: Match lists, suppression lists, entity groups, tags, entity criticality, custom entities.
- **Stage 3 — Rule Tuning**: Built-in rule tuning expressions (RTEs), custom rules, custom insights and signals schedule.

### Entities and Insight Generation
- Signals are generated on **entities** (IP, hostname, username, MAC address, or custom).
- Each signal contributes a severity score. When an entity's **Activity Score** exceeds 12 within 14 days, an **Insight** is created (threshold is configurable).
- **Signal Suppression**: same rule + same entity suppressed for 12 hours to prevent duplicate insights.
- **Entity Groups**: define groups by name, IP, or inventory data; assign criticality, tags, suppression status.
- **Entity Criticality**: adjust signal severity for specific high-value or low-value entities.

### Rule Types
| Type | Description |
|------|-------------|
| **Match** | Single record matches rule expression → signal fires |
| **Chain** | Two or more expressions, with minimum match counts in a time window |
| **Aggregation** | Fires based on aggregate conditions over time (e.g. ratio of failed/successful HTTP) |
| **Threshold** | Fires when expression matches ≥ N times in a time period |
| **UEBA: First Seen** | Fires when entity behaviour hasn't been seen before |
| **UEBA: Outlier** | Fires when entity behaviour deviates from its baseline |

### Rule Tuning Expressions (RTEs)
- RTEs allow include/exclude logic applied on top of existing rules without modifying the base rule.
- **Important**: RTEs preserve ongoing updates from the Sumo Threat Labs team. Copying a rule loses those updates.
- Common use cases: exclude known IP addresses from a rule, scope a rule to a specific host list, exclude specific users.
- When to copy a rule instead: when you need to change the "on entity" type (e.g. fire on `srcDevice_IP` only vs. all entity types).

### Suppression & Match Lists
- **Match Lists**: evaluated against each record; matched records can be used in detection rule conditions.
- **Suppression Lists**: if a record field value is in the list, all signals from that record are suppressed.
- **Threat Intelligence**: two engines — Unified TI (`hasThreatMatch` operator, configured in core platform) and legacy Threat Intel Lists (`listMatches` array in records).
- **User/Host Name Normalization**: creates common name forms across AD, AWS, FQDNs to prevent duplicate entity signals for the same user.

---

## 4. Log Search: Core Platform

### Query Structure
```
_index=<partition> _sourcecategory=<scope> keyword(s)
| parse "pattern * *" as field1, field2
| where field1 matches "5*"
| count by field2
| sort by _count
```

### Performance Best Practices (fastest → slowest)
1. Scope with `_index=` or `_sourcecategory=` before the first `|`
2. Add keyword(s) (bloom filter) to reduce retrieved data
3. Use indexed/FER fields in scope for 3–5× speed improvement
4. Avoid: `where matches` without keywords, lookups before aggregation, `top` vs `topk` misuse, unnecessary parsing/sorting, `where` at end when it could be earlier, very high cardinality, regex.

### Key Metadata Fields
| Field | Description |
|-------|-------------|
| `_collector` | Collector name |
| `_source` | Source name |
| `_sourcecategory` | Source category (most important for scoping) |
| `_sourceHost` | Hostname of source |
| `_index` / `_view` | Partition where logs are stored |
| `_messagetime` | Parsed timestamp of log event |
| `_receipttime` | Time Sumo received the log |
| `_messageid` | Unique ID of the log message |
| `_format` | How the timestamp was parsed (hidden, for debugging) |

### Alerting
- **Legacy Scheduled Search**: log only; fires every time schedule runs and matches; useful for recurring email reports.
- **Monitors** (preferred): logs, metrics, or SLO; stateful alerting (warning/critical/no data); full API support for managing as code.

---

## 5. Log Search: Normalized (CSIEM) Data

### Reflected Data Index Structure
| Index | Contents |
|-------|----------|
| `sec_record_*` | Normalized records (one per ingested security event) |
| `sec_record_failure` | Records that failed to parse or map |
| `sec_signal` | Normalized signal data |
| `sumologic_audit_events` | Insight state-change audit events |
| `sumologic_system_events` | System-level CSIEM events |

### Querying Records (`sec_record_*`)
- Column in UI is called **"Security Record Details"**, not "Message".
- Top-level fields (e.g. `metadata_vendor`, `metadata_product`, `metadata_parser`, `metadata_mapperName`) can be used in query scope directly.
- Nested fields in the `fields` array must use search-time parsing with their full path: `%"fields.events.type"`.
- Right-click any field in the UI → **"Copy Field Name"** to get the correct path syntax.
- Track failed records back to source: use `_messageid` and `metadata_sourceCategory` from `sec_record_failure` to query the original raw log.

### Querying Signals (`sec_signal`)
- Keyword expressions work well and are fast (not case sensitive).
- Some top-level fields can be used in scope (e.g. `attackStage`); embedded arrays (e.g. `fullRecords[0].description`) must use `where` syntax (case sensitive).
- Example: `| where %"fullRecords[0].description" = "A change was made to the Windows Firewall exception list."`
- Tags (e.g. MITRE ATT&CK) are JSON arrays — use `parse regex ... multi` to extract multiple values.

### Querying Insights (audit/event indexes)
- Scope: `_sourcecategory=cseinsight (_index=sumologic_audit_events OR _index=sumologic_system_events)`
- JSON payload contains `insightIdentity` and `insight` keys — expand in Messages tab to explore.

### Insight Trainer (ML Tuning)
- ML tool included in the Enterprise Audit - Cloud SIEM app (Insight Analysis folder).
- Learns from SOC resolution history: true positive, false positive, no action.
- Calculates recommended severity adjustments to: preserve true positives, minimize false positives, optionally minimize no-action insights.
- **Tunability score**: high score = good candidate for tuning (few entities driving most FP/no-action signals).
- Export suggestions to CSV via "Open in Search" on the rules details panel.
- Small severity changes guided by Insight Trainer can significantly reduce overall insight volume.

---

## 6. Key Queries Reference

### Ingest Lag Detection
```
_sourcecategory=<scope>
| _format as tz_format
| _receipttime - _messagetime as lag_ms
| lag_ms / (1000 * 60) as lag_m
| values(tz_format) as tz_formats, min(lag_m) as min_lag, avg(lag_m) as avg_lag,
  max(lag_m) as max_lag by _collector, _source, _sourcecategory
| sort avg_lag
| if(avg_lag < 0, "ERROR - future timestamp!", "OK") as status
| if(avg_lag > 5, "WARN - high lag source", status) as status
| if(avg_lag > 60, "ERROR - Very high lag time on source ingestion", status) as status
```

### Record Partition & Metadata Audit
```
_index=sec_record*
| count by _view, metadata_parser, metadata_product, metadata_vendor,
  metadata_mapperName, metadata_sourceCategory
```

### Failed Record Investigation
```
_index=sec_record_failure objectType=FailedRecord
| json "reason" nodrop
| limit 100
| count by metadata_sourceMessageId, metadata_vendor, metadata_product, reason,
  metadata_sourcecategory
| concat("_sourcecategory= ", metadata_sourceCategory, " _messageid=", metadata_sourceMessageId)
  as raw_query
```

### Signal MITRE ATT&CK Tag Analysis
```
_index=sec_signal
| if(isempty(suppressedreasons),"NO","YES") as suppressed
| if(suppressed="YES",1,0) as is_suppressed
| if(suppressed="NO",1,0) as is_generated
| where is_generated=1
| json field=entities "[0].value" as entityid nodrop
| json field=fullRecords "[0].metadata_vendor" as vendor nodrop
| json field=fullRecords "[0].metadata_product" as product nodrop
| json field=fullRecords "[0].metadata_mapperName" as mapperName nodrop
| concat(ruleid," ",rulename) as rule
| parse regex field=tags "\"(?<tagname>[^:\"]+):(?<tagvalue>[^:\"]+)" multi
| where tagname matches "_mitreAttack*"
| if(is_suppressed=1,0,severity) as s
| sum(s) as total_severity, max(severity) as max_sev,
  count_distinct(entityid) as entities, count_distinct(rule) as rules
  by tagname, tagvalue
| sort total_severity
```

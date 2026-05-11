# Sumo Logic Search Job Skills

This directory contains Claude Code skills for executing Sumo Logic Search Job API workflows. The underlying tool is `../execute_search_job.py`.

## Available Skills

| Skill File | Use When |
|---|---|
| [sumo-search-job.md](sumo-search-job.md) | Running a single search query (records or messages) |
| [sumo-batch-export.md](sumo-batch-export.md) | Exporting data across large time ranges in batches |
| [sumo-bulk-messages.md](sumo-bulk-messages.md) | Bulk raw log export with adaptive bucketing (>100k events) |
| [sumo-search-workflow.md](sumo-search-workflow.md) | Integrating search results into agent pipelines and analysis workflows |

## Quick Reference

### Script location
```
apis/scripts/search_job/execute_search_job.py
```

### Authentication — always required
```bash
--region {us1|us2|eu|au|de|jp|ca|in}
--access-id  $SUMO_ACCESS_ID
--access-key $SUMO_ACCESS_KEY
```

### API hard limits to know
| Limit | Value |
|---|---|
| Raw messages per job | 100,000 |
| Aggregate records per job | 10,000 |
| Messages per page | 10,000 or 100 MB |
| Recommended max wait | 300 s |

### Time format options
```
-1h   -30m   -2d   -1w          # relative
2024-01-01T00:00:00Z             # ISO 8601
1704067200000                    # epoch milliseconds
now                              # current time
```

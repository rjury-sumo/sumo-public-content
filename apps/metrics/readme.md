# metrics dashboards
## apps/metrics/metric_dpm_dv_beta.json
A dashboard of ```_index=sumologic_volume _sourceCategory=byMetricDataPoints``` data (only valid with metrics DPM beta as of oct 2023)
Enables per metric DPM calculations.

### Example metric DPM beta queries
converting dp to dpm requires a speical approach for aggregate vs timeslice as the sparse data makes conversion tricky.
```
//timeslicing
(_index=sumologic_volume _sourceCategory=byMetricDataPoints)
| parse "intervalStart: *\n" as interval
| parse regex "\n(?<singleRecord>.*)" multi
//| where singleRecord matches "*"
| split singleRecord delim=';' extract 1 as metric, 2 as dpm
| timeslice 1h
| (__timeslice_end - _timeslice)/ (1000 * 60) as ts_min
| max(ts_min) as ts_min,sum(dpm) as totalDp group by metric,_timeslice
| round(totalDp / ts_min, 0) as dpm
| if (dpm < 5000,"others",metric) as metric
| fields -totalDp,ts_min | transpose row _timeslice column metric


//aggregate
(_index=sumologic_volume _sourceCategory=byMetricDataPoints) 
| parse "intervalStart: *\n" as interval
| parse regex "\n(?<singleRecord>.*)" multi
//| where singleRecord matches "*"
| split singleRecord delim=';' extract 1 as metric, 2 as dp
| sum(dp) as totalDp by metric
| (queryendtime() - querystarttime())/(1000 * 60) as query_min
| round(totalDp / query_min, 0) as dpm //| fields -query_min
| if (dpm < 5000,"others",metric) as metric
| sum(totaldp) as %"Total Data Points",sum(dpm) as %"Est. DPM", count as metrics by metric
| sort %"Est. DPM" //| limit
```

## apps/metrics/metrics_dv_over_time.json
Shows the regular metric data volume over time by sourcecategory,collector,sourcehost ann source.
Useful for identing top high level drivers of dpm volume and changes over time.
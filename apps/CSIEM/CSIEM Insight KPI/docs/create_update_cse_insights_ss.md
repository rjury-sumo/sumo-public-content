# schedule ongoing updates every 15m via a scheduled search
create a scheduled search similar to above with we will use save to lookup as the action.

You can do this two ways:
a) import import/update_cse_insights_status_sched_search.json  (note if you have a non standard path this will fail unless you update it to match)
b) manually create the scheduled search using steps in ../docs/create_update_cse_insights_ss.md
- query:
```

// Schedule a version of this search to save to the lookup every 15m for -15m 

(_index=sumologic_audit_events _sourcecategory=cseinsight insightupdated
OR
_index=sumologic_system_events _sourcecategory=cseinsight insightcreated)

| json field=_raw "eventName"
| json field=_raw "insightIdentity.id" as id
| json field=_raw "insightIdentity.readableId" as insightid
| json field=_raw "insight.status" as status
| json field=_raw "insight.name" as name
| json field=_raw "insight.entityType" as entitytype
| json field=_raw "insight.entityValue" as entityvalue
| json field=_raw "insight.tags" as tags
| json field=_raw "insight.severity" as severity
| json field=_raw "insight.confidence" as confidence
| json field=_raw "insight.signals" as signals

// in closed events
| json field=_raw "insight.assignee" as assignee nodrop
| json field=_raw "insight.resolution" as resolution nodrop

// in update events 
//| json field=_raw "to" as last_change nodrop

// may exist after an update
| json field=_raw "insight.timeToResponse" as timeToResponse nodrop
| json field=_raw "insight.timeToDetection" as timeToDetection nodrop
| json field=_raw "insight.timeToRemediation" as timeToRemediation nodrop

| if (isnull(timeToResponse),-1,timeToResponse) as timeToResponse
| if (isnull(timeToDetection),-1,timeToDetection) as timeToDetection
| if (isnull(timeToRemediation),-1,timeToRemediation) as timeToRemediation
| sort _messagetime

// ensure we only store the most recent result
| count as events, max(_messagetime) as _messagetime,first(status) as status,first(tags) as tags, max(severity) as severity,first(confidence) as confidence,first(assignee) as assignee,first(resolution) as resolution,first(timeToResponse) as timeToResponse,first(timeToDetection) as timeToDetection,first(timeToRemediation) as timeToRemediation,first(signals) as signals,values(eventname) as eventnames by id,insightid,name,entitytype,entityvalue 

// lets squash down size of the signals field so we don't generate a massive lookup
| parse regex field=signals "\"ruleId\":\"(?<rule>[^\"]+\",\"ruleName\":\"[^\"]+\")" multi
| replace (rule,"\"","") as rule
| replace (rule,"ruleName","") as rule

// handling for change to sev between string and numbers
| tostring(severity) as sev_string
| 0 as s
| if (sev_string matches /1|LOW/,1,s) as s
| if (sev_string matches /2|MEDIUM/,2,s) as s
| if (sev_string matches /3|HIGH/,3,s) as s
| if (sev_string matches /4|CRITICAL/,4,s) as s
| todouble(s) as severity

// final aggregation to save to a lookup with only one row for most recent status of insight
| values(rule) as rules,max(_messagetime) as time,first(status) as status,first(tags) as tags, max(severity) as severity,first(confidence) as confidence,first(assignee) as assignee,first(resolution) as resolution,first(timeToResponse) as timeToResponse,first(timeToDetection) as timeToDetection,first(timeToRemediation) as timeToRemediation,first(eventnames) as eventnames by id,insightid,name,entitytype,entityvalue // first(signals) as signals,

// enable this line to write data to populate the lookup table with backdated data say one time for -90d
// Schedule a version of this search to save to the lookup every 15m for -15m 
//| save path://"/Library/Admin Recommended/CSIEM/Lookups/cse_insights_status"

```

Save the search and schedule 
In the scheduling tab:
-  every 15m for -15m
- for action type choose save to lookup
- choose the path from earlier to the cse_insights_status
- choose Merge type

This should overwrite each row with the most recent insight-xxx value as it turns up in the audit log and over time we will still end up with one row with the most recent status update.
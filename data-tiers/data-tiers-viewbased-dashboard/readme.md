# Logs data volume tiers view based dashboards and sample queries
In large sumo accounts the data volume with tiers can have high cardinaility and result in slow queries or timeouts due to the 'parse regex... multi' required to parse the data volume indexes.

This solution demonstrates how to create one or more custom scheduled view to provide faster query performance and much greater scalability for larger accounts that have high cardinality in data volume diemsions, or want to run reporting over long time ranges.

The queries in this solution effectively replace origional this expensive parse regex multi in the original query:
```
(_index=sumologic_volume) _sourcecategory=*_and_tier_volume
| parse regex "\{\"field\":\"(?<value>[^\"]+)\",\"dataTier\":\"(?<dataTier>[^\"]+)\",\"sizeInBytes\":(?<sizeInBytes>[^\"]+),\"count\":(?<count>[^\"]+)\}," multi

```
with
```
_view=data_volume_custom_tiers_*
```

Note: because scheduled views summarise data as it's ingested rather than by event time you may see small timeshifts in the totals reported vs the raw data query. Over hours or days though this difference is statistically insignifigant in most cases. 

An alternative approach is to use scheduled searches running similar queries that 'save to index' rather than scheduled view. This allows for changes to custom queries over time and larger aggregation timeslices (say 15m rather than 1m).

## Determine required number of views
Run the data-tiers/data-tiers-viewbased-dashboard/scheduled-view-query.sumo for a recent period of 1 minute (say '-10m -9m') in the last 24 hours
ideally this would be a peak ingest time where cardinality is highest.

If either of the answers to the questions below are 'no' make multiple views instead of one view.
- does the query execute in <15s?
- does the query complete without a warning about regex?
- do I get a very large number of result rows > 5000, (usually this will be just one 'dimension' that has high cardinality)?

## Create one or more views
A) single view (NO to all questions)
Create a single scheduled view similar to the image shown below. For the name use 'data_volume_custom_tiers_all'

B) Multiple views (YES to one or more questions)
Create a single view for the highest cardinality dimension with a modified query for example:
One or more high cardinatliy views:
query: 
```
(_index=sumologic_volume) _sourcecategory=sourcecategory_and_tier_volume
...
```

name: data_volume_custom_tiers_sourcecategory

Remaining catch all view:
query: 
```
(_index=sumologic_volume) _sourcecategory=*_and_tier_volume
not _sourcecategory=sourcecategory_and_tier_volume // exclude each high cardinatlity category
...
```
name: data_volume_custom_tiers_other

So say we might end up with two views: ```(_view=data_volume_custom_tiers_sourcehost or  _view=data_volume_custom_tiers_other)```

## custom views for very high cardinality dimensions 3000+ per day
Generally where there are lots of ephemeral container ids or similar in a data volume dimension such as sourcehost it's preferable to remove these to have a smaller number of view rows per interval (and much faster query performance.)

You will see this when testing out the views queries in earlier steps where you say get 100s of pages of results for a 1m period. Ideally one would want less than 1000 result rows per dimension (sourcecategory, sourcehost etc) per minute. If there are greater than 5000 rows for a dimension per minute reporting will get very slow.

In cases where a dimension such as _sourcehost might contain an ephemeral container guid as there are 10s of thousands of rows per day you may have to use a custom aggregation in the scheduled view query to remove the guid string to get good performance for example:
```
(_index=sumologic_volume) _sourcecategory=sourcehost_and_tier_volume 
| parse regex "\{\"field\":\"(?<value>[^\"]+)\",\"dataTier\":\"(?<dataTier>[^\"]+)\",\"sizeInBytes\":(?<sizeInBytes>[^\"]+),\"count\":(?<count>[^\"]+)\}," multi 
| timeslice by 1m 
| parse field=_sourcecategory "*_and_tier_volume" as dimension 
| sum(count) as events,sum(sizeinbytes) as bytes by datatier, dimension,value,_timeslice
// one or more such replacements might be useful here
| replace (value,/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/,"GUID") as value
| replace (value,/[a-f0-9]{20,}/,"GUID") as value
| sum(events) as events,sum(bytes) as bytes by datatier, dimension,value,_timeslice
```

so say I had 100 rows of versions of a category with guid values like this:
a/b/c/7f727381-389f-4ed1-ba24-2540e53a4007

the view would have one row like this:
a/b/c/GUID

If it's likely that changes would be required to these custom aggregations over time there are several possible approaches:.
1. version schedulded views. When a change is required disable the previous view and create a new version with no backfill with a version string in the view name for example _view=data_volume_custom_sourcecategory_v1 _view=data_volume_custom_sourcecategory_v2 etc
2. consider using scheduled searches that save to a view instead of ascheduled view. This means changes can be made to the scheduled view over time to modify the custom aggregations

## Import the views dashboard
Open the-dashboard.json in a text editor and make sure this part of each panel query matches your views you have created:
```
(_view=data_volume_custom_tiers_sourcehost or  _view=data_volume_custom_tiers_other)
```
for example you might edit/replace this with ```_view=data_volume_custom_*``` instead.

## Query Notes for Using the New Views
### filtering
filtering by type is done on the 'dimension' column instead of the _sourcecategory value.

### bytes not sizeInBytes
in this view query the 'sizeInBytes' parsed field is called bytes

### sum not count
to get totals of events or bytes make sure to sum(column) not count e.g ```sum(events) as events```


# Log Explorers

## Keyword Log Explorer
A custom dashboard that enables you to start with a search say by category, collector and /or keywords, then drill down to a new search tab only showing surrounding messages.

The new search window will show events from just that source file up to n events, +/- seconds (set in filters) centered on the event matching the search string. Keywords in the new search are included as an "OR" so they are still highlighted but all rows of the log are shown.

Here is how you use it.
- Set the required time range, filters and keyword(s) in the filter parameters for the dashboard.
- The dashboard will display two time series graphs to show event counts by category and collector over time, and in the bottom panel an Matching records window.
- Each row of the table has a clickable link to open a new search tab for the original source file showing just your desired context. 
- Right  click on this link for the event you want to view in context and choose 'open in new sumo tab'

This will open a new search  

For example say my filter settings were:
```
Search string: _sourceCategory=beta* _collector=pm* error
maximum events returned: 25
+/- seconds: 15
```

I might get back a number of error events. each row has a clickable in context link. Say for this one event:
```
15.12.2021 11:06:06.989 Error [111] connecting socket: Connection refused
```

the right click drilldown query will be for +/- 15 seconds of that time: '12/15/2021 12:05:51 PM to 12/15/2021 12:06:21 PM' in the same log and for only messages closest in messageid to that record which might be say 1035046449433087643
```
_sourcecategory=beta/log/app/cms _sourcename=/var/log/cms/newlog.log _collector=pm-uatcms-beta.abc.efg
((not XXIGNOREDXX) or error)
 | "1035046449433087643" as mid | abs(_messageid - mid) as offset | sort offset asc | limit 25 | tostring(_messageid) as id | fields -mid,offset,id | sort _messagetime
 ```

This will open a new search window that includes events from the source file around the matching event. The +/- time range for the new window and number of events are controlled by the dashboard filters. 

Since we still have this query all records are returned by keyword such as error will still be highlighted in the UI.
```
((not XXIGNOREDXX) or error)
```

You can also use the built in drill-down capability in sumo to filter the dashboard using the UI.
Click on a value in the time series chart for collector or sourcecategory
this will open the side bar for that series in which you can click the linked dashboard.
this will reopen the dashboard with that category or collector added in the filters
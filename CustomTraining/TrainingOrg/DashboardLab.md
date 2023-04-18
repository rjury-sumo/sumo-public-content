This lab uses the Training Org that is used in Sumo Certjams.

Log in as a training user as per usual method such as training+analyst###@sumologic.com where ### is a number from 0001-999

# Create a dashboard
- Use the New menu to make an new dashboard
- It should open a new tab with a mostly blank dashboard
- First click the time range selector in the top right corner.
- Tick 'set as dashboards's default time range' and change it to 'Last 60 Minutes'

## First let's setup a template variable 
You can see detailed info about filters here: https://help.sumologic.com/docs/dashboards-new/filter-template-variables/
- Click Create new variable + to add a new parameter on top left of the dashboard (if you can't see this click the filter button in top right.)
- For Variable Name use  ```keywords```
- For Variable Type use ```Custom List```
- You can put a list of things such as a,b,c in the list but it's optional
- Users can actually type anything in a template variable the list is only suggesitons
- Save it.

## Set a name
- Change your dashboard name including your initials for example: ```My Demo Cloudfront Dashboard - RJ``` by clicking on the name to edit it.

## Add a Categorical panel
- Add a new panel of type Categorical. 
- Use the query below, note the variable name must match what you set in the last step or the query will not run.
- This search selects cloudfront logs by sourcecategory, parses the tab separated fields into runtime fields and counts by the status field.
```
_sourcecategory = *cloudfront* {{keywords}} 
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by status | sort _count
``` 
- Click the looking glass icon or press enter to run the search.
- In the "Categorical" section try changing the chart type to try Table, Bar or Pie
- You can click the panel title 'Untitled' to change it's name
- When you are happy with it Click Add to Dashboard to save.

## Using the filter
This dashboard  has a filter defined, we called ```keywords``` . Filters make it easy to re-use dashboards across environments or services, and to enable them to be powerful first step troubleshooting tools. This means are run time the value ```{{keywords}}``` in the panel will be replaced by whatever you type in the filter.
- Try changing entering a keyword such as ```304``` or ```Miss```  
- what effect does this have on results?
- Put the value back to *

## Duplicate and edit to add a new panel
- Use the ellipsis button on the panel to bring up the panel menu on the top righ tof a panel. (You have to hover over the top right near the time range to see it).
- Choose Duplicate. 
- Then choose Edit on the new panel. 
- Remove the count line at the end. You can delete it or add ```//``` to the line to comment it out
- Add a new aggregation instead:
```
| timeslice
| count by _timeslice
```
- Change the panel type to **Time Series** 
- Run the query 
- Change the panel time range to -3h and run again
- Then try some different time series chart types such as line and area.

## Using time compare
Time compare is a very powerful way to understand if current performance is anomalous with previous performance.https://help.sumologic.com/docs/search/time-compare/
- Edit the panel again and add: ``` | compare with timeshift 7d```
  The query should now be:
```
_sourcecategory = *cloudfront* {{keywords}} 
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| timeslice
| count by _timeslice | compare with timeshift 7d
```
- Save the panel by using Update Dashboard
- You will now see the count of events compare to the count of previous events from last week at the same time as two seperate lines on the graph.

## Multi Series Time Charts
It's very useful to represent dynamic series changes over time.
- Duplicate the time series panel you just created.
- Change the last line so it looks like this. Transpose reformats time series data with a series column into a format for graphing over time. 
```
_sourcecategory = *cloudfront* {{keywords}} 
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| timeslice
| count by _timeslice, status | transpose row _timeslice column status
```
- change the Chart Type to Column
- Change the Display Type below that to Stacked
- Update the chart and you will see each status code stacked in time series buckets over time.

## Honeycomb Panels
Let's add a new panel type - the honeycomb type. This is good for showing dynamic changes ranges of things like nodes in auto scale groups for example vs a dimension such as CPU use.
- Add a new panel using Add Panel 
- Choose the honeycomb type. 
- Add this search for the panel:
```
_sourcecategory = *cloudfront* {{keywords}}
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by edgeloc | sort _count 
 ```
 - You will see one node for each edge location, and it is color coded by volume of count
 - Name the panel something like Hits by edgeloc and Update Panel

## Map panels with geo location
- Add a Map type panel. 
- This uses an ip lookup service to geolocate user traffic. For the query use:
```
_sourcecategory = *cloudfront* {{keywords}}
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by c_ip
| geoip c_ip
| sum(_count) as hits by latitude,longitude,country_name
```

## Review the Cookbook for more options
This is only a taste of what is possible with dashboards. Check out the panel cookbook at: https://service.sumologic.com/ui/#/dashboardv2/x8XDNocVZV9c0vwxV8dRGtFPiTSKwuXOd2UpAVyviIMB2dNkAL5yI0OfRnOe


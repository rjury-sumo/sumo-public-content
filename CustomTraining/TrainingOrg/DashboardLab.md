This lab uses the Training Org that is used in Sumo Certjams.

Log in as a training user as per usual method such as training+analyst###@sumologic.com where ### is a number from 0001-999

Use the New menu to make an new dashboard

1. First let's setup a template variable on this dashboard so it's filterable later as we build out the dash. You can see detailed info about filters here: https://help.sumologic.com/docs/dashboards-new/filter-template-variables/
- Click the filter icon
- click + to add a new parameter on top left of the dashboard
- for Variable Name use  ```keywords```
- for Variable Type use ```Custom List```
- you can put a list of things such as a,b,c in the list but it's optional
- users can actually type anything in a filter param later
- Save it.

1. Change your dashboard name for example: ```My Demo Cloudfront Dashboard - RJ``` by clicking on the name to edit it.

2. Add a new panel of type Categorical. For query use 
```
_sourcecategory = *cloudfront* {{keywords}} 
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by status | sort _count
``` 
Click the looking glass icon or press enter to run the search.
In the "Categorical" section try changing the chart type to try Table, Bar or Pie
-  then when you are happy with it Click Update Dashboard to save.

1. This dashboard already has a filter defined, we called ```keywords``` . Filters make it easy to re-use dashboards across environments or services, and to enable them to be powerful first step troubleshooting tools. 
Try changing the sourcecategory in the filter and entering a keyword such as 304 - what effect does this have on results?

1. Use the ellipsis button on the panel to bring up the panel menu. Choose Duplicate. Then choose Edit on the new panel. Remove the count line and instead do:
```
| timeslice
| count by _timeslice
```
Change the panel type to **Time Series** and try running the query to with different chart types and save it.

1. Edit the panel again and add: ``` | compare timeshift 7d```
Save the panel and you will now see the count of events compare to the count of previous events from last week at the same time. Time compare is a very powerful way to understand if current performance is anomalous with previous performance.https://help.sumologic.com/docs/search/time-compare/


6. Let's add a new panel type. 
- Duplicate your panel again and edit the new version. 
- Choose the honeycomb type. This is good for showing dynamic changes ranges of things like nodes in auto scale groups for example vs a dimension such as CPU use.
- Add this search for the panel and name it something like Errors by domain:
```
_sourcecategory = *cloudfront* {{keywords}}
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by edgeloc | sort _count 
 ```

6. Add a Map type panel. This uses an ip lookup service to geolocate user traffic. For the query use:
```
_sourcecategory = {{sourcecategory}}  {{keywords}} 
| parse "*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*" as _filedate,time,edgeloc, scbytes, c_ip,method,cs_host,uri_stem,status,referer,user_agent,uri_query,cookie,edgeresult,edge_request,domain,protocol,bytes,time_taken,forwarded_for,ssl_protocol,ssl_cipher, x_edge_response_result_type,protocol_version 
| count by c_ip
| geoip c_ip
| sum(_count) as hits by latitude,longitude,country_name
```

7. This is only a taste of what is possible with dashboards. Check out the panel cookbook at: https://service.sumologic.com/ui/#/dashboardv2/x8XDNocVZV9c0vwxV8dRGtFPiTSKwuXOd2UpAVyviIMB2dNkAL5yI0OfRnOe


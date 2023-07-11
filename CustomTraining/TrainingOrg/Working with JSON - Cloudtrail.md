# Search Lab - Working with JSON Cloudtrail.
This lab uses the Training Org that is used in Sumo Certjams.
Log in as a training user as per usual method such as training+analyst###@sumologic.com where ### is a number from 0001-999

**Note**: we will be searcing using Advanced Mode. You might find your UI is in basic mode so you will have to switch to Advanced as per: https://help.sumologic.com/docs/search/get-started-with-search/search-page/search-modes/


**Tip:** Adding and removing comment lines
You can select lines and comment/uncomment them with ```Cmd + /``` (```Cntrl + /``` on Windows)

**Tip:** Pressing Enter or Return runs the search. You can add a new line with Shift + Enter|Return.

# In this Lab
- How to run a basic search using JSON formatted log
- How to navigate the UI: field browser, time picker etc
- Raw messages vs Aggregate results
- How to turn raw logs into insights by parsing fields and making charts

## About AWS CloudTrail Logs
Cloudtrail api audit events have an errorCode key if the API call failed.
This can be a very valuable source for both observability to find and fix broken workloads and in the security domain to prevent, detect and respond to security threats.

## AWS Cloudtrail Errors
What an AWS Cloudtrail API call fails a cloudwatch event is logged containing an errorCode key.

This can be a very valuable source for both observability to find and fix broken workloads and in the security domain to prevent,detect and respond to security threats.

# Lab Exercises

## 1. Run a search
Start with New Button then choose Search
Paste this into your new search window and run this search for "last 15m" which is the default. This search is scoped using a metadata field (_sourcecategory) and a keyword so it will only include cloudtrails with errorcode as a string.

```
_sourceCategory = *cloudtrail*  errorcode
```

You will now see Messages returned in the search window.

## 2. Review the Search UI Page Features in Help Docs
![](search_page.png)
Open this sumo docs page and you can see what the various parts of the search UI can do.
https://help.sumologic.com/docs/search/get-started-with-search/search-page/

## 3. Using the search histogram
![](histogram.png)
There are two really useful features of the search histogram which shows messages over time.a
a. You can click a segment to move to the messages page for that time range
b. If you Shift + click on a selected histogram bar it will open a duplicate search window for just that time range. Try this and then return back to this search Tab.

## 4. Using the Field Browser
The [field browser](https://help.sumologic.com/docs/search/get-started-with-search/search-page/field-browser/) shows fields in the current search scope. 
1. Tick a box next to some fields in the browser and note how this changes the columns displayed.  
2. Try the search box in the browser to see fields with 'arn' in the name.
3. Click on the text of a field name such as eventName to show a pop up. The pop up shows the breakdown of events for the first 100k results. 
4.  In the pop up click on ```Top Values Over Time``` This will open a new search tab that adds to your base query in a new search window. Run this new search and note how there is now an 'aggregates tab'. 



## Messages and Aggregate Results
Next try changing the time range to another value by entering a relative time expression:
```-6h```

Run the search below which counts each value of eventname but in 5 minute time buckets and outputs this in a format suitable for charting (using transpose). 

Once this search completes try out some of the different chart types in the Aggregates tab like Column, Area and Line using the icons in the aggregates tab:
```
_sourceCategory = *cloudtrail*  errorcode
| timeslice 5m | count _timeslice, eventname | transpose row _timeslice column eventname
```

## 6. Parsing Fields Manually
By default Sumo auto parses JSON logs at search time but it's good query practice to parse out fields explicitly even though we don't have to, and parsing is a key skill for working wiht logs as it enables you to create any required fields at search time.
Here you see two parse operators - JSON and Parse (which uses pattern matching). Run this search:

```
_sourceCategory = *cloudtrail*  errorcode
| json field=_raw "errorCode" 
| json field=_raw "errorMessage"
| parse "eventSource\":\"*\"" as event_source 
| parse "\"eventName\":\"*\"" as event_name 
| parse "awsRegion\":\"*\"" as aws_Region 
| json field=_raw "recipientAccountId"

// If a field is optional we want to add nodrop or sumo will filter out events that don't match
| parse "\"userName\":\"*\"" as user nodrop
| json "userIdentity.arn" as arn nodrop
```

You will find there is now an 'arn' field in the field browser. 

Next to the Run search Hourglass button open the settings cog and disable JSOM auto parse mode. Run the search again and note how the list of fields in the browser is reduced as only indexed fields or explicitly parsed fields are shown.

## 7. Filtering searches
Next we will use some filtering to narrow down search results.
This will filter results just to AccessDenied in the errorcode field. Run:
```
_sourceCategory = *cloudtrail*  errorcode
| json field=_raw "errorCode" 
| json field=_raw "errorMessage"
| where errorcode = "AccessDenied"
| parse "eventSource\":\"*\"" as event_source 
| parse "\"eventName\":\"*\"" as event_name 
| parse "awsRegion\":\"*\"" as aws_Region 
| json field=_raw "recipientAccountId"
| parse "\"userName\":\"*\"" as user nodrop
| json "userIdentity.arn" as arn nodrop
```

## Iterating on a search to drill down further
We want to know more about these access deined errors so we can break things down in more detail. In most cases high numbers of failures here will just indicate broken workloads in AWS but in a security context could point to security issues or malicous activity.

To provide more details this new search version is an iteration on the previous one that provides a higher level of detail and some aggregation to summarize the results in format suitable for a table.  

Here is the next version of the search to execute:
```
_sourceCategory = *cloudtrail*  errorcode
| json field=_raw "errorCode" 
| json field=_raw "errorMessage"
| where errorcode = "AccessDenied"
| parse "eventSource\":\"*\"" as event_source 
| parse "\"eventName\":\"*\"" as event_name 
| parse "awsRegion\":\"*\"" as aws_Region 
| json field=_raw "recipientAccountId"
| parse "\"userName\":\"*\"" as user nodrop
| json "userIdentity.arn" as arn nodrop
| count by errorcode,errormessage,recipientaccountid,user,arn | sort _count
```

You will now have an Aggregates Tab as well as messages tab. 
On the aggregates choose the Table format. 

## Review Best Practices for Search
There are few key things to know to make fast efficient searches in Sumo. 

Follow these key tips:
### Always use a sourcecategory or index in your search 
A good built in metadta scope will reduce data scanned and speed up search for example:
``` 
_sourcecategory=prod/*
_sourcecategory=prod/aws/cloudtrail
_index=prod_data
```
As you run searches you can check what categories or indexes apply to your logs by checking the values in the field browser for the Source Category and Index field.

### Keywords speed up searches
Add a keyword to make your search specific if you can - even if it just gets rid of most events you don't want. Keywords make searches much faster than those that use just where to filter results.

In our above example we could do someting like:
```
_sourceCategory = *cloudtrail*  AccessDenied
| json field=_raw "errorCode" nodrop
| where errorocde=AccessDenied
```

### Fields can be pre-parsed at indexing time with a Field Extraction Rule
Your Sumo Amin can create a Field Extraction to store fields in the index where data is ingested. If an administrator had setup an extraction rule to pre-parse and index the errorcode field we could simply do this:
```
_sourceCategory = *cloudtrail*  errorcode=AccessDenied
```

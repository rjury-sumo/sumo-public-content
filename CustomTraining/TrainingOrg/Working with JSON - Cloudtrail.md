# Search Lab - Working with JSON Cloudtrail.
This lab uses the Training Org that is used in Sumo Certjams.
Log in as a training user as per usual method such as training+analyst###@sumologic.com where ### is a number from 0001-999

Start with New Button then choose Search

**Note**: we will be searcing using Advanced Mode. You might find your UI is in basic mode so you will have to switch to Advanced as per: https://help.sumologic.com/docs/search/get-started-with-search/search-page/search-modes/


**Tip:** Adding and removing comment lines
You can select lines and comment/uncomment them with ```Cmd + /``` (```Cntrl + /``` on Windows)

**Tip:** Pressing Enter or Return runs the search. You can add a new line with Shift + Enter|Return.

## Search AWS CloudTrail API logs
Cloudtrail api audit events have an errorCode key if the API call failed.
This can be a very valuable source for both observability to find and fix broken workloads and in the security domain to prevent,detect and respond to security threats.

First we will search for cloudtrail logs by sourcecategory, and add errorcode as a keyword.

Paste this into your new search window and run this search for "last 15m" which is the default.
```
_sourceCategory = *cloudtrail*  errorcode
```

Next open this docs link to explore the various options in the seach UI page
Open this sumo docs page and you can see what the various parts of the search UI can do.
https://help.sumologic.com/docs/search/get-started-with-search/search-page/

A couple of key things to try before we go further:
1. in the Field Browser on the left side tick the box next to some field names to add them to the results table. Review the docs page and about Field Browser features: https://help.sumologic.com/docs/search/get-started-with-search/search-page/field-browser/
2. In the field browser, click on a text of a field name such as eventName to show a pop up. The pop up shows the breakdown of events for the first 100k results. 
3.  Click on ```Top Values Over Time``` This will open a new search tab that adds to your base query. This adds timeslice and transpose to format a breakdown of event names over time.
```
| timeslice 10 buckets | count _timeslice, eventname | transpose row _timeslice column eventname
```

Next try changing the time range to another value say "last 3 hours" or you can put in a relative time like -6h. Let's try a different timeslice query with the times in 5 minute buckets. Once this search completes try out some of the different chart types in the Aggregates tab like Column, Area and Line:
```
_sourceCategory = *cloudtrail*  errorcode
| timeslice 5m | count _timeslice, eventname | transpose row _timeslice column eventname
```

By default Sumo auto parses JSON logs at search time but it's good query practice to parse out fields explicitly even though we don't have to
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

Next we will use some filtering to narrow down search results.
This will filter results just to AccessDenied in the errorcode field. Add this to your search and run:
```
| where errorcode = "AccessDenied"
```

Next we are going to use some aggregate operators to drill down further into the AccessDenied errors. We want to know more about these access deined errors so we can break things down in more detail. In most cases high numbers of failures here will just indicate broken workloads in AWS that need cleaning up but can also are relevant in security domain.

Add this to your search and run it again:
```
| count by errorcode,errormessage,recipientaccountid,user,arn | sort _count
```

You will now have an Aggregates Tab. On the aggregates tab you can now choose options like Table, various charts or "Add to Dashboard". Depending on what syntax you chose for the search you will have various options for chart layouts.

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
Add a keyword to make your search specific if you can - even if it just gets rid of most events you don't want
This is always faster than parsing a field at search time and then filtering using a where clause. 
In our above example we could do someting like:
```
_sourceCategory = *cloudtrail*  AccessDenied
| json field=_raw "errorCode" nodrop
| where errorocde=AccessDenied
```

### Fields can be pre-parsed at indexing time with a Field Extraction Rule
Your Sumo Amin can create a Field Extraction to store fields in the index where data is ingested. This makes searches run faster with less typing as you could just do say:
```
_sourceCategory = *cloudtrail*  errorcode=AccessDenied
```
### More Tips
Review this docs page about search best practices. These are most relevant in large Sumo environments or when running searches over larger data sets. Following key points here will make your searches fast and much more efficient:
https://help.sumologic.com/docs/search/get-started-with-search/build-search/best-practices-search/

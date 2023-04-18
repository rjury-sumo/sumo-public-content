# Search Lab - Working with JSON Cloudtrail.
This lab uses the Training Org that is used in Sumo Certjams.
Log in as a training user as per usual method such as training+analyst###@sumologic.com where ### is a number from 0001-999


Here is the search we will be using. 
You can paste in the whole query and comment/comment sections as required

## Adding and removing comment lines
You can select lines and comment/uncomment them with ```Cmd + /``` (```Cntrl + /``` on Windows)

## Reference Query
```
// cloudtrail api audit events have an errorCode key if the API call failed
// This can be a very valuable source for both observability to find and fix broken workloads
// And in the security domain to prevent,detect and respond to security threats
// This will search for cloudtrail logs by sourcecategory, and return those that have errorCode as a keyword
_sourceCategory = *cloudtrail*  errorcode

// by default Sumo auto parses JSON logs at search time but it's good query practice to parse out fields explicitly even though we don't have to
// Here you see two parse operators - JSON and Parse (which uses pattern matching)
| json field=_raw "errorCode" nodrop
| json field=_raw "errorMessage"
| parse "eventSource\":\"*\"" as event_source 
| parse "\"eventName\":\"*\"" as event_name 
| parse "awsRegion\":\"*\"" as aws_Region 
| json field=_raw "recipientAccountId"

// If a field is optional we want to add nodrop or sumo will filter out events that don't match
| parse "\"userName\":\"*\"" as user nodrop
| json "userIdentity.arn" as arn nodrop

// 2 lets try searching for AccessDenied Errors to find out what API calls are failing authentication
// add a where clause for accessdenied 
//(note we could also have used AccessDenied as a keyword in this query too!)
//| where errorcode = "AccessDenied"

// 3
// we want to know more about these access deined errors so we can break things down in more detail
// in most cases high numbers of failures here will just indicate broken workloads in AWS that need cleaning up but can also are relevant in security domain.
//| count by errorcode,errormessage,recipientaccountid,user,arn | sort _count
```

# Create a log search.
Start with New / Log Search
Note: we will be searcing using Advanced Mode. You might find your UI is in basic mode so you will have to switch to Advanced as per: https://help.sumologic.com/docs/search/get-started-with-search/search-page/search-modes/

## 1 Paste in the reference query and review in Search Page
Paste in the reference query and run it
Since parts 2 and 3 are commented out it will return just Messages tab.

Review the docs page: https://help.sumologic.com/docs/search/get-started-with-search/search-page/

The fields you created will be visible in the Field Browser on left side. Review the docs page and about Field Browser features https://help.sumologic.com/docs/search/get-started-with-search/search-page/field-browser/

Note how if you scroll across the messages window to the final Message column it's formatted in the UI to show the JSON structure.
Try a right click on a a key name to see what options are avaialable and then the same for a key value.

## 2 Search for AccessDenied Only
Let's try searching for AccessDenied Errors to find out what API calls are failing authentication
Add a where clause for accessdenied by uncommenting this line:
```
| where errorcode = "AccessDenied"
```

Note you could also add AccessDenied as a keyword on line one of the search. This would be fast to run but might not get correct results if it was possible for AccessDenied to appear outside the errorcode field.

Run the search and see what results are returned.

## 3 Create an Insight with Aggregation
A key technique in both Observabiltiy and Security with Sumo is to use search time fields to iterate on the data and use the fields you created to create valuable insights. This enables you to quickly understand trends and find root causes.

Uncomment the section 3 line and run the query again.
```
| count by errorcode,errormessage,recipientaccountid,user,arn | sort _count
```

You will now have a Aggregates tab and a table of summarized data that could quickly help us understand which users are having AccessDenied errors. A strip of new buttons can be found on the Aggregates results tab where a vizualzation other than the table we have now might apply to your data, or you can use this to add this search to a Dashboard.

## 4 Building syntax with Field Browser
Change back to the Messages tab that shows your raw messages.
In field browser click on the name of the event_name field so a pop up window appears. It will show statistics.
Click on ```Top Values Over Time```
this will open a new search tab that adds to your base query, This adds timeslice and transpose to format a breakdown of event names over time.
```
| timeslice 10 buckets | count _timeslice, eventname | transpose row _timeslice column eventname
```

In the new aggregates tab try different chart types such as line, area and column to see how this could be formatted for easier review.

## 5 Review Best Practices for Search
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

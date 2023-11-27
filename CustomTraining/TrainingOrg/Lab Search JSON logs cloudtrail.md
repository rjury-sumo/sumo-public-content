# Lab Search - Working with JSON Cloudtrail.
This lab uses the Training Org that is used in Sumo Certjams.
Log in as a training user as per usual method such as:
- training+analyst###@sumologic.com 
  
where ### is a number from 0001-999.

You can find this month's training password by going to your Sumo instance, then use the Home, Certification tab to open the training portal.

Work through the exercises below.

**Note**: In this lab we assume your searches are in Advanced Mode. You might find your UI is in 'basic mode' so you will have to switch to Advanced as per: https://help.sumologic.com/docs/search/get-started-with-search/search-page/search-modes/

Tip:
- Adding and removing comment lines. You can select lines and comment/uncomment them with ```Cmd + /``` (```Cntrl + /``` on Windows)
- Pressing Enter or Return runs the search but
- Add a new line with ```Shift + Enter```  or ```Shift + Return```.

# In this Lab
- How to run a basic search vs JSON formatted log
- How to navigate the UI: field browser, time picker etc
- Raw messages vs Aggregate results
- How to turn raw logs into insights by parsing fields and making charts

## About AWS CloudTrail Logs
Searching JSON structured logs is a common use case for Sumo Logic as JSON logs are used for many applications.
A good example of JSON logs is AWS Cloudtrail - the audit log for all API calls vs APIs in an AWS account.
So for this exercise we will use JSON formatted Cloudtrail logs in the lab environment.

# Use Case Overview
When an AWS Cloudtrail API call fails, a CloudTrail event is logged containing errorCode and errorMessage keys. This can be a very valuable source for both observability to find and fix broken workloads and in the security domain to prevent, detect and respond to security threats.

For example AccessDenied could indicate a broken workload or a failed authentication attempt by a malicious user.

In these exercises we will create some searches to drill into AWS API errors in AWS Cloudtrail logs and show how to turn JSON logs into insights.

## 1. Run a search and review Messages Tab
At top of the Sumo Logic UI window click the blue + New button then choose Search. 

The search below includes a metadata value (sourcecategory) and some keywords to narrow down results to just valid Cloudtrail events with an errorCode string in them.

**Tip**: It's a good search practice to include a **_sourcecategory** or **_index** in each search to scope for best performance.

- Paste this into your new search window
```
_sourcecategory = Labs/AWS/CloudTrail* recipientaccountid errorcode
```

-  Change the time range to "last 60 minutes" (time picker is just to left of blue search icon)
-  Run the search by clicking the blue search button icon or pressing enter in the search window.

You will now see Messages returned in the Messages Tab and fields in the Field Browser.
![](./images/search_result.png)

- In the "message" column note how the [UI formats the logs as JSON events](https://help.sumologic.com/docs/search/get-started-with-search/search-basics/view-search-results-json-logs/) to make them more readable. 
- You can right click on JSON key or values to bring up menu quick actions for working with the logs such as 'Copy Message' or 'Parse the selected key'
- You can click 'view as Raw' to see the raw JSON formatted message
- There are other UI options to expand/collapse JSON

Take a quick visit to the [Getting Started With Search docs page](https://help.sumologic.com/docs/search/get-started-with-search/). This is the key resource as a new user to learn more about how to use the search interface. 


## 2. Use Log Message Inspector
Hover over any message in the results and use the pop up menu on the right to open [Log Message Inspector](https://help.sumologic.com/docs/search/get-started-with-search/search-page/log-message-inspector/). This shows detailed field values for each field in the event. 
![Alt text](./images/log-message-inspector-approach-2.png)

Click on a field and use the elipsis menu on right to 'filter selected value'. this will add more search filtering to the base query and is a handy way to quickly add more filtering dimensions.

## 3. Using the Search histogram and Auto Log Level Detection
![](./images/histogram.png)
There are several really useful features of the search histogram which shows messages over time.
a. You can click a segment to move to the messages page for that time range
b. If you ```Shift + click``` on a selected histogram bar it will open a duplicate search window for just that new time range
c. Events are color coded in the histogram by [auto detected log level](https://help.sumologic.com/docs/search/get-started-with-search/search-page/log-level/). You can click a level such as "ERROR" to filter to only logs of that level.

## 4. Using the Field Browser
On the left of the Messages tab you will see the [field browser](https://help.sumologic.com/docs/search/get-started-with-search/search-page/field-browser/). This shows all fields that exist in the current search scope, and could be a mix of metadata, pre-indexed fields and fields extracted at search time. 

By default sumo extracts every JSON field from logs at search time using "Auto Parsing" search mode so every possible Cloudtrail JSON key value will appear in the current search.

![](./images/field_browser_seearch.png)

In your search window with results try the following:
1. Tick a box next to some fields in the browser and note how this changes the columns displayed.  
2. Type 'error' in the search box in the top section of the field browser to see fields with 'error' in the name.
3. Click on the text errorCode field name to show a pop up. The pop up shows the breakdown of events for the first 100k results. This is a quick way to get insights about what is happening in your logs for key fields.
4.  At the bottom of the pop menu for the field click:  ```Top Values```. This will open a new search tab that adds to your base query in a new search window": 

```
( _sourcecategory = Labs/AWS/CloudTrail*  )
| count errorcode | top 10 errorcode by _count
```

Run this new search above. You will now have TWO search tabs: Messages and Aggregates.

By starting with raw logs, parsing fields and then using aggregation we can turn large volumes of log events into valuable insights in real time.

For example this search above now answers this querstion:
 - what are the top API errors by errorcode? 

## 5. Graphing Over Time
A key use case for Sumo Logic is to understand trends in extracted fields over time. How can we tell what errors are occurring and what the pattern is over the last six hours?

Use time range picker to change the time range to another value by entering a relative time expression:
```-6h```

Run the search below which counts each value of eventname but in 5 minute time buckets (using timeslice) and outputs this in a format suitable for charting (using transpose). 

```
 _sourcecategory = Labs/AWS/CloudTrail*
| json field=_raw "eventName"
| timeslice 5m 
| count _timeslice, eventname 
| transpose row _timeslice column eventname
```

On the Aggregates message tab:
- change to the column chart type using the column chart icon
- click the Options cog icon just to left of 'Add to Dashboard'
- choose 'Change Properties' from the list
- in the 'Stacking' section select Normal rather than None and click Save.
The new stacked chart nicely shows the distribution of errors over time. Since this is a lab environment the errors are quite periodic.

## 6. Parsing Fields Manually
By default JSON logs are auto parsed and all fields extracted. It's a good search practice as you get more advanced with Sumo Logic to parse out fields using parsing operators.

Here you see two parse operators - **JSON** and simple **Parse** anchor (which uses pattern matching) that shows a few ways to extract fields from logs. Don't worry if the search syntax is overwhelming right now - the key things to note are:
- parsed fields are already displayed as a column in results, and ticked in field browser
- parsing is one of the key skills in Sumo Logic to extract fields and generate insights from structured or semi-structured logs.

Run this search:
```
 _sourcecategory = Labs/AWS/CloudTrail* errorcode
// Parse a field using JSON operator
| json field=_raw "errorCode" 
| json field=_raw "errorMessage"
| json field=_raw "recipientAccountId"

// Parse a field using Parse anchor for simple patterns
| parse "eventSource\":\"*\"" as event_source 
| parse "\"eventName\":\"*\"" as event_name 

// nodrop keyword tells sumo to include all results even ones that fail parse.
// This is desired behaviour for optional JSON keys
| parse "\"userName\":\"*\"" as user nodrop
| json "userIdentity.arn" as arn nodrop

// You can parse a field as well as the whole message
// Here is example using the parse regex capture group parser
| parse regex field=arn "^arn:aws:[a-z]+::[0-9]+:(?<role>.+)" nodrop
```

## Bonus Time: Review Best Practices for Search
If you still have time in the lab review the key things to know to make fast efficient searches in Sumo.

### Always use a sourcecategory or index in your search 
A good built in metadta scope will reduce data scanned and speed up search and using an index or sourcecategory usually works best. For example:
```
_sourcecategory=prod/*
_index=prod_data
```

### Keywords speed up searches
Add a keyword to make your search specific if you can - even if it just gets rid of most events you don't want. Keywords make searches much faster than those that use just where to filter results because less events must be retrieved to be processed later.

In our above example we could use accesdenied as a keyword:
```
_sourceCategory = *cloudtrail*  AccessDenied
| json field=_raw "errorCode" nodrop
| where errorocde=AccessDenied
```

### Fields can be pre-parsed at indexing time with a Field Extraction Rule
Your Sumo admin can create a Field Extraction Rule that stores fields in the index when data is ingested to make searching easier and faster to execute. If an administrator had setup an extraction rule to pre-parse and index the errorcode field we could simply do this:
```
_sourceCategory = *cloudtrail*  errorcode=AccessDenied
```

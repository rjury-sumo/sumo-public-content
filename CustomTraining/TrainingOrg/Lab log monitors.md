# Lab: Creating Log Search Based Monitors

- [Lab: Creating Log Search Based Monitors](#lab-creating-log-search-based-monitors)
  - [New UI vs Old UI](#new-ui-vs-old-ui)
  - [In this Lab](#in-this-lab)
- [1. BASIC LAB](#1-basic-lab)
  - [1.1 Create a new log search](#11-create-a-new-log-search)
  - [1.2 Create a log monitor](#12-create-a-log-monitor)
  - [1.3 Trigger Conditions](#13-trigger-conditions)
  - [1.4 Trigger Types](#14-trigger-types)
  - [1.5 Alert Grouping](#15-alert-grouping)
  - [1.6 Formatting notification output with alert Variables](#16-formatting-notification-output-with-alert-variables)
  - [1.7 Playbooks](#17-playbooks)
  - [1.8 Monitor Details](#18-monitor-details)
  - [1.9 Other settings](#19-other-settings)
- [2. ADVANCED LAB](#2-advanced-lab)
  - [2.1 Dynamic thresholds with Time compare alerting](#21-dynamic-thresholds-with-time-compare-alerting)
  - [2.2  Creating a monitor for a timeslice log searches](#22--creating-a-monitor-for-a-timeslice-log-searches)
  - [2.3 Timeslice For AI Anomaly](#23-timeslice-for-ai-anomaly)
  - [2.4 Timesliced Data and Trigger Conditions](#24-timesliced-data-and-trigger-conditions)
  - [2.5 Timeslice vs 'effective timeslice'](#25-timeslice-vs-effective-timeslice)
  - [2.6 Modelling thresholds with alert grouping for logs with timeslice / transpose](#26-modelling-thresholds-with-alert-grouping-for-logs-with-timeslice--transpose)

This lab uses the Training Org that is used in Sumo Certjams but should work in any Sumo org ingesting container logs via the Kubernetes Collection Solution.

There are TWO lab sections: BASIC and ADVANCED

Log in as a training user as per usual method such as:
- training+analyst###@sumologic.com 
  
where ### is a number from 0001-999.

You can find this month's training password by going to your Sumo instance, then use the Home, Certification tab to open the training portal.

## New UI vs Old UI
There are two Web UIs available the [new UI](https://help.sumologic.com/docs/get-started/sumo-logic-ui/) and legacy old UI. Some steps in lab might vary based on what UI you are using. 
You can tell which UI your user account is using by checking these images. It's suggested to switch to new UI. In new UI the easiest way to start a new tab is:
1. click 'goto' or use cmd + k to open the goto dialog
2. start typing what you want to open e.g log for log search
3. click the menu item to open it. New UI uses native browser tabs so you can cmd + click to open this page as new tab

**new UI**
![alt text](images/new-ui.png)

**old UI**
![alt text](images/old-ui.png)

## In this Lab
**Note**: Detailed descriptions for all monitor UI options such as types of monitor, thresholds, and payload settings can be found in the [metrics lab](<./Lab metric search and create monitor.md>).

-------
# 1. BASIC LAB

This lab only covers the process to model monitors specifically for log search not all settings.
- How to run a logs search and create a monitor for a simple trigger on _count
- Typical monitor thresholds and settings
- View alerts page
- Open an alert response page, and start a Copilot investigation

For this basic lab the logs will count kubernetes container log errors to create log monitors. We will look at both how to alert for total errors or errors for each container seperately using alert grouping.

- Once you are finished with the lab don't save the monitor, instead **Cancel out of the new monitor** and return to the log search screen

## 1.1 Create a new log search
- new UI: cmd + K or open Goto and select Log Search
- old UI: At top of the Sumo Logic UI window click the blue + New button then choose Search.

**Tips**: 
You might be in 'basic' or 'advanced' search mode. For this lab we will use advanced mode to make it easy to paste in complete  searches. Verify you are in advanced mode by clicking the elipsis button on the right of the query window (just next to Blue query button). When editing log searches:
- Pressing Enter or Return runs the search
- Add a new line with ```Shift + Enter```  or ```Shift + Return```
- you can comment out search syntax by prefixing the line with //

Let's create the first search:
- paste in the search box:

```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
```
- Click the Blue search icon or press enter in the search window

You now have an raw log query with Messages tab only showing results.

Aggregate searches are easier to use last in features like alert grouping or customizing notifications Add ```| count``` to your search so now it is:
```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
| count
```
Run the search and you now have Messages and Aggregate results tabs

## 1.2 Create a log monitor
From the query elipsis menu select Create a [Monitor](https://help.sumologic.com/docs/alerts/monitors/overview/)

![Alt text](images/monitor_create.png)

You might find the docs page for [Create a Monitor](https://help.sumologic.com/docs/alerts/monitors/create-monitor/) helpful if you get stuck on any of the following sections.

## 1.3 Trigger Conditions
Monitors only alert on a change of state. This is different to legacy scheduled search that alerts whenever the condition (such as number of results) is satisfied.

Simple log alerts trigger where > 0 rows are returned or for aggreagate on the _count column. For this query type we would:
- setup the query with filtering where clause(s) so it returns no results unless there is an error
- setup a threshold in the alert in a monitor if the row count is >0

In the trigger conditions section:
- note this is a **Logs** type (Metrics and SLO are also possible types)
- note that for detection method this is **static** but anomaly models are available. 
  
Log monitors can use any numeric resulting column from aggregate from output. Instead for a raw query this would usually be  **returned row count**. Returned row count means different things in a raw vs aggregate context:
- for a raw log query this is the **count of events** returned by the search in the time range
- for an aggregate query this would be the **count of rows** in the aggregate result table

For aggregate searches usually we would use a column like _count as the trigger so  choose '_count' as the 'Trigger Alerts on' value

## 1.4 Trigger Types
In the next section enable a critical notification on the critical tab and enter a threshold, time range and evaluation interval. This would enable a notification for a critical state, but you can have critical, warning and/or no data alerts.

![alt text](images/alert.threshold.png)

Leave the 'advanced settings' as is:
- Alert Name Use Monitor Name

## 1.5 Alert Grouping
Two models are possible for monitors to track state for the monitor:
1. one alert /state per monitor as a whole
2. maintain separate states for each group (value of a field) or time series - this is called [Alert Grouping](https://help.sumologic.com/docs/alerts/monitors/alert-grouping/)

Update the query as below and then change the "Alert Grouping" setting to "one alert per: pod"

```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
| count by pod
```

Now our single monitor could track seperate statuses for each pod.
![alt text](images/alert.per.pod.png)

*You might notice the graph of status over time no longer displays. That's normal it's not supported for alert grouping in logs yet.*

## 1.6 Formatting notification output with alert Variables
It's nice to have descriptive alerts at 3am on your phone and there are many [alert variables](https://help.sumologic.com/docs/alerts/monitors/alert-variables/) available to customize the title and payload for the notification.

 One very useful field is ```{{ResultsJson.fieldName}}```. In our new alert grouped aggregate query ```{{ResultsJson.pod}}``` will put the pod name in the text in title or description or payload.

Go back to the "Alert Name" under advanced settings for trigger type.. Customize the "alert name" box to have a custom alert name:  
```High container errors for pod: {{ResultsJson.pod}}"```

- tick 'Critical' for the notification level. This will alert on critical only (not resolution)
  ![alt text](images/critical.alert.png)

In the notifications configuration:
- For type choose 'Create New Email'.
- enter any email address (we aren't going to save this!!)
- For subject choose: ```Monitor Alert: {{TriggerType}} on {{AlertName}}```

The message can be any customizable payload here is a suggested payload. This includes the url for the Alert Response Page. Update the notifcation message payload:

```
High errors found in kubernetes pod: {{ResultsJson.pod}}
Alert Response Page: {{AlertResponseURL}}
Description: {{Description}}
Detection: {{DetectionMethod}}
Type: {{MonitorType}}
Level: {{TriggerType}}
Condition: {{TriggerCondition}}
Value: {{TriggerValue}}
Query {{Query}}
```
![Alt text](images/monitor_settings.png)

## 1.7 Playbooks
In the final playbook section this would enable admins to codify tribal knowledge for an on-call so they know what exactly to do when they receive an alert. Playbooks support markdown and are visible in the alert response page, or can be added to notifications via the ```{{Playbook}}``` variable.

Automated Playbooks allow you to link to the [Automation Service](https://help.sumologic.com/docs/platform-services/automation-service/) to run automated responses or more complex notification actions.

## 1.8 Monitor Details
- Enter a monitor name such as "High error count for a Kubernetes Pod"
- Location: you can create folders to organize monitors, for now leave as is
- Tags: You can [tag monitors](https://help.sumologic.com/docs/alerts/monitors/settings/#tags). 
- Lets add: ```service=foo owner=bar``` tags.

## 1.9 Other settings
You can find more info on all possible monitor settings here: https://help.sumologic.com/docs/alerts/monitors/create-monitor/

**That is the end of the BASIC lab**. You can continue on to the advanced topics below if you have more time. **If you are finishing here just cancel out of the create monitor dilog without saving changes.**

--------
# 2. ADVANCED LAB
Advanced optional topics:
- Using timeslice searches in monitors
- Time compare log monitors
- Formatting data for Anomaly monitors
- Modelling thresholds with alert grouping for logs with timeslice / transpose

## 2.1 Dynamic thresholds with Time compare alerting

[Time compare](https://help.sumologic.com/docs/search/time-compare/) is a standard log query technique to compare current vs previous baseline performance. It works very well to compare performance for the monitor or per group in alert situations vs a baseline of previous periods. Here is an example that would produce > 0 rows only where error counts are much higher than the same time last week, and could use 'alert grouping' one per path
```
_index=Apache_Access1
status_code = 5*
| replace(url,/\?.*/,"") as path
| count by path
| compare with timeshift 7d 2 avg
| if(isnull(_count_14d_avg),0,_count_14d_avg) as _count_14d_avg
| _count - _count_14d_avg as change 
| 100 * (change / _count_14d_avg) as increase_pct
| where change > 5 and increase_pct > 50
```

## 2.2  Creating a monitor for a timeslice log searches
In some log monitor scenarios the starting query might contain a timeslice operator and that can impact final evaluation. you don't need to timeslice monitor searches and doing so can cause confusing evaluation results if the _timeslice and "in the last" settings are different.

Back in a new log search window execute this search using a time range of -6h
```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
| timeslice 5m | count by _timeslice
```

- Change this to a line graph layout to see trend over time. This will give you a good idea what 'normal' is and some benchmarks for threshold levels.
![alt text](images/k8s.error.count.timesliced.png)
The Aggregates tab shows tabular output of what will be passed to the monitor engine (since it's an aggregate query).

- Use the elipsis to create a new monitor.

## 2.3 Timeslice For AI Anomaly
Since the data is timesliced it would support the [AI Anomaly](https://www.youtube.com/watch?v=nMRoYb1YCfg) type, where each timeslice period data is streamed to the external data model. AI-driven alerting provides a simple easy to configure dynamic alerting experience:

- Model-driven anomaly detection: AI-driven alerts use 60 days of historical data (when available) to train and test an ML model so that hourly, daily and weekly (especially, weekday/weekend) seasonality are factored into baselines.
- AutoML: AI-driven alerts embed an AutoML framework where the analytics tune itself based on model performance on training datasets. Simply put, AutoML supports a “set it and forget it” experience with minimal user intervention.
- Model contextual and dynamic thresholds: AI-driven alerts have a sensitivity setting (low sensitivity for signals that are expected to be noisy and high sensitivity for critical indicators). Additionally, the user can configure the incident detector based on context. For example, in the Cluster detector, the user can specify how many data points in a detection window of say 5m need to be unusual before triggering an alert.

## 2.4 Timesliced Data and Trigger Conditions
As before this is a logs, static monitor. Let's **stay with 'static' for this lab.**

For this monitor trigger settings:
- trigger alerts on _count
- change the Trigger type to Critical, alert when > 250 for 5 minutes
- change the historical trend graph time range to -6h

The 'Historical Trend' graph may render differently if you use a timeslice in the monitor query, and will depend relationship between the timeslice vs the 'within > x' time value. 
How does changing the 'within' period to different values affect the graph?
- 15m
- 1 hour

## 2.5 Timeslice vs 'effective timeslice'
Go back to the Query box in the monitor editor window and change it to a 'non timesliced' version below and press enter in the query box to run it. Now it has no time element to it.

```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
//| timeslice 5m 
| count // by _timeslice
```

**The monitor evaluation graph will still draw a history graph similar to if the data was timesliced**
So the monitor version of the same query is *effectively timesliced* even though it's a count. This means that:
- timeslice queries are useful for predicting what a monitor might do over a certain time range
- BUT ! you don't need to timeslice log monitor queries.

The 'effective timeslice' value in a monitor used is the 'within X minutes' value. So if this was say 15m then the _count would be the total count in each 15m time range.
- Try changing this within value to say 15m or 1h and review the changes to the 'Historical Trend' graph.
- note how the trend line value will increase as you use larger time blocks and this could impact the threshold value.

If you have larger 'within' values you would need larger thresholds values also. When creating a log monitor you can tune it by using less granular / larger window/threshold settings.

## 2.6 Modelling thresholds with alert grouping for logs with timeslice / transpose
'Historical Trend' graph on the monitors page doesn't yet support log alert group threshold prediction for logs. This means to model a good threshold for an alert grouped log query we would need to run a test query in a new log search window using timeslice and transpose.

- cancel the monitor creation
- open a new log search
- select -6h
- paste and execute this query:

The timeslice, count by timeslice, transpose syntax below is the standard method in Sumo Logic to graph multiple values of a field as seperate dynamic series over time.

```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
| timeslice 15m | count by container, _timeslice |transpose row _timeslice column container
```

This screenshot shows that both the containers with errors would have over 15 but less than 30 errors in the current time range in any 15m period. So this query would provide a good basis for evaluating a good threshold level for a monitor query - even though we would not need timeslice in the final monitor version!

![Alt text](images/log_search_timeslice_transpose.png)

However the monitor query version we would use for alert grouping instead should be:
```
_sourcecategory=*kubernetes* stream  stderr
_loglevel=error
| json "stream","log" | where stream="stderr"
| count by container 
```

# This page shows examples for webhook payloads to use with the insighcreated search.

configure webhooks for this query to use in alerting with one webhook per event
s/s version add 	"AlertURL": "{{AlertResponseURL}}", for monitor

fields in our Query

```
{{ResultsJson._messagetime}}
{{ResultsJson.time}}
{{ResultsJson.insightid}}
{{ResultsJson.name}}
{{ResultsJson.eventName}}
{{ResultsJson.entitytype}}
{{ResultsJson.entityvalue}}
{{ResultsJson.status}}
{{ResultsJson.severity}}
{{ResultsJson.severityname}}
{{ResultsJson.confidence}}
{{ResultsJson.riskscore}}
{{ResultsJson.description}}
{{ResultsJson.timeToDetection}}
{{ResultsJson.signal_timeline}}
{{ResultsJson.tags}}
{{ResultsJson.rules}}

```

example payload

```
{
  "AlertName": "Insight Alert: {{ResultsJson.eventName}} {{ResultsJson.insightid}} sev: {{ResultsJson.severityname}} for {{ResultsJson.entityvalue}}",
  "Description": "{{Description}}",
  "action": "create",
  "Time": "{{ResultsJson.time}}",
  "Insight":"{{ResultsJson.insightid}} {{ResultsJson.name}}",
  "Entity":"{{ResultsJson.entitytype}} {{ResultsJson.entityvalue}}",
  "Confidence":"{{ResultsJson.confidence}} ",
  "Riskscore":"{{ResultsJson.riskscore}}",
  "Rules":"{{ResultsJson.rules}}",
  "Tags":"{{ResultsJson.tags}}",
  "SignalTimeline":"{{ResultsJson.signal_timeline}}",
  "DetectionTimeHours":"{{ResultsJson.timeToDetection}}"
}

``````
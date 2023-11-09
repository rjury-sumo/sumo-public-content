# Audit Dashboards

This folder contains custom app content for audit indexes in sumo logic.
Import the raw version of the JSON below into your sumo org using the Import function in the library, then share the dashboard as appropriate with admin or security teams.

## Sumo Logic Login and API Activity
Key use case is to vew and audit the following:
- config changes made via a sumo API
- search job api use
- sumosupport user account

This is a single dashboard that summarises login, configuration changes via api, search job api and sumosupport account activity in a single pane of glass and:
- adds geo and asn location by ip to enable security teams to audit access locations
- can be filtered by user
- an expected regular expression can be defined to flag normal or exceptions for geo/asn location signature
- show all traffic or just exceptions
- shows changes in geo/asn location signatures for the current time vs previous periods. This can be used to quickly determine if new api configuration or search audit activity is occuring.

In addition these panels should provide a customer good examples for all three use cases below should they want to make their own scheduled alerting or monitoring.
- api config changes
- search job api use
- sumosupport user account
  
### asn_geo and location
where an ip address is avialable events are enriched with geo/asn using the source ip. From these are signature is created per user and geo/asn. This can become a signature effectively for identifying typical or unexpected api sources.

### api history
The two api history panels summarize use time compare feature to compare changes in signatures over time for API config change and search job api

### to monitor for unexpected API source locations
This dashboard makes it easy to monitor for unexpected api activities.
1. set expected_asn_geo_regex parameter to a regular expression that matches your expected asn_geo location signature strings such as Australia|New.Zealand
2. you may want to make the expected pattern for your account the parameter default
3. set the value of the show_asn_geo parameter to exception, so panels will be blank unless an exception to expected regular expression

### Support account activity
The bottom two panels show logins or search activty by the sumosupport user. 
Note: filters do not apply to the sumo support account panels 
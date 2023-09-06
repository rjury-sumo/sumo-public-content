# setup lookup table
switch to content admin mode.
Create folder: admin recommended / CSIEM / Lookups

Either :
a) import cse_insights_status.json from the import folder.
or 
b) follow the manual lookup creation steps in docs/create_cse_insights_lookup.md 
manually create the lookup with the correct schema as below:
- name cse_insights_status
- description: Current status of insights updated via a scheduled search.
- TTL: yes - 365d (more or less if you think they might blow out the 100 MB limit) 
- size handling: delete old data
- choose upload file and use the file insights_lookup_schema.csv or create your own with these columns on one line:
```
id,insightid,name,entitytype,entityvalue,rules,time,status,tags,severity,confidence,assignee,resolution,timeToResponse,timeToDetection,timeToRemediation,eventnames
```
- use insightid as the key column
- we must set correct data types on some columns to avoid this error later: Mismatched field types 
- timeToResponse: Double
- time: Double, 
- timeToDetection: Double, 
- timeToRemediation: Double, 
- severity: Double.

If your resulting path is NOT path://"/Library/Admin Recommended/CSIEM/Lookups/cse_insights_status" you will need to make extra changes further down the track to the import content.

Make sure this lookup is shared to required users (ideally via a share on the parent folder in Admin recommended)

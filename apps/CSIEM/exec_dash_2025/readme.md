# Cloud SIEM Executive KPI Dashboard - 2025 version

This solution provides a executive level dashboard using pre-computed insights as a lookup table. The lookup stores only the most recent state of any insight using id as primary key.

By pre caching the last status of any insight in a lookup it's possible to dashboard key KPI for Cloud SIEM performance over weeks, months or quarters in seconds.

In addition this lookup query correctly re-computes the TimeToResponse value manually overcomming a known bug in Cloud SIEM that using automatoin service with an insight trigger triggers an invalid update of the response time metric for the insight. This script uses the first status change time as the TimeToResponse.

- [Cloud SIEM Executive KPI Dashboard - 2025 version](#cloud-siem-executive-kpi-dashboard---2025-version)
  - [Setup Steps - terraform](#setup-steps---terraform)
  - [Setup Steps - Import](#setup-steps---import)
    - [Create lookup siem\_metrics](#create-lookup-siem_metrics)
    - [Create Scheduled Search](#create-scheduled-search)
    - [Optional backfilling](#optional-backfilling)
    - [Setup Dashboard: dashboard\_executive\_view](#setup-dashboard-dashboard_executive_view)


## Setup Steps - terraform

Refer to the ./README_TERRAFORM.md files for more info.

- There can be contention / timing issues setting up the components so it had to be split into 3 as a workaround.  Run deploy.sh to deploy all three parts together, this should eliminate issues with plan or apply that the lookup table doesn't exist, causing deployment to fail.
- tf currently doesn't set 'your entire org' or another role to view permission on the lookup. It will only work with Administrator. Add another role data source and permission block to the permissions section in 1-folder main.tf file.
- the optional backfilling process still needs to be done manually as per topic below.

## Setup Steps - Import

### Create lookup siem_metrics
Determine a library location for your solution. Admin recommended folder is ideal.
Create a folder then import [1.lookup_siem_metrics.json](apps/CSIEM/exec_dash_2025/1.lookup_siem_metrics.json)

### Create Scheduled Search
For this step source code is: [2.schedule_siem_metrics.json](apps/CSIEM/exec_dash_2025/2.schedule_siem_metrics.json)

Open this file in a text editor then:

1. Change the save lookup line in the search query so it matches your lookup path from above. **If the lookup path does not match, and your user have permissions the import will fail.**
2. Edit the email address to send alerts (note it won't send any but this is best practice)
3. Import this schedule into the library folder
4. Open the search and execute it one time for a time period such as -7days, accepting the dialog to save to lookup. Ensure it completes without errors.
5. Wait a few minutes then cat the lookup path to ensure it has been properly updated.

### Optional backfilling
You may want to import history from the existing insight events. You can backfill this lookup by running the search in continguous time ranges going from past to presetn. These time ranges much never produce more than 500 rows of results (500 is max save rows to lookup size). For most accounts that would mean you could start in past and work forward in 7d blocks waiting for the search to complete each time.

To automate backfilling via a script over a long time: for example 365 days in 1 day search blocks use: [execute_search_job.py](apis/scripts/search_job/execute_search_job.md) with batch mode:

- create a search yaml config containing the backfill query
- execute with batch mode parameters:

```
python3 ./execute_search_job.py --region au \
  --access-id=$SUMO_ACCESS_ID --access-key=$SUMO_ACCESS_KEY \
  --yaml-config=my_backfill_query.yaml --batch-mode \
  --batch-start="-365d" --batch-end="now" --batch-interval="1d" \
  --mode records
  ```

Note: lookup merge operations are run asynchronously via a backgound batch process not instananeously so don't try to run more than one update query at one time or older status for an insight might overwrite newer ones. Picking a time range such as 1d - 1w ensures the query takes long enough that updates should complete between update operations.

### Setup Dashboard: dashboard_executive_view

Open [3.dashboard_executive_view.json](apps/CSIEM/exec_dash_2025/3.dashboard_executive_view.json) in a text editor. Edit and replace the default value of the lookup parameter so it matches the path you created earlier.  You can do this after importing but doing it now is better practice.

The lookup path occurs twice in the parameter - once as the value option and once as default.

terraform {
  required_providers {
    sumologic = {
      source  = "SumoLogic/sumologic"
      version = ">= 2.28.0"
    }
  }
  required_version = ">= 1.6"
}

# Provider configuration
provider "sumologic" {
  access_id   = var.access_id
  access_key  = var.access_key
  environment = var.environment
  admin_mode  = true
}

# Create scheduled search using sumologic_content
resource "sumologic_content" "siem_metrics_scheduled" {
  parent_id = var.folder_id

  config = jsonencode(merge(
    jsondecode(file("${path.module}/../2.schedule_siem_metrics.json")),
    {
      search = merge(
        jsondecode(file("${path.module}/../2.schedule_siem_metrics.json")).search,
        {
          queryText = replace(
            jsondecode(file("${path.module}/../2.schedule_siem_metrics.json")).search.queryText,
            "path://\"/Library/Users/some.user@sumologic.com/looukps/siem_metrics\"",
            var.lookup_path
          )
        }
      )
      searchSchedule = merge(
        jsondecode(file("${path.module}/../2.schedule_siem_metrics.json")).searchSchedule,
        {
          notification = merge(
            jsondecode(file("${path.module}/../2.schedule_siem_metrics.json")).searchSchedule.notification,
            {
              toList = [var.alert_email]
            }
          )
        }
      )
    }
  ))
}

# Create the dashboard using sumologic_content
resource "sumologic_content" "executive_view" {
  parent_id = var.folder_id

  config = jsonencode({
    type        = "DashboardV2SyncDefinition"
    name        = "Insights - Executive View (v3 Oct 2025)"
    description = "New lookup based KPI dashboard, Uses new Oct 2025 lookup with valid MTTResp"
    title       = "Insights - Executive View (v3 Oct 2025)"
    theme       = "Dark"
    topologyLabelMap = {
      data = {}
    }
    refreshInterval = 0
    timeRange = {
      type = "BeginBoundedTimeRange"
      from = {
        type         = "RelativeTimeRangeBoundary"
        relativeTime = "-15m"
      }
      to = null
    }
    layout = jsondecode(file("${path.module}/../3.dashboard_executive_view.json")).layout
    panels = jsondecode(file("${path.module}/../3.dashboard_executive_view.json")).panels
    variables = [
      {
        id   = null
        name = "lookup"
        displayName = "lookup"
        defaultValue = var.lookup_path
        sourceDefinition = {
          variableSourceType = "CsvVariableSourceDefinition"
          values = var.lookup_path
        }
        allowMultiSelect = false
        includeAllOption = false
        hideFromUI       = false
        valueType        = "Any"
      },
      {
        id   = null
        name = "days"
        displayName = "days"
        defaultValue = "365"
        sourceDefinition = {
          variableSourceType = "CsvVariableSourceDefinition"
          values = "30,60,90,180,365,1000"
        }
        allowMultiSelect = false
        includeAllOption = false
        hideFromUI       = false
        valueType        = "Any"
      }
    ]
    coloringRules = []
  })
}

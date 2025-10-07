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
# Reads from TF_VAR_access_id, TF_VAR_access_key, and TF_VAR_environment
# admin_mode = true is required to use Admin Recommended folder
provider "sumologic" {
  access_id   = var.access_id
  access_key  = var.access_key
  environment = var.environment
  admin_mode  = true
}

# Get parent folder - use Admin Recommended or Personal folder
data "sumologic_admin_recommended_folder" "admin_recommended" {
  count = var.parent_folder_id == "" ? 1 : 0
}

data "sumologic_personal_folder" "personal" {
  count = var.parent_folder_id == "" && var.use_personal_folder ? 1 : 0
}

# Get administrator role
data "sumologic_role" "administrator" {
  name = "Administrator"
}

# Determine parent folder ID
locals {
  parent_id = var.parent_folder_id != "" ? var.parent_folder_id : (
    var.use_personal_folder ? data.sumologic_personal_folder.personal[0].id : data.sumologic_admin_recommended_folder.admin_recommended[0].id
  )
}

# Create folder for CSIEM Executive View resources
resource "sumologic_content" "csiem_exec_view" {
  parent_id = local.parent_id
  config = jsonencode({
    "type" : "FolderSyncDefinition",
    "name" : "CSIEM_Exec_View",
    "description" : "Cloud SIEM Executive KPI Dashboard and related resources",
    "children" : []
  })
}

# Grant "Manage" permission to Administrator role on the folder
resource "sumologic_content_permission" "csiem_exec_view_permissions" {
  content_id           = sumologic_content.csiem_exec_view.id
  notify_recipient     = false
  notification_message = "You now have the permission to access this content"

  permission {
    permission_name = "Manage"
    source_type     = "role"
    source_id       = data.sumologic_role.administrator.id
  }

  depends_on = [sumologic_content.csiem_exec_view]
}

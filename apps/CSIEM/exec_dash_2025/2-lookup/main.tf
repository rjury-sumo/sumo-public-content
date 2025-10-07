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

# Create the lookup table for SIEM metrics using sumologic_content
resource "sumologic_content" "siem_metrics" {
  parent_id = var.folder_id

  config = jsonencode(jsondecode(file("${path.module}/../1.lookup_siem_metrics.json")))
}

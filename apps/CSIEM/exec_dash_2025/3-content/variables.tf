variable "access_id" {
  description = "Sumo Logic Access ID (set via TF_VAR_access_id from SUMO_ACCESS_ID)"
  type        = string
  sensitive   = true
}

variable "access_key" {
  description = "Sumo Logic Access Key (set via TF_VAR_access_key from SUMO_ACCESS_KEY)"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Sumo Logic Environment/Region (set via TF_VAR_environment from SUMO_ENDPOINT)"
  type        = string
}

variable "folder_id" {
  description = "The folder ID from project 1-folder output"
  type        = string
}

variable "lookup_path" {
  description = "The full path to the lookup table in the Admin Recommended folder"
  type        = string
  default     = "path://\"/Library/Admin Recommended/CSIEM_Exec_View/siem_metrics\""
}

variable "alert_email" {
  description = "Email address for scheduled search notifications"
  type        = string
  default     = "some.user@sumologic.com"
}

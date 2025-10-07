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
  description = "Sumo Logic Environment/Region (set via TF_VAR_environment from SUMO_ENDPOINT, e.g., 'au', 'us2', 'eu', etc.)"
  type        = string
}

variable "parent_folder_id" {
  description = "Parent folder ID where CSIEM_Exec_View will be created. Leave empty to use Admin Recommended or Personal folder."
  type        = string
  default     = ""
}

variable "use_personal_folder" {
  description = "If true and parent_folder_id is empty, use Personal folder instead of Admin Recommended folder"
  type        = bool
  default     = false
}

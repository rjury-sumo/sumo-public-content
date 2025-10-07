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

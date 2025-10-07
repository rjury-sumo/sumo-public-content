output "lookup_table_id" {
  description = "The ID of the created lookup table"
  value       = sumologic_content.siem_metrics.id
}

output "lookup_table_path" {
  description = "The path to the created lookup table"
  value       = "/Library/Admin Recommended/CSIEM_Exec_View/siem_metrics"
}

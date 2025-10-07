output "scheduled_search_id" {
  description = "The ID of the scheduled search"
  value       = sumologic_content.siem_metrics_scheduled.id
}

output "dashboard_id" {
  description = "The ID of the dashboard"
  value       = sumologic_content.executive_view.id
}

output "folder_id" {
  description = "The ID of the created CSIEM_Exec_View folder"
  value       = sumologic_content.csiem_exec_view.id
}

output "folder_path" {
  description = "The path to the created CSIEM_Exec_View folder"
  value       = var.use_personal_folder ? "Personal folder CSIEM_Exec_View" : "/Library/Admin Recommended/CSIEM_Exec_View"
}

output "parent_folder_id" {
  description = "The parent folder ID used"
  value       = local.parent_id
}

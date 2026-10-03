# =======================================================
# Outputs
# =======================================================

output "bookorbit_public_ip" {
  description = "Public IP of the bookorbit server"
  value       = module.compute.public_ip
}

output "bookorbit_private_ip" {
  description = "Private IP of the bookorbit server"
  value       = module.compute.private_ip
}

output "bookorbit_instance_id" {
  description = "OCID of the bookorbit instance"
  value       = module.compute.instance_id
}

output "bookorbit_backup_id" {
  description = "OCID of the bookorbit pre-upgrade backup"
  value       = module.compute.backup_id
}

output "dr_backup_bucket" {
  value = module.storage.backup_bucket_name
}

output "backup_bucket_name" {
  description = "Name of the disaster recovery Object Storage bucket"
  value       = oci_objectstorage_bucket.dr_backups.name
}

output "backup_bucket_id" {
  description = "OCID / ID of the disaster recovery Object Storage bucket"
  value       = oci_objectstorage_bucket.dr_backups.bucket_id
}

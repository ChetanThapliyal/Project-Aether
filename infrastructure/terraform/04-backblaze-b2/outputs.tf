output "bucket_name" {
  description = "Backblaze B2 offsite backup bucket name"
  value       = b2_bucket.etcd_offsite.bucket_name
}

output "bucket_id" {
  description = "Backblaze B2 offsite backup bucket ID"
  value       = b2_bucket.etcd_offsite.bucket_id
}

output "application_key_id" {
  description = "Application key ID for homelab Restic replication"
  value       = b2_application_key.homelab_restic.application_key_id
}

output "application_key" {
  description = "Secret application key for homelab Restic replication"
  value       = b2_application_key.homelab_restic.application_key
  sensitive   = true
}

output "locked_bucket_name" {
  description = "Object Lock offsite bucket (HARD-12)"
  value       = b2_bucket.etcd_offsite_locked.bucket_name
}

output "offsite_upload_key_id" {
  description = "Upload-only key ID for the homelab (HARD-12)"
  value       = b2_application_key.homelab_offsite_upload.application_key_id
}

output "offsite_upload_key" {
  description = "Upload-only key secret for the homelab (HARD-12)"
  value       = b2_application_key.homelab_offsite_upload.application_key
  sensitive   = true
}

output "offsite_restore_key_id" {
  description = "Read-only key ID for restores (HARD-12)"
  value       = b2_application_key.offsite_restore.application_key_id
}

output "offsite_restore_key" {
  description = "Read-only key secret for restores (HARD-12)"
  value       = b2_application_key.offsite_restore.application_key
  sensitive   = true
}

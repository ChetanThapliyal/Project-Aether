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

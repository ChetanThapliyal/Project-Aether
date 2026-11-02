# =============================================================================
# Project Aether — Backblaze B2 Infrastructure Layer (DR-04)
# =============================================================================

resource "b2_bucket" "etcd_offsite" {
  bucket_name = var.bucket_name
  bucket_type = "allPrivate"

  default_server_side_encryption {
    algorithm = "AES256"
    mode      = "SSE-B2"
  }

  lifecycle_rules {
    file_name_prefix             = ""
    days_from_hiding_to_deleting = var.days_from_hiding_to_deleting
  }
}

resource "b2_application_key" "homelab_restic" {
  key_name     = var.key_name
  bucket_ids   = [b2_bucket.etcd_offsite.bucket_id]
  capabilities = var.key_capabilities
}

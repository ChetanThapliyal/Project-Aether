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

# =============================================================================
# HARD-12: immutable offsite copy
# =============================================================================
# Each night the hypervisor age-encrypts that night's etcd snapshot and uploads
# it here as its own object. Every version is locked for object_lock_days in
# governance mode, so nothing the homelab holds can delete it inside the window
# (only the account master key can bypass). Objects stand alone, unlike a restic
# repo, so a lock on each one protects every copy completely.
#
# The provider can't enable Object Lock on an existing bucket (it forces a
# replacement), which is why this is a new bucket. etcd_offsite above keeps
# running in parallel until the new restore path is drilled, then it's retired.

resource "b2_bucket" "etcd_offsite_locked" {
  bucket_name = var.locked_bucket_name
  bucket_type = "allPrivate"

  default_server_side_encryption {
    algorithm = "AES256"
    mode      = "SSE-B2"
  }

  file_lock_configuration {
    is_file_lock_enabled = true
    default_retention {
      mode = "governance"
      period {
        duration = var.object_lock_days
        unit     = "days"
      }
    }
  }

  # Keep exactly one lock window of nightly snapshots: hide each object once its
  # lock has run out, and purge it a day later.
  lifecycle_rules {
    file_name_prefix              = ""
    days_from_uploading_to_hiding = var.object_lock_days
    days_from_hiding_to_deleting  = 1
  }

  lifecycle {
    prevent_destroy = true # a replacement would delete every offsite backup
  }
}

# Upload only: no readFiles, deleteFiles, bypassGovernance or writeFileRetentions.
# writeFiles does allow b2_hide_file (verified 10 Nov), so a compromised host can
# hide objects, but every hidden version stays locked and recoverable with the
# master key until its 30 days run out. It can't delete one (401, tested).
resource "b2_application_key" "homelab_offsite_upload" {
  key_name     = "${var.key_name}-upload"
  bucket_ids   = [b2_bucket.etcd_offsite_locked.bucket_id]
  capabilities = ["listBuckets", "listFiles", "writeFiles"]
}

# Read only, for restores from a workstation (Scenario 03 Branch D). Never
# deployed to the homelab.
resource "b2_application_key" "offsite_restore" {
  key_name     = "${var.key_name}-restore"
  bucket_ids   = [b2_bucket.etcd_offsite_locked.bucket_id]
  capabilities = ["listBuckets", "listFiles", "readFiles"]
}

variable "b2_application_key_id" {
  type        = string
  description = "Backblaze B2 Master/Admin Application Key ID (or via B2_APPLICATION_KEY_ID env var)"
  sensitive   = true
  default     = null
}

variable "b2_application_key" {
  type        = string
  description = "Backblaze B2 Master/Admin Application Key secret (or via B2_APPLICATION_KEY env var)"
  sensitive   = true
  default     = null
}

variable "bucket_name" {
  type        = string
  description = "Globally unique name for the Backblaze B2 offsite backup bucket"
  default     = "aether-restic-etcd-offsite"
}

variable "key_name" {
  type        = string
  description = "Name for the scoped application key provisioned for the homelab"
  default     = "aether-homelab-restic-etcd"
}

variable "key_capabilities" {
  type        = list(string)
  description = "Capabilities granted to the B2 application key"
  default = [
    "listBuckets",
    "listFiles",
    "readFiles",
    "writeFiles",
    "deleteFiles"
  ]
}

variable "days_from_hiding_to_deleting" {
  type        = number
  description = "Days from hiding an older file version to permanently deleting it (B2 lifecycle cleanup for Restic)"
  default     = 1
}

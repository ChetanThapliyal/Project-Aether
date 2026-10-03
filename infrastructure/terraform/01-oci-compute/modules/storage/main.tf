variable "compartment_ocid" {}

# Dynamically fetch your OCI Namespace so you don't have to hardcode it
data "oci_objectstorage_namespace" "user_namespace" {
  compartment_id = var.compartment_ocid
}

# OCI Object Storage bucket for Disaster Recovery (Restic/Velero)
resource "oci_objectstorage_bucket" "dr_backups" {
  compartment_id = var.compartment_ocid
  name           = "dr-backups"
  namespace      = data.oci_objectstorage_namespace.user_namespace.namespace
  access_type    = "NoPublicAccess"

  # Standard tier is part of the 20GB Always Free limit
  storage_tier = "Standard"
}

output "backup_bucket_name" {
  value = oci_objectstorage_bucket.dr_backups.name
}

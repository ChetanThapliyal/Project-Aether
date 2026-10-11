# =============================================================================
# Project Aether — Cross-Module Remote State (IaC-07)
# =============================================================================
# Allows reading exported outputs from the OCI compute module in GCS:
#   - bookorbit_public_ip
#   - bookorbit_private_ip
#   - bookorbit_instance_id
#   - dr_backup_bucket
#
# Usage example:
#   data.terraform_remote_state.oci.outputs.bookorbit_public_ip
# =============================================================================

data "terraform_remote_state" "oci" {
  backend = "gcs"
  config = {
    bucket = "tf-backend-oci-hlab-gcs"
    prefix = "oci"
  }
}

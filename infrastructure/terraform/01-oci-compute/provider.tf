terraform {
  required_version = "~> 1.15.0" # FND-07: matches CI and mise.toml (1.15.9)

  backend "gcs" {
    bucket = "tf-backend-oci-hlab-gcs"
    prefix = "oci"
  }

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}

provider "oci" {
  tenancy_ocid = var.tenancy_ocid
  user_ocid    = var.user_ocid
  fingerprint  = var.fingerprint
  private_key  = var.private_key # PEM from SOPS, so CI can plan without a key file (FND-05)
  region       = var.region
}

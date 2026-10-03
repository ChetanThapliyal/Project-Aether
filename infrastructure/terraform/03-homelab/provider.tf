terraform {
  backend "gcs" {
    bucket = "tf-backend-oci-hlab-gcs"
    prefix = "homelab"
  }

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.113.1" # Stable, actively maintained release
    }
  }
}

terraform {
  required_version = ">= 1.5.0"

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

provider "proxmox" {
  endpoint  = var.proxmox_api_url
  api_token = "${var.proxmox_api_token_id}=${var.proxmox_api_token_secret}"
  insecure  = false # Verified Let's Encrypt TLS cert (OPS-04)

  ssh {
    agent = true
  }
}

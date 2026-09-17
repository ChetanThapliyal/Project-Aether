terraform {
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
  insecure  = true # Self-signed cert on homelab — safe to skip TLS verification
}

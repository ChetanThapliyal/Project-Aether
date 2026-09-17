variable "proxmox_api_url" {
  type        = string
  description = "Proxmox API URL (e.g., https://192.168.1.200:8006/api2/json)"
}

variable "proxmox_api_token_id" {
  type      = string
  sensitive = true
}

variable "proxmox_api_token_secret" {
  type      = string
  sensitive = true
}

variable "ssh_public_key" {
  type        = string
  description = "Your public SSH key to inject into VMs"
}

variable "network_gateway" {
  type        = string
  description = "Default gateway for VM network (your router IP)"
  default     = "192.168.1.1"
}

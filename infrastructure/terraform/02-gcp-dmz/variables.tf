# =============================================================================
# GCP DMZ Observability Node — Input Variables
# =============================================================================

variable "project_id" {
  description = "The Google Cloud project ID hosting the DMZ"
  type        = string
  default     = "gcs-oci-homelab-controlplane"
}

variable "region" {
  description = "GCP Region for Always-Free tier eligibility (us-central1, us-east1, us-west1)"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP Zone within the chosen region"
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Identifier for the Compute Engine instance and associated resources"
  type        = string
  default     = "aether-gcp-dmz"
}

variable "machine_type" {
  description = "Compute instance machine type. Must be e2-micro to remain free tier."
  type        = string
  default     = "e2-micro"
}

variable "boot_disk_size" {
  description = "Boot disk size in GB (Free tier covers up to 30 GB standard persistent disk)"
  type        = number
  default     = 30
}

variable "boot_disk_type" {
  description = "Boot disk storage type. Must be pd-standard for Always-Free tier."
  type        = string
  default     = "pd-standard"
}

variable "boot_disk_image" {
  description = "Boot disk image family/project (Debian 12 is lightweight and minimal for e2-micro)"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "network_tier" {
  description = "Public IP network tier (STANDARD or PREMIUM). STANDARD aligns with free-tier egress allowance."
  type        = string
  default     = "STANDARD"
}

variable "ssh_user" {
  description = "Default administrative username created on the instance"
  type        = string
  default     = "owl"
}

variable "ssh_public_key" {
  description = "Public SSH key for administrative login (e.g., ssh-ed25519 ...)"
  type        = string
}

variable "tailscale_auth_key" {
  description = "Tailscale pre-authentication key for automatic mesh enrollment"
  type        = string
  sensitive   = true
  default     = ""
}

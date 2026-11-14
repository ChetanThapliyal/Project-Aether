variable "tenancy_ocid" {
  description = "The tenancy OCID"
  type        = string
}

variable "user_ocid" {
  description = "The user OCID"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the public key"
  type        = string
}

variable "private_key" {
  description = "OCI API signing key (PEM), stored in terraform.sops.tfvars (FND-05)"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "The OCI region"
  type        = string
}

variable "compartment_ocid" {
  description = "The compartment OCID where resources are located"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
  sensitive   = true
}

variable "subnet_ocid" {
  description = "The subnet OCID to place instances in"
  type        = string
}

variable "image_ocid" {
  description = "The OS image OCID for instances"
  type        = string
}

variable "vcn_ocid" {
  type        = string
  description = "OCID of the existing VCN to import"
}

variable "igw_ocid" {
  type        = string
  description = "OCID of the existing Internet Gateway to import"
}

variable "sl_ocid" {
  type        = string
  description = "OCID of the existing Security List to import"
}

variable "bootstrap_ssh_cidr" {
  description = "Source CIDR (for example 203.0.113.7/32) allowed to SSH to the instance while it is rebuilt and not yet on the tailnet (FND-18). Leave empty otherwise; set it with TF_VAR_bootstrap_ssh_cidr, never in a tfvars file."
  type        = string
  default     = ""

  validation {
    condition     = var.bootstrap_ssh_cidr == "" || can(cidrhost(var.bootstrap_ssh_cidr, 0))
    error_message = "bootstrap_ssh_cidr must be empty or a CIDR such as 203.0.113.7/32."
  }
}

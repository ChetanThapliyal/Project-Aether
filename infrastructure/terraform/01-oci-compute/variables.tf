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

variable "private_key_path" {
  description = "Path to the private key file"
  type        = string
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

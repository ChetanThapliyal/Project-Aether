variable "compartment_ocid" {
  description = "The compartment OCID where resources are located"
  type        = string
}

variable "bootstrap_ssh_cidr" {
  description = "Temporary source CIDR for public SSH during a rebuild (FND-18). Empty means no rule."
  type        = string
  default     = ""
}

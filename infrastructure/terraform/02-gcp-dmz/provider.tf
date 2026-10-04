terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "tf-backend-oci-hlab-gcs"
    prefix = "gcp-dmz"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

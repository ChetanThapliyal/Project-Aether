terraform {
  required_version = "~> 1.15.0" # FND-07: matches CI and mise.toml (1.15.9)

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

terraform {
  required_version = "~> 1.15.0" # FND-07: matches CI and mise.toml (1.15.9)

  backend "gcs" {
    bucket = "tf-backend-oci-hlab-gcs"
    prefix = "backblaze-b2"
  }

  required_providers {
    b2 = {
      source  = "Backblaze/b2"
      version = "~> 0.14.0"
    }
  }
}

provider "b2" {
  application_key_id = var.b2_application_key_id # gitleaks:allow
  application_key    = var.b2_application_key    # gitleaks:allow
}

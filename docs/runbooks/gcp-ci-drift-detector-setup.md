# GCP CI identity and Terraform drift detector runbook

> **Scope:** Setup and credential rotation for the least-privilege GCP service account used by GitHub Actions for nightly Terraform drift detection.
> **Target repository:** `Project Aether`
> **Identity source:** `GCS-CP` bootstrap repository (`/home/owl/Projects/GCS-CP/gcp/iam_ci.tf`)
> **Related issue / chore:** OPS-05 · ADR-012

## 1. Context and architecture

To prevent configuration drift across clouds without crossing the Day-0 bootstrap boundary ([ADR-012](../adr/012-oci-monorepo-consolidation.md)), the CI identity is provisioned in the `GCS-CP` repository.

The state backend bucket (`tf-backend-oci-hlab-gcs`) and Cloud KMS keyring (`sops-key`) are Day-0 assets managed by `GCS-CP`. Placing CI IAM roles in `Project Aether` would create circular dependencies and grant GitHub Actions broader IAM permissions over GCP than necessary.

The service account follows least privilege:
- Viewer access (`roles/compute.viewer`) to inspect compute instances and firewall rules.
- Storage object admin (`roles/storage.objectAdmin`) to read and lock remote state during `terraform plan`.
- Cloud KMS decryption (`roles/cloudkms.cryptoKeyDecrypter`) to decrypt `.sops.tfvars`.

It cannot create, modify, or destroy compute resources.

### Architecture and execution flow

```mermaid
---
title: "Terraform Drift Detection: Architecture and Execution Flow"
config:
  theme: "base"
  themeVariables:
    darkMode: true
    background: "#0d1117"
    mainBkg: "#161b22"
    clusterBkg: "#0d1117"
    clusterBorder: "#30363d"
    primaryColor: "#161b22"
    primaryTextColor: "#f0f6fc"
    primaryBorderColor: "#388bfd"
    secondaryColor: "#161b22"
    secondaryBorderColor: "#30363d"
    secondaryTextColor: "#f0f6fc"
    tertiaryColor: "#0d1117"
    tertiaryBorderColor: "#30363d"
    tertiaryTextColor: "#8b949e"
    lineColor: "#8b949e"
    textColor: "#c9d1d9"
    nodeTextColor: "#f0f6fc"
    titleColor: "#58a6ff"
    edgeLabelBackground: "#161b22"
---
flowchart TB
    %% Nodes & Subgraphs

    subgraph Day0 ["Day-0 Bootstrap Plane (GCS-CP)"]
        direction TB
        TF_APPLY["terraform apply<br/><code>gcp/iam_ci.tf</code>"]
        SA_ID[/"GCP Service Account<br/><code>terraform-drift-detector</code>"/]
        SA_KEY{{"Service Account JSON Key<br/><code>drift_detector_key</code>"}}

        TF_APPLY -->|"Provisions Identity"| SA_ID
        SA_ID -->|"Generates Private Key"| SA_KEY
    end

    subgraph SecretsManagement ["GitHub Secrets & Configuration"]
        GH_SECRET{{"Repository Secret<br/><code>GCP_SA_KEY</code>"}}
        WORKFLOW_FILE["Workflow Definition<br/><code>.github/workflows/terraform-drift.yml</code>"]
    end

    SA_KEY -.->|"Pipe via gh secret set"| GH_SECRET

    subgraph ActionsRunner ["GitHub Actions Runner (ubuntu-latest)"]
        direction TB
        TRIGGER(["Trigger Event<br/>Nightly 02:00 UTC / manual"])

        subgraph Pipeline ["Runner Pipeline Steps"]
            direction TB
            STEP_AUTH["1. Authenticate to GCP<br/><code>google-github-actions/auth@v2</code>"]
            STEP_DECRYPT["2. Decrypt SOPS tfvars<br/><code>sops -d terraform.sops.tfvars</code>"]
            STEP_INIT["3. Terraform Init<br/><code>remote state config</code>"]
            STEP_PLAN["4. Terraform Plan<br/><code>terraform plan -detailed-exitcode</code>"]

            STEP_AUTH --> STEP_DECRYPT --> STEP_INIT --> STEP_PLAN
        end

        TRIGGER --> STEP_AUTH
    end

    GH_SECRET ==>|"Injects JSON Credential"| STEP_AUTH
    WORKFLOW_FILE -.->|"Defines Execution"| TRIGGER

    subgraph GCP ["Target GCP Environment (gcs-oci-homelab-controlplane)"]
        direction TB
        KMS["Cloud KMS Key<br/><code>sops-key</code>"]
        GCS[("GCS State Bucket<br/><code>tf-backend-oci-hlab-gcs</code>")]
        COMPUTE["Compute Engine<br/><code>aether-gcp-dmz</code>"]
    end

    STEP_DECRYPT <-->|"roles/cloudkms.cryptoKeyDecrypter"| KMS
    STEP_INIT <-->|"roles/storage.objectAdmin (State & Lock)"| GCS
    STEP_PLAN <-->|"roles/compute.viewer (Read-Only Inspection)"| COMPUTE

    subgraph Outcome ["Drift Evaluation & Reporting"]
        direction TB
        EVAL{"Evaluate Plan<br/>Exit Code"}
        RES_CLEAN(["Exit 0: In-Sync<br/>Zero drift detected"]):::success
        RES_DRIFT(["Exit 2: Drift Detected<br/>Workflow failed, alert posted"]):::danger
        RES_ERROR(["Exit 1: Error<br/>Plan execution failed"]):::warning

        EVAL -->|"Code 0"| RES_CLEAN
        EVAL -->|"Code 2"| RES_DRIFT
        EVAL -->|"Code 1"| RES_ERROR
    end

    STEP_PLAN --> EVAL

    %% Class Definitions for Clean Dark Visuals
    classDef success fill:#0d2818,stroke:#2ea043,stroke-width:2px,color:#3fb950;
    classDef danger fill:#311016,stroke:#f85149,stroke-width:2px,color:#ff7b72;
    classDef warning fill:#2d2206,stroke:#d29922,stroke-width:2px,color:#e3b341;
    classDef default font-family:sans-serif;
```

## 2. Service account specification

- Service account ID: `terraform-drift-detector`
- Email: `terraform-drift-detector@gcs-oci-homelab-controlplane.iam.gserviceaccount.com`
- Assigned roles:
  - `roles/compute.viewer` on project `gcs-oci-homelab-controlplane` (inspects compute instance metadata and firewall rules)
  - `roles/storage.objectAdmin` on bucket `tf-backend-oci-hlab-gcs` (reads remote state and manages lock objects during `terraform plan`)
  - `roles/cloudkms.cryptoKeyDecrypter` on key `projects/gcs-oci-homelab-controlplane/locations/global/keyRings/sops/cryptoKeys/sops-key` (decrypts `terraform.sops.tfvars`)

## 3. Terraform definition in GCS-CP (`gcp/iam_ci.tf`)

```hcl
# Service Account for GitHub Actions Drift Detection
resource "google_service_account" "drift_detector" {
  account_id   = "terraform-drift-detector"
  display_name = "CI Drift Detector Service Account"
  description  = "Least-privilege identity used by GitHub Actions for nightly terraform plan drift detection"
}

# 1. Compute Viewer (Inspection only)
resource "google_project_iam_member" "compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.drift_detector.email}"
}

# 2. GCS State Bucket Access & State Locking
resource "google_storage_bucket_iam_member" "state_object_admin" {
  bucket = var.state_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.drift_detector.email}"
}

# 3. KMS Decryption for SOPS tfvars
resource "google_kms_crypto_key_iam_member" "sops_decrypter" {
  crypto_key_id = google_kms_crypto_key.sops_key.id
  role          = "roles/cloudkms.cryptoKeyDecrypter"
  member        = "serviceAccount:${google_service_account.drift_detector.email}"
}

# 4. Service Account Key Generation
resource "google_service_account_key" "drift_detector_key" {
  service_account_id = google_service_account.drift_detector.name
}

# Sensitive Output for GitHub Actions Secret Injection
output "github_secret_gcp_sa_key" {
  description = "Base64-decoded JSON credentials for GitHub Secret GCP_SA_KEY"
  value       = base64decode(google_service_account_key.drift_detector_key.private_key)
  sensitive   = true
}
```

## 4. Operational procedures

### Setting or rotating the GitHub secret

From the `GCS-CP/gcp/` directory, apply the configuration and pipe the secret directly to GitHub using the CLI:

```bash
cd /home/owl/Projects/GCS-CP/gcp

# 1. Validate and apply changes
terraform plan
terraform apply

# 2. Pipe key directly to GitHub Secret (avoid writing unencrypted key to disk)
terraform output -raw github_secret_gcp_sa_key | \
  gh secret set GCP_SA_KEY --repo ChetanThapliyal/Project-Aether

# 3. Verify secret presence
gh secret list --repo ChetanThapliyal/Project-Aether
```

### Verifying service account permissions locally

To smoke-test the credentials without waiting for CI:

```bash
# Export key to temporary file
TMP_KEY=$(mktemp)
terraform -chdir=/home/owl/Projects/GCS-CP/gcp output -raw github_secret_gcp_sa_key > "$TMP_KEY"

# Authenticate as SA
gcloud auth activate-service-account --key-file="$TMP_KEY"

# Test Compute Viewer
gcloud compute instances list --project=gcs-oci-homelab-controlplane

# Test State Storage Access
gcloud storage ls gs://tf-backend-oci-hlab-gcs/gcp-dmz/

# Test SOPS Decryption
sops -d infrastructure/terraform/02-gcp-dmz/terraform.sops.tfvars > /dev/null && echo "SOPS Decrypt SUCCESSFUL!"

# Clean up
rm -f "$TMP_KEY"
gcloud config set account thapliyal.chetan93@gmail.com
```

### Triggering a manual drift check

Once `.github/workflows/terraform-drift.yml` is pushed to GitHub `main`:

```bash
gh workflow run "Terraform Drift Detection" --repo ChetanThapliyal/Project-Aether
gh run watch --repo ChetanThapliyal/Project-Aether
```

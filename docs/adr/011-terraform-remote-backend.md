```text
================================================================================
ADR-011: Terraform Remote State Backend (GCS)
================================================================================
```
- **Status:** Accepted (Supersedes original MinIO/S3 proposal)
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Terraform utilizes a state file (`terraform.tfstate`) to map real-world infrastructure to configuration. This file often contains sensitive infrastructure secrets (passwords, tokens) in plaintext. Committing this file to version control is a critical security vulnerability, but keeping it locally on a single laptop prevents CI/CD automation and risks data loss.
- **Problem Statement:** How do we securely store and manage Terraform state to prevent secret leakage, ensure disaster recovery, and enable future CI/CD automation?
- **Decision Drivers:**
  - Absolute requirement to keep plaintext secrets out of Git.
  - Need for a centralized state to allow future GitHub Actions to run `terraform plan`.
  - Desire to align with heavy-enterprise industry standards.
  - Need for native state locking without additional infrastructure.
  - MinIO project archived on GitHub – support has ended, making it an unmaintainable dependency.
- **Decision:** I will utilize a **Google Cloud Storage (GCS) bucket** as the Terraform remote backend. The bucket `tf-backend-oci-hlab-gcs` stores state under the `homelab` prefix.
- **Architecture Impact:** The local `.tfstate` file has been migrated to `gs://tf-backend-oci-hlab-gcs/homelab/default.tfstate`. All future `terraform plan` and `terraform apply` executions require GCP authentication (Application Default Credentials) to read and write the state file. GCS provides native state locking – no external locking mechanism is needed.

- **Alternatives Considered:**
  - *Local State with strict `.gitignore`:* Rejected. While it keeps secrets out of Git, it creates a single point of failure (laptop drive crash) and completely blocks any future CI/CD automation from accessing the state.
  - *Self-hosted MinIO (S3-compatible) on OCI:* Originally proposed but superseded. The MinIO GitHub repository has been archived and support has ended, making it an unmaintainable dependency. Beyond the EOL concern, MinIO also lacked native DynamoDB-style state locking, required managing an additional Docker service, and introduced operational overhead for a single-operator environment.
  - *Terraform Cloud (Managed SaaS):* Rejected. While an excellent modern standard, using a cloud-provider-native bucket provides deeper hands-on experience and avoids reliance on third-party SaaS.
  - *PostgreSQL Backend:* Rejected. While native and supports locking, S3/GCS API compatibility is the overwhelming industry standard for state storage.
- **Decision Rationale:** The primary trigger for this change was MinIO reaching end-of-life – its GitHub repository has been archived, meaning no further security patches or bug fixes. Beyond the EOL urgency, GCS was chosen for three additional reasons: (1) native state locking eliminates the open question from the original ADR about DynamoDB-compatible locking, (2) zero operational overhead – no Docker containers or OCI instances to maintain, and (3) GCP's free tier provides sufficient storage at no cost. The `homelab` prefix allows the same bucket to be shared across multiple Terraform root modules (e.g., `homelab`, `oci`) in the future.
- **Consequences:**
  - *Positive:* Secrets are completely secure; state is backed up offsite; native locking prevents concurrent state corruption; infrastructure is ready for CI/CD automation pipelines; zero self-hosted infrastructure to maintain.
  - *Negative:* Introduces a network dependency on GCP for any infrastructure changes.
  - *Risks:* If the GCS bucket is deleted and not backed up, the Terraform state is permanently lost (requiring a difficult `terraform import` recovery). Mitigated by: `force_destroy = false` (prevents accidental deletion), object versioning (retains last 5 versions for rollback), and uniform IAM access control.
  - *Trade-offs:* Dependency on a cloud provider (GCP) rather than fully self-hosted state management.
- **Security Considerations:** Access to the GCS bucket is controlled via GCP IAM. Local authentication uses Application Default Credentials (ADC). For CI/CD, a service account with minimal `roles/storage.objectAdmin` on the specific bucket should be used.
- **Reliability Considerations:** The state file is decoupled from the Proxmox host, meaning even if the entire homelab burns down, the infrastructure blueprint and state remain safe in GCP. GCS provides 99.95% availability SLA. Object versioning retains the last 5 noncurrent versions, enabling rollback if a bad state write occurs.
- **Scalability Considerations:** The `prefix` mechanism allows multiple Terraform workspaces to share a single bucket (e.g., `homelab/`, `oci/`, `gcp/`).
- **Performance Considerations:** Negligible impact. State retrieval takes milliseconds.
- **Operational Considerations:** Requires GCP authentication (via `gcloud auth application-default login`) before Terraform can be initialized.
- **Cost Considerations:** Infrastructure: ₹0.00 (GCP free tier – 5 GB Cloud Storage). The lifecycle rule caps noncurrent versions at 5, ensuring storage stays well within the free tier limit even with frequent state writes.
- **Migration Plan:**
  1. Create the GCS bucket `tf-backend-oci-hlab-gcs` in GCP.
  2. Add the `backend "gcs"` block to `provider.tf`.
  3. Run `terraform init -migrate-state` to copy the local state to GCS.
  4. Remove the local `terraform.tfstate` and `terraform.tfstate.backup` files.
- **Validation / Fitness Functions:**
  - Running `terraform plan` on a new machine after `gcloud auth application-default login` must succeed without copying any local files.
  - Running `terraform state list` must return all managed resources from the remote backend.
- **Dependencies:** GCP account, GCS bucket, `gcloud` CLI (for authentication).
- **Open Questions:** None. Native GCS locking resolves the open locking question from the original MinIO proposal.
- **Related ADRs:** ADR-007 (Secrets Management).
- **Review Conditions:** Review if multi-environment state isolation requires separate buckets or Terraform workspaces.

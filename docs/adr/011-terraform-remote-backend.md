```text
================================================================================
ADR-011: Terraform Remote State Backend (GCS)
================================================================================
```
- **Status:** Accepted (Supersedes original MinIO/S3 proposal)
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Terraform uses a state file (`terraform.tfstate`) to map real-world infrastructure to configuration. This file often contains sensitive infrastructure secrets (such as passwords and tokens) in plaintext. Committing it to version control exposes credentials, while keeping it only on a local workstation prevents CI/CD automation and risks data loss.
- **Problem Statement:** How do we store and lock Terraform state securely to prevent secret exposure, ensure disaster recovery, and enable automated CI/CD pipelines?
- **Decision Drivers:**
  - Prevent plaintext secrets from being committed to Git.
  - Centralize state for future pipeline executions.
  - Native state locking without running extra infrastructure services.
  - MinIO project was archived on GitHub, making it unmaintained.
- **Decision:** Use a Google Cloud Storage (GCS) bucket as the Terraform remote backend. The bucket `tf-backend-oci-hlab-gcs` stores state under the `homelab` prefix.
- **Architecture Impact:** Local state files are migrated to `gs://tf-backend-oci-hlab-gcs/homelab/default.tfstate`. Terraform commands require GCP Application Default Credentials to access state. GCS handles locking natively without external databases.
- **Alternatives Considered:**
  - *Local state with `.gitignore`:* Rejected. Retains a single point of failure on the workstation drive and prevents automated CI/CD runs.
  - *Self-hosted MinIO on OCI:* Rejected. The MinIO repository was archived and no longer receives maintenance. MinIO also lacked built-in locking without DynamoDB emulation, adding extra operational burden.
  - *Terraform Cloud SaaS:* Rejected. A cloud storage bucket keeps infrastructure decoupled from third-party platform lock-in.
  - *PostgreSQL Backend:* Rejected. Object storage APIs remain the primary standard for Terraform state backends.
- **Decision Rationale:** The original MinIO proposal was dropped because the project repository was archived and no longer receives security updates. GCS provides native state locking without extra services like DynamoDB, requires no container maintenance, and falls within GCP's free storage tier. Prefixing state keys allows the bucket to store state for multiple root modules (such as `homelab` and `oci`).
- **Consequences:**
  - *Positive:* Offsite encrypted state storage, native concurrency locking, and readiness for CI/CD pipelines without maintaining self-hosted services.
  - *Negative:* Introduces an internet and GCP authentication dependency when running Terraform plans.
  - *Risks:* Accidental deletion of the bucket could lose state history. Mitigated by setting `force_destroy = false`, enabling object versioning for rollback, and restricting IAM roles.
  - *Trade-offs:* Accepting dependency on a public cloud provider in exchange for managed availability and locking.
- **Security Considerations:** Access is governed by GCP IAM policies. Local workstations authenticate via Application Default Credentials, and CI/CD pipelines use scoped service accounts.
- **Reliability Considerations:** State is preserved offsite independently of local hypervisor hardware. GCS object versioning retains recent state versions for recovery if corrupt writes occur.
- **Scalability Considerations:** The prefix mechanism allows multiple directories to share a single bucket safely.
- **Performance Considerations:** Minimal latency impact; state downloads complete in milliseconds.
- **Operational Considerations:** Workstations must run `gcloud auth application-default login` before initializing Terraform.
- **Cost Considerations:** Infrastructure: ₹0.00 (GCP free tier, 5 GB storage). Object lifecycle rules prune old versions to stay well within free limits.
- **Migration Plan:**
  1. Create bucket `tf-backend-oci-hlab-gcs` in GCP.
  2. Add the `backend "gcs"` block to `provider.tf`.
  3. Run `terraform init -migrate-state` to push local state into GCS.
  4. Delete local `terraform.tfstate` files once migration completes.
- **Validation / Fitness Functions:**
  - Running `terraform plan` on a fresh machine authenticated via `gcloud` must complete successfully without manual file copying.
  - `terraform state list` must return managed resources directly from the remote backend.
- **Dependencies:** GCP account, GCS bucket, `gcloud` CLI.
- **Open Questions:** None.
- **Related ADRs:** ADR-007 (Secrets Management), ADR-014 (Single-Environment Infrastructure Strategy).
- **Review Conditions:** Resolved by ADR-014 (confirms single-environment default workspace per module without bucket or workspace partitioning).

---

### Addendum: The External Foundation, GCS-CP (2026-11-13, FND-06)
- **Ownership.** The state bucket `tf-backend-oci-hlab-gcs`, the SOPS KMS key ring and key (`sops/sops-key`), the Cloud KMS, STS and IAM Credentials APIs, and CI's identity (service account `terraform-drift-detector` with its Workload Identity pool and provider) are owned by a separate repository, **GCS-CP**. Its `bootstrap/` root creates the bucket and keeps its own state locally, because it can't store state in a bucket it creates. Its `gcp/` root stores state in the bucket under prefix **`gcp`**.
- **Rule.** Never run Terraform against prefix `gcp` from this repository, and never add these resources here. Doing so would give two roots ownership of the foundation every other root depends on.
- **Protections (verified 2026-11-13).**
  - `prevent_destroy` on the bucket, the key ring and the key.
  - KMS key: 30-day scheduled destruction, 90-day automatic rotation (next 2026-12-31). Old key versions keep decrypting, so rotation doesn't break existing SOPS files.
  - Bucket: versioning (5 noncurrent versions kept), 7-day soft delete, uniform bucket-level access, and **public access prevention `enforced`** (was `inherited` until FND-06).
- **Recovery.** GCS-CP is a prerequisite for every DR scenario. Without the KMS key only the Age recipient remains ([DR Scenario 04](../disaster-recovery/scenarios/04-age-key-loss.md)); without the bucket there's no state. If the bootstrap state file is lost, `terraform import` the existing bucket: it's the only resource in that root.

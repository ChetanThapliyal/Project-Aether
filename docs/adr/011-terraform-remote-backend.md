```text
================================================================================
ADR-011: Terraform Remote State Backend (MinIO / S3)
================================================================================
```
- **Status:** Accepted
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Terraform utilizes a state file (`terraform.tfstate`) to map real-world infrastructure to configuration. This file often contains sensitive infrastructure secrets (passwords, tokens) in plaintext. Committing this file to version control is a critical security vulnerability, but keeping it locally on a single laptop prevents CI/CD automation and risks data loss.
- **Problem Statement:** How do we securely store and manage Terraform state to prevent secret leakage, ensure disaster recovery, and enable future CI/CD automation?
- **Decision Drivers:**
  - Absolute requirement to keep plaintext secrets out of Git.
  - Need for a centralized state to allow future GitHub Actions to run `terraform plan`.
  - Desire to align with heavy-enterprise industry standards.
- **Decision:** I will utilize a self-hosted **MinIO (S3-compatible) Object Store** running on an external OCI cloud instance as the Terraform remote backend.
- **Architecture Impact:** The local `.tfstate` file will be migrated to an S3 bucket on the OCI server. All future `terraform plan` and `terraform apply` executions will require network access to the OCI server to read and write the state file.
- **Alternatives Considered:**
  - *Local State with strict `.gitignore`:* Rejected. While it keeps secrets out of Git, it creates a single point of failure (laptop drive crash) and completely blocks any future CI/CD automation from accessing the state.
  - *Terraform Cloud (Managed SaaS):* Rejected. While an excellent modern standard, self-hosting an S3-compatible store provides deeper hands-on experience with object storage infrastructure and avoids reliance on third-party SaaS.
  - *PostgreSQL Backend:* Rejected. While native and supports locking, S3 API compatibility is the overwhelming industry standard for state storage.
- **Decision Rationale:** Using an S3-compatible bucket is the textbook enterprise standard for infrastructure state (mirroring massive AWS S3 deployments). By hosting MinIO on the 6GB OCI Always Free ARM instance, we achieve enterprise-grade state management at zero cost, strictly segregate state from the infrastructure it manages (solving the "chicken and egg" problem), and gain highly transferable engineering skills.
- **Consequences:**
  - *Positive:* Secrets are completely secure; state is backed up offsite; infrastructure is now ready for CI/CD automation pipelines.
  - *Negative:* Introduces a strict network dependency on the OCI server for any infrastructure changes.
  - *Risks:* If the OCI server is lost and the bucket isn't backed up, the Terraform state is permanently lost (requiring a difficult `terraform import` recovery).
  - *Trade-offs:* Added operational complexity to manage the external MinIO instance.
- **Security Considerations:** The MinIO bucket must be secured with strong Access Keys and Secret Keys. Connections from Terraform to MinIO must occur over HTTPS (TLS).
- **Reliability Considerations:** The state file is now decoupled from the Proxmox host, meaning even if the entire homelab burns down, the infrastructure blueprint and state remain safe in the cloud.
- **Scalability Considerations:** MinIO is incredibly lightweight and will consume negligible resources on the 6GB RAM OCI instance.
- **Performance Considerations:** Negligible impact. State retrieval takes milliseconds.
- **Operational Considerations:** Requires manually bootstrapping the MinIO server via Docker Compose on the OCI server *before* Terraform can be initialized.
- **Cost Considerations:** Infrastructure: ₹0.00 (Oracle Cloud Always Free tier).
- **Migration Plan:**
  1. Manually deploy MinIO on OCI.
  2. Add the `backend "s3"` block to `provider.tf`.
  3. Run `terraform init` to automatically migrate the local state file to the bucket.
- **Validation / Fitness Functions:**
  - Running `terraform plan` on a new laptop after simply authenticating with MinIO must succeed without copying any local files.
- **Dependencies:** OCI Cloud Instance, Docker, MinIO.
- **Open Questions:** How will we handle state locking since MinIO does not natively support DynamoDB locking? (Likely acceptable risk for a single-operator environment).
- **Related ADRs:** ADR-007 (Secrets Management).
- **Review Conditions:** N/A - Foundational decision.

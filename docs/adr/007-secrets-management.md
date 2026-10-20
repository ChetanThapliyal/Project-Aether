```text
================================================================================
ADR-007: Secrets Management with SOPS, Age, and GCP Cloud KMS
================================================================================
```
- **Status:** Amended (October 2026; see amendment below)
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** A GitOps workflow requires committing infrastructure and application state to a Git repository. This introduces the risk of exposing sensitive data such as API tokens, passwords, and TLS certificates. We need a way to store encrypted secrets safely in Git and decrypt them during deployment.
- **Problem Statement:** How do we encrypt sensitive configuration values in Git without running resource-heavy external secret managers?
- **Decision Drivers:**
  - Zero plaintext secrets committed to version control.
  - Low memory footprint to accommodate a 12GB host limit.
  - Stateless disaster recovery independent of any single cluster instance.
- **Decision:** Use Mozilla SOPS with age for asymmetric file encryption.
- **Architecture Impact:** `age` generates a public and private key pair. The public recipient key is committed in `.sops.yaml` to enforce encryption rules across the repository. The private key remains local and is injected into the cluster to decrypt values during runtime.
- **Alternatives Considered:**
  - *HashiCorp Vault:* Rejected. Requires too much memory for a 12GB host running multiple services.
  - *Bitnami Sealed Secrets:* Rejected. Couplings encryption keys directly to the Kubernetes cluster, complicating disaster recovery if the cluster is lost.
  - *GPG:* Rejected. More complex key management and tooling setup compared to age.
- **Decision Rationale:** SOPS with age provides lightweight, stateless file encryption decoupled from Kubernetes cluster state. Secrets can be recovered during a full rebuild as long as the offline age key is preserved.
- **Consequences:**
  - *Positive:* Minimal memory overhead, decoupled from cluster lifecycle, and compatible with GitOps workflows.
  - *Negative:* Requires manual distribution and backup of local private keys.
  - *Risks:* Losing the age private key makes encrypted secrets unrecoverable. (Mitigated; see amendment below.)
  - *Trade-offs:* Trading centralized secret auditing (such as Vault) for stateless local encryption.
- **Security Considerations:** The age private key is never committed to Git and is backed up offline in a secure password manager.
- **Reliability Considerations:** Encryption and decryption are deterministic and do not depend on external APIs during offline operations.
- **Scalability Considerations:** Scales across repository paths through `.sops.yaml` path matching.
- **Performance Considerations:** In-memory decryption adds negligible latency to pipeline executions and GitOps syncs.
- **Operational Considerations:** Requires the `sops` and `age` CLI binaries on machines editing encrypted repository files.
- **Cost Considerations:** Infrastructure: ₹0.00 (open source tools; see amendment for KMS details).
- **Migration Plan:** N/A (implemented during bootstrap).
- **Validation / Fitness Functions:**
  - Pre-commit hooks must catch and block any unencrypted configuration files containing sensitive credential keys.
- **Dependencies:** Mozilla SOPS, Age cryptography tool.
- **Open Questions:** None.
- **Related ADRs:** ADR-008 (Operational Toolchain), ADR-012 (OCI Monorepo Consolidation).
- **Review Conditions:** Review if managing an offline key becomes difficult or if multi-user access controls are required.

---

### Amendment: October 2026: GCP Cloud KMS added as co-primary key provider

- **Trigger:** Relying solely on a single age key created a single point of failure when an operating system reinstall temporarily displaced the local key file.
- **Change:** GCP Cloud KMS (`projects/gcs-oci-homelab-controlplane/locations/global/keyRings/sops/cryptoKeys/sops-key`) was provisioned in the GCP control-plane project and added as a co-primary recipient in `.sops.yaml`. Creation rules now list both `gcp_kms` and `age`.
- **How It Works:** SOPS encrypts data keys with each provider independently. Either provider can decrypt the file. If KMS is inaccessible, the age key works; if the age key is missing, KMS decrypts the file.
- **Operational Model:**
  - *Day-to-day:* Decrypt via `gcloud auth application-default login` on any machine authenticated to GCP without copying key files.
  - *Disaster recovery:* Age key kept in a password manager as an offline fallback.
  - *New machine setup:* Running `gcloud auth application-default login` allows decryption without moving private key files.
- **Key properties:** `ENCRYPT_DECRYPT` purpose, `global` location, 90-day automatic rotation. Terraform sets `prevent_destroy = true` to guard against accidental deletion.
- **Existing files migrated:** Re-encrypted all repository secret files with `sops updatekeys` to include both recipients.
- **Cost:** GCP free tier covers 2,000 active key versions and 10,000 operations per month. With 1 active key version and ~50 monthly operations, effective cost is ₹0.00.
- **Risk after amendment:** Risk of key loss is low, requiring simultaneous loss of both GCP project access and the offline age backup.

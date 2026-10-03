```text
================================================================================
ADR-007: Secrets Management with SOPS, Age, and GCP Cloud KMS
================================================================================
```
- **Status:** Amended (October 2026 – see amendment below)
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** A GitOps workflow requires committing infrastructure and application state to a Git repository. This introduces the risk of exposing sensitive data (API tokens, database passwords, TLS certificates). We need a mechanism to safely store encrypted secrets in Git and decrypt them dynamically.
- **Problem Statement:** How do we securely encrypt sensitive configuration values in Git without introducing heavy, resource-intensive external secret managers?
- **Decision Drivers:**
  - Zero plaintext secrets committed to version control.
  - Strict RAM capping limits our ability to run heavy secret management servers.
  - Desire for stateless disaster recovery (secrets should not be locked to a specific cluster instance).
- **Decision:** I will use **Mozilla SOPS** paired with **Age** for asymmetric encryption.
- **Architecture Impact:** `age` will generate a public/private key pair. The public key will be committed via `.sops.yaml` to enforce encryption rules across the repository. The private key remains local (and injected into the K3s cluster) to decrypt values on the fly.
- **Alternatives Considered:**
  - *HashiCorp Vault:* Rejected. Too resource-intensive for a 12GB RAM homelab environment.
  - *Bitnami Sealed Secrets:* Rejected. Creates vendor lock-in to the specific Kubernetes cluster. Keys are stored in the cluster, making cold-start disaster recovery highly complex.
  - *GPG:* Rejected due to poor developer experience and complex web-of-trust management compared to modern `age` cryptography.
- **Decision Rationale:** SOPS + Age provides a completely stateless, extremely lightweight encryption layer. It is decoupled from the cluster state, meaning full disaster recovery is possible even if the cluster is completely destroyed, as long as the offline `age` key is preserved.
- **Consequences:**
  - *Positive:* Zero external dependencies (saves RAM); decoupled from cluster state; seamless GitOps integration.
  - *Negative:* Requires strict local key management.
  - *Risks:* If the `age` private key is lost, all encrypted secrets become permanently unrecoverable. *(Mitigated – see amendment below.)*
  - *Trade-offs:* Trading centralized secret auditing (like Vault) for lightweight stateless operation.
- **Security Considerations:** The `age` private key must never be committed and should be backed up securely offline (e.g., password manager or secure vault).
- **Reliability Considerations:** Encryption and decryption are mathematically deterministic and do not rely on an external API being online.
- **Scalability Considerations:** Scales easily to any number of encrypted files via `.sops.yaml` regex matching.
- **Performance Considerations:** In-memory decryption adds negligible overhead to pipeline executions and ArgoCD syncs.
- **Operational Considerations:** Requires `sops` and `age` CLI binaries to be installed on any client machine interacting with the repository.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source tools). See amendment for KMS cost.
- **Migration Plan:** N/A - Implemented during foundational bootstrap.
- **Validation / Fitness Functions:**
  - Pre-commit hooks must catch and block any attempt to commit plaintext YAML files containing keywords like `password` or `token`.
- **Dependencies:** Mozilla SOPS, Age cryptography tool.
- **Open Questions:** None.
- **Related ADRs:** ADR-008 (Operational Toolchain), ADR-012 (OCI Monorepo Consolidation).
- **Review Conditions:** Review if managing a single offline key becomes too risky, or if multi-user access control is required.

---

### Amendment – October 2026: GCP Cloud KMS Added as Co-Primary Key Provider

- **Trigger:** The single age key represented an unacceptable single point of failure after a real incident where an OS reinstall caused the key to be lost temporarily.
- **Change:** GCP Cloud KMS (`projects/gcs-oci-homelab-controlplane/locations/global/keyRings/sops/cryptoKeys/sops-key`) was provisioned in the existing GCP control-plane project (Terraform-managed, `gcp/` module in the bootstrap repo) and added as a co-primary recipient in `.sops.yaml`. Every creation rule now lists both `gcp_kms` **and** `age`.
- **How It Works:** SOPS encrypts the data key once with each provider. Either one can independently decrypt. If KMS is unavailable, the age key works. If the age key is lost, KMS works.
- **Operational Model:**
  - *Day-to-day:* Decrypt via `gcloud auth application-default login` – works on any machine authenticated to GCP, no key file required.
  - *Disaster recovery:* age key backed up to password manager as offline fallback.
  - *New machine setup:* `gcloud auth application-default login` is sufficient. No copying of key files.
- **Key properties:** `ENCRYPT_DECRYPT` purpose, `global` location, 90-day automatic rotation. `prevent_destroy = true` prevents accidental Terraform deletion.
- **Existing files migrated:** `sops updatekeys` re-wrapped all existing encrypted files to include both recipients.
- **Cost:** Free tier – 2,000 active key versions and 10,000 crypto operations/month. Actual usage: 1 key version, ~50 ops/month. Effective cost: ₹0.00.
- **Risk after amendment:** Key loss risk downgraded from *Critical* to *Low*. Requires both GCP project access AND age key to be simultaneously lost.

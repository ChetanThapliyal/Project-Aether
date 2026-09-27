```text
================================================================================
ADR-007: Secrets Management with SOPS and Age
================================================================================
```
- **Status:** Accepted
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
  - *Risks:* If the `age` private key is lost, all encrypted secrets become permanently unrecoverable.
  - *Trade-offs:* Trading centralized secret auditing (like Vault) for lightweight stateless operation.
- **Security Considerations:** The `age` private key must never be committed and should be backed up securely offline (e.g., password manager or secure vault).
- **Reliability Considerations:** Encryption and decryption are mathematically deterministic and do not rely on an external API being online.
- **Scalability Considerations:** Scales easily to any number of encrypted files via `.sops.yaml` regex matching.
- **Performance Considerations:** In-memory decryption adds negligible overhead to pipeline executions and ArgoCD syncs.
- **Operational Considerations:** Requires `sops` and `age` CLI binaries to be installed on any client machine interacting with the repository.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source tools).
- **Migration Plan:** N/A - Implemented during foundational bootstrap.
- **Validation / Fitness Functions:**
  - Pre-commit hooks must catch and block any attempt to commit plaintext YAML files containing keywords like `password` or `token`.
- **Dependencies:** Mozilla SOPS, Age cryptography tool.
- **Open Questions:** None.
- **Related ADRs:** ADR-008 (Operational Toolchain).
- **Review Conditions:** Review if managing a single offline key becomes too risky, or if multi-user access control is required.

# ADR-006: Secrets Management with SOPS and Age

## Status: Accepted

## Context

A GitOps workflow requires committing infrastructure and application state to a public or private Git repository. This introduces the risk of exposing sensitive data (API tokens, database passwords, TLS certificates). We need a mechanism to safely store encrypted secrets in Git and decrypt them dynamically.

## Decision

We will use **Mozilla SOPS** paired with **Age** for asymmetric encryption.

- `age` will generate a public/private key pair.
- The public key will be committed via `.sops.yaml` to enforce encryption rules.
- The private key will remain local (and securely injected into the K3s cluster later) to decrypt values.

## Consequences

- **Positive:** No external dependencies (unlike HashiCorp Vault) saving precious RAM on the hypervisor.
- **Positive:** Decoupled from the cluster state (unlike Bitnami Sealed Secrets), meaning disaster recovery is possible even if the cluster is completely destroyed.
- **Negative:** Requires strict local key management. If the `age` private key is lost, all encrypted secrets become unrecoverable.

## Alternatives Rejected

- **HashiCorp Vault:** Too resource-intensive for a 12GB RAM homelab environment.
- **Bitnami Sealed Secrets:** Creates a vendor lock-in to the specific Kubernetes cluster. Keys are stored in the cluster, making cold-start disaster recovery highly complex.
- **GPG:** Rejected due to poor developer experience and complex web-of-trust management compared to modern `age` cryptography.

```text
================================================================================
ADR-003: Kubernetes Distribution Selection (K3s vs Talos)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether requires a Kubernetes distribution as the core orchestration layer. The host machine has 12GB of RAM shared with the hypervisor and other VMs.
- **Problem Statement:** Which Kubernetes distribution provides a reliable orchestration environment within memory constraints while keeping standard Linux debuggability?
- **Decision Drivers:**
  - Resource efficiency (low RAM footprint).
  - Operational simplicity and interactive troubleshooting.
  - Common use in edge and production deployments.
- **Decision:** Deploy K3s as the Kubernetes distribution.
- **Architecture Impact:** K3s is installed on Ubuntu VMs provisioned via Terraform. The cluster is initialised with `--cluster-init`, replacing the default SQLite backend with an embedded etcd datastore. This elevates the node role to `control-plane,etcd` and enables native `k3s etcd-snapshot save` point-in-time state backups with direct upload to S3-compatible cloud storage.
- **Alternatives Considered:**
  - *Talos Linux:* Rejected. While Talos provides an immutable, API-driven operating system, it removes shell access for debugging. Standard SSH and Linux tools are useful for interactive troubleshooting in a single-operator environment.
  - *MicroK8s:* Rejected. MicroK8s relies on Canonical snap packaging and is less common outside Ubuntu environments. K3s maps more directly to general edge and lightweight deployments.
- **Decision Rationale:** K3s packages Kubernetes into a single lightweight binary with in-tree cloud providers and alpha APIs removed, keeping memory usage low on a host with 12GB RAM. Running on a standard Ubuntu VM retains conventional SSH and Linux troubleshooting workflows, and its widespread adoption matches common edge deployment patterns.
- **Consequences:**
  - *Positive:* Low memory footprint, standard Linux system debugging tools, active ecosystem support, and native etcd snapshot support enabling point-in-time backups uploadable directly to S3-compatible cloud storage.
  - *Negative:* Single-node embedded etcd still does not provide distributed high availability; it is acceptable for a single control-plane topology.
  - *Risks:* Modifying the underlying Ubuntu OS manually could destabilize the K3s agent. etcd snapshot restoration requires cluster downtime.
  - *Trade-offs:* Trading the strict immutability of an OS like Talos for familiar Linux troubleshooting tools.
- **Security Considerations:** K3s must be bound to internal network interfaces.
- **Reliability Considerations:** A single control plane node using embedded etcd has no distributed high availability. If the VM fails, the cluster API is unavailable until restored. Point-in-time recovery is operationalised via `k3s etcd-snapshot save` (OPS-09); snapshots are uploaded to S3-compatible cloud storage for off-node durability.
- **Scalability Considerations:** Can scale by adding worker nodes to the cluster through agent join tokens.
- **Performance Considerations:** Faster cluster bootstrap time compared to full Kubernetes (k8s).
- **Operational Considerations:** Upgrades are managed via the K3s upgrade controller or binary replacement. etcd snapshots are triggered via `k3s etcd-snapshot save` and stored in S3-compatible cloud storage; restoration follows standard K3s etcd recovery procedures.
- **Cost Considerations:** Infrastructure: ₹0.00 (open source).
- **Migration Plan:** Installed automatically via Ansible during Phase 1 bootstrap.
- **Validation / Fitness Functions:**
  - Control plane VM memory consumption should remain under 1.5GB while idle.
- **Dependencies:** Ubuntu Cloud Images, Ansible.
- **Open Questions:** None. *(OPS-09 resolved the SQLite → etcd migration; S3 snapshot destination configured in `infrastructure/ansible/playbooks/control.yml`.)*
- **Related ADRs:** ADR-006 (Proxmox VM Provisioning).
- **Review Conditions:** Review if migrating to a high-availability multi-master control plane. Embedded etcd already satisfies the datastore requirement; the primary trigger would be adding additional control-plane nodes.

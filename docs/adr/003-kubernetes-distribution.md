```text
================================================================================
ADR-003: Kubernetes Distribution Selection (K3s vs Talos)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether requires a Kubernetes distribution to act as the core orchestration layer. The host machine has limited resources (12GB RAM total, shared with the hypervisor and other potential VMs).
- **Problem Statement:** Which Kubernetes distribution provides a production-grade orchestration environment while operating within severe memory constraints and maintaining standard Linux debuggability?
- **Decision Drivers:**
  - Strict resource efficiency (RAM footprint).
  - Operational simplicity and ease of interactive troubleshooting.
  - Industry relevance and alignment with standard edge/production deployments.
- **Decision:** I will deploy **K3s** as the Kubernetes distribution.
- **Architecture Impact:** K3s will be installed on Ubuntu VMs provisioned via Terraform. It will use its default embedded SQLite datastore (instead of a heavy separate etcd cluster) to conserve memory.
- **Alternatives Considered:**
  - *Talos Linux:* Rejected. While Talos is API-driven, immutable, and excellent for declarative infrastructure, it removes the ability to SSH in and debug interactively at the OS level. Standard Linux/DevOps troubleshooting muscle memory is critical when learning and managing a single-operator environment.
  - *MicroK8s:* Rejected. MicroK8s is heavily tied to the Canonical/Ubuntu ecosystem (relying on snap packaging) and is less common outside of that specific ecosystem. K3s maps much closer to industry-standard edge and SMB deployments.
- **Decision Rationale:** K3s wins on three fronts:
  1. *Resource efficiency:* It strips out legacy alpha APIs and in-tree cloud provider code, bundling everything into a single lightweight binary, which is critical for an i3 processor with limited RAM.
  2. *Debuggability:* It runs on a standard Linux VM, allowing traditional SSH access for troubleshooting.
  3. *Industry Relevance:* K3s is widely adopted in real-world edge production environments, making hands-on experience highly relevant to standard industry practices.
- **Consequences:**
  - *Positive:* Minimal memory footprint; standard Linux debugging; high industry relevance.
  - *Negative:* Embedded SQLite datastore is less resilient than a true distributed etcd cluster (though acceptable for a single-node control plane).
  - *Risks:* Modifying the underlying Ubuntu OS manually could destabilize the K3s agent.
  - *Trade-offs:* Sacrificing the strict immutability of an OS like Talos for familiar, accessible Linux troubleshooting.
- **Security Considerations:** K3s must be bound securely to the internal network interfaces.
- **Reliability Considerations:** Single control plane node (SQLite) means zero control-plane high availability (HA). If the control plane VM dies, the API is down.
- **Scalability Considerations:** Can easily scale by adding more worker nodes to the cluster via simple agent join tokens.
- **Performance Considerations:** Extremely fast cluster bootstrap time compared to full Kubernetes (K8s).
- **Operational Considerations:** Upgrades are managed via the K3s upgrade controller or manual binary replacement.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source).
- **Migration Plan:** Installed automatically via Ansible during Phase 1 bootstrap.
- **Validation / Fitness Functions:**
  - Control plane VM memory consumption should remain under 1.5GB while idle.
- **Dependencies:** Ubuntu Cloud Images, Ansible.
- **Open Questions:** None.
- **Related ADRs:** ADR-006 (Proxmox VM Provisioning).
- **Review Conditions:** Review if moving to a highly available (HA) multi-master control plane requiring a distributed datastore.

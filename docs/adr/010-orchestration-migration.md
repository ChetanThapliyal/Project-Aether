```text
================================================================================
ADR-010: Orchestration Migration (LXC Docker Compose to Kubernetes)
================================================================================
```
- **Status:** Accepted
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The homelab initially ran 34 self-hosted applications using Docker Compose inside a single Proxmox LXC container. A single container crash or Docker daemon restart affected all 34 services simultaneously, and state management required manual host intervention.
- **Problem Statement:** How do we transition to a declarative, self-healing orchestration platform without exceeding the physical 12GB RAM limit?
- **Decision Drivers:**
  - Eliminating the single failure domain of a shared Docker daemon.
  - Adopting declarative GitOps workflows.
  - Building operational skills on Kubernetes.
  - Keeping memory consumption within physical host constraints.
- **Decision:** Migrate orchestration from the single LXC Docker Compose container to a K3s cluster managed via GitOps, offloading non-critical services to an external OCI instance to keep the local footprint to 5 or 6 core applications.
- **Architecture Impact:** The legacy LXC container is retired. Target applications are rewritten into Kubernetes deployments and statefulsets managed by ArgoCD on the K3s worker node.
- **Alternatives Considered:**
  - *Maintain Monolithic LXC Docker Compose:* Rejected. Lacks automated health self-healing, advanced ingress routing, and declarative state synchronization.
  - *Multi-VM Docker Compose:* Rejected. Running multiple virtual machines purely for Docker Compose duplicates OS memory overhead without providing declarative container scheduling.
- **Decision Rationale:** Kubernetes provides declarative GitOps synchronization, automated pod restarts, and container network policies. Because the control plane, kubelet, and ArgoCD require dedicated memory, retaining all 34 local services would exceed the 12GB host limit. Moving 28 non-essential services to an external OCI instance preserves enough memory to run K3s reliably for the remaining core applications.
- **Consequences:**
  - *Positive:** GitOps deployment workflows, automated pod restarts, rolling updates, and isolated failure domains.
  - *Negative:* Higher operational complexity and baseline memory overhead compared to a single LXC container.
  - *Risks:* Initial effort required to convert Docker Compose files into Kubernetes manifests.
  - *Trade-offs:* Trading the minimal memory footprint of a single Docker daemon for declarative orchestration and resilience.
- **Security Considerations:** Kubernetes network policies enforce network isolation between applications, replacing the shared flat Docker bridge network.
- **Reliability Considerations:** K3s provides automated restart and scheduling for crashed pods.
- **Scalability Considerations:** Worker capacity can be expanded by adding physical nodes to the K3s cluster.
- **Performance Considerations:** Adds modest virtualization and network proxy overhead, which is manageable with the reduced application count.
- **Operational Considerations:** Replaces `docker compose` with Kubernetes tooling including Helm, Kustomize, and `kubectl`.
- **Cost Considerations:** Infrastructure: ₹0.00 (open source). The OCI server runs on the Oracle Cloud Always Free tier.
- **Migration Plan:** The legacy LXC container runs in parallel while core applications are migrated to K3s incrementally via ArgoCD. Once workloads are stable, the LXC container is decommissioned.
- **Validation / Fitness Functions:**
  - The K3s cluster must run target core applications and ArgoCD without causing host out-of-memory errors on the 12GB machine.
- **Dependencies:** K3s, ArgoCD, OCI compute instance.
- **Open Questions:** None.
- **Related ADRs:** ADR-001 (Hypervisor Selection), ADR-003 (Kubernetes Distribution), ADR-009 (GitOps Controller).
- **Review Conditions:** N/A (permanent architecture change).

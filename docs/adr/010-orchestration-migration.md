```text
================================================================================
ADR-010: Orchestration Migration (LXC Docker Compose to Kubernetes)
================================================================================
```
- **Status:** Accepted
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Historically, the homelab operated 34 self-hosted applications using Docker Compose within a single monolithic Proxmox LXC container. While this was highly resource-efficient for the 12GB RAM limit, it created a massive blast radius. A single misconfigured container or Docker daemon restart disrupted all 34 services simultaneously. Furthermore, managing state and updates became a manual, fragile process ("pet infrastructure").
- **Problem Statement:** How do we modernize the orchestration layer to provide high availability, declarative management, and operational maturity without exhausting the strict hardware resource constraints?
- **Decision Drivers:**
  - Need to eliminate the single massive blast radius of the monolithic Docker daemon.
  - Desire to adopt declarative GitOps (infrastructure as code).
  - Need to modernize skills towards enterprise-grade Kubernetes operations.
  - Recognition that 34 local applications are unsustainable on 12GB RAM if moved to a more robust, heavier orchestration platform.
- **Decision:** I will migrate orchestration from the monolithic **LXC Docker Compose** to a **GitOps-driven Kubernetes (K3s) cluster**, while aggressively offloading non-critical applications to an external OCI server, reducing the local footprint to 5-6 core services.
- **Architecture Impact:** The legacy LXC container will be deprecated. Workloads will be refactored into Kubernetes deployments/statefulsets, managed by ArgoCD, and deployed onto the K3s worker node.
- **Alternatives Considered:**
  - *Maintain Monolithic LXC Docker Compose:* Rejected. It lacks self-healing, advanced ingress traffic routing (like Gateway API/Ingress), and fails to provide the operational maturity required for a production-grade environment.
  - *Multi-VM Docker Compose (Splitting the monolith):* Rejected. Running multiple VMs just for Docker Compose introduces significant hypervisor overhead (OS duplication) without providing the orchestration benefits (scheduling, self-healing) of Kubernetes.
- **Decision Rationale:** Moving to Kubernetes is a fundamental step up in platform maturity. It unlocks GitOps, dynamic secrets management, and robust networking policies. Because Kubernetes introduces additional overhead (etcd/SQLite, kubelet, ArgoCD), running all 34 original apps locally would guarantee Out-Of-Memory (OOM) failures. By making the hard architectural choice to offload 28+ apps to a cloud OCI instance, we free up enough resources to run a truly robust, production-grade K3s cluster for the 5-6 core services that actually require local execution.
- **Consequences:**
  - *Positive:* Enterprise-grade operational maturity; GitOps deployment pipelines; zero-downtime rolling updates; strict failure domain isolation.
  - *Negative:* Massive increase in architectural complexity; higher base memory overhead compared to a single LXC container.
  - *Risks:* Learning curve associated with migrating Docker Compose files to complex Kubernetes manifests.
  - *Trade-offs:* Trading the simplicity and ultra-low overhead of a single Docker daemon for the resilience and scalability of a distributed orchestrator.
- **Security Considerations:** Kubernetes network policies will allow for granular zero-trust isolation between the remaining 5-6 local applications, which was impossible in the shared Docker bridge network.
- **Reliability Considerations:** K3s provides pod self-healing and automatic restarts if an application crashes, unlike static Docker containers.
- **Scalability Considerations:** The cluster can seamlessly scale out to new physical nodes if hardware is upgraded in the future.
- **Performance Considerations:** Migrating away from a single LXC container introduces virtualization networking and Kube-proxy overhead, but is acceptable given the reduced application count.
- **Operational Considerations:** Requires an entirely new operational toolchain (Helm, Kustomize, `kubectl`) replacing simple `docker-compose up` commands.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source). The OCI server utilized for offloaded apps utilizes the Oracle Cloud Always Free tier.
- **Migration Plan:** The legacy LXC container will run in parallel (strangler pattern) while the 5-6 core apps are migrated to K3s one by one via ArgoCD (Phase 4). Once the core apps are stable, the LXC container will be gracefully shut down.
- **Validation / Fitness Functions:**
  - The K3s cluster must successfully run the 5-6 core applications along with ArgoCD without triggering host-level OOM kills on the 12GB RAM machine.
- **Dependencies:** K3s, ArgoCD, OCI Cloud Instance (for offloaded apps).
- **Open Questions:** None.
- **Related ADRs:** ADR-001 (Hypervisor Selection), ADR-003 (Kubernetes Distribution), ADR-009 (GitOps Controller).
- **Review Conditions:** N/A - This is a one-way architectural shift.

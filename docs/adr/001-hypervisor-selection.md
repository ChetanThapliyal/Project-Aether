```text
================================================================================
ADR-001: Hypervisor Selection (Proxmox vs Bare-Metal Docker)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The foundational hardware for Project Aether is a single physical machine (Intel Core i3, 12GB RAM). This hardware must host the entire infrastructure, including Kubernetes, storage management, and networking layers.
- **Problem Statement:** How do we partition a single physical machine to run diverse workloads while maintaining strict isolation, preventing a single failure from taking down the entire system?
- **Decision Drivers:**
  - Blast radius containment (a bad update should not break the host network).
  - Ability to roll back quickly when making experimental or risky changes.
  - Support for mixing full VMs (for Kubernetes) and lightweight containers.
- **Decision:** Adopt Proxmox Virtual Environment (PVE) as the bare-metal hypervisor.
- **Architecture Impact:** Proxmox becomes the base OS (Type-1 hypervisor). All workloads, including the K3s cluster, run as virtualized guests (KVM) or lightweight Linux containers (LXC) on top of Proxmox.
- **Alternatives Considered:**
  - *Bare-metal Ubuntu + Docker:* Rejected. Running all workloads on one shared kernel and root filesystem risks host downtime if a container, `apt upgrade`, or kernel panic fails. It also lacks hypervisor-level snapshotting.
  - *VMware ESXi:* Rejected. Licensing changes have restricted the free tier, the platform is closed source, and its resource footprint is heavier than Proxmox's KVM/LXC model on an i3 processor.
- **Decision Rationale:** Proxmox provides VM-level isolation. K3s runs in its own VM kernel boundary, while lighter services run in LXC. Proxmox supports hypervisor snapshots and rollbacks, and integrates with Terraform through existing open-source providers.
- **Consequences:**
  - *Positive:* Isolated failure domains, snapshot-based rollbacks, and support for both KVM and LXC workloads.
  - *Negative:* Virtualization overhead consumes part of the 12GB RAM.
  - *Risks:* Single physical host failure crashes all VMs simultaneously.
  - *Trade-offs:* Trading bare-metal efficiency for faster recovery and isolated failure domains.
- **Security Considerations:** The Proxmox management interface (port 8006) is not exposed to the public internet and is accessible only via internal LAN or VPN.
- **Reliability Considerations:** A kernel panic inside the K3s VM does not affect other isolated LXC containers or host networking.
- **Scalability Considerations:** Limited strictly by the physical 12GB of RAM on the host.
- **Performance Considerations:** CPU virtualization flags (VT-x) must be enabled in BIOS.
- **Operational Considerations:** Host updates via Debian APT must be managed separately from guest OS updates.
- **Cost Considerations:** Infrastructure: ₹0.00 (community no-subscription repository).
- **Migration Plan:** N/A (initial installation).
- **Validation / Fitness Functions:**
  - Taking a full VM snapshot must complete without pausing the K3s cluster for more than 5 seconds.
- **Dependencies:** Intel VT-x hardware virtualization.
- **Open Questions:** None.
- **Related ADRs:** ADR-002 (Storage Topology).
- **Review Conditions:** Review if hardware is upgraded or a secondary physical node is added to create a Proxmox cluster.

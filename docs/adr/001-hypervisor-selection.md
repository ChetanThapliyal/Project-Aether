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
  - Blast radius containment (a bad update shouldn't break the host network).
  - Ability to rollback quickly when making experimental or risky changes.
  - Support for mixing full VMs (for Kubernetes) and lightweight containers.
- **Decision:** I will use **Proxmox Virtual Environment (PVE)** as the bare-metal hypervisor.
- **Architecture Impact:** Proxmox becomes the base OS (Type-1 Hypervisor). All workloads, including the K3s cluster, will run as virtualized guests (KVM) or lightweight Linux Containers (LXC) on top of Proxmox.
- **Alternatives Considered:**
  - *Bare-metal Ubuntu + Docker:* Rejected. Puts every workload in one shared kernel and root filesystem. A misbehaving container, bad `apt upgrade`, or kernel panic takes down the entire system (including the remote access layer). It lacks native hypervisor-level snapshotting.
  - *VMware ESXi:* Rejected. Broadcom's licensing changes have severely restricted the free hypervisor tier. It is closed-source, less idiomatic for homelabs, and has a heavier resource footprint than Proxmox's KVM/LXC hybrid – a real concern on an i3 processor.
- **Decision Rationale:** Proxmox provides strict VM-level isolation. K3s can run in its own VM boundary with its own kernel, while lightweight services can use LXC. Crucially, Proxmox allows for instant hypervisor-level snapshots and rollbacks, demonstrating high operational maturity. Furthermore, Proxmox integrates natively with Terraform via open-source providers, directly transferring skills to KVM-based cloud infra.
- **Consequences:**
  - *Positive:* Hard failure domain isolation; instant snapshot rollbacks; clean mixing of KVM and LXC workloads.
  - *Negative:* Virtualization overhead consumes a portion of the limited 12GB RAM.
  - *Risks:* Single physical host failure still crashes all VMs simultaneously.
  - *Trade-offs:* Sacrificing bare-metal performance efficiency for operational agility and recovery boundaries.
- **Security Considerations:** The Proxmox management interface (Port 8006) is not exposed to the public internet, accessible only via internal LAN or VPN.
- **Reliability Considerations:** A kernel panic inside the K3s VM will not affect other isolated LXC containers or the host networking.
- **Scalability Considerations:** Limited strictly by the physical 12GB of RAM on the host.
- **Performance Considerations:** CPU virtualization flags (VT-x) must be enabled in BIOS.
- **Operational Considerations:** Requires managing Proxmox host updates via Debian APT separately from the guest OS updates.
- **Cost Considerations:** Infrastructure: ₹0.00 (Community No-Subscription Repository).
- **Migration Plan:** N/A - Foundational installation.
- **Validation / Fitness Functions:**
  - Taking a full VM snapshot must complete without pausing the K3s cluster for more than 5 seconds.
- **Dependencies:** Intel VT-x hardware virtualization.
- **Open Questions:** None.
- **Related ADRs:** ADR-002 (Storage Topology).
- **Review Conditions:** Review if hardware is upgraded or a secondary physical node is added to create a Proxmox cluster.

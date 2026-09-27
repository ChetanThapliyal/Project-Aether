```text
================================================================================
ADR-002: Dual-Tier Storage Topology
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The homelab chassis contains two physically disparate storage drives: a high-performance 256GB SSD and a high-capacity 500GB mechanical HDD.
- **Problem Statement:** How do we architect storage allocation across mismatched hardware to maximize application I/O throughput while ensuring capacity-heavy media and backups do not exhaust primary operating system disks?
- **Decision Drivers:**
  - High random IOPS required by Kubernetes (K3s SQLite/etcd) and database workloads.
  - High storage capacity required for media streaming (Jellyfin) and disaster recovery snapshots.
  - Prevention of SSD write-wear and disk-full lockouts on OS partitions.
- **Decision:** I will establish a strict **Two-Tier Storage Topology**:
  1. *Tier 1 (Hot - 256GB SSD):* Dedicated to the Proxmox host OS, VM/LXC root disks, K3s node OS disks, embedded datastores, container images, and observability working data.
  2. *Tier 2 (Cold - 500GB HDD):* Dedicated to bulk/cold storage, including the Jellyfin media library, Proxmox `vzdump` backups, and recovered ZFS data pools.
- **Architecture Impact:** Affects Proxmox storage pools, Terraform VM disk provisioning, and Kubernetes Persistent Volume Claim (PVC) storage classes.
- **Alternatives Considered:**
  - *Single Unified Drive:* Rejected. K3s is highly sensitive to slow disk I/O; running its embedded datastore on a mechanical HDD causes extreme disk contention, high I/O wait, and poor cluster performance.
  - *ZFS Mirror across SSD and HDD:* Rejected. ZFS mirrors are throttled to the speed of the slowest drive (HDD) and capacity is capped at the smallest drive (256GB), wasting space and destroying performance.
- **Decision Rationale:** A tiering approach aligns with standard production practices. Anything the scheduler, control plane, or databases touch frequently lives on flash memory where IOPS matter. Bulk sequential read/write operations (like media streaming or taking backups) do not require SSD speed and belong on the HDD. The HDD also utilizes ZFS for bitrot protection on irreplaceable data.
- **Consequences:**
  - *Positive:* High I/O performance for applications; capacity preserved for cold media; zero risk of backup jobs filling the root OS drive.
  - *Negative:* Requires manual path mounting and explicit disk targeting when provisioning VMs.
  - *Risks:* The 500GB HDD is a single point of failure for cold data if not backed up offsite.
  - *Trade-offs:* Added complexity in managing multiple storage pools.
- **Security Considerations:** Storage mounts are restricted by Linux file permissions.
- **Reliability Considerations:** Physical separation ensures heavy I/O workloads operate smoothly without being choked by bulk backup writes.
- **Scalability Considerations:** The 256GB SSD will become the primary bottleneck as more K3s applications are deployed.
- **Performance Considerations:** K3s datastore achieves necessary sub-millisecond sync times on the SSD.
- **Operational Considerations:** Backup tasks must be strictly configured to target the HDD storage pool to prevent spilling onto the local SSD.
- **Cost Considerations:** Infrastructure: ₹0.00 (Existing drives).
- **Migration Plan:** N/A - Implemented during Proxmox installation.
- **Validation / Fitness Functions:**
  - Disk I/O wait (`wa` in `top`) during nightly backups must not degrade K8s API latency significantly.
- **Dependencies:** Proxmox storage subsystem, ZFS.
- **Open Questions:** None.
- **Related ADRs:** ADR-001 (Hypervisor Selection).
- **Review Conditions:** Review when SSD free space drops below 20%.

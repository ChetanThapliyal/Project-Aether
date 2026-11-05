```text
================================================================================
ADR-002: Dual-Tier Storage Topology
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The homelab machine contains two physical storage drives: a 256GB SSD and a 500GB mechanical HDD.
- **Problem Statement:** How do we partition storage across mismatched hardware to support Kubernetes I/O demand while preserving space for media and backups without filling root disks?
- **Decision Drivers:**
  - High random IOPS required by Kubernetes (K3s SQLite/etcd) and database workloads.
  - High storage capacity required for media streaming (Jellyfin) and disaster recovery snapshots.
  - Prevention of SSD write wear and disk-full lockouts on OS partitions.
- **Decision:** Establish a two-tier storage topology:
  1. *Tier 1 (Hot, 256GB SSD):* Dedicated to the Proxmox host OS, VM/LXC root disks, K3s node OS disks, embedded datastores, container images, and observability working data.
  2. *Tier 2 (Cold, 500GB HDD):* Dedicated to bulk and cold storage, including the Jellyfin media library, Proxmox `vzdump` backups, and ZFS data pools.
- **Architecture Impact:** Governs Proxmox storage pools, Terraform VM disk definitions, and Kubernetes Persistent Volume Claim (PVC) storage classes.
- **Alternatives Considered:**
  - *Single Unified Drive:* Rejected. Running the K3s datastore on a mechanical HDD causes high disk I/O wait and degrades cluster performance.
  - *ZFS Mirror across SSD and HDD:* Rejected. A mirror between mismatched drives throttles write speeds to the HDD and caps usable space at 256GB.
- **Decision Rationale:** Workloads requiring random I/O (the Kubernetes control plane, SQLite, container runtimes) reside on SSD storage. Sequential bulk operations such as media storage and system backups run on the mechanical HDD, which also uses ZFS for data integrity checks.
- **Consequences:**
  - *Positive:* Fast I/O for cluster services, dedicated capacity for media, and separation between backups and root OS disks.
  - *Negative:* Requires manual path mounting and explicit disk targeting when provisioning VMs.
  - *Risks:* The 500GB HDD is a single point of failure for cold data if not backed up offsite.
  - *Trade-offs:* Added operational complexity in managing multiple storage pools.
- **Security Considerations:** Storage mounts are restricted by Linux file permissions.
- **Reliability Considerations:** Physical separation ensures heavy I/O workloads operate without contention from bulk backup writes.
- **Scalability Considerations:** The 256GB SSD will become the primary capacity constraint as more K3s applications are deployed.
- **Performance Considerations:** The K3s datastore achieves required sub-millisecond sync times on the SSD.
- **Operational Considerations:** Backup tasks must target the HDD storage pool to prevent consuming space on the root SSD.
- **Cost Considerations:** Infrastructure: ₹0.00 (existing drives).
- **Migration Plan:** N/A (configured during Proxmox installation).
- **Validation / Fitness Functions:**
  - Disk I/O wait (`wa` in `top`) during nightly backups must not degrade Kubernetes API response times.
- **Dependencies:** Proxmox storage subsystem, ZFS.
- **Open Questions:** None.
- **Related ADRs:** ADR-001 (Hypervisor Selection).
- **Review Conditions:** Review when SSD free space drops below 20%.

## Addendum (2026-11-05): backups must be on a dataset, not a path

"Backup tasks must target the HDD storage pool" was not enforced. The DR jobs wrote to `/mnt/aether-pool/`, which was a directory on the SSD, while the pool was mounted elsewhere ([INC-2026-007](../incidents/INC-2026-007-dr-copies-on-wrong-disk.md)). Each backup target is now a named ZFS dataset mounted at the path the job uses, and the job checks the mount source before writing. The HDD pool is a single-disk vdev. The ZFS ARC is capped at 512 MiB (`/etc/modprobe.d/zfs.conf`), because the 12 GB host has about 1 GiB free.

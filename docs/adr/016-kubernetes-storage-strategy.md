```text
================================================================================
ADR-016: Kubernetes Storage Strategy & In-Cluster Storage Engine Ruling
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether operates a 3-node K3s cluster on a 12 GB RAM notebook (1 control plane VM, 2 worker VMs with ~3.5 GB allocatable RAM each). Stateful workloads require persistent volume provisioning across the dual-tier physical hardware (256 GB SSD and 500 GB HDD, per ADR-002).
- **Problem Statement:** How do we provision reliable persistent storage for Kubernetes workloads without exceeding the physical 12 GB RAM ceiling or subjecting consumer SSDs to destructive write churn?
- **Decision Drivers:**
  - Strict host memory constraints: 12 GB total RAM on the notebook; worker VMs carry ~3.5 GB allocatable RAM each.
  - Physical storage tiering (ADR-002): Tier 1 (256 GB SSD) for high-IOPS random access; Tier 2 (500 GB HDD ZFS) for bulk cold storage.
  - Storage access patterns: Workload configs/databases require low-latency ReadWriteOnce (RWO), while media apps (Jellyfin, qBittorrent in Phase 04) require shared ReadWriteMany (RWX).
  - Observability architecture: Heavy time-series metrics (Prometheus TSDB) and log aggregation (Loki/Grafana) are externalized to Oracle Cloud (OCI Always-Free 2 OCPU / 12 GB RAM instance) over Tailscale, avoiding in-cluster compute and storage exhaustion.
- **Decision:**
  1. *Reject in-cluster replicated block storage (Longhorn / Rook-Ceph):* In-cluster storage engines require 1.2–1.5 GB of RAM across nodes for CSI controllers, instance managers, and replica daemons, consuming ~40% of worker RAM.
  2. *Confirm Rancher `local-path` as the Default StorageClass:* Rancher's embedded `local-path-provisioner` provides dynamic hostPath persistent volume provisioning backed by the node's local SSD. It has negligible memory overhead (< 15 MiB), zero background CPU overhead, and native SSD random I/O performance using `WaitForFirstConsumer` binding.
  3. *Reserve Proxmox ZFS NFS for Phase 04 Bulk Media (RWX):* Shared multi-node access for media applications will be served directly from the Proxmox Tier 2 mechanical HDD ZFS pool (`/mnt/aether-pool`) via an external NFS export, keeping storage engine complexity outside the Kubernetes control loop.
  4. *Externalize Observability TSDB to OCI:* Prometheus and Grafana are hosted on the OCI A1.Flex tier (200 GB block storage, 12 GB RAM). OCI Prometheus scrapes K3s metrics via Tailscale (`tag:oci` → `tag:k3s:9100` per ADR-013). This eliminates in-cluster TSDB write amplification on the homelab SSD and ensures monitoring survives a complete homelab node outage.
- **Architecture Impact:**
  - `local-path` is the default StorageClass across the cluster.
  - No storage controller pods or replica daemons are scheduled on worker nodes, preserving ~1.5 GB of RAM for platform ingress and core workloads.
  - Phase 04 stateful applications target either `local-path` (for node-local SQLite/config state) or NFS (for media libraries).
  - Monitoring and alerting act as an out-of-band observer from OCI, rather than a failure co-domain within the homelab.
- **Alternatives Considered:**
  - *Longhorn (CSI Block Storage):* Rejected. Requires ~1.2–1.5 GB RAM baseline across workers, introduces replica synchronization network overhead over 1 GbE, and provides redundant HA capabilities for workloads whose disaster recovery is already governed by Restic snapshots and GitOps rebuilds.
  - *Rook-Ceph:* Rejected. Exceeds available RAM and CPU budget (> 2 GB RAM minimum, demanding dedicated OSD disks).
  - *NFS as Default StorageClass for all Persistent Volumes:* Rejected. SQLite and etcd require sub-millisecond `fsync` latencies. Network file locks over NFS frequently induce SQLite database locks and control plane instability.
- **Decision Rationale:** On hardware-constrained homelab nodes, in-cluster replicated storage provides diminishing returns at crippling resource costs. Disaster recovery in Project Aether relies on automated offsite backups (Restic to Backblaze B2) and GitOps declarations rather than live block-level replication. `local-path` delivers raw SSD I/O for local databases with almost zero RAM penalty, Proxmox ZFS handles bulk media via NFS, and OCI handles heavy TSDB storage out-of-band.
- **Consequences:**
  - *Positive:* Zero storage engine RAM penalty (< 15 MiB vs ~1.5 GB for Longhorn); full NVMe/SSD IOPS for local state; out-of-band monitoring survivability; clean separation of fast local data and bulk cold storage.
  - *Negative:* `local-path` volumes are bound to a specific node; if a worker VM dies, pods using its local volumes cannot automatically fail over to another node without backup restoration.
  - *Risks:* Accidental pod rescheduling across nodes requires volume recreation or node affinity pinning.
  - *Trade-offs:* Trading automatic multi-node block failover for 1.5 GB of free RAM and sub-millisecond database I/O.
- **Security Considerations:** Local volumes are isolated to `/opt/local-path-provisioner` on the host with standard Linux directory permissions. NFS exports from Proxmox are constrained to the internal VM network subnet (`192.168.1.0/24`).
- **Reliability Considerations:** Because `local-path` is node-pinned, stateful workloads rely on Restic file-level backup pipelines rather than storage-layer replication.
- **Scalability Considerations:** If high-availability storage is required in a future multi-node bare-metal cluster, storage can be migrated to a dedicated NAS or external SAN without altering application deployment manifests.
- **Performance Considerations:** Near-native SSD random read/write speeds with zero network encapsulation overhead.
- **Operational Considerations:** Volumes use `VOLUMEBINDINGMODE: WaitForFirstConsumer` to ensure volumes are allocated on the exact node where the consumer pod is scheduled.
- **Cost Considerations:** ₹0.00 infrastructure cost; utilizes built-in K3s components and free-tier OCI compute/storage.
- **Validation / Fitness Functions:**
  - `storage-smoke-pvc` successfully bound and mounted to a test pod within 12 seconds on `local-path` StorageClass.
  - Cluster memory commitment remains below 50% across both workers.
- **Dependencies:** Rancher `local-path-provisioner`, Proxmox ZFS, Tailscale Grants, OCI Compute instance.
- **Related ADRs:** ADR-001 (Hypervisor Selection), ADR-002 (Dual-Tier Storage Topology), ADR-003 (Kubernetes Distribution), ADR-010 (Orchestration Migration), ADR-013 (Tailnet Micro-segmentation).
- **Review Conditions:** Re-evaluate if worker hardware is upgraded beyond 32 GB RAM or if a multi-node Ceph cluster is introduced.

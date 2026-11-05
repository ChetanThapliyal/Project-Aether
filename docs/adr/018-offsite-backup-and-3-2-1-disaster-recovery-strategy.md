```text
================================================================================
ADR-018: Offsite Backup and 3-2-1 Disaster Recovery Architecture
================================================================================
```
- **Status:** Accepted
- **Date:** November 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether's core control plane runs as a 3-node K3s cluster on a physical notebook running Proxmox VE 9.2. To conserve RAM within the 12 GB physical limit, K3s runs embedded etcd with a single control-plane node (`k3s-control-01`). In ADR-002 (Dual-Tier Storage Topology), the mechanical 500 GB HDD (`aether-pool`) was allocated for bulk backups, but explicitly flagged as a single point of failure if not replicated offsite. Furthermore, Project Aether's Zero-Trust security model (ADR-004, ADR-013) prohibits inbound connections from cloud or public tiers into the internal homelab network.
- **Problem Statement:** How do we establish a resilient, automated, and ransomware-resistant 3-2-1 backup and disaster recovery architecture for the Kubernetes control plane and stateful data that guarantees rapid recovery from total homelab hardware loss without incurring cloud storage/egress fees or puncturing network isolation boundaries?
- **Decision Drivers:**
  - *Zero-Cost / Always-Free Storage Ceiling:* ₹0.00 / $0.00 operational cost target; cloud storage must fit within generous free tiers with zero or predictable egress charges.
  - *3-2-1 Backup Rule Enforcement:* 3 copies of data, across 2 different media types, with 1 copy situated geographically offsite in an independent cloud failure domain.
  - *Ransomware & Blast Radius Isolation:* Compromise of an on-prem node or hypervisor root must not allow an attacker or corrupted prune operation to purge, encrypt, or overwrite historical cloud backups.
  - *Zero-Trust Network Perimeter (ADR-013):* Cloud nodes (OCI Kestra, GCP DMZ) must not hold SSH keys or open inbound network tunnels to the physical Proxmox host. All offsite replication must initiate outbound from the homelab over TLS/HTTPS.
  - *Repository Decoupling vs. Dumb Sync:* A raw bucket-to-bucket mirror (e.g., `rclone sync`) blindly propagates corrupted or purged repositories directly to the cloud. The offsite copy must use cryptographic repository-to-repository replication (`restic copy`).
- **Decision:**
  1. *Adopt the 4-Stage 3-2-1 Disaster Recovery Pipeline:*
     - **Stage 1 (DR-01, 02:00 UTC): In-Node Compressed Datastore Snapshots.** `k3s-control-01` runs automated daily cron (`0 2 * * *`) generating frozen, zstd-compressed etcd database snapshots into `/var/lib/rancher/k3s/server/db/snapshots/` with 14-day local retention.
     - **Stage 2 (DR-02, 02:30 UTC): Off-Node Physical Hypervisor Pull.** Proxmox VE host (`192.168.1.200`) executes an automated daily pull via `rsync` over internal LAN, copying frozen snapshot archives to `/mnt/aether-pool/k3s-etcd-snapshots/` on the ZFS HDD pool.
     - **Stage 3 (DR-03, 03:00 UTC): Dedicated Encrypted Local Restic Repository.** Proxmox commits snapshot files into an independent encrypted Restic repository at `/mnt/aether-pool/restic-k3s-etcd/` (password `/etc/restic/etcd-password.txt`), applies a GFS retention policy (14 daily, 4 weekly, 6 monthly snapshots), prunes orphaned blobs, and executes integrity checks.
     - **Stage 4 (DR-04, 03:30 UTC): Offsite Cloud Replication via `restic copy`.** Proxmox replicates snapshots to Backblaze B2 (`aether-restic-etcd-offsite`) using native `restic copy` over WAN, verified by remote repository integrity checks.
  2. *Select Backblaze B2 (Decision P3-D3) via S3-Compatible API:*
     - Choose Backblaze B2 for the offsite storage tier (10 GB Always-Free storage, free egress via Cloudflare Bandwidth Alliance partnership).
     - Standardize on Backblaze B2's S3-Compatible API endpoint (`s3:https://s3.us-east-005.backblazeb2.com/<bucket>`). The legacy native B2 Go client in Restic relies on the deprecated `/b2api/v1/b2_authorize_account` API which rejects modern bucket-restricted Application Keys with HTTP 400. B2's S3 API avoids this limitation completely, allowing modern bucket-scoped keys to function seamlessly.
  3. *Enforce Scoped Least-Privilege Application Credentials:*
     - Manage the B2 bucket (`aether-restic-etcd-offsite`) and write-scoped Application Key declaratively via a dedicated 4th root Terraform module (`infrastructure/terraform/04-backblaze-b2/`) per ADR-014.
     - Restrict the homelab application key to the specific backup bucket with minimum capabilities (`["listBuckets", "listFiles", "readFiles", "writeFiles", "deleteFiles"]`).
     - Decouple repository passwords: The offsite B2 repository is encrypted with a distinct 256-bit passphrase stored in SOPS, preventing local credential compromises from exposing the offsite archive.
  4. *Enforce Unidirectional Outbound WAN Transit:*
     - Proxmox VE initiates outbound HTTPS uploads directly to Backblaze B2 over WAN. Cloud automation (OCI Kestra) does not possess network routes or SSH credentials into Proxmox, maintaining ADR-013 zero-trust microsegmentation.
- **Architecture Impact:**
  - Mitigates the risk in ADR-002: A total physical failure of the Proxmox host or HDD pool does not result in permanent datastore loss.
  - Control plane Recovery Point Objective (RPO) is bounded to $\le 24$ hours; Recovery Time Objective (RTO) for a cold rebuild from snapshot is $\le 30$ minutes per DR Scenario 03.
  - Codifies 4 independent root Terraform modules in Project Aether (`01-oci-compute`, `02-gcp-dmz`, `03-homelab`, `04-backblaze-b2`).
- **Alternatives Considered:**
  - *Cloudflare R2:* Evaluated. While offering free egress, R2 does not natively offer a 10 GB free tier without credit card entry, and lacks the fine-grained bucket lifecycle rules available in B2.
  - *AWS S3 Standard-IA / Glacier:* Rejected. Egress transfer fees and API request charges incur continuous monthly billing, violating the $0.00 / ₹0.00 budget principle.
  - *Raw Bucket Mirror (`rclone sync` or S3 replication):* Rejected. A dumb mirror blindly replicates accidental deletions, malicious `restic forget` purges, or local repository corruptions directly to the cloud. `restic copy` performs cryptographic, object-level deduplication across independent repository trees.
  - *Inbound Push Orchestration via OCI Kestra:* Rejected. Exposing Proxmox SSH or opening Tailscale ingress routes from `tag:oci` violates ADR-013 microsegmentation and expands the homelab blast radius to cloud compromises.
- **Consequences:**
  - *Positive:*
    - Strict 3-2-1 compliance achieved across SSD, ZFS HDD, and Backblaze B2.
    - Zero cloud cost incurred ($0.00/month).
    - Immutable repository decoupling prevents cloud backup destruction from compromised local nodes.
    - Zero-Trust boundary preserved with outbound-only WAN replication.
  - *Negative:*
    - Requires maintaining two separate Restic password files (`/etc/restic/etcd-password.txt` and `/etc/restic/b2-etcd-password.txt`).
    - Staggered timers (02:00, 02:30, 03:00, 03:30 UTC) require sequential scheduling discipline.
  - *Risks:*
    - If snapshot size grows beyond the 10 GB free tier in future years, billing or pruning adjustments will be required (mitigated by B2 lifecycle rules and 14-day local retention).
- **Security Considerations:**
  - Backblaze B2 bucket enforces Server-Side Encryption (`SSE-B2` / AES-256).
  - All Restic repository blobs are double-encrypted (client-side 256-bit AES-GCM/Poly1305 + B2 server-side).
  - Credentials stored in SOPS Age/KMS encrypted files (`infrastructure/ansible/group_vars/proxmox/vault.yaml`).
- **Reliability Considerations:**
  - In-node frozen snapshots prevent SQLite/etcd database lock contention during backup capture.
  - Proxmox systemd timers (`k3s-etcd-sync.timer`, `k3s-etcd-restic.timer`, `k3s-etcd-b2.timer`) use `Persistent=true` to automatically catch up if the host is powered off during the nightly 02:00–03:30 window.
- **Validation / Fitness Functions:**
  - Verified 2026-11-02: Initial replication copied 4 snapshot trees (63.072 MiB) to `aether-restic-etcd-offsite`; `restic check` verified remote index and blob integrity with 0 errors.
  - Quarterly cold-restore simulation drill scheduled under Task 3.20 (DR-05 / Scenario 03).
- **Dependencies:** K3s embedded etcd, Proxmox VE ZFS subsystem, Restic (v0.16+), Backblaze B2 S3 API, SOPS.
- **Related ADRs:** ADR-002 (Storage Topology), ADR-003 (Kubernetes Distribution), ADR-007 (Secrets Management), ADR-011 (Terraform Remote Backend), ADR-013 (Tailnet Microsegmentation), ADR-014 (Environment Isolation Strategy), ADR-016 (Kubernetes Storage Strategy).
- **Review Conditions:** Review if backup size approaches 8 GB (80% of B2 free tier) or when Bare-Metal multi-node HA is introduced.

## Addendum (2026-11-05): stages 2 and 3 moved onto the HDD

Until 5 Nov, `/mnt/aether-pool/` was a plain directory on the Proxmox root filesystem (the SSD that also holds every VM disk), while the ZFS pool was mounted at `/aether-pool` and held almost nothing. Stages 2 and 3 were on the same disk as the data they protect, so the "2 media" leg of 3-2-1 was not met ([INC-2026-007](../incidents/INC-2026-007-dr-copies-on-wrong-disk.md)).

- Each stage now has its own dataset, `aether-pool/k3s-etcd-snapshots` and `aether-pool/restic-k3s-etcd`, mounted at the original paths, with `compression=lz4`, `atime=off` and `copies=2`.
- `aether-pool` is a **single-disk** vdev, not a mirror. `copies=2` lets ZFS repair bad sectors on that disk; it does not survive losing the disk. B2 covers that.
- The three DR playbooks and their scripts refuse to run unless each path is its `aether-pool` dataset, so a failed mount can't fall back to the SSD silently.
- The 3-2-1 media are now: SSD (live etcd on the control VM), HDD (snapshot mirror and local restic repo), and Backblaze B2.
- New fitness function: `findmnt -n -o SOURCE --target /mnt/aether-pool/restic-k3s-etcd` → `aether-pool/restic-k3s-etcd`.

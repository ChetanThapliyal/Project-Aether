# Disaster Recovery Strategy & Failure Drills

These are my disaster recovery runbooks for Project Aether: what I expect to recover in how long, where every piece of state lives, how I get in when the tailnet is down, and how I drill each failure.

Every `task` command below runs from the repository root. `tf:*` tasks always need `DIR=<root module>`, for example `task tf:plan DIR=01-oci-compute`.

---

## 1. Recovery Objectives (RTO & RPO)

| Component | My Target RTO | My Target RPO | Backup Mechanism |
|---|---|---|---|
| **Homelab K3s cluster** | 30 min in place (DR-05 measured about 18 min); total hardware loss is rebuild time plus about 3 min of restore (HARD-11) | ≤ 24 h | 4-stage etcd pipeline (ADR-018), all IST: K3s snapshot 02:00 → Proxmox pull 02:30 → local restic 03:00 → Backblaze B2 03:30 (age-encrypted object in a 30-day Object Lock bucket, plus a transitional `restic copy`) |
| **OCI applications & databases** | 45 min (instance loss); none if the OCI tenancy is lost (see §5) | ≤ 24 h | Restic to the OCI Object Storage bucket `dr-backups`, 03:00 UTC (08:30 IST), scheduled by the Kestra flow `aether.ops.restic-nightly` |
| **GCP DMZ observer** | 15 min for the VM; monitors need a manual rebuild | Uptime Kuma data is **not** backed up | Terraform + Ansible + compose files in Git |
| **Secrets access** | 15 min | 0 | SOPS with two recipients: Age + GCP Cloud KMS (both proven working, 3 Nov) |
| **Terraform state** | 10 min | 0 | GCS bucket `tf-backend-oci-hlab-gcs` with object versioning |

---

## 2. Critical Asset & State Inventory

| Asset | Primary Location | Backup / Replica | How I Decrypt / Access It |
|---|---|---|---|
| Terraform state | `gs://tf-backend-oci-hlab-gcs/` (prefixes `oci`, `gcp-dmz`, `homelab`, `backblaze-b2`) | GCS object versions | `gcloud auth application-default login` |
| Repository secrets | Git: `*.sops.yaml`, `terraform.sops.tfvars`, `group_vars/proxmox/vault.yaml` | Git history, GitHub, local clones | Age key `~/.config/sops/age/keys.txt` or GCP KMS `sops-key` |
| SOPS Age private key | My workstation | GCP KMS (decrypts everything without it); a copy in the cluster secret `argocd/argocd-sops-age-key`; **offline copy: not documented yet** | — |
| K3s etcd snapshots | `k3s-control-01:/var/lib/rancher/k3s/server/db/snapshots/` (14 kept) | Proxmox `/mnt/aether-pool/k3s-etcd-snapshots` → restic `/mnt/aether-pool/restic-k3s-etcd` → B2 `aether-etcd-offsite-lock` (age, locked 30 days) and `aether-restic-etcd-offsite` (transitional) | Locked bucket: read-only restore key in `group_vars/proxmox/vault.yaml`, age identity `dr_offsite_age_identity` in `ansible-secrets.sops.yaml`. Local repo: `/etc/restic/etcd-password.txt` on Proxmox (**randomly generated, not in SOPS**). B2 repo: `restic_b2_password` + B2 key in `group_vars/proxmox/vault.yaml` |
| K3s server token | `/var/lib/rancher/k3s/server/token` on the control VM | **None yet.** HARD-10 escrows it in SOPS as `k3s_server_token` | Without it I can't restore a snapshot onto a new VM |
| Kubernetes persistent volumes | `local-path` on each node's SSD | **None** | — |
| OCI app volumes & databases | `/home/ubuntu/` on `bookorbit` | Restic repo `s3:<oci endpoint>/dr-backups` (same OCI tenancy) | `/opt/backup/restic.env`, rendered from `oci_backup_*` keys in `ansible-secrets.sops.yaml` |
| OCI database dumps | Written nightly before the restic run: `blinko/db.sql`, `bookorbit/db.sql`, `affine/db.sql`, `kestra/db.sql`, `anytype/mongo.archive` | Inside the restic snapshot | — |
| OCI data **not** backed up | `calibre-library/`, `navidrome/` (excluded on purpose); `kestra/postgres/` (raw data dir, covered by the dump) | — | — |
| OCI boot volume | OCI block storage | One manual boot-volume backup, `bookorbit-pre-upgrade` (Terraform output `bookorbit_backup_id`) | OCI console |
| Kestra flows | Git `automation/kestra/flows/` | Synced by `system/git-sync-flows.yml` | — |
| DMZ Uptime Kuma data | `aether-gcp-dmz:/opt/dmz/uptime-kuma/` | **None** | — |
| Tailscale policy | `infrastructure/secrets/tailscale-policy.sops.yaml` | Git | SOPS; pasted into the admin console by hand |
| Cloudflare tunnel token | `/opt/dmz/.env` on the DMZ (`CLOUDFLARE_TUNNEL_TOKEN`) | Cloudflare dashboard | — |

---

## 3. Break-Glass Access Matrix

My normal path to every host is the tailnet (`ssh homelab`, `ssh k3s-control-01`, `ssh bookorbit`, `ssh owl@aether-gcp-dmz`). When the tailnet is down I use these instead:

| Target | Break-Glass Route | What I Need |
|---|---|---|
| **Proxmox host** | `ssh root@192.168.1.200` (web UI `https://192.168.1.200:8006`) | To be on the home LAN; `~/.ssh/homelab` |
| **K3s nodes** | `ssh owl@192.168.1.51` / `.52` / `.53` | To be on the home LAN; `~/.ssh/homelab` |
| **OCI `bookorbit`** | `ssh -i ~/.ssh/oci_bookorbit ubuntu@<public IPv4>` (`terraform -chdir=infrastructure/terraform/01-oci-compute output -raw bookorbit_public_ip`) | Port 22 open in the OCI security list. If I close it (FND-04 option A), I first re-add the rule in the OCI console |
| **GCP `aether-gcp-dmz`** | `gcloud compute ssh aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap` | **Doesn't work until FND-12 adds the IAP firewall rule** (`35.235.240.0/20` on port 22). Until then I have no break-glass into the DMZ, and I rebuild it instead (Scenario 05) |

---

## 4. Scenarios & Drills

Each runbook has symptoms, the restore steps, checks to run afterwards, and a drill I can run safely. Severity uses the same scale as [my incidents](../incidents/README.md) (SEV1–SEV3).

| Scenario | Severity | Last drilled |
|---|---|---|
| [01: Tailscale control plane & DERP outage](scenarios/01-tailscale-outage.md) | SEV3 | Not recorded |
| [02: OCI instance loss & restic restore](scenarios/02-oci-loss-restic.md) | SEV1 | Single-volume restore: not recorded |
| [03: Homelab hardware failure & K3s etcd recovery](scenarios/03-homelab-hardware.md) | SEV1 | In-place reset (DR-05): about 18 min. Cold restore from B2 (HARD-11): 10 Nov 2026, reset to ready API 54 s |
| [04: Age key loss & GCP KMS recovery](scenarios/04-age-key-loss.md) | SEV2 | Dual-recipient check passed 3 Nov |
| [05: GCP DMZ rebuild](scenarios/05-gcp-dmz-rebuild.md) | SEV2 | Not recorded |

Related:
- [ArgoCD recovery runbook](../runbooks/argocd-recovery.md)
- [Tailscale auth key rotation](../runbooks/tailscale-auth-key-rotation.md)
- [Incidents](../incidents/README.md). INC-2026-001 explains why the OCI backup heartbeat is the last step of the backup script.

---

## 5. Known Gaps

These are the gaps I know about and have accepted for now:

- **The OCI backups aren't offsite.** The `dr-backups` bucket is in the same OCI tenancy as the instance. If I lose the tenancy, I lose the backups too. A second-provider copy is deferred to the Phase 04 DR review.
- **Nothing backs up the Kubernetes PVs** (`local-path`).
- **Nothing backs up DMZ Uptime Kuma.** If I lose it, I rebuild every monitor by hand and change the OCI backup push URL. FND-17 fixes this.
- **No playbook installs Tailscale on the OCI host.** A rebuild joins it by hand (Scenario 02 §3.3). FND-18 fixes this.
- **No runbooks yet** for: losing the GCP project (Terraform state, KMS and DMZ all live there), losing the OCI tenancy, losing my workstation (toolchain and keys), or losing the GitHub repository.

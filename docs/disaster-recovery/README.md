# Disaster Recovery Strategy & Failure Drills

These are my disaster recovery runbooks for Project Aether: what I expect to recover in how long, where every piece of state lives, how I get in when the tailnet is down, and how I drill each failure.

Every `task` command below runs from the repository root. `tf:*` tasks always need `DIR=<root module>`, for example `task tf:plan DIR=01-oci-compute`.

---

## 1. Recovery Objectives (RTO & RPO)

The public status page shows a short form of this table from [`objectives.yml`](objectives.yml), with what each drill proved and each component's newest backup read live. Change both together.

| Component | My Target RTO | My Target RPO | Backup Mechanism |
|---|---|---|---|
| **Homelab K3s cluster** | 30 min in place (the in-place reset drill measured about 18 min); total hardware loss is rebuild time plus about 3 min of restore (measured in the cold-restore drill) | ≤ 24 h | 4-stage etcd pipeline (ADR-018), all IST: K3s snapshot 02:00 → Proxmox pull 02:30 → local restic 03:00 → Backblaze B2 03:30 (age-encrypted object in a 30-day Object Lock bucket, plus a transitional `restic copy`) |
| **OCI applications & databases** | 45 min (instance loss); tenancy loss not timed ([Scenario 06](scenarios/06-account-and-workstation-loss.md)) | ≤ 24 h | Restic to the OCI Object Storage bucket `dr-backups`, 03:00 UTC (08:30 IST), scheduled by the Kestra flow `aether.ops.restic-nightly`; then the newest snapshot without metrics and logs, age-encrypted, to its own Object Lock bucket on B2, `aether-oci-offsite-lock` (3-day lock, about four nights kept) |
| **GCP DMZ observer** | 30 min, Kuma restore included (was 15; the 19 Nov rebuild showed the first deploy alone takes 16) | ≤ 24 h (nightly Kuma backup) | Terraform + Ansible + compose files in Git; Kuma data in GCS |
| **Secrets access** | 15 min | 0 | SOPS with two recipients: Age + GCP Cloud KMS (both proven working, 3 Nov) |
| **Terraform state** | 10 min | 0 | GCS bucket `tf-backend-oci-hlab-gcs` with object versioning |

---

## 2. Critical Asset & State Inventory

| Asset | Primary Location | Backup / Replica | How I Decrypt / Access It |
|---|---|---|---|
| Terraform state | `gs://tf-backend-oci-hlab-gcs/` (prefixes `oci`, `gcp-dmz`, `homelab`, `backblaze-b2`; `gcp` belongs to the separate foundation repository, GCS-CP, below) | GCS object versions (5 kept) + 7-day soft delete; public access prevention enforced | `gcloud auth application-default login` |
| **Control-plane foundation (GCS-CP)**: the state bucket, the SOPS KMS key `sops-key`, CI's drift identity (WIF) | Separate repo `GCS-CP` (local clone + GitHub). `gcp/` state in the bucket under prefix `gcp`; the **bootstrap root's state (the bucket itself) is a local file on my workstation only** | `prevent_destroy` on the bucket, key ring and key; KMS 30-day scheduled destruction, 90-day rotation (old versions still decrypt) | **Recovery prerequisite** for every other scenario: without the KMS key only the Age recipient remains (Scenario 04); without the bucket there's no Terraform state. Lost bootstrap state → `terraform import` the existing bucket |
| Repository secrets | Git: `*.sops.yaml`, `terraform.sops.tfvars`, `group_vars/proxmox/vault.yaml` | Git history, GitHub, local clones | Age key `~/.config/sops/age/keys.txt` or GCP KMS `sops-key` |
| SOPS Age private key | My workstation | GCP KMS (decrypts everything without it); a copy in the cluster secret `argocd/argocd-sops-age-key`; an offline copy in the password manager ([SOPS key rotation](../runbooks/sops-key-rotation.md) replaces it on every rotation) | — |
| K3s etcd snapshots | `k3s-control-01:/var/lib/rancher/k3s/server/db/snapshots/` (14 kept) | Proxmox `/mnt/aether-pool/k3s-etcd-snapshots` → restic `/mnt/aether-pool/restic-k3s-etcd` → B2 `aether-etcd-offsite-lock` (age, locked 30 days) and `aether-restic-etcd-offsite` (transitional) | Locked bucket: read-only restore key in `group_vars/proxmox/vault.yaml`, age identity `dr_offsite_age_identity` in `ansible-secrets.sops.yaml`. Local repo: `/etc/restic/etcd-password.txt` on Proxmox (**randomly generated, not in SOPS**). B2 repo: `restic_b2_password` + B2 key in `group_vars/proxmox/vault.yaml` |
| K3s server token | `/var/lib/rancher/k3s/server/token` on the control VM | Escrowed in SOPS as `k3s_server_token` (since 10 Nov); fresh installs are seeded from it | Without it I can't restore a snapshot onto a new VM |
| Kubernetes persistent volumes | PostgreSQL and CouchDB on `local-path` (worker-01); app files on `nfs-zfs` (the hypervisor's ZFS pool) | Nightly database dumps and CouchDB export onto `nfs-zfs` (it has its own heartbeat), hourly and daily ZFS snapshots, then the dataset age-encrypted to the Object Lock bucket under `apps/` (also with a heartbeat; ADR-022) | Same restore key and age identity as the etcd copies; `task dr:drill:k8s` |
| OCI app volumes & databases | `/home/ubuntu/` on `bookorbit` | Restic repo `s3:<oci endpoint>/dr-backups` (same OCI tenancy); since 20 Nov 2026 the newest snapshot each night, without Prometheus and Loki data, as `oci/<date>.tar.zst.age` in B2 `aether-oci-offsite-lock` (locked 3 days, about four nights kept; with its own heartbeat) | Restic: `/opt/backup/restic.env`, rendered from `oci_backup_*` keys in `ansible-secrets.sops.yaml`. B2 copy: `b2_oci_offsite_restore_key*` and `dr_offsite_age_identity`, both in `ansible-secrets.sops.yaml` ([Scenario 02 §3.5b](scenarios/02-oci-loss-restic.md)) |
| OCI database dumps | Written nightly before the restic run: `bookorbit/db.sql`, `kestra/db.sql`, `anytype/mongo.archive` (Blinko's and AFFiNE's last dumps of 17 Nov stay until the old copies are removed) | Inside the restic snapshot, so in the B2 copy too | — |
| OCI data **not** backed up | `calibre-library/`, `navidrome/` (excluded on purpose); `kestra/postgres/` (raw data dir, covered by the dump) | — | — |
| OCI boot volume | OCI block storage | One manual boot-volume backup, `bookorbit-pre-upgrade` (Terraform output `bookorbit_backup_id`) | OCI console |
| Kestra flows | Git `automation/kestra/flows/` | Synced by `system/git-sync-flows.yml` | — |
| DMZ Uptime Kuma data | `aether-gcp-dmz:/opt/dmz/uptime-kuma/` | Nightly at 01:30 UTC to `gs://gcs-oci-homelab-controlplane-dmz-backups/kuma/`, kept 30 days. The VM can create objects there but not read, overwrite or delete them. Heartbeat: OCI Kuma "DMZ Kuma Backup" | [Scenario 05 §3.5](scenarios/05-gcp-dmz-rebuild.md) |
| Tailscale policy | `infrastructure/secrets/tailscale-policy.sops.yaml` | Git | SOPS; pasted into the admin console by hand |
| Cloudflare tunnel token | `/opt/dmz/.env` on the DMZ (`CLOUDFLARE_TUNNEL_TOKEN`) | Cloudflare dashboard | — |

---

## 3. Break-Glass Access Matrix

My normal path to every host is the tailnet (`ssh homelab`, `ssh k3s-control-01`, `ssh bookorbit`, `ssh owl@aether-gcp-dmz`). When the tailnet is down I use these instead:

| Target | Break-Glass Route | What I Need |
|---|---|---|
| **Proxmox host** | `ssh root@192.168.1.200` (web UI `https://192.168.1.200:8006`) | To be on the home LAN; `~/.ssh/homelab` |
| **K3s nodes** | `ssh owl@192.168.1.51` / `.52` / `.53` | To be on the home LAN; `~/.ssh/homelab` |
| **OCI `bookorbit`** | `ssh -i ~/.ssh/oci_bookorbit ubuntu@<public IPv4>` (`terraform -chdir=infrastructure/terraform/01-oci-compute output -raw bookorbit_public_ip`) | Public port 22 is closed. First set `TF_VAR_bootstrap_ssh_cidr="<my IPv4>/32"` and run `task tf:apply DIR=01-oci-compute`, which adds the rule; clear it and apply again afterwards ([Scenario 01 §3.2](scenarios/01-tailscale-outage.md)) |
| **GCP `aether-gcp-dmz`** | `gcloud compute ssh owl@aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap --ssh-key-file ~/.ssh/homelab` | Works since 14 Nov: a firewall rule admits Google's IAP range (`35.235.240.0/20`) on port 22, gated by my Google IAM identity. Keep `owl@` and `--ssh-key-file`: this instance blocks project SSH keys, so a bare `gcloud compute ssh` writes a new key into the *instance* metadata, which Terraform would then remove and the nightly drift check would flag |

---

## 4. Scenarios & Drills

Each runbook has symptoms, the restore steps, checks to run afterwards, and a drill I can run safely. Severity uses the same scale as [my incidents](../incidents/README.md) (SEV1–SEV3).

| Scenario | Severity | Last drilled |
|---|---|---|
| [01: Tailscale control plane & DERP outage](scenarios/01-tailscale-outage.md) | SEV3 | Not recorded |
| [02: OCI instance loss & restic restore](scenarios/02-oci-loss-restic.md) | SEV1 | Single-app restore, 15 Nov 2026: 972 MiB restored in 11 s, the dump loaded into a throwaway database in 4 s, 176 tables and 39,599 rows matched live (`task dr:drill:oci`). Full instance rebuild: not timed yet |
| [03: Homelab hardware failure & K3s etcd recovery](scenarios/03-homelab-hardware.md) | SEV1 | In-place reset drill: about 18 min. Cold restore from B2: 10 Nov 2026, reset to ready API 54 s |
| [04: Age key loss & GCP KMS recovery](scenarios/04-age-key-loss.md) | SEV2 | Dual-recipient check passed 3 Nov |
| [05: GCP DMZ rebuild](scenarios/05-gcp-dmz-rebuild.md) | SEV2 | Full rebuild, 19 Nov 2026: 48 min 25 s from deleting the VM to every monitor green, against the then 15 min target (now 30). The first deploy on a fresh e2-micro takes 16 min (image pulls), and three breaks cost the rest: the join key couldn't tag the VM, a deploy step crashed before the restore, heartbeats were pinned to the old mesh IP ([INC-2026-016](../incidents/INC-2026-016-edge-rebuild-drill-found-three-breaks.md)) |
| [06: Losing an account or the workstation](scenarios/06-account-and-workstation-loss.md) | SEV1–SEV2 | Not drilled; section 5 lists the safe checks |

Related:
- [ArgoCD recovery runbook](../runbooks/argocd-recovery.md)
- [Tailscale auth key rotation](../runbooks/tailscale-auth-key-rotation.md)
- [Incidents](../incidents/README.md). INC-2026-001 explains why the OCI backup heartbeat is the last step of the backup script.

---

## 5. Known Gaps

These are the gaps I know about and have accepted for now:

- **A rebuilt OCI host needs a fresh Tailscale auth key.** The base playbook installs and joins Tailscale, but the key is one-time and expires after 90 days, so I create a new one for each rebuild (Scenario 02 §3.3).
- **GCS-CP's bootstrap state lives only on my workstation.** It describes one resource (the state bucket), so losing it means re-importing the bucket, not losing data.
- **Losing a whole account or the workstation is written down but not drilled** ([Scenario 06](scenarios/06-account-and-workstation-loss.md)). The GCP project holds the Terraform state and the edge Kuma's backups with nothing outside it, so its loss means importing every resource back into new state and starting monitor history from zero.
- **Restores from B2 depend on the account's daily download cap** (Backblaze Caps & Alerts). Set to $0.10/day (about 11 GB) on 20 Nov after a check download hit the free 1 GB (INC-2026-018); raise it further before a full restore of everything.
- **`calibre-library/` and `navidrome/` on the cloud host have no backup** (excluded on purpose: re-importable, and too large for nightly full copies).

# DR Scenario 06: Losing an Account or the Workstation

**Severity:** SEV1 for the GCP project or the OCI tenancy; SEV2 for the workstation or the GitHub repository
**Target RTO:** not set. None of these has been drilled; the steps below are worked out from the configuration, not timed
**Target RPO:** ≤ 24 h for app data (the nightly offsite copies); 0 for anything in Git

> **Scope:** the four losses no other scenario covers: a whole GCP project, a whole OCI tenancy, my workstation, or the GitHub repository. Losing a single machine is Scenarios 02 (cloud host), 03 (homelab) and 05 (edge VM); losing the age key alone is Scenario 04. Written 20 Nov 2026 (Phase 05 task 5.62).

What makes these survivable is that every one of the four places can be rebuilt from the other three plus two things kept outside all of them: **the SOPS age key** (workstation, cluster secret and password manager) and **the offsite bucket on Backblaze B2** (a fifth provider, Object-Locked for 30 days).

---

## 1. The GCP project

Everything Google-side is one project, `gcs-oci-homelab-controlplane`:

| Lives there | Survives elsewhere? |
|---|---|
| Terraform state for every root (`gs://tf-backend-oci-hlab-gcs/`) | **No.** The resources it describes keep running; only the record of them is gone |
| The SOPS KMS key `sops-key` | Yes, in effect: every encrypted file also has the age recipient |
| The edge VM: status page, Uptime Kuma, the Cloudflare tunnel | Config in Git; the tunnel token in SOPS |
| Kuma's nightly backups (`…-dmz-backups`) | **No.** Monitor history is lost; the monitors are re-provisioned from Git |
| CI's keyless identity (Workload Identity Federation) | Defined in the `GCS-CP` repo |

**Symptoms:** `terraform plan` fails with 403 or "bucket does not exist"; the status page and the edge Kuma are gone; the nightly drift workflow fails to authenticate; `sops -d` prints a KMS error before falling back to age.

**Recovery:**
1. **Secrets first.** Decrypt with age only: `SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d <file>` works without KMS ([Scenario 04](04-age-key-loss.md) in reverse).
2. **New project and state bucket** with the `GCS-CP` repo: `bootstrap/` creates the bucket, `gcp/` the KMS key ring and CI's identity pool. Set the new project ID in each root's tfvars and in `.sops.yaml`.
3. **Re-encrypt for the new KMS key:** update the `gcp_kms` lines in `.sops.yaml`, then `sops updatekeys -y` on every encrypted file (the 5.40 pre-commit check verifies the recipients).
4. **Rebuild the state, root by root.** The OCI instance, the Proxmox VMs and the B2 buckets still exist, so **import** them rather than create them: `terraform import` each resource `terraform plan` wants to add, until plan shows no changes. Never apply a plan that recreates the B2 buckets (`prevent_destroy` stops it) or the Proxmox VMs.
5. **The edge VM:** [Scenario 05](05-gcp-dmz-rebuild.md) in the new project. Skip its Kuma restore step: the backups went with the project. `task ansible:dmz` re-creates every monitor, push monitor and the status page from Git; monitor history and uptime percentages start again from zero.
6. **CI:** update the WIF provider and service account names in `.github/workflows/terraform-drift.yml` from the `GCS-CP` outputs, and run the drift workflow once by hand.

**Not lost:** the cluster, the cloud host, all app data, and all secrets.

---

## 2. The OCI tenancy

| Lives there | Survives elsewhere? |
|---|---|
| The cloud host (`bookorbit`): BookOrbit, Navidrome, NextExplorer, n8n, Kestra, Anytype, openGym, the monitoring core | Config in Git and SOPS |
| Its restic repository (`dr-backups`) | Yes since 5.61: each night's snapshot, age-encrypted, in the B2 bucket under `oci/` |
| `calibre-library/` and `navidrome/` (excluded from backups on purpose) | **No.** Re-import from the original sources |
| Prometheus, Loki and Grafana data | In the offsite copy (as files in the snapshot), so history survives up to the last copy |

**Symptoms:** the OCI console login fails or shows the tenancy closed; every cloud-host monitor and the "OCI Nightly Restic Backup" heartbeat go down; the cluster keeps running, but its metrics, logs and alerts stop (the monitoring core was on that host).

**Recovery:**
1. **A new tenancy** (or another provider's ARM or x86 VM: the stacks are Docker Compose). Create API credentials and update `infrastructure/terraform/01-oci-compute` (tenancy, compartment, region in its tfvars) and a new Object Storage bucket for restic (`oci_backup_*` keys in `ansible-secrets.sops.yaml`).
2. **The instance:** [Scenario 02](02-oci-loss-restic.md) steps 3.2–3.4: Terraform, tailnet join, base system.
3. **The data:** Scenario 02's "If the whole tenancy is gone" section: fetch the newest `oci/` object from B2 with the read-only restore key, decrypt it with the DR age identity, and unpack it in place of the restic restore. Then Scenario 02 steps 3.6–3.8.
4. **Point the cluster at the new host:** Prometheus scrapes and Alloy pushes use the cloud host's tailnet name, so if the new machine takes the same name (`bookorbit`) nothing changes; otherwise update `prometheus.yml`, the Alloy config and the tailnet policy.
5. **Start backups again** with `task ansible:oci:ops`: the first run initialises the new restic repository, and the offsite copy resumes the same night.

---

## 3. My workstation

| Lives only there | Copy elsewhere |
|---|---|
| The SOPS age key (`~/.config/sops/age/keys.txt`) | Password manager; the cluster secret `argocd/argocd-sops-age-key`; GCP KMS decrypts every file too |
| SSH private keys `~/.ssh/homelab` and `~/.ssh/oci_bookorbit` | **Unknown: check the password manager has both.** Without them, see step 4 |
| `GCS-CP`'s bootstrap Terraform state (the state bucket only) | None needed: `terraform import` the bucket |
| Repository clones | GitHub |
| Logins: `gcloud`, `gh`, Tailscale, Cloudflare, OCI | Re-authenticate; no secrets live in them |

**Recovery:**
1. Install the toolchain: clone the repo, then `mise install` (Terraform, SOPS, age, Helm, kubectl, Task, restic at the pinned versions), plus Ansible and pre-commit from pip.
2. Restore the age key from the password manager to `~/.config/sops/age/keys.txt` (mode 600). Check: `sops -d infrastructure/secrets/ansible-secrets.sops.yaml >/dev/null`.
3. Sign in: `gcloud auth login` and `gcloud auth application-default login`, `gh auth login`, Tailscale (the device needs approval and its tag in the admin console).
4. **SSH keys.** From the password manager if they are there. If not, make a new pair and get its public key onto each machine: the edge VM through Terraform (`ssh_public_key` in its tfvars, then apply; IAP gets you in meanwhile); the homelab through the Proxmox web console as root; the cloud host through the OCI console's serial console. Then update the three `ssh_public_key` variables so a rebuild uses the new key.
5. `kubectl`: copy the kubeconfig from the control VM (`task ansible:kubeconfig`).

---

## 4. The GitHub repository

The cluster pulls everything from this repository: 21 ArgoCD Applications point at it, the drift workflow runs in it, and CI's GCP identity accepts only this exact repository name on `main`.

**Symptoms:** ArgoCD shows `ComparisonError` / repository not found on every app, but **running workloads keep running**: ArgoCD just stops reconciling. Renovate and the drift workflow stop.

**Recovery:**
1. **Push a local clone** (the workstation has one; so does anywhere the repo was cloned) to a new repository: `git push --mirror <new URL>`. History, tags and every encrypted secret come with it.
2. **If the name or owner changes:** replace `repoURL` in every Application (`grep -rl 'github.com/ChetanThapliyal/Project-Aether' kubernetes`), apply the root app by hand once, and let ArgoCD pick up the rest. Update `github_repository` in `GCS-CP/gcp` and apply (the WIF condition matches the name exactly). Update the GitHub webhook to ArgoCD (secret `argocd_github_webhook_secret` in SOPS) and the README links.
3. **Re-enable** branch protection, Renovate (install the app on the new repo) and the drift workflow's schedule.

**Not lost:** anything running, and nothing in Git as long as one clone exists. **The risk is a stale clone:** pull before relying on it.

---

## 5. Drill

None of the four has been drilled, and three can't be without real risk. What can be checked safely, quarterly:
- **Workstation:** on a spare machine or a throwaway VM, follow section 3 steps 1–3 and decrypt one file. Proves the password manager copy of the age key works.
- **GitHub:** `git clone --mirror` the repo to a scratch directory and `git fsck`; confirms a full copy exists.
- **OCI tenancy:** download and decrypt last night's `oci/` object (Scenario 02, "If the whole tenancy is gone", steps 1–3) and list it: proves the offsite copy is complete without touching the live host.

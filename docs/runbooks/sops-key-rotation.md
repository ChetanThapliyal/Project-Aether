# SOPS key rotation

> **Scope:** Replacing the age key or acting on the Cloud KMS key that encrypt every secret in this repository, without breaking ArgoCD on the way, and what to change when a key may have leaked.
> **Status:** Operational runbook (Phase 05 task 5.40), written 19 Nov 2026 against SOPS 3.13 and KSOPS 4.3.
> **Related:** [DR Scenario 04: Age Key Loss](../disaster-recovery/scenarios/04-age-key-loss.md) (the key is gone, not exposed) · [ADR-007](../adr/007-secrets-management.md) · [Tailscale key rotation](tailscale-auth-key-rotation.md) · [ArgoCD recovery](argocd-recovery.md)

## 1. The keys and where they live

Every encrypted file has two recipients, and either one alone can decrypt it. `scripts/check-sops-recipients.py` (a pre-commit hook, so CI runs it too) fails when any file lacks one of them or still has one that `.sops.yaml` no longer names.

| Key | Public part | Private part, and every copy of it |
| --- | --- | --- |
| **age** | The `age1…` recipient, repeated in all four rules of `.sops.yaml` | The workstation (`~/.config/sops/age/keys.txt`); the password manager; the cluster Secret `argocd/argocd-sops-age-key`, which KSOPS uses to decrypt during syncs; and so also every etcd snapshot (on the hypervisor, in its restic repository and in B2) |
| **Cloud KMS** `sops-key` | Its resource name, in the same four rules | Never leaves Google. Who can use it is IAM: the owner account, and the drift detector's CI identity (`cryptoKeyDecrypter`, keyless, `main` only). Defined in the separate GCS-CP repository (`gcp/main.tf`) |

**Encrypted files:** 16 on 19 Nov 2026: the app and platform Secrets under `kubernetes/`, `infrastructure/secrets/` (Ansible variables and the tailnet policy), `group_vars/proxmox/vault.yaml` and the four `terraform.sops.tfvars`. List them with:

```bash
git ls-files | grep -E '\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$' | grep -v '^\.sops\.yaml$'
```

**This repository is public.** Every encrypted file in every old commit can be read by anyone who holds a key it was encrypted for. Re-encrypting today's files doesn't change old commits. So if a key may have leaked, **changing the secret values themselves is the fix**, and re-keying the files only stops new leaks (section 4).

## 2. Which case are you in?

| Situation | Do |
| --- | --- |
| The age key file is gone and nobody else has it | [DR Scenario 04](../disaster-recovery/scenarios/04-age-key-loss.md). No rotation needed |
| Routine replacement, or a copy went somewhere it shouldn't but probably wasn't read (an unencrypted backup, a shared screen) | Section 3 |
| The age key was, or may have been, read by someone else | Section 3, then section 4 |
| The KMS key's automatic rotation | Nothing to do (section 5) |
| Someone may have been able to use the KMS key (a leaked Google credential, a CI identity misused) | Section 5, then section 4 |

## 3. Replace the age key without breaking ArgoCD

The order matters. KSOPS in the cluster can only decrypt with the key in its Secret. If the files are re-keyed first, every sync of an app with a secret fails until the cluster has the new key. So the cluster gets **both** keys first: an age key file can hold several identities, and SOPS tries each one.

**1. Make the new key, next to the old one.**

```bash
K=~/.config/sops/age/keys.txt
OLD=$(age-keygen -y "$K")
age-keygen -o ~/.config/sops/age/new.txt
NEW=$(age-keygen -y ~/.config/sops/age/new.txt); echo "$NEW"
cp "$K" ~/.config/sops/age/old.txt                  # until step 6
cat ~/.config/sops/age/new.txt >> "$K"              # keys.txt now holds old and new
chmod 600 ~/.config/sops/age/*.txt
```

**2. Give the cluster both keys.**

```bash
task k8s:sops-secret
kubectl -n argocd rollout restart deployment argocd-repo-server
kubectl -n argocd rollout status deployment argocd-repo-server
```

Nothing changes yet: every file still opens with the old key.

**3. Point `.sops.yaml` at the new key and re-key every file.**

```bash
sed -i "s/$OLD/$NEW/g" .sops.yaml
grep -c "$NEW" .sops.yaml                           # 4
git ls-files | grep -E '\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$' | grep -v '^\.sops\.yaml$' \
  | xargs -n1 sops updatekeys -y
scripts/check-sops-recipients.py                    # every file: the new age key and KMS, nothing else
```

`updatekeys` re-wraps each file's data key for the new recipient list. The values and the data key stay the same, so the diff is only in the `sops:` blocks.

If the old key may have been read (section 2), also give every file a new data key. Otherwise the old key can still unwrap a data key it saw before, in an old commit, and that data key still opens the new file:

```bash
git ls-files | grep -E '\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$' | grep -v '^\.sops\.yaml$' \
  | xargs -n1 sops rotate -i
```

**4. Commit and push.** The pre-commit hooks run the recipients check again. ArgoCD then syncs the re-keyed Secrets, still able to decrypt them because it holds both keys.

**5. Check that it all still opens.**

- The dual-recipient check in [DR Scenario 04 §4](../disaster-recovery/scenarios/04-age-key-loss.md#4-post-recovery-verification): KMS-only and age-only both decrypt. Run it with `SOPS_AGE_KEY_FILE=~/.config/sops/age/new.txt`, so the old key can't be what made it pass.
- `kubectl -n argocd get applications`: all `Synced` and `Healthy`. `kubectl -n argocd logs deploy/argocd-repo-server -c ksops-plugin --since=15m | grep -i error` is empty.
- `task tf:plan DIR=<each root>` decrypts (the four roots under `infrastructure/terraform/`), and an Ansible run in check mode reads the variables, for example `task ansible:dmz -- --check`.

**6. Retire the old key.**

```bash
cp ~/.config/sops/age/new.txt ~/.config/sops/age/keys.txt && chmod 600 ~/.config/sops/age/keys.txt
task k8s:sops-secret
kubectl -n argocd rollout restart deployment argocd-repo-server
```

Hard-refresh one app with a secret in ArgoCD to prove it decrypts with the new key alone. Then replace the password manager copy with the new key, and delete `old.txt` and `new.txt`.

Copies of the old key remain in older etcd snapshots and their backups until those expire (14 local snapshots, a 30-day lock in B2). If the key leaked, that doesn't matter once section 4 is done: they decrypt only values that no longer work.

## 4. A key leaked: change the secrets themselves

Do this when a key may have been read. Whoever has the old key can read every value in every commit, so each value below has to change where it is issued, and then in its encrypted file (`sops <file>`), followed by a deploy. Work from the top: the first group works from anywhere on the internet; the rest needs a way into the tailnet or the hosts first.

| Priority | Secret (key names in the files) | Change it at | Then |
| --- | --- | --- | --- |
| 1 | OCI API signing key (`private_key`, `fingerprint` in `01-oci-compute`) | OCI console: add a new API key, delete the old one | `tf:plan` for `01-oci-compute` |
| 1 | Backblaze B2 keys (`b2_application_key*`, `b2_offsite_upload_key*`, `b2_offsite_restore_key*`) | B2: create new application keys with the same scopes, delete the old ones | The Proxmox backup playbooks; `tf:plan` for `04-backblaze-b2` |
| 1 | Cloudflare tokens (`cloudflare-api-token`, `gcp_dmz_cloudflare_tunnel_token`, `cloudflare_analytics_token`) | Cloudflare: roll each token; for the tunnel, rotate its token | cert-manager syncs from Git; `task ansible:dmz` |
| 1 | GitHub (`gh_pat_kestra`, `argocd_github_webhook_secret`) | GitHub: regenerate the PAT; new webhook secret in the repository's webhook settings | `task ansible:oci:apps` (Kestra's flow sync); `task k8s:bootstrap-argocd`, which puts the webhook secret into ArgoCD |
| 1 | Telegram bot token | BotFather: revoke and issue a new token | The OCI monitoring playbook (Alertmanager) and `task ansible:dmz` (the DMZ's Kuma alerts) |
| 1 | OCI Object Storage keys (`oci_backup_s3_*`, `oci_anytype_s3_*`) | OCI console: new customer secret keys, delete the old ones | `task ansible:oci:apps` and the backup config |
| 1 | Tailscale (`tailscale_auth_key`, `oci_host_tailscale_auth_key`, `oci_tsdproxy_*`, `operator-oauth`, the DMZ's `tailscale_auth_key`) | [Tailscale key rotation](tailscale-auth-key-rotation.md): revoke the keys and OAuth clients, create new ones with the same tags | Running nodes stay joined; only the stored keys change |
| 2 | Proxmox API token (`proxmox_api_token_*` in `03-homelab`) | Proxmox: Datacenter → API Tokens, new token with the same role, remove the old | `tf:plan` for `03-homelab` |
| 2 | K3s join token (`k3s_server_token`) | `k3s token rotate` on control-01 | Re-escrow it; `task ansible:control` checks it |
| 2 | restic repository passwords (`restic_b2_password`, `oci_backup_restic_password`) | `restic key add`, then `restic key remove` the old key ID, per repository. The data stays as it is | The backup jobs' variables |
| 2 | Offsite backup age key (`dr_offsite_age_identity` and its recipient) | `age-keygen`: a new pair for new backups | Keep the old identity offline until the last backup encrypted to it passes its 30-day lock; restores of those still need it |
| 2 | Cluster databases (`postgres-admin`, `app-db-passwords`, `redis`, `db-metrics`) | `ALTER ROLE … PASSWORD` in PostgreSQL; Redis takes its password from the Secret on restart | Update the app Secrets that embed them too (`DATABASE_URL`, `PAPERLESS_DBPASS`, `PAPERLESS_REDIS`) in the same commit |
| 2 | App signing keys (`NEXTAUTH_SECRET`, `PAPERLESS_SECRET_KEY`, `COUCHDB_SECRET`, `AFFINE_PRIVATE_KEY`) | New random values | Everyone is signed out. Check AFFiNE's release notes before changing its private key |
| 2 | Admin and app passwords on the OCI host (Uptime Kuma, Grafana, Kestra, CouchDB, BookOrbit, the Anytype Garage RPC secret) | Each app's admin UI or config | `task ansible:oci:apps` |
| 2 | Kestra's login (`oci_kestra_auth_password`) | **Not just SOPS**: Kestra keeps its basic-auth credentials in its own database and uses the config value only to create the first account. Changing SOPS and redeploying leaves the old password working and breaks Kestra's own API calls from flows (Git sync). Change it with `POST /api/v1/main/basicAuth` (body `username`, `password`, `currentPassword`) from the host, against the container's address (Kestra publishes no host port) | Then `task ansible:oci:apps -- --tags kestra`; check the old password gets 401, the new one 200 and `git-sync-flows` succeeds. Rotated 24 Nov 2026 |
| 3 | Kuma push URLs and tokens (`kuma_push_*`, `oci_backup_kuma_push_url`) | Uptime Kuma: regenerate each push monitor's token | The heartbeat senders' variables. Low value: a stolen token can only fake a heartbeat |
| 3 | The tailnet policy, the smoke-test token | Nothing to rotate; the policy is not a secret | |

Leave the old commits alone. Rewriting public history doesn't recall copies already cloned, and it breaks every commit hash quoted in the docs.

## 5. The Cloud KMS key

**Automatic rotation needs nothing from you.** The key makes a new primary version every 90 days (the first on 31 Dec 2026). New encryptions use the newest version. Files keep working with the version that encrypted them, because old versions stay enabled. `sops updatekeys` doesn't move a file to the new version; `sops rotate -i` does.

**Never disable or destroy an old version** unless every file has been through `sops rotate -i` since it stopped being primary. A file still wrapped by a disabled version opens only with age, and ArgoCD doesn't care, but the dual-recipient guarantee is gone without any error.

**If someone may have used the key** (a leaked owner credential, the CI identity misused):

1. Remove the access: revoke the credential, or remove the IAM binding in GCS-CP (`gcp/iam_ci.tf`) and apply there.
2. Look at what was decrypted, if anything was recorded. KMS decrypt calls appear in Cloud Audit Logs only when Data Access logs are on for Cloud KMS, which they are not by default. Without them, assume everything was read.
3. Rotate the key by hand to a new primary version (`gcloud kms keys versions create --key sops-key --keyring sops --location global --primary`), run `sops rotate -i` on every file, commit, and run `scripts/check-sops-recipients.py` and the dual-recipient check.
4. Disable the old versions (`gcloud kms keys versions disable <n> …`). Destroy them later if you want old commits closed to KMS too; age still opens them.
5. Section 4: whoever could decrypt has read the values.

## 6. Checks to keep

| When | What |
| --- | --- |
| Every commit (pre-commit and CI) | `scripts/check-sops-recipients.py`: both recipients on every file, no old ones; `check-sops-encryption.sh`: no plaintext `*.sops.yaml` |
| Every quarter | The dual-recipient check, [DR Scenario 04 §5](../disaster-recovery/scenarios/04-age-key-loss.md#5-simulation-drill) |
| After any rotation | Section 3 step 5 in full |

The recipients check found its first problem on the day it was written. `kubernetes/platform/tailscale/secret/operator-oauth.sops.yaml` had been encrypted for age only since 28 Oct, so KMS couldn't open it. It was re-keyed with `sops updatekeys` (the value is unchanged).

# DR Scenario 04: Age Key Loss & GCP Cloud KMS Recovery

**Severity:** SEV2 (my automation is blocked; running services are fine)
**Target RTO:** < 15 minutes
**Target RPO:** 0 (no secrets lost)

---

## 1. Trigger & Symptoms

* **Trigger:** My workstation is wiped or reinstalled, or `~/.config/sops/age/keys.txt` is deleted.
* **Symptoms:** `task tf:plan DIR=…`, Ansible playbooks or `sops -d` fail with:
  ```
  Failed to decrypt file: Error decrypting with age: no matching key found
  ```
  (They only fail if KMS is also unavailable. With working gcloud ADC, SOPS falls back to KMS silently.)

---

## 2. Blast Radius

| Component | Status | Impact |
|---|---|---|
| **Live workloads** | Up | Running services and in-cluster Secrets are untouched |
| **ArgoCD / KSOPS** | Up | The cluster has its own copy of the key (`argocd/argocd-sops-age-key`) |
| **My automation** | Blocked without KMS | Terraform and Ansible can't decrypt |
| **Secrets** | Intact | Every file has two recipients, Age and GCP KMS `sops-key` |

---

## 3. Recovery

First I decide which case I'm in:

* **Lost key** (deleted, disk wiped): Step 3.1, then optionally 3.2. No rotation is needed.
* **Stolen or exposed key**: Steps 3.1 → 3.3 → 3.4 → 3.5. I generate a new key and rotate the secrets themselves.

### Step 3.1: Decrypt Through GCP KMS

```bash
gcloud auth application-default login
gcloud config set project gcs-oci-homelab-controlplane
sops -d infrastructure/secrets/ansible-secrets.sops.yaml > /dev/null && echo "KMS decryption OK"
```

This is enough to unblock Terraform and Ansible straight away.

### Step 3.2: Get the Same Key Back from the Cluster (lost key only)

The cluster holds the private key that ArgoCD/KSOPS uses:

```bash
mkdir -p ~/.config/sops/age
kubectl -n argocd get secret argocd-sops-age-key -o jsonpath='{.data.keys\.txt}' | base64 -d > ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
age-keygen -y ~/.config/sops/age/keys.txt    # must match the age1… recipient in .sops.yaml
```

If the public key matches, I'm done; I skip to §4. (If the cluster is down too, see Scenario 03. The key comes back with the etcd restore.)

### Step 3.3: Generate a New Age Keypair

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt && chmod 600 ~/.config/sops/age/keys.txt
NEW=$(age-keygen -y ~/.config/sops/age/keys.txt); echo "$NEW"
```

### Step 3.4: Replace the Recipient in Every Rule and Re-encrypt Every File

`.sops.yaml` has **four** creation rules, all with the same `age:` recipient. I replace it in all of them:

```bash
OLD=$(grep -m1 -oE 'age1[0-9a-z]+' .sops.yaml)
sed -i "s/$OLD/$NEW/g" .sops.yaml
grep -c "$NEW" .sops.yaml    # → 4
```

Then I update the keys on every encrypted file Git tracks. That covers `infrastructure/secrets/`, `group_vars/proxmox/vault.yaml`, every `terraform.sops.tfvars` and the Kubernetes `*.sops.yaml` files:

```bash
git ls-files | grep -E '\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$' \
  | xargs -n1 sops updatekeys -y
```

If the old key was **stolen**, I also rotate each file's data key, and then change the actual secret values (API keys, passwords, the Tailscale auth key, the B2 key) at their providers:

```bash
git ls-files | grep -E '\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$' \
  | xargs -n1 sops rotate -i
```

### Step 3.5: Give the Cluster the New Key

KSOPS still has the old key, so after Step 3.4 ArgoCD can't decrypt anything:

```bash
task k8s:sops-secret
kubectl -n argocd rollout restart deployment argocd-repo-server
```

---

## 4. Post-Recovery Verification

1. **Both recipients work** (the dual-recipient check from FND-16):
   ```bash
   F=kubernetes/platform/smoke-test/secret.sops.yaml; E=$(mktemp -d)
   env -u SOPS_AGE_KEY -u SOPS_AGE_KEY_FILE XDG_CONFIG_HOME=$E HOME=$E \
     CLOUDSDK_CONFIG=$HOME/.config/gcloud GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json \
     sops -d $F >/dev/null && echo "KMS-only OK"
   env CLOUDSDK_CONFIG=$E GOOGLE_APPLICATION_CREDENTIALS=$E/none.json SOPS_AGE_KEY_FILE=$HOME/.config/sops/age/keys.txt \
     sops -d $F >/dev/null && echo "Age-only OK"
   rmdir $E
   ```
2. `task tf:plan DIR=01-oci-compute` shows no changes.
3. ArgoCD: `kubectl get applications -n argocd`. Everything is Synced and Healthy, with no KSOPS decrypt errors in the repo-server logs.
4. Commit (only after Steps 3.3–3.5):
   ```bash
   git add .sops.yaml $(git ls-files -m | grep -E '\.sops\.|vault\.yaml')
   git commit -m "security(sops): rotate workstation age key via gcp kms recovery"
   ```
5. I put an offline copy of the new private key in my password manager.

---

## 5. Simulation Drill

Run the dual-recipient check in §4 step 1 every quarter. It proves that either recipient alone can decrypt, without moving the key file. I record the date in the [DR README](../README.md#4-scenarios--drills).

# ArgoCD disaster recovery and state backup runbook

> **Scope:** Standard operating procedure for recovering the GitOps control plane (ArgoCD, KSOPS decryption, and the App-of-Apps pipeline) after partial or total loss on the homelab K3s cluster.
> **Status:** Operational runbook (GITOPS-09)
> **Related:** [DR Scenario 03: Homelab Hardware Failure](../disaster-recovery/scenarios/03-homelab-hardware.md) · [DR Scenario 04: Age Key Loss](../disaster-recovery/scenarios/04-age-key-loss.md) · [Tailscale Auth Key Rotation](tailscale-auth-key-rotation.md)
> **References:** [ADR-009](../adr/009-gitops-controller.md) · [ADR-007](../adr/007-secrets-management.md) · [Disaster Recovery Overview](../disaster-recovery/README.md)

## 1. Recovery philosophy

Project Aether treats cluster state as declarative. Kubernetes applications, namespaces, and the delivery engine itself are defined in Git (`kubernetes/`), making the ArgoCD control plane disposable. Disaster recovery replays the bootstrap pipeline:

```text
Git (source of truth)  →  task k8s:bootstrap-argocd  →  root-apps Application  →  full platform convergence
```

| State | Storage location | Recovery mechanism |
| --- | --- | --- |
| Application definitions, sync waves | Git (`kubernetes/cluster/`, `kubernetes/platform/`, `kubernetes/apps/`) | Automatic (ArgoCD self-reconciles) |
| ArgoCD deployment and tuning | Git (`kubernetes/bootstrap/argocd/values.yaml`, `cmp-ksops-config.yaml`) | `helm upgrade --install` (pinned chart) |
| SOPS Age private key | Operator workstation `~/.config/sops/age/keys.txt` (+ GCP Cloud KMS backup) | Secret re-injection |
| K3s cluster state | etcd on `k3s-control-01` | Snapshot restore (DR Scenario 03) |

The Age private key and the etcd datastore are the only state not stored in Git. Everything else converges directly from Git history.

### Recovery objectives

| Recovery level | Trigger | Target RTO | Target RPO |
| --- | --- | --- | --- |
| Level 1: ArgoCD lost, cluster healthy | Namespace or Helm release deleted, OOM crash loop, datastore intact | < 5 min | 0 (Git HEAD) |
| Level 2: Full cluster loss, VMs intact | etcd corruption, node failure requiring reprovision | < 30 min | 0 to 24 h (etcd snapshot) |
| Level 3: Full VM loss | Proxmox pool destroyed | < 60 min | 0 (Git HEAD) |

## 2. Prerequisites

Verify these prerequisites before starting recovery or running a drill. Each item includes a fallback:

| # | Requirement | Verify | Fallback if missing |
| --- | --- | --- | --- |
| 1 | Workstation with `kubectl`, `helm`, `sops`, `task`, and Ansible access to homelab | `kubectl get nodes` | If Tailscale fails, use LAN access: `ssh owl@192.168.1.51` |
| 2 | SOPS Age private key present | `ls ~/.config/sops/age/keys.txt` or `$SOPS_AGE_KEY_FILE` | [DR Scenario 04](../disaster-recovery/scenarios/04-age-key-loss.md) (GCP Cloud KMS restore). Without this key, secrets cannot decrypt and recovery stops at Step 2 |
| 3 | Fresh kubeconfig (`~/.kube/config`) from control plane | `task ansible:kubeconfig` | Re-run after any cluster rebuild |
| 4 | Network access to repository and chart repository | `git ls-remote` / `helm repo update argo` | Use mirrored local clone |
| 5 | Proxmox reachable (Levels 2 and 3) | `ssh owl@192.168.1.200`, VM IDs 101, 102, 103 running | [DR Scenario 03 Branch A](../disaster-recovery/scenarios/03-homelab-hardware.md) |

> [!CAUTION]
> The Age private key cannot be recovered from Git. If `~/.config/sops/age/keys.txt` is missing and Cloud KMS is unreachable, encrypted manifests in Git cannot be decrypted. Verify prerequisite 2 before discarding remaining cluster state (`kubectl get secret -n argocd argocd-sops-age-key` in a broken cluster may still hold a copy).

## 3. Level 1 recovery: ArgoCD lost, cluster intact

Use this procedure when `kubectl get nodes` reports all nodes `Ready` but the `argocd` namespace is missing, empty, or crashing.

### Step 1: Inject the SOPS Age key secret

```bash
task k8s:sops-secret
```

Equivalent raw commands (see `Taskfile.yaml`):

```bash
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic argocd-sops-age-key \
  --namespace argocd \
  --from-file=keys.txt=${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt} \
  --dry-run=client -o yaml | kubectl apply -f -
```

Verify:

```bash
kubectl get secret -n argocd argocd-sops-age-key
# NAME                  TYPE     DATA   AGE
# argocd-sops-age-key   Opaque   1      <1m
```

> [!IMPORTANT]
> The secret is mounted by the `ksops-plugin` sidecar running as non-root `runAsUser: 999`. It must be created before the repo-server pod starts, or decryption fails with `Error getting data key: 0 successful groups required, got 0`. The task `task k8s:bootstrap-argocd` declares this as a dependency.

### Step 2: Bootstrap ArgoCD with the pinned Helm chart

```bash
task k8s:bootstrap-argocd
```

This applies the KSOPS plugin ConfigMap (`kubernetes/bootstrap/argocd/cmp-ksops-config.yaml`), then installs `argo-cd` chart v7.8.26 (pinned per ADR-IaC-05) using the memory-tuned `values.yaml`. It pins workloads to `k3s-worker-02` with HA, Dex, Notifications, and ApplicationSet disabled, giving a steady-state footprint of ~189 MiB against the 1 GB ADR-009 ceiling.

> [!NOTE]
> In chart v7, disabling the ApplicationSet controller requires a different configuration key than older versions, so the controller may still run using ~20 MiB. This is an accepted deviation; do not attempt to tune it during an active recovery.

Verify all pods. The critical indicator is `argocd-repo-server` showing `2/2` Ready (sidecar active):

```bash
kubectl get pods -n argocd -o wide
# argocd-application-controller-0   1/1   Running   k3s-worker-02
# argocd-applicationset-*           1/1   Running   k3s-worker-02
# argocd-redis-*                    1/1   Running   k3s-worker-02
# argocd-repo-server-*              2/2   Running   k3s-worker-02   ← 2/2 = sidecar active
# argocd-server-*                   1/1   Running   k3s-worker-02
```

### Step 3: Retrieve initial admin credentials

```bash
task argocd:password
```

Verify the API server responds over port-forward (port-forward uses HTTP because `server.insecure: true`):

```bash
task argocd:port-forward        # or: kubectl port-forward svc/argocd-server -n argocd 8090:80
curl -I http://localhost:8090   # expect HTTP 200 OK
```

Access path: `task argocd:port-forward` is the Phase 2 interim per ADR-004/ADR-013. Tailscale Operator exposure lands in Phase 3. Do not expose ArgoCD via NodePort or raw LAN.

> [!NOTE]
> The initial admin password changes on every reinstall. Rotate it to a vaulted credential after recovery and before closing the incident.

### Step 4: Re-apply the App-of-Apps root application

```bash
kubectl apply -f kubernetes/cluster/root-application.yaml
# application.argoproj.io/root-apps created
```

`root-apps` reads `kubernetes/cluster/` from `github.com/ChetanThapliyal/Project-Aether.git` at `targetRevision: HEAD` with `automated.prune: true` and `automated.selfHeal: true`. Every child application (platform namespaces wave -3, smoke-test canary, and platform services) reconciles automatically without manually applying individual manifests.

### Step 5: Verify convergence

```bash
kubectl get applications -n argocd
# NAME                  SYNC STATUS   HEALTH STATUS
# platform-namespaces   Synced        Healthy
# root-apps             Synced        Healthy
# smoke-test            Synced        Healthy

kubectl get namespaces platform apps   # created via App-of-Apps, not manually
```

Canary check to confirm end-to-end secret decryption:

```bash
kubectl get secret -n platform gitops-smoke-secret -o jsonpath="{.data.token}" | base64 -d
# Expected: smoke-test-token-12345
```

Success criteria: all applications show `Synced` and `Healthy`, the Age key is readable, and `gitops-smoke-secret` decrypts successfully. Escalate to Level 2 if the underlying cluster is damaged.

## 4. Level 2 recovery: etcd restore and ArgoCD replay

If the K3s embedded etcd is corrupt or a node failed with datastore damage, follow [DR Scenario 03 (Branch B)](../disaster-recovery/scenarios/03-homelab-hardware.md) to restore the latest snapshot:

```bash
ssh owl@192.168.1.51 "sudo systemctl stop k3s"
ssh owl@192.168.1.51 "sudo k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<latest-snapshot>"
ssh owl@192.168.1.51 "sudo systemctl start k3s"
ssh owl@192.168.1.52 "sudo systemctl restart k3s-agent"
ssh owl@192.168.1.53 "sudo systemctl restart k3s-agent"
```

Once `kubectl get nodes` shows all three nodes as `Ready`, refresh your kubeconfig (`task ansible:kubeconfig`) and execute Steps 1 through 5 of Level 1 recovery in full. A clean replay is idempotent whether the restored snapshot predates ArgoCD, rolls back the Helm release, or contains an unhealthy release state.

> [!NOTE]
> An etcd snapshot restore recovers whatever ArgoCD state existed at snapshot time. If that state is stale or corrupt, wipe the `argocd` namespace (`helm uninstall argocd -n argocd || kubectl delete ns argocd`) before Step 2 to avoid release ownership conflicts during the reinstall.

## 5. Level 3 recovery: Full VM loss

1. Re-provision VMs (IDs 101 to 103, Cloud-Init template 9000) using Terraform:

   ```bash
   cd infrastructure/terraform/03-homelab && task tf:init && task tf:apply
   ```

2. Bootstrap the cluster (common → control → workers → kubeconfig):

   ```bash
   task ansible:bootstrap
   ```

3. Execute Steps 1 through 5 of Level 1 recovery. The entire procedure takes ~60 minutes, including OS provisioning and Ansible execution.

> [!NOTE]
> You do not need to apply namespace manifests manually. `root-apps` and its child applications recreate `platform` and `apps` using the `CreateNamespace=true` sync option.

## 6. State backup: K3s etcd snapshot schedule

The etcd datastore is the only state not reproducible from Git, so verify snapshots are actively created before relying on Level 2 recovery. Check the plan documented in [Disaster Recovery Overview](../disaster-recovery/README.md) (RTO 30 min / RPO 0 to 24 h) against the host's active snapshot schedule:

### Verification (weekly or during drills)

```bash
ssh owl@192.168.1.51 "sudo k3s etcd-snapshot list"
# Expect at least one snapshot younger than 24 hours
ssh owl@192.168.1.51 "sudo ls -lh /var/lib/rancher/k3s/server/db/snapshots/"
```

- By default, K3s takes embedded datastore snapshots every 12 hours and retains 5 on the control plane node. Restarting the control plane also produces a snapshot.
- K3s stores snapshots locally on `k3s-control-01` (`/var/lib/rancher/k3s/server/db/snapshots/`) on the Proxmox ZFS pool (`aether-pool`). Because local snapshots share hardware with the control plane VM, copying snapshots off-node is recommended hardening.
- Take an on-demand snapshot before risky maintenance:

  ```bash
  ssh owl@192.168.1.51 "sudo k3s etcd-snapshot save --name pre-change-$(date +%Y%m%d-%H%M)"
  ```
- Restore procedure and executable drill: [DR Scenario 03, §5](../disaster-recovery/scenarios/03-homelab-hardware.md).

### Proposed hardening

Nightly clock-time snapshots with off-node retention, configured through Ansible:

```yaml
# infrastructure/ansible/roles/k3s common config suggestion
etcd-snapshot-schedule-cron: "0 2 * * *"   # once daily, off-peak (cfg under "0 */12 * * *" default)
etcd-snapshot-retention: 14
```

Off-node copy to the Proxmox host (recommended follow-up task; update this runbook when implemented):

```bash
# cron on k3s-control-01
rsync -az /var/lib/rancher/k3s/server/db/snapshots/ owl@192.168.1.200:/mnt/aether-pool/k3s-etcd-snapshots/
```

## 7. Troubleshooting: Known failure signatures

Collected from the original Phase 02 bootstrap (GITOPS-02 through 07). Match the symptom before improvising:

| Symptom | Root cause | Fix |
| --- | --- | --- |
| `0 successful groups required, got 0` in `argocd-repo-server` logs | `argocd-sops-age-key` secret missing, wrong key, or wrong in-pod path | Run `task k8s:sops-secret`. Confirm `$SOPS_AGE_KEY_FILE` environment variable in the sidecar points to `/home/argocd/.config/sops/age/keys.txt`. |
| `Permission denied` on `keys.txt`, same `0 successful groups` error | Secret mounted with `defaultMode: 0400`, sidecar runs as UID 999 | Mount the secret with `defaultMode: 0444` in `values.yaml` (Bug F). Do not revert to 0400. |
| `read-only file system` errors from `kustomize` or `sops` in sidecar | Missing /tmp writability behind `readOnlyRootFilesystem: true` | Mount `cmp-tmp` `emptyDir` at `/tmp` on the sidecar (Bug B). |
| CMP never fires; `smoke-test` shows empty or failed manifest render | `plugin.name` set on the Application or ConfigMap `discover` glob broken | Remove `plugin.name`. CMP v2 auto-discovers via `**/ksops-*.yaml` (Bug A). Verify `plugin.yaml` is copied into the plugin config volume. |
| Kustomize validation fails on *.sops.yaml before decryption | Repo-root `.sops.yaml` missing `encrypted_regex: '^(data|stringData)$'` | Set `encrypted_regex: '^(data|stringData)$'` (Bug C). Encrypt only payload keys, not `apiVersion`, `kind`, or `metadata`. |
| `root-apps` exists but platform manifests never sync | `kubernetes/cluster/platform.yaml` child Application missing | Verify `kubernetes/cluster/platform.yaml` exists so the App-of-Apps tree syncs child manifests (Bug D). |
| `helm upgrade` fails with release-state conflicts on Level 2 restore | Stale Helm release metadata inside restored etcd | Run `helm uninstall argocd -n argocd` (or delete the namespace) before Step 2. |
| Application schema error: `spec.source.recurse` invalid | Wrong CRD field placement | Use `spec.source.directory.recurse: true` in `kubernetes/cluster/root-application.yaml`. |
| Legacy chart field errors on install | Deprecated `server.config`, `server.extraArgs`, or `server.insecure` flag placement | Set `configs.params.server.insecure: true` for chart v5.5+ (Bug E). |
| `kubectl` refuses connection to `192.168.1.51:6443` | Node down or kubeconfig stale after rebuild | Check node health via [DR Scenario 03](../disaster-recovery/scenarios/03-homelab-hardware.md), then run `task ansible:kubeconfig`. |

Debug commands:

```bash
kubectl logs -n argocd deploy/argocd-repo-server -c ksops-plugin --tail=50
kubectl logs -n argocd deploy/argocd-repo-server --tail=50 | grep -iE 'sops|decrypt|error'
kubectl describe application -n argocd smoke-test     # events near the error
kubectl exec -n argocd deploy/argocd-repo-server -c ksops-plugin -- ls -l /home/argocd/.config/sops/age/
# expected: keys.txt with -r--r--r-- (0444)
```

## 8. Routine backup and drill schedule

| Cadence | Operator action | Command |
| --- | --- | --- |
| Weekly | Verify etcd snapshot freshness | `sudo k3s etcd-snapshot list` on `k3s-control-01` |
| Weekly | Verify Age key is present and Cloud KMS is accessible | `sops --decrypt infrastructure/secrets/ansible-secrets.sops.yaml > /dev/null` |
| Before any Helm or manual change | Take pre-change etcd snapshot | `k3s etcd-snapshot save --name pre-change-$(date +%Y%m%d-%H%M)` |
| Quarterly | Full Level 1 recovery drill on the smoke-test app | Delete secret: `kubectl -n platform delete secret gitops-smoke-secret`. Confirm ArgoCD recreates it decrypted, or run `kubectl patch application -n argocd smoke-test --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'` |
| Quarterly | Proxmox ZFS pool and etcd snapshot restore drill | [DR Scenario 03 §5](../disaster-recovery/scenarios/03-homelab-hardware.md) |
| Yearly | Rotate ArgoCD admin password; rerun recovery drill from clean kubeconfig | `task argocd:password` |

## 9. Recovery success checklist

- [ ] All 3 nodes show `Ready` (`kubectl get nodes`)
- [ ] `task k8s:sops-secret` succeeded with secret `argocd-sops-age-key` present
- [ ] All ArgoCD pods are `Running`, with `argocd-repo-server` showing `2/2` (sidecar active)
- [ ] `root-apps`, `platform-namespaces`, and `smoke-test` all report `Synced` and `Healthy`
- [ ] `gitops-smoke-secret` decrypts in-cluster
- [ ] `argocd-repo-server` steady-state memory is within ~189 MiB, well below the 1 GB ADR-009 ceiling
- [ ] Fresh admin password vaulted; `argocd-initial-admin-secret` deleted: `kubectl delete secret -n argocd argocd-initial-admin-secret`
- [ ] Etcd snapshot verified; incident notes recorded

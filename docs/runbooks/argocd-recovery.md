# ArgoCD disaster recovery and state backup runbook

> **Scope:** Standard operating procedure for recovering the GitOps control plane (ArgoCD, KSOPS decryption, and the App-of-Apps pipeline) after partial or total loss on the homelab K3s cluster.
> **Status:** Operational runbook. Refreshed 16 Nov 2026 for ArgoCD v3.5.7 on chart 10.11.7, the delivered DR pipeline and Tailscale access.
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
| 1 | Workstation with the pinned toolchain (`mise install` reads `mise.toml`: Terraform, SOPS, age, Helm, kubectl, Task, restic) and Ansible access to the homelab | `kubectl get nodes` | SSH uses the inventory key. If Tailscale fails, use the LAN: `ssh -i ~/.ssh/homelab owl@192.168.1.51` |
| 2 | SOPS Age private key present | `ls ~/.config/sops/age/keys.txt` or `$SOPS_AGE_KEY_FILE` | [DR Scenario 04](../disaster-recovery/scenarios/04-age-key-loss.md) (GCP Cloud KMS restore). Without this key, secrets cannot decrypt and recovery stops at Step 2 |
| 3 | Fresh kubeconfig (`~/.kube/config`) from control plane | `task ansible:kubeconfig` | Re-run after any cluster rebuild |
| 4 | Network access to repository and chart repository | `git ls-remote` / `helm repo update argo` | Use mirrored local clone |
| 5 | Proxmox reachable (Levels 2 and 3) | `ssh -i ~/.ssh/homelab root@192.168.1.200 'qm list'`: VM IDs 101, 102, 103 running | [DR Scenario 03 Branch A](../disaster-recovery/scenarios/03-homelab-hardware.md) |
| 6 | ArgoCD UI | `https://argocd.tail7067ab.ts.net` from an operator device (Tailscale operator ingress) | `task argocd:port-forward`, then `http://localhost:8090`. The Tailscale address only exists after `tailscale-secret` → `tailscale-operator` → `tailscale-apps` have synced |

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

This applies the KSOPS plugin ConfigMap (`kubernetes/bootstrap/argocd/cmp-ksops-config.yaml`), then installs the `argo-cd` chart at the version pinned in the Taskfile (`ARGOCD_CHART_VERSION`, 10.11.7 = ArgoCD v3.5.7) with the memory-tuned `values.yaml`, `--wait` and `--rollback-on-failure`. It pins every component to `k3s-worker-02`, with HA, Dex and notifications disabled. Steady state is about 660 MiB for all ArgoCD pods (measured 15 Nov 2026 with 17 apps), under the 1 GB ADR-009 ceiling.

> [!NOTE]
> The chart has no working `applicationSet.enabled` switch, so `values.yaml` sets `applicationSet.replicas: 0` (Bug G). No ApplicationSet pod is expected.

Verify all pods. The critical indicator is `argocd-repo-server` showing `2/2` Ready (sidecar active):

```bash
kubectl get pods -n argocd -o wide
# argocd-application-controller-0   1/1   Running   k3s-worker-02
# argocd-redis-*                    1/1   Running   k3s-worker-02
# argocd-repo-server-*              2/2   Running   k3s-worker-02   ← 2/2 = sidecar active
# argocd-server-*                   1/1   Running   k3s-worker-02
```

Then confirm the live release matches Git (values and chart version):

```bash
task argocd:drift      # ok: argo-cd-10.11.7 rev N matches Git
```

### Step 3: Admin credentials

```bash
task argocd:password
```

After a fresh install this prints the generated password. Otherwise it says the secret was deleted: the admin password lives in the password manager entry "ArgoCD admin".

Verify the API server responds over port-forward (port-forward uses HTTP because `server.insecure: true`):

```bash
task argocd:port-forward        # or: kubectl port-forward svc/argocd-server -n argocd 8090:80
curl -I http://localhost:8090   # expect HTTP 200 OK
```

Normal access is `https://argocd.tail7067ab.ts.net` over Tailscale, which works once the Tailscale apps have synced (waves −1 → 0 → 1). Until then, and whenever the operator is down, use the port-forward. Never expose ArgoCD through a NodePort or the raw LAN (ADR-004, ADR-013).

> [!NOTE]
> A reinstall generates a new initial password. Change it to the password-manager value (or store the new one there), then delete `argocd-initial-admin-secret` before closing the incident.

### Step 4: Re-apply the App-of-Apps root application

```bash
kubectl apply -f kubernetes/cluster/root-application.yaml
# application.argoproj.io/root-apps created
```

`root-apps` reads `kubernetes/cluster/` from `github.com/ChetanThapliyal/Project-Aether.git` at `targetRevision: main` with `automated.prune: true` and `automated.selfHeal: true`. Every child application (platform namespaces wave -3, smoke-test canary, and platform services) reconciles automatically without manually applying individual manifests.

### Step 5: Verify convergence

```bash
kubectl get applications -n argocd                            # 17 apps on 16 Nov 2026
kubectl get applications -n argocd --no-headers | grep -vE 'Synced +Healthy'   # must print nothing

kubectl get namespaces platform apps   # created via App-of-Apps, not manually
```

Canary check to confirm end-to-end secret decryption:

```bash
kubectl get secret -n platform gitops-smoke-secret -o jsonpath="{.data.token}" | base64 -d
# Expected: smoke-test-token-12345
```

Success criteria: every application shows `Synced` and `Healthy`, the Age key is readable, and `gitops-smoke-secret` decrypts. **`Unknown` is a failure, not a pass:** it means ArgoCD can't compare the app at all (see §7, INC-2026-005). Escalate to Level 2 if the underlying cluster is damaged.

## 4. Level 2 recovery: etcd restore and ArgoCD replay

If the K3s embedded etcd is corrupt or a node failed with datastore damage, follow [DR Scenario 03, Branch B](../disaster-recovery/scenarios/03-homelab-hardware.md). Take the snapshot from the best copy that survived, in this order (details in Scenario 03, "Where the Snapshots Are"):

1. `k3s-control-01:/var/lib/rancher/k3s/server/db/snapshots/` (nightly 02:00 IST, 14 kept)
2. Proxmox `/mnt/aether-pool/k3s-etcd-snapshots/` (ZFS dataset on the HDD, pulled 02:30 IST)
3. Proxmox restic repository `/mnt/aether-pool/restic-k3s-etcd` (03:00 IST)
4. Backblaze B2, including the Object-Locked bucket (03:30 IST): [Branch D](../disaster-recovery/scenarios/03-homelab-hardware.md)

```bash
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo k3s etcd-snapshot list"     # pick the newest good one
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo systemctl stop k3s"
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo k3s server --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<snapshot>"
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo systemctl start k3s"
ssh -i ~/.ssh/homelab owl@192.168.1.52 "sudo systemctl restart k3s-agent"
ssh -i ~/.ssh/homelab owl@192.168.1.53 "sudo systemctl restart k3s-agent"
```

Restoring onto a **new** control-plane VM needs the original K3s server token. It's escrowed in SOPS as `k3s_server_token`, and `task ansible:control` seeds new installs from it. The restore path is drilled: an isolated cold restore from B2 on 10 Nov 2026 reached a ready API 54 s after the reset (Scenario 03 §5).

Once `kubectl get nodes` shows all three nodes as `Ready`, refresh your kubeconfig (`task ansible:kubeconfig`) and execute Steps 1 through 5 of Level 1 recovery in full. A clean replay is idempotent whether the restored snapshot predates ArgoCD, rolls back the Helm release, or contains an unhealthy release state.

> [!NOTE]
> An etcd snapshot restore recovers whatever ArgoCD state existed at snapshot time. If that state is stale or corrupt, wipe the `argocd` namespace (`helm uninstall argocd -n argocd || kubectl delete ns argocd`) before Step 2 to avoid release ownership conflicts during the reinstall.

## 5. Level 3 recovery: Full VM loss

First choose the branch in [DR Scenario 03](../disaster-recovery/scenarios/03-homelab-hardware.md):

* **Branch C, VMs lost, Proxmox intact:** rebuild the VMs, then either restore cluster state from the Proxmox copy, or start a fresh cluster and let GitOps rebuild it.
* **Branch D, total hardware loss:** rebuild the host and VMs, then restore from Backblaze B2.

**Decision rule:** restore when the cluster holds state that Git doesn't (out-of-band secrets, Tailscale operator proxy identities, PV data). Today almost nothing lives only in etcd: the Age key Secret is re-injected anyway, Tailscale proxies and the internal root CA regenerate, and there are no PVs, so a fresh cluster rebuilt by GitOps is acceptable. Once Phase 04 adds stateful apps, restore. Everything in Git comes back either way.

1. Re-provision the VMs (IDs 101 to 103, cloned from Cloud-Init template 9000):

   ```bash
   task tf:init  DIR=03-homelab
   task tf:apply DIR=03-homelab
   ```

2. Bootstrap the cluster (common → control → workers → kubeconfig):

   ```bash
   task ansible:bootstrap
   ```

3. If restoring, follow the branch's restore steps now. Then run Steps 1 through 5 of Level 1. The whole procedure takes about 60 minutes, including OS provisioning and Ansible.

> [!NOTE]
> You do not need to apply namespace manifests manually. `root-apps` and its child applications recreate `platform` and `apps` using the `CreateNamespace=true` sync option.

## 6. State backup: delivered in Phase 03

The etcd datastore is the only cluster state not reproducible from Git. It's protected by a five-stage pipeline (ADR-018). The Proxmox stages run on IST timers, in order, under one shared lock, and each stage sends a heartbeat to the DMZ Uptime Kuma, which alerts on Telegram when one is missing:

| Stage | When (IST) | What |
|---|---|---|
| Stage 1 | 02:00 | K3s snapshot on `k3s-control-01` (`etcd-snapshot-schedule-cron: "0 2 * * *"`, 14 kept, compressed; `control.yml`) |
| Stage 2 | 02:30 | Proxmox pulls the snapshots to the ZFS dataset `aether-pool/k3s-etcd-snapshots` (`k3s-etcd-sync.timer`) |
| Stage 3 | 03:00 | Local restic repository on the ZFS dataset `aether-pool/restic-k3s-etcd` (`k3s-etcd-restic.timer`) |
| Stage 4 | 03:30 | Offsite to Backblaze B2: one age-encrypted object per night in a bucket where each object is Object-Locked for 30 days (`k3s-etcd-b2.timer`) |
| Drill | on demand | In-place reset drill (about 18 min, Scenario 03) |

Each Proxmox job refuses to run unless its path is the expected ZFS dataset, so a failed mount can't fall back to the SSD (INC-2026-007).

### Verification (weekly or during drills)

```bash
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo k3s etcd-snapshot list"                   # one younger than 24 h
ssh -i ~/.ssh/homelab root@192.168.1.200 "systemctl list-timers 'k3s-etcd-*'"   # last runs this morning
```

The public status page shows the newest offsite copy's age under "Recovery objectives".

Take an on-demand snapshot before risky maintenance:

```bash
ssh -i ~/.ssh/homelab owl@192.168.1.51 "sudo k3s etcd-snapshot save --name pre-change-$(date +%Y%m%d-%H%M)"
```

## 7. Troubleshooting: Known failure signatures

Collected from the original Phase 02 bootstrap. Match the symptom before improvising:

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
| App shows `Unknown`; `ComparisonError: … .status.terminatingReplicas: field not declared in schema` | ArgoCD's built-in Kubernetes schema is older than the cluster's (ArgoCD 2.14 on Kubernetes 1.36, INC-2026-005) | Upgrade ArgoCD to a release whose `k8s.io/*` libraries match the cluster minor (currently v3.5.7). ADR-009 review condition |
| Several apps `Unknown` right after a push; `rpc error: code = DeadlineExceeded`; the KSOPS sidecar logs `deadline -Ns from now` | A webhook refreshed many apps at once and the repo server's queue (parallelism 2) outran the 60 s deadline; ArgoCD then caches the failure for a few minutes (INC-2026-013) | Hard-refresh the apps (`kubectl -n argocd patch application <app> --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'`). Make sure every repo-sourced Application has `argocd.argoproj.io/manifest-generate-paths: .` |
| A values change "has no effect" | The live Helm release differs from `values.yaml`, or the chart ignores the key | `task argocd:drift` shows the difference; `task lint:helm-values` catches keys the pinned chart doesn't define |
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
| Weekly | Verify etcd snapshot freshness and the DR timers | §6 Verification |
| Weekly | Verify Age key is present and Cloud KMS is accessible | `sops --decrypt infrastructure/secrets/ansible-secrets.sops.yaml > /dev/null` |
| Before any Helm or manual change | Take pre-change etcd snapshot | `k3s etcd-snapshot save --name pre-change-$(date +%Y%m%d-%H%M)` |
| Quarterly | Full Level 1 recovery drill on the smoke-test app | Delete secret: `kubectl -n platform delete secret gitops-smoke-secret`. Confirm ArgoCD recreates it decrypted, or run `kubectl patch application -n argocd smoke-test --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'` |
| Quarterly | Isolated cold restore from B2 | [DR Scenario 03 §5](../disaster-recovery/scenarios/03-homelab-hardware.md) |
| Quarterly | SOPS dual-recipient check: KMS-only and Age-only decryption both succeed | [DR Scenario 04, §4 step 1](../disaster-recovery/scenarios/04-age-key-loss.md) |
| Quarterly, and after any ArgoCD change | Live release matches Git | `task argocd:drift` |
| Yearly | Rotate the ArgoCD admin password (update the password manager); rerun the Level 1 drill from a clean kubeconfig | ArgoCD UI → User info → Update password |

## 9. Recovery success checklist

- [ ] All 3 nodes show `Ready` (`kubectl get nodes`)
- [ ] `task k8s:sops-secret` succeeded with secret `argocd-sops-age-key` present
- [ ] All ArgoCD pods are `Running`, with `argocd-repo-server` showing `2/2` (sidecar active)
- [ ] Every application reports `Synced` and `Healthy`; the `grep -vE 'Synced +Healthy'` check prints nothing (no `Unknown`)
- [ ] `task argocd:drift` → `ok`
- [ ] `gitops-smoke-secret` decrypts in-cluster
- [ ] ArgoCD pods' steady-state memory is under the 1 GB ADR-009 ceiling (`kubectl top pods -n argocd`; about 660 MiB in Nov 2026)
- [ ] `https://argocd.tail7067ab.ts.net` answers 200 from an operator device
- [ ] Admin password matches the password manager; `argocd-initial-admin-secret` deleted: `kubectl delete secret -n argocd argocd-initial-admin-secret`
- [ ] Etcd snapshot verified; incident notes recorded

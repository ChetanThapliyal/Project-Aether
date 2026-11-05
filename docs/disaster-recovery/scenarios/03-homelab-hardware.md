# DR Scenario 03: Homelab Hardware Failure & K3s Embedded etcd Recovery

**Severity:** SEV1 (core platform outage)
**Target RTO:** Branch A ~10 min · Branch B ~20 min (DR-05 in-place reset measured about 18 min) · Branch C ~1 h · Branch D unmeasured (HARD-11)
**Target RPO:** 0 for a cold boot; ≤ 24 h from an etcd snapshot (snapshot taken daily at 02:00 UTC)

---

## 1. Trigger & Symptoms

* **Alerts:**
  * DMZ Uptime Kuma marks the homelab endpoints DOWN.
  * OCI Prometheus loses the node-exporter targets on `192.168.1.51–53` and the Proxmox host.
* **Symptoms:**
  * `https://192.168.1.200:8006` doesn't load.
  * `kubectl` returns `The connection to the server 192.168.1.51:6443 was refused`.
  * `journalctl -u k3s` on `k3s-control-01` shows raft errors or datastore corruption.

---

## 2. Blast Radius

| Component | Status | Impact |
|---|---|---|
| **Homelab K3s** | Down | Control plane, workers and every pod |
| **ArgoCD / GitOps** | Down | Nothing reconciles until the cluster is back |
| **OCI `bookorbit`** | Up | Unaffected |
| **GCP DMZ** | Up | Keeps alerting |

### Where the Snapshots Are (best copy first)

| # | Location | Survives |
|---|---|---|
| 1 | `k3s-control-01:/var/lib/rancher/k3s/server/db/snapshots/` (14 kept) | Losing k3s only |
| 2 | Proxmox `/mnt/aether-pool/k3s-etcd-snapshots/` (ZFS dataset on the HDD, pulled 02:30 UTC) | Losing the VMs or the SSD |
| 3 | Proxmox restic repo `/mnt/aether-pool/restic-k3s-etcd` (ZFS dataset on the HDD, 03:00 UTC, password `/etc/restic/etcd-password.txt`) | Losing the VMs or the SSD |
| 4 | Backblaze B2 `aether-restic-etcd-offsite` (03:30 UTC, credentials in `group_vars/proxmox/vault.yaml`) | Losing the whole homelab |

> Copies 2 and 3 share one HDD (a single-disk pool). If the HDD fails, copies 1 and 4 are left.
>
> Restoring a snapshot onto a **new** control-plane VM needs the original K3s server token. Until HARD-10 escrows it in SOPS as `k3s_server_token`, the only copy is on the control VM, so a restore after Branch C or D can't work yet.

---

## 3. Recovery Procedures

### Branch A: Power Loss / Cold Start

1. Power on the laptop. Wait about 2 minutes for Proxmox VE to boot.
2. `ssh root@192.168.1.200`
3. Check the ZFS pool: `zpool status aether-pool`. If it's missing, run `zpool import aether-pool`. Then `zfs list -o name,mounted -r aether-pool`: both DR datasets must say `yes`. If one doesn't, the nightly jobs stop with `ERROR: ... is not the aether-pool ZFS dataset`; run `zfs mount -a`.
4. Start the VMs in order:
   ```bash
   qm start 101                                   # k3s-control-01
   sleep 90; ssh owl@192.168.1.51 "sudo systemctl is-active k3s"
   qm start 102; qm start 103                     # workers
   ```
5. `ssh owl@192.168.1.51 "kubectl get nodes"`: all three are `Ready`.
6. The DR timers use `Persistent=true`, so they run any job missed overnight. Check: `systemctl list-timers 'k3s-etcd*'` and `systemctl --failed`.

---

### Branch B: etcd Datastore Corruption (VMs Intact)

On `k3s-control-01` (`ssh owl@192.168.1.51`):

1. Stop K3s: `sudo systemctl stop k3s`
2. Pick a snapshot: `sudo ls -lt /var/lib/rancher/k3s/server/db/snapshots/`. If the local copies are gone too, I copy one back from Proxmox copy 2:
   ```bash
   # from the Proxmox host
   scp /mnt/aether-pool/k3s-etcd-snapshots/<snapshot> owl@192.168.1.51:/tmp/
   ssh owl@192.168.1.51 "sudo mv /tmp/<snapshot> /var/lib/rancher/k3s/server/db/snapshots/"
   ```
3. Reset and restore. This runs in the foreground and **exits by design**, with "restart without --cluster-reset flag now":
   ```bash
   sudo k3s server --cluster-reset \
     --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<snapshot>
   ```
4. `sudo systemctl start k3s`
5. Restart the agents:
   ```bash
   ssh owl@192.168.1.52 "sudo systemctl restart k3s-agent"
   ssh owl@192.168.1.53 "sudo systemctl restart k3s-agent"
   ```

---

### Branch C: VMs Lost, Proxmox Host Intact

1. Recreate the VMs (IDs 101–103, cloned from template 9000, with the same static IPs):
   ```bash
   task tf:init  DIR=03-homelab
   task tf:apply DIR=03-homelab
   ```
   If template 9000 is gone too, I rebuild it first with [proxmox-ubuntu-cloudinit-template.md](../../runbooks/proxmox-ubuntu-cloudinit-template.md).
2. Choose one of these:
   * **Restore cluster state** *(needs HARD-10)*. I follow Branch D steps 3–7, but take the snapshot from Proxmox copy 2 instead of B2.
   * **Start a fresh cluster.** Everything in Git comes back. Out-of-band secrets, Tailscale operator proxy identities and PV data do **not**.
     ```bash
     task ansible:bootstrap           # common → control → workers → kubeconfig
     task k8s:bootstrap-argocd        # also injects the Age key (k8s:sops-secret)
     ```
     Then I follow [argocd-recovery.md](../../runbooks/argocd-recovery.md) until every Application is Synced and Healthy.
3. Re-run the DR pipeline deployment so the Proxmox sync key is authorised on the new control VM:
   ```bash
   task ansible:etcd:sync
   ```

---

### Branch D: Total Hardware Loss — Restore from Backblaze B2

> **Not yet possible:** this needs HARD-10 (token escrow), and it hasn't been drilled (HARD-11). The steps come from the HARD-11 plan.

1. Install Proxmox on replacement hardware, then rebuild the storage, the network and template 9000. Then `task tf:apply DIR=03-homelab`.
2. `task ansible:common`
3. On the new control VM, install the K3s binary without starting it:
   ```bash
   curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.4+k3s1 INSTALL_K3S_SKIP_START=true sh -s - server
   ```
4. From my workstation, fetch the latest snapshot from B2:
   ```bash
   V=infrastructure/ansible/group_vars/proxmox/vault.yaml
   export AWS_ACCESS_KEY_ID=$(sops -d --extract '["b2_application_key_id"]' $V)
   export AWS_SECRET_ACCESS_KEY=$(sops -d --extract '["b2_application_key"]' $V)
   export RESTIC_PASSWORD=$(sops -d --extract '["restic_b2_password"]' $V)
   export RESTIC_REPOSITORY="s3:https://s3.us-east-005.backblazeb2.com/aether-restic-etcd-offsite"
   restic restore latest --target ./dr-restore
   ls -t ./dr-restore/mnt/aether-pool/k3s-etcd-snapshots/ | head -1
   ```
   I copy that file to `/var/lib/rancher/k3s/server/db/snapshots/` on the control VM. If it's a `.zip`, I extract it there first.
5. Restore with the escrowed token:
   ```bash
   sudo k3s server --cluster-reset \
     --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<snapshot> \
     --token="$(sops -d --extract '["k3s_server_token"]' infrastructure/secrets/ansible-secrets.sops.yaml)"
   ```
6. `sudo systemctl start k3s`, then `task ansible:control` (checks the token and applies the snapshot schedule).
7. `task ansible:workers`. ArgoCD, KSOPS, the Age key secret and every Application are already in the restored etcd, and reconcile once the workers are Ready.
8. In the Tailscale console I remove the stale devices for the old nodes.
9. Redeploy the DR pipeline: `task ansible:etcd:sync && task ansible:etcd:restic && task ansible:etcd:b2`.
10. `rm -rf ./dr-restore` and unset the exported credentials.

---

## 4. Post-Recovery Verification

1. `kubectl get nodes -o wide`: `k3s-control-01`, `k3s-worker-01` and `k3s-worker-02` are `Ready`.
2. Platform namespaces:
   ```bash
   kubectl get pods -n kube-system
   kubectl get pods -n gateway-system
   kubectl get pods -n metallb-system
   kubectl get applications -n argocd     # all Synced / Healthy
   ```
3. `tailscale status`: the homelab nodes and the operator proxies are online.
4. DR pipeline: on Proxmox, `systemctl list-timers 'k3s-etcd*'` shows the next runs, and `systemctl --failed` lists no `k3s-etcd-*` units.

---

## 5. Simulation Drills

**Snapshot health** (quick, any time):

```bash
ssh owl@192.168.1.51
sudo k3s etcd-snapshot save --name manual-dr-drill-$(date +%Y%m%d)
sudo k3s etcd-snapshot list | grep manual-dr-drill
```

**Cold restore from B2** (quarterly, per ADR-018): this is the isolated container drill in HARD-11. It restores the latest B2 snapshot into a K3s container with no network route out, with the agent disabled, and checks that the 3 original nodes, every ArgoCD Application and `argocd-sops-age-key` are present. I record the restore-to-ready time here and in the [DR README](../README.md#4-scenarios--drills).

Last cold-restore drill: not yet run.

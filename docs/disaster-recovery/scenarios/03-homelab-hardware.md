# DR Scenario 03: Homelab Hardware Failure & K3s Embedded etcd Recovery

**Severity:** SEV1 (core platform outage)
**Target RTO:** Branch A ~10 min · Branch B ~20 min (DR-05 in-place reset measured about 18 min) · Branch C ~1 h · Branch D: hardware and VM rebuild time plus about 3 min of restore (HARD-11 drill: B2 fetch 1.5 min, reset to ready API 54 s)
**Target RPO:** 0 for a cold boot; ≤ 24 h from an etcd snapshot (taken daily at 02:00 IST); ≤ about 25.5 h from B2 (copied at 03:30 IST)

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
| 2 | Proxmox `/mnt/aether-pool/k3s-etcd-snapshots/` (ZFS dataset on the HDD, pulled 02:30 IST) | Losing the VMs or the SSD |
| 3 | Proxmox restic repo `/mnt/aether-pool/restic-k3s-etcd` (ZFS dataset on the HDD, 03:00 IST, password `/etc/restic/etcd-password.txt`) | Losing the VMs or the SSD |
| 4 | Backblaze B2 `aether-restic-etcd-offsite` (03:30 IST, credentials in `group_vars/proxmox/vault.yaml`) | Losing the whole homelab |
| 5 | Backblaze B2 `aether-etcd-offsite-lock` (03:30 IST, one age-encrypted object per night, each locked 30 days; read-only key in `vault.yaml`, age identity in `ansible-secrets.sops.yaml`) | Losing the whole homelab, **and** an attacker with root on the hypervisor |

> Copies 2 and 3 share one HDD (a single-disk pool). If the HDD fails, copies 1 and 4 are left.
>
> Restoring a snapshot onto a **new** control-plane VM needs the original K3s server token. It's escrowed in SOPS as `k3s_server_token` (`infrastructure/secrets/ansible-secrets.sops.yaml`), and `task ansible:control` fails if the live token ever stops matching it. With the wrong token, K3s refuses the snapshot: `bootstrap data already found and encrypted with different token`.

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
   * **Restore cluster state.** I follow Branch D steps 3–7, but take the snapshot from Proxmox copy 2 instead of B2.
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

> Drilled 10 Nov 2026 (HARD-11) in an isolated container: steps 4 and 5 and the first start of step 6. Hardware, VM rebuild and worker rejoin weren't part of the drill. The drill used the restic copy; the locked-bucket path in step 4 was checked on 10 Nov as far as a verified, byte-identical snapshot (HARD-12), not yet through a container restore.

1. Install Proxmox on replacement hardware, then rebuild the storage, the network and template 9000. Then `task tf:apply DIR=03-homelab`.
2. `task ansible:common`
3. On the new control VM, install K3s without starting it, **with the same flags as `control.yml`**. `task ansible:control` skips the install once the binary exists, so flags left out here are never added later (a K3s without `--disable traefik --disable servicelb` deploys both on first start). From my workstation:
   ```bash
   K3S_TOKEN=$(sops -d --extract '["k3s_server_token"]' infrastructure/secrets/ansible-secrets.sops.yaml)
   ssh owl@192.168.1.51 "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.4+k3s1 INSTALL_K3S_SKIP_START=true \
     K3S_TOKEN='$K3S_TOKEN' sh -s - server --cluster-init --write-kubeconfig-mode 644 --tls-san 192.168.1.51 \
     --node-taint node-role.kubernetes.io/control-plane:NoSchedule --disable traefik --disable servicelb"
   ```
4. From my workstation, fetch the latest snapshot from the Object Lock bucket (HARD-12) with the read-only key, and decrypt it with the escrowed age identity:
   ```bash
   V=infrastructure/ansible/group_vars/proxmox/vault.yaml; B=aether-etcd-offsite-lock
   export RCLONE_B2_ACCOUNT=$(sops -d --extract '["b2_offsite_restore_key_id"]' $V)
   export RCLONE_B2_KEY=$(sops -d --extract '["b2_offsite_restore_key"]' $V)
   OBJ=$(rclone lsf :b2:$B/etcd/ | sort | tail -1); echo "$OBJ"          # newest night
   mkdir -p ./dr-restore/staged && rclone copyto :b2:$B/etcd/$OBJ ./dr-restore/$OBJ
   age -d -i <(sops -d --extract '["dr_offsite_age_identity"]' infrastructure/secrets/ansible-secrets.sops.yaml) \
     -o ./dr-restore/snap.zip ./dr-restore/$OBJ
   python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' ./dr-restore/snap.zip ./dr-restore/staged
   NAME=${OBJ%.zip.age}; ls -lh "./dr-restore/staged/$NAME"   # must exist, about 13 MiB
   ```
   If the newest object is missing, it may have been hidden. Hidden versions stay locked for 30 days; I list them with the master key (`rclone lsl --b2-versions`) and download the version I need.

   *Until the old bucket is retired*, the restic copy is a second source:
   ```bash
   export AWS_ACCESS_KEY_ID=$(sops -d --extract '["b2_application_key_id"]' $V)
   export AWS_SECRET_ACCESS_KEY=$(sops -d --extract '["b2_application_key"]' $V)
   export RESTIC_PASSWORD=$(sops -d --extract '["restic_b2_password"]' $V)
   export RESTIC_REPOSITORY="s3:https://s3.us-east-005.backblazeb2.com/aether-restic-etcd-offsite"
   restic restore latest --target ./dr-restore
   SNAP=$(ls -t ./dr-restore/mnt/aether-pool/k3s-etcd-snapshots/* | head -1)
   python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$SNAP" ./dr-restore/staged
   NAME=$(basename "${SNAP%.zip}")
   ```
   I copy `./dr-restore/staged/$NAME` to `/var/lib/rancher/k3s/server/db/snapshots/` on the control VM. Check `$NAME` is set before step 5: with an empty name the reset fails with `snapshot path does not exist`, and a plain start afterwards creates a new, **empty** cluster with new CAs. If that happens, stop K3s, delete `/var/lib/rancher/k3s/server/{db,tls,cred,token}` and start again from this step.
5. Restore with the escrowed token. SOPS and the Age key are on my workstation, not the VM, so I pass the token over SSH. The command exits by design after "restart without --cluster-reset flag now":
   ```bash
   ssh owl@192.168.1.51 "sudo k3s server --cluster-reset \
     --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/$NAME --token='$K3S_TOKEN'"
   ```
6. `sudo systemctl start k3s`, then `task ansible:control` (checks the token and applies the snapshot schedule).
7. `task ansible:workers`. ArgoCD, KSOPS, the Age key secret and every Application are already in the restored etcd, and reconcile once the workers are Ready.
8. In the Tailscale console I remove the stale devices for the old nodes.
9. Redeploy the DR pipeline: `task ansible:etcd:sync && task ansible:etcd:restic && task ansible:etcd:b2`.
10. `rm -rf ./dr-restore` (it holds every cluster Secret) and `unset RCLONE_B2_ACCOUNT RCLONE_B2_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY RESTIC_PASSWORD RESTIC_REPOSITORY K3S_TOKEN`.

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

Last cold-restore drill: **10 Nov 2026** (HARD-11). B2 snapshot of 03:00 IST holding the 02:00 IST etcd snapshot. `restic restore` 1 min 26 s, reset to ready API 54 s. The 3 original nodes, all 16 Applications (Synced/Healthy), `argocd-sops-age-key` and `operator-oauth` were present. Negative control: a wrong token failed with `bootstrap data already found and encrypted with different token`.

> In the drill, the nodes showed `Ready` at first. That is the status stored in the snapshot, not a live check. With the agent disabled, nothing renews it, and the node controller marks the nodes `NotReady` after its grace period.

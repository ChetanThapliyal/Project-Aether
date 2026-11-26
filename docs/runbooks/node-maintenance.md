# Node maintenance: drain, reboot, resize

> **Scope:** Taking one K3s node, or the whole hypervisor, out of service for planned work (kernel updates, a VM resize, a RAM or hardware change) and bringing it back.
> **Status:** Operational runbook, written 19 Nov 2026 against the 12 GB hypervisor. Rerun the capacity check in section 2 after the RAM upgrade; the procedure stays the same.
> **Related:** [ArgoCD recovery](argocd-recovery.md) · [DR Scenario 03: Homelab Hardware Failure](../disaster-recovery/scenarios/03-homelab-hardware.md) · [ADR-022: app data and backups](../adr/022-app-data-storage-and-backups.md)

## 1. The cluster in one table

| Node | VM | Runs | If it goes away |
| --- | --- | --- | --- |
| `k3s-control-01` (192.168.1.51) | 101 | The API server and the only etcd member. Tainted, so only CoreDNS, metrics-server and local-path-provisioner run there besides the DaemonSets | Running pods keep running and keep serving. Nothing can be scheduled, ArgoCD can't sync, `kubectl` fails. Draining it first moves CoreDNS to a worker, so in-cluster DNS keeps working |
| `k3s-worker-01` (192.168.1.52) | 102 | **PostgreSQL and CouchDB, pinned here by their `local-path` volumes**, plus Redis, the Envoy gateway proxy, the tailnet gateway and most apps | Every app that uses PostgreSQL (AFFiNE, Blinko, Linkwarden, Paperless) and Obsidian sync (CouchDB) are down until it is back. **This is a planned outage, not a failover** |
| `k3s-worker-02` (192.168.1.53) | 103 | Paperless, ArgoCD, cert-manager, the Envoy Gateway controller, the MetalLB controller, the Tailscale operator | Running traffic is unaffected: these are controllers, and the gateway proxy itself is on worker-01. New certificates, new LoadBalancer IPs and new tailnet ingresses wait until it is back |

Everything is a single replica and there are no PodDisruptionBudgets, so a drain evicts every pod on the node at once. App data on `nfs-zfs` (the hypervisor's ZFS pool) is not tied to a node: those pods start on whichever worker has room.

Priority classes decide who gets the room when it runs short: `platform` (PostgreSQL, Redis, the gateway proxy, the tailnet gateway) beats `apps`, which beats everything without a class (ArgoCD, cert-manager, the controllers). Higher-priority pods **preempt**: they evict lower-priority pods to make room. `batch` (backup Jobs) never preempts.

## 2. Check capacity before you drain

```bash
scripts/drain-check.py k3s-worker-02
```

It lists every pod that will move and says, from the memory and CPU requests, whether it **fits** on another node, **preempts** something there, stays **PENDING** until the node is back, or is **PINNED** by a local volume. It reads the cluster and changes nothing.

On 19 Nov 2026 (workers at 3.5 GiB, about 2.5 GiB allocatable each), neither worker can hold the other's pods:

| Drain | Moves | Stays down until uncordon |
| --- | --- | --- |
| worker-02 | ArgoCD, CSI NFS controller, cert-manager webhook | **Paperless** (needs 640 Mi, 632 Mi free), cert-manager, cert-manager cainjector, Envoy Gateway controller, MetalLB controller, Tailscale operator, the ArgoCD tailnet ingress |
| worker-01 | Redis, gateway proxy, tailnet gateway, AFFiNE, Blinko, IT-Tools, Linkwarden | PostgreSQL and CouchDB (pinned), kube-state-metrics. **Linkwarden preempts all four ArgoCD pods** on worker-02, which then stay Pending too |
| control-01 | CoreDNS, metrics-server, local-path-provisioner | nothing |

None of that breaks anything that matters for a short window, but know it before you start. The 5.57 resize (workers to 5 GiB) is meant to make worker-02 hold everything that can move from worker-01; rerun the check afterwards and update this table.

## 3. Before any maintenance

1. **Pick the window.** Not between 01:00 and 04:30 IST: the Paperless export (01:15), the database dumps (01:30), the CouchDB backup (01:45), the etcd snapshot (02:00) and the offsite copies (04:00) run then, and a drain in the middle fails that night's backup heartbeat.
2. **Everything healthy first.** `kubectl get nodes` all `Ready`; `kubectl get pods -A | grep -v -E 'Running|Completed'` empty; ArgoCD apps `Synced`/`Healthy`. Don't start maintenance on top of an unexplained fault.
3. **Pending reboot?** A node needs a reboot when `/var/run/reboot-required` exists (unattended-upgrades installs security updates but never reboots):
   ```bash
   for ip in 51 52 53; do ssh -i ~/.ssh/homelab owl@192.168.1.$ip 'echo "$(hostname): $(cat /var/run/reboot-required.pkgs 2>/dev/null | tr "\n" " " || echo none)"'; done
   ```
4. **Expect alerts.** Uptime Kuma pages for whatever goes down. For worker-01 or the hypervisor, set a maintenance window in DMZ Kuma covering the cluster monitors first.

## 4. One worker

Do one node at a time, and wait for it to be back before the next.

```bash
NODE=k3s-worker-02
scripts/drain-check.py "$NODE"                     # know what will be down
kubectl drain "$NODE" --ignore-daemonsets --delete-emptydir-data --timeout=10m
```

- `--ignore-daemonsets`: Alloy, node exporter, MetalLB speaker and the NFS CSI node plugin stay; they belong to the node.
- `--delete-emptydir-data`: the emptyDirs are scratch only (`/tmp`, caches, Paperless's `/run`). Redis's emptyDir is its only data volume and runs with no persistence by design: queues and caches refill.
- `--timeout=10m`: the Envoy gateway proxy has a 360 s grace period to drain connections, PostgreSQL 60 s for a clean shutdown.

The drain cordons the node, so evicted pods can't come back to it. Then do the work:

| Work | How |
| --- | --- |
| Reboot for updates | `ssh -i ~/.ssh/homelab owl@192.168.1.53 'sudo apt-get update && sudo apt-get -y full-upgrade && sudo reboot'` |
| Resize the VM | Change `memory` for that node in [`03-homelab/main.tf`](../../infrastructure/terraform/03-homelab/main.tf), then `task tf:apply DIR=03-homelab -- -target='proxmox_virtual_environment_vm.k3s_nodes["k3s-worker-02"]'`. The Proxmox provider reboots the VM to apply it. Owner runs the apply |
| Hardware on the host | See section 7: the whole cluster goes down |

Bring it back:

```bash
kubectl wait --for=condition=Ready node/"$NODE" --timeout=10m
kubectl uncordon "$NODE"
```

Pending pods schedule onto it within seconds. Pods that moved stay where they are: the scheduler doesn't rebalance. **Put them back before the next drain** ([INC-2026-019](../incidents/INC-2026-019-upgrade-drain-preempted-node-agents.md)): with neither worker able to hold the other's pods, a node left full makes the next drain evict things. `kubectl cordon` the node a pod is on, delete the pod so it is recreated on the other node, then `kubectl uncordon`; cordoning evicts nothing. Paperless prefers worker-02 (a preference, not a rule) and only acts on it when it is next scheduled.

The per-node agents (MetalLB's speaker, node exporter, Alloy) run at `system-node-critical` since 20 Nov, so a crowded node evicts an app before them, never the other way round.

## 5. worker-01: the databases

The same steps as section 4, with three differences:

- **It is an outage.** PostgreSQL and CouchDB can't move, so every app that uses them is down from the drain until PostgreSQL is `Ready` again. Do it last when doing several nodes, in a quiet evening window, and expect about 5 minutes for a reboot.
- **The drain shuts the databases down cleanly** (SIGTERM, PostgreSQL's fast shutdown). Always drain; never just reboot the VM. The kubelet has no graceful node shutdown configured, so a bare reboot kills PostgreSQL mid-write and leaves it to WAL recovery.
- **ArgoCD may be preempted** on worker-02 (section 2). It comes back by itself after the uncordon; nothing needs syncing in the meantime.

Afterwards, check the databases specifically:

```bash
kubectl -n databases get pods          # postgres-0 Running 1/1
kubectl -n apps get pods               # couchdb-0 and every app 1/1
kubectl -n databases logs postgres-0 --tail=20 | grep -i "ready to accept"
```

## 6. control-01: the API server

```bash
kubectl drain k3s-control-01 --ignore-daemonsets --delete-emptydir-data --timeout=5m
```

This moves CoreDNS, metrics-server and local-path-provisioner to the workers. Then reboot or resize as in section 4. While it is down, `kubectl` and ArgoCD fail and nothing new is scheduled, but every running app keeps serving. K3s is back within about a minute of the VM booting; then `kubectl uncordon k3s-control-01`. CoreDNS stays on the worker until its next restart, which is harmless.

etcd lives only here. Its snapshot is taken once a day at 02:00 and copied offsite, so for anything riskier than a reboot, such as a resize or an upgrade, take a fresh one first: `ssh -i ~/.ssh/homelab owl@192.168.1.51 'sudo k3s etcd-snapshot save --name pre-maintenance'`.

## 7. The hypervisor (all of it)

Everything goes down: the cluster, the NFS exports the apps use, and the hypervisor's own backup and log shipping. Uptime Kuma on the DMZ alerts for all of it; set the maintenance window first.

1. Drain the workers (worker-02, then worker-01) so the databases shut down cleanly. Skip draining control-01: its pods stop with the VM anyway.
2. Shut the VMs down from the host, workers first, control last:
   ```bash
   ssh -i ~/.ssh/homelab root@192.168.1.200 'for id in 103 102 101; do qm shutdown $id --timeout 180; done'
   ```
3. Do the work: `apt full-upgrade` on Proxmox, a reboot, or power off for hardware. **For new RAM, run memtest86+ overnight before booting Proxmox on it** (INC-2026-012: bad memory looked like random crashes).
4. All three VMs have `onboot: 1` and start with the host. Then uncordon both workers. Pods that were Pending schedule as space appears.

## 8. Patching everything: the order

1. **worker-02.** Least impact: only Paperless and controllers.
2. **control-01.** A minute without the API; apps keep running.
3. **worker-01.** The planned database outage, last, so a problem with the earlier nodes is found before you take the databases down.
4. **The hypervisor**, if it needs a reboot too (section 7). Doing it last can replace the individual VM reboots: a host reboot restarts all three.

## 9. Checks afterwards

| Check | Command or place | Expect |
| --- | --- | --- |
| Nodes | `kubectl get nodes` | All `Ready`, none `SchedulingDisabled` |
| Pods | `kubectl get pods -A \| grep -v -E 'Running\|Completed'` | Only the header |
| GitOps | ArgoCD UI, or `kubectl -n argocd get applications` | All `Synced` and `Healthy` |
| Apps from outside | DMZ Uptime Kuma | All cluster monitors green |
| Logs flowing | Grafana, `LogShippingStalled` | Not firing; each node's stream resumed |
| Memory headroom | `kubectl describe node <node> \| grep -A6 'Allocated resources'` | Requests below allocatable; after a resize, allocatable matches the new size |
| Next backup | The following morning: `kubectl -n apps get jobs`, `kubectl -n databases get jobs` | The night's export and dumps `Complete`; Kuma backup heartbeats green |

## 10. Known limits

- **No high availability by design.** One control-plane node, single replicas and node-local databases fit a two-worker homelab; this runbook makes the outages planned and short, not zero.
- **K3s version upgrades** have their own runbook and playbook: [K3s upgrade](k3s-upgrade.md). They use this page's drain steps and order.
- **No alert for a pending reboot.** Section 3's check is manual.

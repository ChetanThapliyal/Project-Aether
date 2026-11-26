# K3s upgrade

> **Scope:** Moving the cluster to a newer K3s release: the control plane first, then the workers one at a time, with an etcd snapshot and a rollback for each step.
> **Status:** Operational runbook, written 19 Nov 2026. First real run 20 Nov 2026: `v1.36.4+k3s1` → `v1.36.6+k3s1`, one node at a time, about 9 minutes of playbook in all (control plane 2.5, worker-02 1.6, worker-01 4.5) plus the clean-up in section 4 ([INC-2026-019](../incidents/INC-2026-019-upgrade-drain-preempted-node-agents.md)).
> **Related:** [Node maintenance](node-maintenance.md) (draining, and what each node's absence breaks) · [DR Scenario 03](../disaster-recovery/scenarios/03-homelab-hardware.md) (etcd restore) · [ADR-003](../adr/003-kubernetes-distribution.md)

## 1. How an upgrade happens here

| Step | Who | What |
| --- | --- | --- |
| A release comes out | Renovate | Opens one pull request changing `k3s_version` in both `infrastructure/ansible/playbooks/control.yml` and `workers.yml`. A patch release comes straight away; a minor release waits for approval in the Dependency Dashboard issue |
| Merge | Owner | Changes nothing on the cluster. Ansible is applied by hand |
| Upgrade | Owner, in a quiet window | `task ansible:k3s:upgrade` (section 3) |

The install tasks in `control.yml` and `workers.yml` run only once (`creates: /usr/local/bin/k3s`). That is deliberate: rerunning the install script would rewrite the systemd unit and needs the escrowed server token. The upgrade playbook (`playbooks/k3s-upgrade.yml`) swaps the binary instead, the method K3s documents as "upgrade using the binary". The unit, its flags and the config files under `/etc/rancher/k3s/config.yaml.d/` (etcd snapshots, secrets encryption, kubelet reservations) stay exactly as they are.

## 2. Before you start

1. **Read the release notes** for every release between the running version and the target: [github.com/k3s-io/k3s/releases](https://github.com/k3s-io/k3s/releases). They list the Kubernetes version and the bundled components (CoreDNS, local-path-provisioner, metrics-server, containerd, flannel) that change with it.
2. **A minor release (1.36 → 1.37) needs more:**
   - One minor at a time, never skipping one. The API server must never be older than a kubelet, which is why the control plane goes first.
   - APIs removed in the new Kubernetes version: `kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis` lists any deprecated API still in use. Fix those manifests first, through Git.
   - Every Helm chart in `kubernetes/` supports the new version: check each chart's `kubeVersion` and release notes (ArgoCD, cert-manager, Envoy Gateway, MetalLB, the Tailscale operator, the NFS CSI driver, Alloy, the monitoring exporters).
3. **The cluster is healthy:** nodes `Ready`, no pods failing, ArgoCD `Synced`/`Healthy` ([node maintenance §3](node-maintenance.md#3-before-any-maintenance)).
4. **Pick the window:** not between 01:00 and 04:30 IST (backups and the etcd snapshot). Draining worker-01 is a planned outage of every app that uses PostgreSQL or CouchDB, about five minutes. Run `scripts/drain-check.py k3s-worker-01` to see what else stays down.
5. **The pins agree and the PR is merged:** the playbook reads its target from `control.yml` and stops if `workers.yml` says something else.

## 3. Run it

```bash
task ansible:k3s:upgrade
```

Or one stage at a time, checking in between (recommended for a minor release):

```bash
task ansible:k3s:upgrade -- --limit control
task ansible:k3s:upgrade -- --limit k3s-worker-02
task ansible:k3s:upgrade -- --limit k3s-worker-01
```

For each node, already on the target or not:

1. Reads the running version. A node already on the target is skipped, so a rerun after a failure carries on where it stopped.
2. Control plane only: an etcd snapshot named `pre-upgrade-<old version>`.
3. Drains the node (`--ignore-daemonsets --delete-emptydir-data --timeout=10m`).
4. Downloads the release's `k3s` binary, checked against the release's `sha256sum-amd64.txt`.
5. Keeps the running binary as `/usr/local/bin/k3s.previous`, then swaps in the new one.
6. Restarts `k3s` (control plane) or `k3s-agent` (workers).
7. Waits until the node is `Ready` and its kubelet reports the new version (up to 10 minutes).
8. Uncordons it.

The workers go worker-02 first. worker-01 holds the databases, so its drain is the planned outage and comes last. While the control plane restarts (about a minute), `kubectl` and ArgoCD fail and nothing new is scheduled; running apps keep serving. When a release changes K3s's bundled CoreDNS manifest, K3s replaces CoreDNS, a single replica, so cluster DNS is down for about 20 seconds after the control plane comes back.

**After each worker, put back what moved before the next node.** A drain moves pods to the other worker and the scheduler never moves them back, so the next drain starts from a full node. On 20 Nov, Paperless moved to worker-01 after worker-02's drain, and Linkwarden to worker-02 after worker-01's, where it held the room ArgoCD (pinned to worker-02) needed. To move a pod back without another drain: `kubectl cordon` the node it is on, delete the pod (its Deployment recreates it on the other node), then `kubectl uncordon`. Cordoning evicts nothing.

## 4. Checks afterwards

| Check | Command | Expect |
| --- | --- | --- |
| Versions | `kubectl get nodes` | Every node on the target, `Ready`, none `SchedulingDisabled` |
| Bundled components | `kubectl -n kube-system get pods` | CoreDNS, local-path-provisioner and metrics-server running; K3s updates them itself from its bundled manifests |
| Workloads | `kubectl get pods -A \| grep -v -E 'Running\|Completed'` | Only the header |
| Per-node agents | `kubectl get ds -A` | DESIRED = READY for every DaemonSet. A Pending agent means a node is full: see section 3's note on moved pods |
| Placement | `kubectl get pods -A -o wide` | Paperless and the ArgoCD pods on worker-02, the other apps on worker-01; put back anything that moved (section 3) |
| GitOps | `kubectl -n argocd get applications` | All `Synced` and `Healthy` |
| From outside | DMZ Uptime Kuma | All cluster monitors green |
| The snapshot | `ssh -i ~/.ssh/homelab owl@192.168.1.51 'sudo k3s etcd-snapshot ls \| grep pre-upgrade'` | The pre-upgrade snapshot is listed |
| Next night | The 02:00 etcd snapshot, the 01:30 dumps and their heartbeats | Green, as every night |

## 5. Rollback

**A worker:** put the old binary back and restart:

```bash
ssh -i ~/.ssh/homelab owl@192.168.1.53 'sudo mv /usr/local/bin/k3s.previous /usr/local/bin/k3s && sudo systemctl restart k3s-agent'
```

**The control plane, patch release:** the same, with `k3s` instead of `k3s-agent`. Patch releases don't change the datastore.

**The control plane, minor release:** a newer Kubernetes may have written data the older version can't read, so swapping the binary back isn't enough. Restore the `pre-upgrade-<old version>` snapshot with the old binary, as in [DR Scenario 03, Branch B](../disaster-recovery/scenarios/03-homelab-hardware.md) (`k3s server --cluster-reset --cluster-reset-restore-path=<snapshot>`). Anything the cluster changed after the snapshot is lost, and ArgoCD puts Git's state back.

In every case, revert the pin commit too, so Git matches the cluster.

## 6. Known limits

- **amd64 only.** The playbook downloads the amd64 binary; every node is amd64.
- **No automatic upgrades.** Renovate proposes, a person runs the playbook. system-upgrade-controller would do it in-cluster, but it is one more controller for three nodes.
- **One node at a time is the way to run it** while the workers can't hold each other's pods: the full run gives no chance to put moved pods back between nodes.
- **Draining makes each VM touch its full memory**, and KVM doesn't hand it back, so the hypervisor sits at its 12 GB ceiling afterwards (`ProxmoxMemoryCritical`, 20 Nov) until the RAM upgrade.

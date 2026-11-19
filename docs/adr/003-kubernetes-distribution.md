```text
================================================================================
ADR-003: Kubernetes Distribution Selection (K3s vs Talos)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether requires a Kubernetes distribution as the core orchestration layer. The host machine has 12GB of RAM shared with the hypervisor and other VMs.
- **Problem Statement:** Which Kubernetes distribution provides a reliable orchestration environment within memory constraints while keeping standard Linux debuggability?
- **Decision Drivers:**
  - Resource efficiency (low RAM footprint).
  - Operational simplicity and interactive troubleshooting.
  - Common use in edge and production deployments.
- **Decision:** Deploy K3s as the Kubernetes distribution.
- **Architecture Impact:** K3s is installed on Ubuntu VMs provisioned via Terraform. The cluster is initialised with `--cluster-init`, replacing the default SQLite backend with an embedded etcd datastore. This elevates the node role to `control-plane,etcd` and enables native `k3s etcd-snapshot save` point-in-time state backups with direct upload to S3-compatible cloud storage.
- **Alternatives Considered:**
  - *Talos Linux:* Rejected. While Talos provides an immutable, API-driven operating system, it removes shell access for debugging. Standard SSH and Linux tools are useful for interactive troubleshooting in a single-operator environment.
  - *MicroK8s:* Rejected. MicroK8s relies on Canonical snap packaging and is less common outside Ubuntu environments. K3s maps more directly to general edge and lightweight deployments.
- **Decision Rationale:** K3s packages Kubernetes into a single lightweight binary with in-tree cloud providers and alpha APIs removed, keeping memory usage low on a host with 12GB RAM. Running on a standard Ubuntu VM retains conventional SSH and Linux troubleshooting workflows, and its widespread adoption matches common edge deployment patterns.
- **Consequences:**
  - *Positive:* Low memory footprint, standard Linux system debugging tools, active ecosystem support, and native etcd snapshot support enabling point-in-time backups uploadable directly to S3-compatible cloud storage.
  - *Negative:* Single-node embedded etcd still does not provide distributed high availability; it is acceptable for a single control-plane topology.
  - *Risks:* Modifying the underlying Ubuntu OS manually could destabilize the K3s agent. etcd snapshot restoration requires cluster downtime.
  - *Trade-offs:* Trading the strict immutability of an OS like Talos for familiar Linux troubleshooting tools.
- **Security Considerations:** K3s must be bound to internal network interfaces.
- **Reliability Considerations:** A single control plane node using embedded etcd has no distributed high availability. If the VM fails, the cluster API is unavailable until restored. Point-in-time recovery is operationalised via `k3s etcd-snapshot save` (OPS-09); snapshots are uploaded to S3-compatible cloud storage for off-node durability.
- **Scalability Considerations:** Can scale by adding worker nodes to the cluster through agent join tokens.
- **Performance Considerations:** Faster cluster bootstrap time compared to full Kubernetes (k8s).
- **Operational Considerations:** Upgrades are managed via the K3s upgrade controller or binary replacement. etcd snapshots are triggered via `k3s etcd-snapshot save` and stored in S3-compatible cloud storage; restoration follows standard K3s etcd recovery procedures.
- **Cost Considerations:** Infrastructure: ₹0.00 (open source).
- **Migration Plan:** Installed automatically via Ansible during Phase 1 bootstrap.
- **Validation / Fitness Functions:**
  - Control plane VM memory consumption should remain under 1.5GB while idle.
- **Dependencies:** Ubuntu Cloud Images, Ansible.
- **Open Questions:** None. *(OPS-09 resolved the SQLite → etcd migration; S3 snapshot destination configured in `infrastructure/ansible/playbooks/control.yml`.)*
- **Related ADRs:** ADR-006 (Proxmox VM Provisioning).
- **Review Conditions:** Review if migrating to a high-availability multi-master control plane. Embedded etcd already satisfies the datastore requirement; the primary trigger would be adding additional control-plane nodes.

### Addendum: Memory Reserved for the System, and a Memory Eviction Threshold (2026-11-19, Phase 04 task 4.32)
- **Context:** a read-only check of the live kubelet config showed that allocatable memory equalled capacity on every node. `systemReserved` and `kubeReserved` were empty, and K3s's default eviction thresholds cover disk only. So the scheduler could promise a node's whole memory to pods, the kubelet never evicted anything for memory, and the kernel's OOM killer was the only backstop. The `platform` priority class claimed "evicted last", which only holds when the kubelet evicts. Nothing had failed: pod requests used about a third of each worker. But memory limits added up to 96–104 % of a worker. On the control node, K3s runs the API server, etcd and the controllers in one process outside any pod (about 1.5 GiB with containerd), and none of it was reserved.
- **Decision:** a K3s config drop-in, `/etc/rancher/k3s/config.yaml.d/40-kubelet-reservations.yaml`, managed by `control.yml` and `workers.yml` (tag `kubelet`). Workers are changed one at a time; Ansible waits for each kubelet to report the new allocatable before moving on.

  | Node | system-reserved | kube-reserved | eviction-hard | Allocatable memory |
  |------|-----------------|---------------|---------------|--------------------|
  | Workers | 100m CPU, 256 MiB | 100m CPU, 384 MiB | `memory.available<200Mi` | 3.3 → 2.5 GiB |
  | Control | 100m CPU, 256 MiB | 250m CPU, 1536 MiB | `memory.available<200Mi` | 2.9 → 0.96 GiB |

  - Setting `eviction-hard` replaces K3s's defaults, so the disk thresholds are restated at their old values (`nodefs` and `imagefs` 5 %).
  - Only allocatable shrinks. `enforce-node-allocatable` stays at `pods`, so K3s itself gets no cgroup limit and can't be killed by its own reservation.
  - The control node is tainted for the control plane, so only DaemonSets run there (about 270 MiB of requests).
- **Priority, corrected:** under memory pressure the kubelet evicts pods using more than their memory request first, then lower priority. A `platform` pod is therefore evicted last only while it stays within its request. Requests now match real use where they didn't: the tailnet gateway proxy went from 32 to 48 MiB, since it used 35. The Envoy data plane and the tailnet gateway proxy now carry `platform` too, as the class description always promised; before this, only the two databases did. MetalLB speakers went to a 64 MiB request and a 96 MiB limit, from 32 and 64 MiB, after measuring 58–63 MiB.
- **Validation (19 Nov):** the live kubelet config on every node shows the reservations and all three eviction thresholds; all nodes Ready, all 25 apps Synced and Healthy, every app answers over HTTPS. The control-node restart briefly took the API down, and the Envoy Gateway controller exited cleanly and restarted when it lost its leader lease, as it does on any API outage. Envoy itself kept serving.
- **Fitness function, revised:** the original "control plane VM under 1.5 GB idle" no longer holds. The K3s server alone uses about 1.3 GiB and the VM about 1.9 GiB. The reservation, not that target, is what protects it now. Review if the K3s server outgrows 1.5 GiB.

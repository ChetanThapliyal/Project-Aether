# Project Aether documentation

Every document in `docs/`, grouped by the question it answers. The [main README](../README.md) explains what the platform is; this page gets you to the document you need. The public status page has the same index on its Docs page.

`scripts/check-docs-index.py` fails the commit if a document under `docs/` is missing here, so this list is complete.

## Why is it built this way?

Architecture decisions, numbered in the order they were made. Each one records the options, the choice and what it costs. Later changes are added to the original as dated addenda, so read them to the end.

| ADR | Decision |
|---|---|
| [001](adr/001-hypervisor-selection.md) | Proxmox on the laptop instead of bare-metal Docker |
| [002](adr/002-storage-topology.md) | Two storage tiers: SSD for the OS and VMs, ZFS on the HDD for backups |
| [003](adr/003-kubernetes-distribution.md) | K3s over Talos, and the node sizes |
| [004](adr/004-network-access.md) | A mesh for operators, and an inventory of every public entry point |
| [005](adr/005-mono-repo-structure.md) | One repository for infrastructure, Kubernetes and docs |
| [006](adr/006-proxmox-vm-provisioning-strategy.md) | VMs from Terraform and a cloud-init template |
| [007](adr/007-secrets-management.md) | SOPS with age and Cloud KMS |
| [008](adr/008-operational-toolchain.md) | Taskfile, pre-commit hooks and a pinned toolchain |
| [009](adr/009-gitops-controller.md) | ArgoCD over Flux |
| [010](adr/010-orchestration-migration.md) | Moving workloads from Docker Compose to Kubernetes |
| [011](adr/011-terraform-remote-backend.md) | Remote state in GCS, owned by a separate foundation |
| [012](adr/012-oci-monorepo-consolidation.md) | Oracle Cloud infrastructure in this repository |
| [013](adr/013-tailnet-microsegmentation.md) | Role tags, grants and policy tests on the mesh |
| [014](adr/014-infrastructure-environment-isolation-strategy.md) | One environment, isolated by namespace, with VM rollback |
| [015](adr/015-ci-validation-pipeline.md) | Validation on every push, keyless nightly drift detection, branch protection, linting |
| [016](adr/016-kubernetes-storage-strategy.md) | `local-path` for databases, NFS from ZFS for app files, Longhorn rejected |
| [017](adr/017-automation-and-scheduling.md) | One scheduler per job: Kestra on the cloud host, CronJobs on the cluster, timers on the hypervisor |
| [018](adr/018-offsite-backup-and-3-2-1-disaster-recovery-strategy.md) | 3-2-1 backups with an Object-Locked offsite copy |
| [019](adr/019-centralized-logging-architecture.md) | Loki on the cloud host, Alloy agents everywhere |
| [020](adr/020-public-observability-data-diode.md) | The public status page and its one-way data feed |
| [021](adr/021-internal-dns-and-pki.md) | Internal names and certificates: a Let's Encrypt wildcard on names only the mesh can reach |
| [022](adr/022-app-data-storage-and-backups.md) | App data: one shared database, files on NFS, nightly dumps and exports to the Object-Locked bucket, drilled |

The cluster's own layout (what ArgoCD owns, sync waves, secret rules) is in [`kubernetes/README.md`](../kubernetes/README.md), and the checklist for adding an app in [`kubernetes/apps/_template/README.md`](../kubernetes/apps/_template/README.md).

## What has gone wrong?

[Incident reviews](incidents/README.md): one blameless review per real failure, with a timeline, the root cause and the guardrail that would have caught it. The index has the severity scale and how each problem was found. New reviews start from [the template](incidents/TEMPLATE.md).

A gap found by review, with nothing broken yet, goes in the backlog instead.

## How do I recover from a failure?

[Disaster recovery](disaster-recovery/README.md) has the recovery objectives, where every piece of state lives, break-glass access when the mesh is down, and the known gaps. [`objectives.yml`](disaster-recovery/objectives.yml) is the short form the status page shows, with what each drill measured.

| Scenario | When |
|---|---|
| [01: Mesh outage](disaster-recovery/scenarios/01-tailscale-outage.md) | Tailscale's control plane or relays are down |
| [02: Cloud host loss](disaster-recovery/scenarios/02-oci-loss-restic.md) | The Oracle Cloud instance is gone: rebuild and restore from restic |
| [03: Home lab hardware](disaster-recovery/scenarios/03-homelab-hardware.md) | The hypervisor or its disks fail: rebuild the cluster and restore etcd |
| [04: Age key loss](disaster-recovery/scenarios/04-age-key-loss.md) | The SOPS age key is lost: recover through Cloud KMS |
| [05: DMZ rebuild](disaster-recovery/scenarios/05-gcp-dmz-rebuild.md) | The edge VM is gone: rebuild from Terraform and restore Uptime Kuma |

For ArgoCD alone, see the ArgoCD recovery runbook below.

## How do I do a routine job?

| Runbook | For |
|---|---|
| [Node maintenance](runbooks/node-maintenance.md) | Draining, rebooting or resizing a node, or taking the hypervisor down, and what each one breaks |
| [ArgoCD recovery](runbooks/argocd-recovery.md) | ArgoCD lost or broken, from a single namespace to the whole cluster |
| [SOPS key rotation](runbooks/sops-key-rotation.md) | Replacing the age key without breaking ArgoCD, the KMS key's versions, and every secret to change if a key leaks |
| [Tailscale key rotation](runbooks/tailscale-auth-key-rotation.md) | Auth keys and OAuth clients for joining nodes to the mesh |
| [Drift detector setup](runbooks/gcp-ci-drift-detector-setup.md) | The keyless CI identity that plans Terraform every night |
| [Proxmox TLS](runbooks/proxmox-acme-cloudflare-tls.md) | The hypervisor's certificate through ACME and Cloudflare DNS |
| [Cloud-init template](runbooks/proxmox-ubuntu-cloudinit-template.md) | Building the VM template the cluster nodes are cloned from |
| [Public page security headers](runbooks/public-page-security-headers.md) | The status page's CSP and other headers, set at Cloudflare |

## What does it look like?

Every diagram is generated from Python in [`diagrams/`](diagrams/) (`task diagrams` runs [`build_all.py`](diagrams/build_all.py), which also copies them to the status page). Edit the builder, never the SVG.

| Diagram | Shows |
|---|---|
| [Architecture](diagrams/project-aether-architecture.svg) | Every site, what runs there and how they connect |
| [Cluster topology](diagrams/flow-topology.svg) | The three VMs, what runs on each, and where the data sits: local-path on a worker, NFS from ZFS |
| [App request](diagrams/flow-app-request.svg) | How a request reaches an app: mesh-only DNS, the gateway, network policies |
| [GitOps](diagrams/flow-gitops.svg) | From a push to a running pod: CI, the signed webhook, ArgoCD, encrypted secrets |
| [Secrets](diagrams/flow-secrets.svg) | Where each secret is encrypted, which key opens it, and how it reaches the cluster, the hosts and Terraform |
| [Monitoring](diagrams/flow-monitoring.svg) | Metrics, logs and alerts, and the always-firing check that proves alerts get out |
| [Backups](diagrams/flow-backups.svg) | Each nightly backup path to the second disk and the offsite bucket, with heartbeats |
| [Mesh](diagrams/flow-tailnet.svg) | Role tags and the only flows the policy allows |
| [Status page](diagrams/flow-status-page.svg) | The one-way feed from the monitoring core to the public page |

## Hardware

- [Fan noise and sudden shutdowns](hw-issues/homelab-fan-issue-summary.md): the home lab laptop's cooling problem and what was done about it.

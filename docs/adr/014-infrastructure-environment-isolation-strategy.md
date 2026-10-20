```text
================================================================================
ADR-014: Single-Environment Infrastructure and Alternative Testing Strategy
================================================================================
```
- **Status:** Accepted (Fulfills and closes ADR-011 review condition)
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Enterprise cloud environments traditionally provision parallel staging environments or utilize Terraform workspaces (`production` vs `staging`) to test infrastructure changes, OS upgrades, and application releases prior to production rollout. Project Aether is a hybrid homelab-to-cloud infrastructure spanning a physical Proxmox VE host, Google Cloud Platform (GCP), and Oracle Cloud Infrastructure (OCI). The physical Proxmox host operates on an Intel Core i3 processor with a hard limit of 12 GB RAM. The 3-node K3s cluster (`k3s-control-01`, `k3s-worker-01`, `k3s-worker-02`) already allocates 9.2 GB of RAM, leaving ~2.8 GB reserved for Proxmox VE OS operations, ZFS/LVM ARC cache, and host overhead. Furthermore, the cloud footprint relies strictly on $0.00 free-tier limits: GCP provides exactly one free `e2-micro` instance, and OCI provides 200 GB of free boot storage.
- **Problem Statement:** How do we safely test infrastructure changes, runtime upgrades, and applications without provisioning parallel staging environments that exceed physical RAM limits or breach zero-cost cloud quotas?
- **Decision Drivers:**
  - Physical memory constraint: 12 GB host RAM cannot support a duplicate staging K3s cluster (which would require 4–9 GB RAM) without triggering hypervisor out-of-memory (OOM) kernel panics.
  - Strict zero-cost cloud budget ($0.00): GCP and OCI free-tier quotas permit only single compute instances; duplicate cloud staging instances immediately incur recurring billing.
  - Blast radius reduction: Terraform workspaces introduce human-error risk where operators apply changes to `production` when intending `staging` due to state selection mistakes.
  - Codebase simplicity: Avoid complex ternary expressions, dynamic VMID/subnet offsets, and parallel `tfvars` matrices for a single-operator environment.
- **Decision:** Formally reject Terraform workspaces and duplicate staging infrastructure across all root modules (`01-oci-compute`, `02-gcp-dmz`, `03-homelab`). Maintain a single state file per module (`<module>/default.tfstate` in GCS). Instead of duplicate hardware, adopt a three-tier alternative testing strategy:
  1. *Infrastructure Code Validation:* Statically validate Terraform via pre-commit hooks (`terraform fmt`, `terraform validate`, `tflint`) and automated dry-run `terraform plan` execution in pull request CI pipelines (IaC-09).
  2. *OS and Cluster Upgrades:* Perform hypervisor and K3s runtime upgrades in-place backed by instant Proxmox VE VM snapshots and etcd snapshots (OPS-09), enabling sub-minute rollback upon failure.
  3. *Application-Level Isolation:* Partition non-production workloads inside the existing K3s cluster using dedicated Kubernetes namespaces (`staging` vs `prod`) managed declaratively via ArgoCD application overlays.
- **Architecture Impact:**
  - Terraform root modules (`01-oci-compute`, `02-gcp-dmz`, `03-homelab`) remain unparameterized by workspace. Resource names, VM IDs (101, 102, 103), and static IPs (192.168.1.5x) remain explicit, static, and deterministic.
  - GCS remote state paths remain linear (`gs://tf-backend-oci-hlab-gcs/<module>/default.tfstate`), fulfilling and closing the review condition in ADR-011.
  - Cloud instances follow a distinct lifecycle model:
    - *GCP DMZ (Disposable):* Purely ephemeral compute codified via Docker Compose; changes deploy in-place or through disposable VM recreation from Git in under 5 minutes.
    - *OCI & Proxmox (Stateful):* Persistent storage requires volume backups or hypervisor snapshots prior to structural changes.
  - Applications share cluster hardware but remain isolated at the Kubernetes API layer via namespaces and RBAC.
- **Alternatives Considered:**
  - *Terraform Workspaces (IaC-08):* Rejected. Requires dynamic offsets for Proxmox VMIDs and IP subnets, risks state confusion, and is impossible to run due to the 12 GB RAM ceiling and GCP free-tier limits.
  - *Directory-Per-Environment (`environments/staging/`, `environments/prod/`):* Rejected. Duplicates module call boilerplate and demands duplicate physical resources that cannot run on available hardware.
  - *Ephemeral Single-Node Staging VM (Tiny 1GB VMID 200):* Rejected. A single-node VM fails to accurately simulate 3-node K3s cluster behavior, etcd quorum, or Flannel CNI networking, adding maintenance overhead for negligible testing fidelity.
  - *Nested Virtualization (Proxmox-in-Proxmox):* Rejected. Memory overhead is prohibitive on a 12 GB physical host.
- **Decision Rationale:** Enterprise infrastructure teams duplicate staging environments because they have scalable, on-demand cloud budgets and multiple engineers deploying concurrently. In a single-operator homelab bounded by 12 GB physical RAM and zero-cost cloud tiers, duplicating infrastructure causes catastrophic memory exhaustion while offering minimal defensive value. Shifting testing up the abstraction layer—validating IaC syntax via CI plans, testing applications via Kubernetes namespaces, and protecting cluster upgrades with hypervisor snapshots—delivers high reliability without hardware inflation.
- **Consequences:**
  - *Positive:*
    - Zero additional RAM overhead on the Proxmox host; eliminates out-of-memory risks.
    - Zero recurring cloud cost; strictly respects GCP and OCI free-tier ceilings.
    - Eliminates workspace selection errors (preventing accidental production applies).
    - Simplified, readable Terraform code without dynamic local ternary expressions for VMIDs and subnets.
  - *Negative:*
    - Destructive infrastructure-level changes (such as recreating a production VM or re-partitioning a disk) cannot be tested end-to-end on identical hardware prior to execution.
  - *Risks:*
    - Flawed Terraform resource replacements must be caught during `terraform plan` review. Mitigated by `prevent_destroy = true` lifecycle rules on critical instances (IaC-02) and automated CI plan diffs (IaC-09).
  - *Trade-offs:*
    - Accepting in-place hypervisor snapshot rollback as the recovery mechanism for OS/runtime changes instead of maintaining a warm staging clone.
- **Security Considerations:**
  - Eliminates risks of orphaned staging instances exposed on the network or consuming cloud API quota.
  - Kubernetes namespace isolation for staging applications should enforce ResourceQuotas and NetworkPolicies to prevent staging pods from exhausting host memory or accessing production databases.
- **Reliability Considerations:**
  - Before applying operating system patches, kernel updates, or K3s version bumps on Proxmox, an instantaneous VM snapshot and an etcd snapshot (OPS-09) must be captured. Rollback time is under 60 seconds if regressions occur.
  - For stateful cloud nodes (OCI), manual block volume snapshots must precede major maintenance. Disposable nodes (GCP DMZ) can be destroyed and reprovisioned from Terraform and Ansible playbooks in under 5 minutes.
- **Operational Considerations:**
  - Workflows use `terraform plan` and `terraform apply` directly without workspace management subcommands (`terraform workspace select/new`).
  - Developers test Helm charts and Kubernetes manifests by deploying to a `staging` namespace on the cluster before merging to the production branch.
- **Cost Considerations:**
  - Infrastructure cost remains strictly ₹0.00 / month.
- **Validation / Fitness Functions:**
  - Terraform root modules must successfully initialize and plan against their default state without requiring workspace variables or `-var-file` flags.
  - Proxmox host RAM utilization must remain below 80% (under 9.6 GB total) to prevent host memory pressure.
- **Dependencies:** Proxmox VE snapshot capability, K3s etcd snapshot tooling, GCP/OCI free-tier quotas.
- **Related ADRs:** ADR-001 (Hypervisor Selection), ADR-003 (Kubernetes Distribution), ADR-006 (Proxmox VM Provisioning), ADR-011 (Terraform Remote State Backend).
- **Review Conditions:** Review if physical host RAM is upgraded to >= 32 GB or if a dedicated secondary physical host is added to the homelab.

```text
================================================================================
ADR-006: Proxmox VM Provisioning Strategy
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The homelab runs on a single Proxmox VE node. As infrastructure components expand (Kubernetes cluster nodes, utility VMs, dev environments), a consistent, repeatable approach to VM provisioning is required.
- **Problem Statement:** How do we provision and configure new virtual machines on Proxmox VE with minimal manual steps while keeping configurations reproducible in Git?
- **Decision Drivers:**
  - Repeatability (provisioning a new VM produces the same baseline every time).
  - Provisioning speed (nodes boot in minutes rather than requiring interactive OS installations).
  - GitOps compatibility (automatable via Terraform and tracked in Git).
  - Simplicity (avoiding complex image pipelines at single-node homelab scale).
  - Secrets hygiene (SSH keys and credentials managed via encryption rather than hardcoded).
- **Decision:** Use Ubuntu 24.04 LTS cloud images with Proxmox Cloud-Init templates as the standard VM provisioning strategy.
- **Architecture Impact:** Template VM ID `9000` serves as the base image. Terraform clones this template, Cloud-Init injects per-VM configuration on first boot, and Ansible manages post-boot configuration.
- **Alternatives Considered:**
  - *Manual Installation (ISO):* Rejected. Interactive installs are slow (10 to 15 minutes per VM), prone to configuration drift, and incompatible with automated GitOps workflows.
  - *Packer Custom Image Build:* Rejected. Adds pipeline overhead that is unnecessary for a single-node homelab. Can be re-evaluated if expanding to a multi-node Proxmox cluster.
- **Decision Rationale:** Canonical maintains and patches official Ubuntu cloud images. Cloud-Init configures hostnames, users, and network settings declaratively on first boot and integrates directly with Terraform's `proxmox_vm_qemu` resource.
- **Consequences:**
  - *Positive:* VMs derive from a consistent base image, provisioning takes roughly two minutes, and VM definitions remain codified in Git.
  - *Negative:* First boot requires roughly 30 seconds for Cloud-Init initialization, and templates must be rebuilt when updating point releases.
  - *Risks:* A single Proxmox host provides no high availability for the base template.
  - *Trade-offs:* Trading custom package pre-baking via Packer for lower maintenance overhead.
- **Security Considerations:** SSH public keys injected via Cloud-Init are encrypted with SOPS and age. No credentials are stored in plaintext.
- **Reliability Considerations:** Running VMs operate as independent clones and are unaffected by template updates.
- **Scalability Considerations:** Scales across multiple VMs within the constraints of host RAM.
- **Performance Considerations:** Cloning uses LVM thin provisioning for fast disk creation.
- **Operational Considerations:** Updating templates requires downloading new cloud images and rebuilding VM 9000.
- **Cost Considerations:** Infrastructure: ₹0.00 (open source tooling).
- **Migration Plan:** N/A (foundational provisioning step).
- **Validation / Fitness Functions:**
  - Provisioning a new Kubernetes worker node via Terraform must complete in under three minutes end-to-end.
- **Dependencies:** Proxmox VE, Terraform, Cloud-Init, Ubuntu Cloud Images.
- **Open Questions:** None.
- **Related ADRs:** ADR-005 (Monorepo Structure), ADR-007 (Secrets Management).
- **Review Conditions:** Review when adopting Ubuntu 26.04 LTS or if expanding to a multi-node cluster where Packer builds become practical.

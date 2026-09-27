```text
================================================================================
ADR-006: Proxmox VM Provisioning Strategy
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** The homelab runs on a single Proxmox VE node. As the infrastructure grows (Kubernetes cluster nodes, utility VMs, dev environments), a consistent, repeatable approach to VM provisioning is required.
- **Problem Statement:** How do we go from "bare Proxmox" to a "running, configured VM" with the least friction and the most consistency?
- **Decision Drivers:**
  - Repeatability (provisioning a new VM should produce the same result every time).
  - Speed (spinning up a new node should take minutes, not the length of a manual install).
  - GitOps compatibility (must be automatable via Terraform and trackable in Git).
  - Simplicity (avoid tooling that adds complexity without proportional value at homelab scale).
  - Secrets hygiene (SSH keys and credentials must never be hardcoded).
- **Decision:** I will use **Ubuntu 24.04 LTS cloud images + Proxmox Cloud-Init templates** as the standard VM provisioning strategy.
- **Architecture Impact:** Template VM ID `9000` becomes the single source of truth for the base image. Terraform clones this template, and Cloud-Init injects per-VM configuration at first boot. Ansible handles post-boot configuration management.
- **Alternatives Considered:**
  - *Manual Installation (ISO):* Rejected. Not repeatable, every VM is a snowflake, slow (~10–15 mins per VM), and incompatible with GitOps.
  - *Packer + Custom Image Build:* Rejected. Significant complexity for homelab scale, requires a build pipeline, and slower iteration cycle. Might revisit if the lab grows to multi-node Proxmox clusters.
- **Decision Rationale:** Cloud images are maintained and security-patched by Canonical. Cloud-Init is a mature standard that injects per-VM config declaratively without interactive steps, integrating perfectly with Terraform's `proxmox_vm_qemu` resource.
- **Consequences:**
  - *Positive:* All VMs are traceable to a known base image; provisioning takes ~2 minutes; completely codified in Git.
  - *Negative:* First boot has a ~30 second Cloud-Init initialization delay; templates must be manually updated for new point releases.
  - *Risks:* Single Proxmox node means no HA for the template itself.
  - *Trade-offs:* Slightly less control over baked-in packages compared to Packer, but massively reduced maintenance overhead.
- **Security Considerations:** SSH public keys injected via Cloud-Init are encrypted with SOPS + age. No hardcoded credentials.
- **Reliability Considerations:** Running VMs are independent clones and are not affected by a template rebuild.
- **Scalability Considerations:** Easily scales to dozens of VMs if RAM permits.
- **Performance Considerations:** Cloning a template is near-instant via thin provisioning (LVM).
- **Operational Considerations:** Template updates require manually re-downloading the cloud image, rebuilding the template, and replacing VM 9000.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source tooling).
- **Migration Plan:** N/A - This is the foundational provisioning step.
- **Validation / Fitness Functions:**
  - Provisioning a new Kubernetes worker node via Terraform must take < 3 minutes end-to-end.
- **Dependencies:** Proxmox VE, Terraform, Cloud-Init, Ubuntu Cloud Images.
- **Open Questions:** None.
- **Related ADRs:** ADR-005 (Monorepo), ADR-007 (Secrets Management).
- **Review Conditions:** Review when migrating to Ubuntu 26.04 LTS or if scaling to a multi-node Proxmox cluster where Packer might become necessary.

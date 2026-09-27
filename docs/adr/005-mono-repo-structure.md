```text
================================================================================
ADR-005: Monorepo Structure for Project Aether
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether involves multiple layers: Infrastructure (Terraform), Configuration (Ansible), and Orchestration (Kubernetes). Managing these in separate repositories can create significant overhead for versioning and cross-component changes.
- **Problem Statement:** How do we organize our codebase to minimize context switching and ensure atomic updates across infrastructure and application layers?
- **Decision Drivers:**
  - Need for a "single source of truth".
  - Simplicity of CI/CD pipeline execution.
  - Ability to make atomic commits that span multiple layers.
- **Decision:** I will use a **Single Monorepo** structure.
- **Architecture Impact:** The repository will be structured logically by layer: `/infrastructure` for Terraform/Ansible, `/kubernetes` for ArgoCD manifests, and `/automation` for n8n workflows.
- **Alternatives Considered:**
  - *Polyrepo (Multiple Repositories):* Rejected due to excessive context switching, the complexity of orchestrating CI pipelines across repos, and difficulty in maintaining a "single source of truth" for the project.
- **Decision Rationale:** A monorepo ensures that an update to an infrastructure resource (like a VM memory limit) and the corresponding Kubernetes limit change can be committed and reviewed atomically in a single Pull Request.
- **Consequences:**
  - *Positive:* Simplified CI/CD validation; atomic changes; single source of truth.
  - *Negative:* Repository size will grow over time.
  - *Risks:* A mistake in the repo could impact all layers simultaneously.
  - *Trade-offs:* Trading smaller repository footprints for streamlined developer experience.
- **Security Considerations:** Secrets management must be strictly enforced at the root level (via SOPS) to prevent accidental leaks across any layer.
- **Reliability Considerations:** Single CI pipeline means if the pipeline breaks, deployments for all layers are blocked.
- **Scalability Considerations:** Perfectly fine for a single-cluster homelab. Not an issue until multiple distinct teams are working on the code.
- **Performance Considerations:** Local `git clone` times might slightly increase over time.
- **Operational Considerations:** Requires robust `pre-commit` hooks and Taskfile configurations at the root level to manage subdirectories.
- **Cost Considerations:** Infrastructure: ₹0.00 (GitHub Free tier).
- **Migration Plan:** N/A - Starting fresh with this structure.
- **Validation / Fitness Functions:**
  - A single GitHub Action must be able to validate Terraform, Ansible, and Kubernetes manifests simultaneously.
- **Dependencies:** GitHub, Git.
- **Open Questions:** None.
- **Related ADRs:** ADR-008 (Operational Toolchain).
- **Review Conditions:** Review if repository size exceeds 1GB or if branching strategy becomes too complex to manage.

```text
================================================================================
ADR-005: Monorepo Structure for Project Aether
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether spans infrastructure (Terraform), configuration (Ansible), and orchestration (Kubernetes). Managing these in separate repositories introduces overhead for cross-component changes.
- **Problem Statement:** How do we organize the codebase to minimize context switching and ensure atomic updates across infrastructure and application layers?
- **Decision Drivers:**
  - Maintaining a single source of truth for the project.
  - Streamlined CI/CD pipeline execution.
  - Atomic commits that span multiple infrastructure and deployment layers.
- **Decision:** Adopt a single monorepo structure.
- **Architecture Impact:** The repository is structured by layer: `/infrastructure` for Terraform and Ansible, `/kubernetes` for ArgoCD manifests, and `/automation` for automated workflows.
- **Alternatives Considered:**
  - *Polyrepo (multiple repositories):* Rejected. Splitting code across repositories adds cross-repo CI coordination overhead and complicates atomic changes across infrastructure and cluster manifests.
- **Decision Rationale:** A monorepo ensures that an update to an infrastructure resource (such as a VM memory limit) and the corresponding Kubernetes manifest change can be committed and reviewed together in a single pull request.
- **Consequences:**
  - *Positive:* Simplified CI/CD validation, atomic multi-layer changes, and a single repository to track state.
  - *Negative:* Repository size increases over time.
  - *Risks:* Pipeline failures or misconfigurations can affect all layers simultaneously.
  - *Trade-offs:* Accepting a larger repository footprint in exchange for atomic commits and unified tooling.
- **Security Considerations:** Secrets management is enforced at the repository root using SOPS to prevent plain-text credentials in version control.
- **Reliability Considerations:** A failing shared CI pipeline blocks deployments across all included layers.
- **Scalability Considerations:** Sufficient for a single-operator homelab. Repository contention is minimal without multiple teams making concurrent changes.
- **Performance Considerations:** Local `git clone` times may increase gradually as history grows.
- **Operational Considerations:** Requires configured `pre-commit` hooks and Taskfile automation at the root directory to run checks across subdirectories.
- **Cost Considerations:** Infrastructure: ₹0.00 (GitHub free tier).
- **Migration Plan:** N/A (initial repository setup).
- **Validation / Fitness Functions:**
  - A single GitHub Actions workflow must validate Terraform, Ansible, and Kubernetes manifests simultaneously.
- **Dependencies:** GitHub, Git.
- **Open Questions:** None.
- **Related ADRs:** ADR-008 (Operational Toolchain).
- **Review Conditions:** Review if repository size exceeds 1GB or if branching strategy complexity increases.

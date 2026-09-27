```text
================================================================================
ADR-008: Operational Toolchain and Pre-commit Hooks
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Managing a hybrid infrastructure (Proxmox hypervisor, Terraform, Ansible, Kubernetes) introduces significant cognitive load. Relying on memorized, complex CLI commands leads to human error. Furthermore, pushing unformatted code or plaintext secrets to Git degrades the quality and security of the repository.
- **Problem Statement:** How do we standardize the local Developer Experience (DevEx) to prevent human error, enforce code quality, and abstract complex operations behind simple commands?
- **Decision Drivers:**
  - Need to reduce cognitive load when context-switching between tools (TF, Ansible, K8s).
  - Absolute requirement to block plaintext secrets from entering Git history.
  - Desire for self-documenting, readable operational commands.
- **Decision:** I will standardize the local Developer Experience using **Taskfile (`go-task`)** and **pre-commit**.
- **Architecture Impact:** `Taskfile.yaml` sits at the root of the repo and replaces bash scripts/Makefiles for all operational commands (e.g., `task tf:apply`). `pre-commit` is installed locally to enforce a strict gatekeeping pipeline before `git commit` succeeds.
- **Alternatives Considered:**
  - *GNU Make:* Rejected. `Make` was designed for compiling C binaries, not running sequential cloud operations. Its syntax (tabs vs. spaces) is notoriously brittle and hard to read.
  - *Bash Scripts:* Rejected. They lack standardization, parallel execution capabilities, and built-in help menus (like `task -l`).
- **Decision Rationale:** Taskfile uses simple YAML to define tasks, natively supports environment variables, and documents itself. Pre-commit hooks provide an automated, fail-safe mechanism to enforce code hygiene without relying on discipline.
- **Consequences:**
  - *Positive:* Self-documenting commands; guaranteed code formatting (e.g. `terraform fmt`); strong protection against secret leaks via `gitleaks`.
  - *Negative:* Introduces a dependency on local binary installations for any machine interacting with this repository.
  - *Risks:* A misconfigured pre-commit hook could block legitimate commits.
  - *Trade-offs:* Forcing an extra step (installing tools) to guarantee repository health.
- **Security Considerations:** `pre-commit` integrates `gitleaks` and `detect-private-key`, ensuring no API tokens or SSH keys leak into the commit history.
- **Reliability Considerations:** Local execution only; does not rely on external cloud pipelines for basic validation.
- **Scalability Considerations:** Taskfile scales cleanly by supporting `includes:` to break tasks into multiple files as the project grows.
- **Performance Considerations:** Pre-commit hooks run locally in seconds, providing instant feedback compared to waiting for a CI/CD pipeline to fail.
- **Operational Considerations:** Contributors must run `pre-commit install` once after cloning the repository.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source tools).
- **Migration Plan:** Install both tools locally and seed the repository with `.pre-commit-config.yaml` and `Taskfile.yaml`.
- **Validation / Fitness Functions:**
  - Attempting to commit a plaintext file containing `PRIVATE KEY` must immediately fail locally.
  - Running `task -l` must print a list of all available operational commands with descriptions.
- **Dependencies:** `go-task`, `pre-commit`, Python (for pre-commit).
- **Open Questions:** None.
- **Related ADRs:** ADR-005 (Monorepo Structure).
- **Review Conditions:** Review if Taskfile becomes too complex to trace execution flows, or if a dedicated CLI wrapper is needed.

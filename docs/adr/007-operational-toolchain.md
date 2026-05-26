# ADR-007: Operational Toolchain and Pre-commit Hooks

## Status: Accepted

## Context

Managing a hybrid infrastructure (Proxmox hypervisor, Terraform, Ansible, Kubernetes) introduces significant cognitive load. Relying on memorized, complex CLI commands leads to human error. Furthermore, pushing unformatted code or plaintext secrets to Git degrades the quality and security of the repository.

## Decision

We will standardize the local Developer Experience (DevEx) using **Taskfile** and **pre-commit**.

- **Task (`go-task`):** Will replace bash scripts and `Makefile` for abstracting operational commands (e.g., `task tf:apply`).
- **pre-commit:** Will enforce a strict gatekeeping pipeline locally before Git commits are allowed.

## Consequences

- **Positive:** `Taskfile.yaml` provides self-documenting, cross-platform execution.
- **Positive:** `pre-commit` integrates `gitleaks`, guaranteeing no plaintext secrets (like Proxmox API tokens) accidentally leak into the commit history.
- **Positive:** Automatic `terraform fmt` and YAML validation enforce a unified code style.
- **Negative:** Introduces a dependency on local binary installations (`task`, `pre-commit`) for any machine interacting with this repository.

## Alternatives Rejected

- **GNU Make:** Rejected because `Make` was designed for compiling C binaries, not running sequential cloud operations. Its syntax (tabs vs. spaces) is notoriously brittle.
- **Bash Scripts:** Rejected because they lack standardization, parallel execution, and built-in help menus (`task -l`).

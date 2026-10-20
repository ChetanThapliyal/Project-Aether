```text
================================================================================
ADR-008: Operational Toolchain and Pre-commit Hooks
================================================================================
```
- **Status:** Accepted (refreshed October 2026)
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Managing a hybrid infrastructure across Proxmox, Terraform, Ansible, and Kubernetes involves dozens of distinct commands. Relying on memorized CLI syntax increases the risk of mistakes. Committing unformatted code or unencrypted configuration values also risks security issues in the repository.
- **Problem Statement:** How do we provide one documented, repeatable interface for routine operations and catch formatting and secret regressions before they enter Git history?
- **Decision Drivers:**
  - A single discoverable entry point for Terraform, Ansible, and SOPS operations.
  - Portable commands that behave the same on every workstation without Make's tab-sensitive syntax.
  - A commit-time gate for formatting, validation, and secret scanning.
  - Minimal overhead suitable for a single-operator, 12 GB homelab.
  - Local checks that can be reused unchanged in CI rather than reimplemented.
- **Decision:** Standardize local development workflows using Taskfile and pre-commit.

  **Task (`go-task` 3.x, validated with 3.53.1):**
  - `Taskfile.yaml` at the repository root is the operator-facing interface. It replaces ad-hoc shell scripts and Makefiles for common operational tasks (such as `task tf:apply`).
  - Task namespaces group commands by layer: `tf:*` for Terraform, `ansible:*` for Ansible, and root-level tasks for SOPS and setup.
  - Terraform tasks change into `infrastructure/terraform/{{.DIR}}`, decrypt `terraform.sops.tfvars` on the fly into `.decrypted.auto.tfvars`, and remove that file through a shell `trap` on exit, including on failure.
  - SOPS is invoked with an explicit `--config "{{.ROOT_DIR}}/.sops.yaml"` so decryption works from any task working directory.
  - `requires: vars` fails fast when `DIR` or `FILE` is omitted.
  - No repository-level `.env` file is used. Terraform variables, including the Proxmox API token, are supplied by `terraform.sops.tfvars` and decrypted per task. `gcloud` Application Default Credentials cover SOPS Cloud KMS access.

  **pre-commit:**
  - `.pre-commit-config.yaml` is the authoritative hook list. At the time of this decision it runs trailing-whitespace, end-of-file-fixer, `check-yaml` with `--allow-multiple-documents`, check-merge-conflict, detect-private-key, a local `terraform fmt` hook, `terraform validate`, and `gitleaks`.
  - `terraform fmt` excludes `*.sops.tfvars` so encrypted payloads are never rewritten.
  - Hook revisions are pinned in the repository and updated deliberately, not implicitly.
  - `task setup` installs the Git hook.

  **Scope boundary:**
  - This ADR covers local execution only. Commit-time hooks are bypassable (`git commit --no-verify`), so merge-time enforcement belongs to ADR-015.
  - Kubernetes execution tasks (`kubectl`, Helm, ArgoCD) are deferred until the Phase 03 GitOps work adds manifests. The current Taskfile intentionally manages Terraform, Ansible, and SOPS only.
- **Architecture Impact:**
  - Taskfile is the documented operator interface; runbooks and disaster-recovery procedures invoke `task` targets instead of raw CLI commands.
  - pre-commit is the commit-time gate. CI is the merge-time gate described in ADR-015.
  - Both layers read the same configuration files committed in the repository, keeping local and automated behavior aligned.
- **Alternatives Considered:**
  - *GNU Make:* Rejected. Make was designed around compiling source targets rather than executing sequential infrastructure commands. Tab-sensitive formatting rules frequently lead to syntax issues.
  - *Bash Scripts:* Rejected. Shell scripts lack built-in task discovery (`task -l`), cross-platform consistency, and clean dependency chaining.
  - *Just:* Rejected. A capable command runner, but it uses a custom DSL and adopting it would mean rewriting the existing Taskfile for no operational gain, diverging from the YAML conventions used elsewhere in the repository.
  - *Nx / Turborepo:* Rejected. JavaScript monorepo orchestrators with dependency graphs and caching designed for application builds. Excessive for a single-operator infrastructure repository.
  - *Lefthook / Husky:* Rejected for now. Lefthook is faster and parallel, and Husky is common in Node projects, but both add another binary or runtime to install. The pre-commit ecosystem already supplies maintained Terraform, YAML, and secret-scanning hooks with revisions pinned in Git.
  - *Local-only Git hooks (no framework):* Rejected. Hand-written hooks are invisible to onboarding, cannot be version-pinned consistently, and are difficult to reuse in CI.
- **Decision Rationale:** Task provides a documented interface with variables, task dependencies, and per-task working directories without Make's syntax traps. pre-commit keeps hook revisions pinned in Git, installs isolated hook environments, and allows the exact same command (`pre-commit run --all-files`) to run locally and in CI. Together they cover the two failure modes that matter here: mistyped operational commands and low-quality or secret-bearing commits.
- **Consequences:**
  - *Positive:* `Taskfile.yaml` provides portable, documented task commands across environments.
  - *Positive:* `pre-commit` runs `gitleaks` to prevent recognized plaintext secrets (such as Proxmox API tokens) from entering Git history.
  - *Positive:* Automatic `terraform fmt` and YAML syntax validation ensure consistent file formatting.
  - *Positive:* The same hook set is reusable in CI, so local and pipeline results do not diverge.
  - *Negative:* Requires local installations of `task`, `pre-commit`, `terraform`, `sops`, `age`, `gcloud`, and `ansible` on development machines.
  - *Negative:* `terraform validate` requires each root module to be initialized, which adds a first-run setup step on a fresh clone.
  - *Risks:* Hook revisions age silently if not updated. Local hooks can be bypassed with `--no-verify`. Neither risk is addressed by this ADR alone; ADR-015 covers CI enforcement and the update cadence is listed under Review Conditions.
  - *Trade-offs:* Accepting a small set of external binaries in exchange for a documented, reproducible operational interface.
- **Security Considerations:**
  - `gitleaks` and `detect-private-key` are detection controls, not guarantees. They catch recognized patterns in staged content; they do not prove that a `.sops.*` file is actually encrypted. The CI gate in ADR-015 adds an encryption-state check.
  - No repository-level `.env` is used for infrastructure credentials. Proxmox values live in `terraform.sops.tfvars` and exist in plaintext only while a task runs. If a local override is unavoidable, use a transient `TF_VAR_*` export or `sops exec-env` rather than a persistent credential file.
  - `.gitignore` continues to exclude `.env` files because application Compose stacks generate them on managed hosts; that rule is unrelated to the Taskfile.
  - `.sops.tfvars` is excluded from `terraform fmt` to prevent reformatting encrypted content.
  - Decrypted Terraform variables exist on disk only for the duration of a task and are removed by `trap`, including when Terraform fails.
  - pre-commit protects commits made on a configured workstation. It does not protect against a contributor who never runs `task setup`.
- **Reliability Considerations:** Tasks fail fast on missing `DIR` or `FILE` variables. Hook environments are cached after first install. A failed task does not leave decrypted variables behind because cleanup is registered before Terraform executes.
- **Scalability Considerations:** Task namespaces extend by prefix (`tf:`, `ansible:`, `ansible:oci:*`) without restructuring. SOPS path rules in `.sops.yaml` scale to new Terraform roots and secret directories without per-file configuration.
- **Performance Considerations:** Task and pre-commit add negligible runtime. The dominant cost is `terraform validate`, which depends on provider installation per root module.
- **Operational Considerations:**
  - Required local tools: `task` 3.x, `pre-commit`, Terraform (repository requires `>= 1.5.0`; CI pins `1.9.8`), `sops`, `age`, `gcloud` (Application Default Credentials for Cloud KMS), `ansible`, and `git`.
  - New workstation sequence: install the tools, run `task setup`, authenticate `gcloud` with `gcloud auth application-default login` for SOPS Cloud KMS, verify the relevant `terraform.sops.tfvars` is present, and run `terraform init` in each root module before committing Terraform changes.
  - Stale, empty `.env` placeholders in module directories are not read by Taskfile and can be removed.
  - Kubernetes tasks are intentionally absent until Phase 03.
- **Cost Considerations:** Infrastructure: ₹0.00. All tools are open source and run locally.
- **Migration Plan:** N/A (implemented during bootstrap). The October 2026 refresh updates this record to the standard ADR template, corrects the toolchain scope, and removes the unused root `.env`/`dotenv` mechanism. Credentials continue to come from SOPS tfvars and gcloud ADC; no secret migration is required.
- **Validation / Fitness Functions:**
  - `task --list` returns the documented task set from a clean checkout.
  - `pre-commit run --all-files` passes on a fresh clone after `task setup` and per-module `terraform init`.
  - No tracked `*.tfvars` file exists other than `*.sops.tfvars`.
  - A deliberately unformatted `.tf` file or a planted test token is blocked at commit time.
  - `task encrypt` followed by `task decrypt` round-trips a test file without leaving plaintext artifacts.
- **Dependencies:** go-task 3.x, pre-commit, Terraform, Mozilla SOPS, age, Google Cloud SDK, Ansible, Git, and the hook repositories pinned in `.pre-commit-config.yaml`.
- **Open Questions:**
  - Should any future local-only variables be delivered through `sops exec-env` as a standard, so no plaintext credential file is reintroduced?
  - Which Kubernetes tasks (Helm, kustomize, ArgoCD sync) should join the Taskfile in Phase 03?
- **Related ADRs:** ADR-005 (Monorepo Structure), ADR-007 (Secrets Management), ADR-011 (Terraform Remote Backend), ADR-014 (Infrastructure Environment Isolation), ADR-015 (CI Validation and Terraform Drift Pipeline).
- **Review Conditions:** Review when Kubernetes manifests come under Taskfile management, when a second operator joins the project, or when ADR-015 lands and changes where enforcement occurs.

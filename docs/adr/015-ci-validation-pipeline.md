```text
================================================================================
ADR-015: CI Validation and Terraform Drift Pipeline
================================================================================
```
- **Status:** Proposed
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether currently enforces code quality only at commit time through pre-commit (ADR-008), and that gate is local and bypassable with `git commit --no-verify`. GitHub Actions runs a single scheduled workflow, `.github/workflows/terraform-drift.yml`, which plans only `02-gcp-dmz` and is not triggered on pull requests. Meanwhile, ADR-005 sets a fitness function requiring one workflow that validates Terraform, Ansible, and Kubernetes manifests, and ADR-014 states that pre-commit runs `tflint` and that pull requests execute dry-run plans (IaC-09). Neither is implemented. The nightly drift workflow is also described in the README as covering all root modules, while its matrix contains one.
- **Problem Statement:** How do we enforce validation at merge time, without relying on contributor discipline and without placing privileged multi-cloud credentials in a public repository's CI?
- **Decision Drivers:**
  - A pull request must fail on formatting errors, invalid Terraform, lint findings, and leaked secrets even if local hooks were skipped.
  - One validation definition, shared by local and CI execution, to prevent configuration drift between the two.
  - Least-privilege cloud credentials, or none at all, for checks that do not need them.
  - Zero recurring cost within GitHub Actions free-tier limits for a public repository.
  - Fast feedback for a single operator; long-running plans must not gate every commit.
- **Decision:** Adopt a phased GitHub Actions pipeline with validation on every pull request, plans limited to the module with an existing CI identity, and drift detection expanded as read-only credentials are provisioned.

  **Phase 1 — Validation (no cloud credentials):**
  - Add `.github/workflows/validate.yml`, triggered on `pull_request` targeting `main` and on `push` to `main`.
  - The workflow installs the pinned toolchain, runs `terraform init -backend=false` in each root module to populate providers, then runs `pre-commit run --all-files`. This reuses the exact hook set from ADR-008, including `terraform fmt`, `terraform validate`, `check-yaml`, and `gitleaks`, and makes `terraform validate` work on a fresh runner.
  - Extend `.pre-commit-config.yaml` with `tflint` (initialized per module) and `ansible-lint`, so the tools named in ADR-014 exist in the shared hook set rather than only in CI.
  - Add a local hook that rejects tracked `*.sops.*` files when `sops --is-encrypted` fails. `gitleaks` detects known secret patterns; it does not verify encryption state.
  - Add `kubeconform` for `kubernetes/**` once Phase 03 introduces manifests. Until then the hook is absent rather than a no-op that implies coverage.
  - Run `terraform fmt -check -recursive` as an explicit step so formatting failures are legible without reading pre-commit output.

  **Phase 2 — Pull request plans (GCP only):**
  - Add a `plan` job for `02-gcp-dmz` using the existing `terraform-drift-detector` service account and `GCP_SA_KEY` secret documented in `docs/runbooks/gcp-ci-drift-detector-setup.md`.
  - Use `pull_request`, never `pull_request_target`. Fork pull requests do not receive repository secrets and therefore skip the plan job.
  - Publish the plan to the workflow step summary. Do not upload plan artifacts or raw plan files, because plan output can contain sensitive values and the repository is public.
  - Do not treat `-detailed-exitcode` code `2` as a failure on pull requests; changes are expected. Drift semantics apply only to the scheduled workflow.
  - Do not add OCI or Proxmox credentials to CI in this phase. Those providers require long-lived API keys with broad blast radius, and no read-only CI identity has been provisioned for them.

  **Phase 3 — Drift expansion:**
  - Expand the nightly matrix in `terraform-drift.yml` to `01-oci-compute` and `03-homelab` only after read-only OCI and Proxmox credentials exist and are stored as GitHub secrets.
  - Until then, keep the matrix at `02-gcp-dmz` and correct the README claim rather than implying coverage that does not exist.
  - Add an explicit notification step on drift (Telegram or Uptime Kuma push) so detection does not depend on someone noticing a failed workflow.
- **Architecture Impact:**
  - Local (pre-commit) and CI (Actions) execute the same hook definitions; CI adds only initialization and orchestration around them.
  - Branch protection on `main` should require the Phase 1 validation check. A solo operator can still use an administrative override, which is an accepted risk rather than a hidden one.
  - Workflow permissions default to `contents: read`; no workflow receives write scopes it does not need.
  - Third-party actions are pinned to commit SHAs rather than floating tags. Dependabot tracks `github-actions` and `terraform`; pre-commit revisions are refreshed with `pre-commit autoupdate` because Dependabot has no pre-commit ecosystem.
- **Alternatives Considered:**
  - *Keep validation local only:* Rejected. `--no-verify`, a missing `task setup`, or a fresh clone all bypass the only existing gate, and pull requests carry no quality signal.
  - *Run full `terraform plan` for every module on every pull request:* Deferred. It requires privileged OCI and Proxmox credentials in a public repository's CI, materially increasing blast radius. It also produces plan output that may contain secrets and consumes provider API quota for limited benefit at this scale.
  - *Self-hosted runner inside the homelab:* Rejected. It couples CI availability to the same host being managed, adds a persistent attack surface, and is unsafe for a public repository accepting fork pull requests.
  - *Terraform Cloud / HCP Terraform:* Rejected. Introduces a third-party dependency and state migration for functionality that GitHub Actions plus the existing GCS backend already provides at zero cost.
  - *A separate CI-specific lint configuration:* Rejected. Divergent local and CI rules create "passes locally, fails in CI" loops and double maintenance.
- **Decision Rationale:** The validation layer is the highest-value gate and needs no cloud credentials: it catches formatting, syntax, lint, and secret regressions before merge. Reusing pre-commit means the pipeline cannot drift from the developer workflow. Plans are then added only where an existing least-privilege identity already exists (GCP), and drift checks expand as equivalent identities are created. This sequences security risk and effort instead of granting broad credentials on day one.
- **Consequences:**
  - *Positive:* Pull requests fail on invalid Terraform, lint findings, formatting drift, and recognized secrets even when local hooks are skipped.
  - *Positive:* Local and CI behavior stay aligned because both run the same `.pre-commit-config.yaml`.
  - *Positive:* The `tflint` and PR-plan statements in ADR-014 become true once Phases 1 and 2 land.
  - *Positive:* Nightly drift coverage expands incrementally without granting standing credentials to every provider.
  - *Negative:* Adds workflow maintenance and a second place where tool versions are pinned.
  - *Negative:* `terraform init -backend=false` and `tflint --init` add runner time on every pull request.
  - *Risks:* A compromised GitHub token or workflow definition could abuse the GCP service account. Mitigated by read-only roles, SHA-pinned actions, minimal `permissions`, and no `pull_request_target` usage.
  - *Risks:* Branch protection can block urgent fixes if Actions is unavailable. Administrative override remains available and is an accepted single-operator trade-off.
  - *Trade-offs:* Accepting GCP-only plan coverage in the near term instead of broad multi-cloud CI credentials.
- **Security Considerations:**
  - The Phase 1 workflow requires no cloud credentials, so a malicious pull request cannot reach GCP, OCI, or Proxmox.
  - `GCP_SA_KEY` is a long-lived service account JSON key. Workload Identity Federation is the preferred replacement; until it is adopted, the key must be rotated on the schedule defined for CI identities.
  - Plan output is written only to the step summary, never uploaded as an artifact, and never printed to a public pull request comment by default.
  - `gitleaks` runs on the full tree in CI (`--all-files`), closing the gap where a contributor commits with `--no-verify`.
  - The SOPS encryption-state hook ensures an accidentally decrypted secret file is rejected even when its contents do not match a known gitleaks pattern.
  - Actions must be pinned to commit SHAs. `actions/checkout@v4`, `google-github-actions/auth@v2`, and `hashicorp/setup-terraform@v3` are currently pinned by tag and should be converted as part of Phase 1.
- **Reliability Considerations:**
  - Validation is deterministic and independent of cloud APIs. It remains available during provider outages.
  - Phase 2 plans depend on GCP authentication and GCS state locking. A failure there blocks the plan job but not the validation job.
  - The nightly drift workflow remains the only check that detects out-of-band infrastructure changes, and its value depends on covering every root module that has a CI identity.
- **Scalability Considerations:** Each root module is a matrix entry, so adding a provider means adding a directory and, at most, one credential set. Validation time grows linearly with modules and is currently trivial at three.
- **Performance Considerations:** Phase 1 is dominated by provider download and `terraform init`; caching the Terraform plugin directory and pre-commit environments keeps runs under a few minutes. Phase 2 adds one plan per pull request for a single module.
- **Operational Considerations:**
  - Required GitHub configuration: repository secret `GCP_SA_KEY`, branch protection requiring the validation check, and read-only OCI/Proxmox credentials before Phase 3.
  - The workflow must be triggerable manually (`workflow_dispatch`) for verification.
  - The README claim that drift detection covers all root modules should be corrected until Phase 3 completes, or the matrix expanded to match it.
- **Cost Considerations:** Infrastructure: ₹0.00. GitHub Actions minutes are free for public repositories, and the checks use open-source tooling only.
- **Migration Plan:**
  1. Add `tflint`, `ansible-lint`, and the SOPS encryption-state hook to `.pre-commit-config.yaml`; update ADR-014's implementation status accordingly.
  2. Add `.github/workflows/validate.yml` with `terraform init -backend=false` and `pre-commit run --all-files`.
  3. Pin third-party actions to commit SHAs and set `permissions: contents: read`.
  4. Enable branch protection requiring the validation check on `main`.
  5. Add the GCP plan job for `02-gcp-dmz` using the existing service account.
  6. Provision read-only OCI and Proxmox identities, then expand the nightly drift matrix to `01-oci-compute` and `03-homelab`.
  7. Add drift notifications and correct the README coverage claim.
  8. Evaluate Workload Identity Federation to retire `GCP_SA_KEY`.
- **Validation / Fitness Functions:**
  - A pull request containing an unformatted `.tf` file fails validation.
  - A pull request containing a planted test token fails `gitleaks` in CI even when the commit was created with `--no-verify`.
  - A pull request containing invalid HCL or a `tflint` violation fails validation.
  - A tracked, decrypted `.sops.*` file fails the encryption-state hook.
  - The validation check is required on `main` and reports in under five minutes.
  - Every Terraform root module with a CI identity appears in the nightly drift matrix.
- **Dependencies:** GitHub Actions, pre-commit, Terraform, tflint, ansible-lint, kubeconform (Phase 03), SOPS, GCP service account `terraform-drift-detector`, and read-only OCI/Proxmox credentials for Phase 3.
- **Open Questions:**
  - Should the GCP plan job be added before or after the validation workflow is stable?
  - Is a read-only Proxmox API token sufficient for `terraform plan` against `03-homelab`, or does the provider require broader privileges?
  - Should `GCP_SA_KEY` be replaced with Workload Identity Federation immediately rather than in a later phase?
  - Which notification channel should receive drift alerts: Telegram, Uptime Kuma push, or both?
- **Related ADRs:** ADR-005 (Monorepo Structure), ADR-007 (Secrets Management), ADR-008 (Operational Toolchain), ADR-011 (Terraform Remote Backend), ADR-014 (Infrastructure Environment Isolation).
- **Review Conditions:** Review when a second operator joins, when Kubernetes manifests enter the repository, or when read-only OCI and Proxmox CI identities are provisioned.

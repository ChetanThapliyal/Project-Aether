```text
================================================================================
ADR-012: OCI Infrastructure Consolidation into Project Aether Monorepo
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** OCI compute infrastructure (Oracle Cloud free-tier A1.Flex instance) was historically managed in a separate private repository (`ChetanThapliyal/OCI-servers`) containing Terraform modules, Ansible playbooks, and Docker Compose files. This created a polyrepo split contradicting the monorepo strategy established in ADR-005. ADR-005 was written before OCI was in use; OCI was not considered in scope at that time.
- **Problem Statement:** With OCI now serving as a permanent part of the infrastructure stack (Argo CD runtime, monitoring relay), managing its code separately from the homelab introduces version drift, context switching between repos, and a dual-SOPS configuration with no shared key management.
- **Decision Drivers:**
  - OCI is no longer an experiment – it is a permanent infrastructure node (ADR-010).
  - A single monorepo provides atomic commits across homelab + OCI changes.
  - Centralising SOPS under one `.sops.yaml` and one GCP KMS key simplifies key management.
  - Secrets in the OCI repo's Git history (discovered via `gitleaks` scan) made the private repo unsafe to keep in its original form.
- **Decision:** Consolidate all OCI infrastructure code into `Project Aether` using a **clean-state import** (no history preservation). The GCS Terraform bootstrap repo (`GCS-CP`) remains **strictly isolated** and is explicitly excluded from this decision.
- **Architecture Impact:**

  | Source (OCI-servers repo) | Destination (Project Aether) |
  |---|---|
  | `infra/` (Terraform modules) | `infrastructure/terraform/01-oci-compute/` |
  | `ansible/` | `infrastructure/ansible/playbooks/bootstrap-oci.yml` + `inventory/oci.ini` |
  | `compose-files/` | `legacy-docker/oci-services/` |

  - Terraform state continues to live in GCS under the `oci` prefix – no state migration required.
  - The OCI Terraform backend config was already pointing at the shared GCS bucket (`tf-backend-oci-hlab-gcs`), so `terraform init` picked up existing state automatically.

- **Alternatives Considered:**
  - *Keep polyrepo:* Rejected. Increases operational friction and creates a second SOPS configuration to maintain. OCI is now core infrastructure, not a side project.
  - *History-preserving merge (`git subtree` / `git filter-repo`):* Rejected. A `gitleaks` scan of the OCI repo's 38 commits found a hardcoded `NEXTAUTH_SECRET` in `compose-files/blinko.env` (commit `866099aa`). Importing the history into a public repo would permanently expose this secret. Clean import is the only safe option.
  - *Move GCS bootstrap repo in too:* Rejected. The bootstrap repo is the foundation layer – it creates the GCS bucket and the GCP project itself. It must remain isolated from the monorepo it enables to avoid circular dependency and blast radius.

- **Decision Rationale:** A clean-state import drops the compromised Git history while preserving all current file state. No services are interrupted (only source code is moved; the running OCI server is untouched). The monorepo benefits of ADR-005 now apply to OCI without exception.
- **Consequences:**
  - *Positive:* Single source of truth for all infrastructure; unified SOPS configuration; secrets history purged; `task tf:plan DIR=01-oci-compute` works identically to homelab.
  - *Negative:* OCI Git history is lost. If you need to trace a historical change, the original private repo still exists locally at `/home/owl/Projects/OCI-servers/` as an archive.
  - *Risks:* If the OCI repo is deleted before archiving, historical context is lost permanently.
  - *Trade-offs:* Security (history purge) over auditability (history preservation).
- **Security Considerations:**
  - All `.env` files excluded from the import. Ansible playbook rewritten to use centralized `infrastructure/secrets/ansible-secrets.sops.yaml` instead of plaintext env files.
  - All `*.env` files added to root `.gitignore`.
  - `gitleaks` scan mandatory before any future monorepo merges.
- **Reliability Considerations:** OCI TF state is remote (GCS) – merging the code does not affect the running infrastructure.
- **Scalability Considerations:** N/A – organizational change, not a scalability concern.
- **Operational Considerations:** The original private OCI repo should be archived (not deleted) and marked read-only on GitHub to preserve audit trail.
- **Cost Considerations:** ₹0.00 – organizational restructuring only.
- **Migration Plan:**
  1. `gitleaks` secret scan of source repo ✅
  2. Directory mapping and conflict analysis ✅
  3. `rsync` copy of files (no `.git/`, no `.env` files) ✅
  4. Playbook rewritten for centralized SOPS vars ✅
  5. Local state files purged (state lives in GCS only) ✅
  6. `terraform init` verified against live GCS state ✅
  7. Archive the original private OCI repo on GitHub ⬜ *(pending)*
- **Validation / Fitness Functions:**
  - `terraform init` in `01-oci-compute/` must succeed without errors against GCS backend.
  - `ansible-playbook --check` against OCI inventory must pass without drift.
- **Dependencies:** ADR-005 (Monorepo Structure), ADR-007 (Secrets Management), ADR-011 (Terraform Remote Backend).
- **Open Questions:**
  - Archive vs. delete the original `ChetanThapliyal/OCI-servers` GitHub repo.
- **Related ADRs:** ADR-005, ADR-007, ADR-010, ADR-011.
- **Review Conditions:** Review if a second OCI tenancy is ever provisioned.

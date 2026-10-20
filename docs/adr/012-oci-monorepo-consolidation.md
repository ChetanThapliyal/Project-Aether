```text
================================================================================
ADR-012: OCI Infrastructure Consolidation into Project Aether Monorepo
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** OCI compute infrastructure (an Oracle Cloud free-tier A1.Flex instance) was originally managed in a separate private repository (`ChetanThapliyal/OCI-servers`) containing Terraform modules, Ansible playbooks, and Docker Compose files. Managing it separately created a split that contradicted the monorepo strategy established in ADR-005.
- **Problem Statement:** With OCI serving as a permanent component of the infrastructure stack (for external workloads and relays), maintaining code separately leads to version drift, context switching, and split SOPS configurations.
- **Decision Drivers:**
  - OCI is a permanent component of Project Aether infrastructure (ADR-010).
  - A single repository provides atomic commits across homelab and cloud configurations.
  - Centralizing secrets under a shared `.sops.yaml` and GCP KMS key unifies key management.
  - Plaintext secrets discovered in the historical Git commits of the old repository required a clean import.
- **Decision:** Consolidate OCI infrastructure code into Project Aether using a clean-state import without history. The GCS Terraform bootstrap repository (`GCS-CP`) remains isolated and is excluded from this repository.
- **Architecture Impact:**

  | Source (OCI-servers repo) | Destination (Project Aether) |
  |---|---|
  | `infra/` (Terraform modules) | `infrastructure/terraform/01-oci-compute/` |
  | `ansible/` | `infrastructure/ansible/playbooks/bootstrap-oci.yml` + `inventory/oci.ini` |
  | `compose-files/` | `legacy-docker/oci-services/` |

  - Terraform state continues to reside in GCS under the `oci` prefix without requiring state migration.
  - The OCI Terraform configuration points to the shared GCS bucket (`tf-backend-oci-hlab-gcs`), and `terraform init` reuses existing state.

- **Alternatives Considered:**
  - *Keep separate repository:* Rejected. Adds administrative overhead and requires maintaining two separate SOPS setups.
  - *Merge Git history (`git subtree` / `git filter-repo`):* Rejected. A `gitleaks` scan identified credentials in early commits of the private repository. Importing full history into a public repository would expose those historical values.
  - *Include GCS bootstrap repository:* Rejected. The bootstrap repository provisions the GCP project and GCS bucket required by this monorepo and must remain decoupled to prevent circular dependencies.
- **Decision Rationale:** A clean-state import removes old Git history while bringing current configurations into the main repository. Live OCI infrastructure continues running uninterrupted during the transfer.
- **Consequences:**
  - *Positive:* Unified repository for all infrastructure, consolidated SOPS rules, and standard `task` execution commands across environments.
  - *Negative:* Historical commit logs from the initial OCI repository are omitted from the main repo history.
  - *Risks:* Historical commit references must be retrieved from the local archive directory (`/home/owl/Projects/OCI-servers/`) if needed.
  - *Trade-offs:* Prioritizing clean secrets hygiene over full commit history preservation.
- **Security Considerations:**
  - Environment files are excluded from import, and variables are referenced via `infrastructure/secrets/ansible-secrets.sops.yaml`.
  - Added `*.env` to the root `.gitignore`.
  - Pre-commit secret scanning via `gitleaks` runs automatically.
- **Reliability Considerations:** State remains in remote GCS; moving code does not affect running cloud workloads.
- **Scalability Considerations:** Organizational consolidation with no impact on runtime scalability.
- **Operational Considerations:** The original private repository is archived and set to read-only on GitHub for reference.
- **Cost Considerations:** ₹0.00 (organizational restructuring).
- **Migration Plan:**
  1. Complete `gitleaks` secret scan of source repo (Completed).
  2. Map directories and resolve naming overlaps (Completed).
  3. Copy current files without `.git/` or `.env` files (Completed).
  4. Update Ansible playbooks to use centralized SOPS secrets (Completed).
  5. Clean up local state artifacts (Completed).
  6. Verify `terraform init` against remote GCS state (Completed).
  7. Archive the original private repository on GitHub (Pending).
- **Validation / Fitness Functions:**
  - Running `terraform init` in `01-oci-compute/` succeeds against the GCS backend.
  - `ansible-playbook --check` against the OCI inventory reports zero configuration drift.
- **Dependencies:** ADR-005 (Monorepo Structure), ADR-007 (Secrets Management), ADR-011 (Terraform Remote Backend).
- **Open Questions:** None.
- **Related ADRs:** ADR-005, ADR-007, ADR-010, ADR-011.
- **Review Conditions:** Review if a second cloud tenancy is added to the project.

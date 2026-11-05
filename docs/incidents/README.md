# Incident reviews

Project Aether is a homelab run to production standards: a three-node K3s cluster on Proxmox, a cloud VM for applications, and a separate cloud VM in a DMZ that watches everything from outside. No customers depend on it. The data, the backups and the attack surface are real, so failures get the same treatment they would get at work: a blameless review, a root cause, and a guardrail that would catch the same failure next time.

Each review says how the problem was found. Four of the first six came from auditing the platform, because no alert fired. Each review's guardrails add the check that was missing.

## Severity

| Level | Meaning in this lab |
|-------|---------------------|
| SEV1 | Data loss, or an exposure an attacker could use, was possible |
| SEV2 | Monitoring or alerting was blind, so a SEV1 could have gone unnoticed |
| SEV3 | Something degraded, with no risk to data or exposure |

## Index

| ID | Date | Title | Severity | Found by | Status |
|----|------|-------|----------|----------|--------|
| [INC-2026-001](INC-2026-001-silent-backup-heartbeat.md) | 2026-11-02 | Nightly backups reported success while their heartbeat never arrived | SEV2 | Audit | Fixed, awaiting first scheduled run |
| [INC-2026-002](INC-2026-002-observer-blind-to-app-host.md) | 2026-11-02 | The outside observer could not see the services it monitored | SEV2 | Audit | Mitigated and verified |
| [INC-2026-003](INC-2026-003-fix-widened-dmz-exposure.md) | 2026-11-03 | Restoring monitoring opened admin tools to the DMZ | SEV1 | Verification check | Fixed and verified |
| INC-2026-004 | 2026-11-03 | DMZ alerts could not leave the host | SEV2 | Investigation | Open, fix planned |
| [INC-2026-005](INC-2026-005-gitops-blind-to-drift.md) | 2026-11-02 | GitOps showed four apps as healthy while it could no longer manage them | SEV2 | Audit | Fixed and verified |
| [INC-2026-006](INC-2026-006-logs-dropped-from-two-nodes.md) | 2026-11-02 | Two of three cluster nodes were sending their logs nowhere | SEV2 | Audit | Fixed and verified |

## Conventions

An incident gets a row in the index, with status `Open`, on the day it's found. The full review is written when the fix is verified, ideally in the same commit. A gap found by review, with nothing yet broken, goes in the backlog, not here.

Hostnames, addresses and the private network layout are generalised. Names such as "the app host" and "the DMZ observer" describe roles. Commit hashes refer to this repository. New reviews start from [TEMPLATE.md](TEMPLATE.md).

# ADR-005: Monorepo Structure for Project-Aether

## Status: Accepted

## Context

Project-Aether involves multiple layers: Infrastructure (Terraform), Configuration (Ansible), and Orchestration (Kubernetes). Managing these in separate repos creates overhead for versioning and cross-component changes.

## Decision

We will use a single Monorepo.

- `/infrastructure`: Terraform for Proxmox + Ansible for OS hardening and K3s bootstrap.
- `/kubernetes`: Kubernetes manifests managed by ArgoCD.
- `/automation`: Automation workflows for n8n.

## Consequences

- Simplified CI/CD: Single GitHub Action can validate the whole stack.
- Atomic changes: A single PR can update a VM resource and its corresponding K8s limit.
- Tradeoff: Repo size will grow, but negligible for a single-cluster homelab.

## Alternatives Rejected

- Polyrepo: Rejected due to excessive context switching and difficulty in maintaining a "single source of truth" for the portfolio.

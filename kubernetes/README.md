# `kubernetes/` — My GitOps layout for Project Aether

This directory is the declarative source of truth for everything running on my Project Aether K3s cluster. ArgoCD reads it from GitHub and reconciles the cluster to match it.

Managed by ArgoCD (App-of-Apps). See [ADR-005 (Monorepo Structure)](../docs/adr/005-mono-repo-structure.md) and [ADR-009 (GitOps Controller)](../docs/adr/009-gitops-controller.md).

Reference: [Phase 02 Foundation Deep-Dive](../docs/git-ignored/notes/architecture/phase-02-foundation.md) · [Phase 02 Chores](../docs/git-ignored/misc/phase-02-chores.md)

---

## The one rule that matters

ArgoCD reads the remote repository on GitHub. It never sees my working tree. A manifest I edit but do not `git push` does not exist as far as the cluster is concerned.

With the default 3-minute poll interval, a pushed change lands in the cluster within up to 180 seconds. Push-triggered sync (GITOPS-10) is deferred until after Phase 03 networking.

---

## Directory structure

```
kubernetes/
├── bootstrap/argocd/            ← Helm-owned (task k8s:bootstrap-argocd). Never ArgoCD-managed.
├── cluster/                     ← Application CRs ONLY (root-apps index)
├── platform/
│   ├── namespaces/              ← wave -3, PSA labels
│   ├── metallb/                 ← IPAddressPool + L2Advertisement
│   ├── gateway/                 ← GatewayClass, Gateway, EnvoyProxy (HARD-14)
│   ├── cert-manager/            ← issuers + certificates
│   ├── tailscale/{secret,apps}/ ← KSOPS OAuth secret; ProxyClass + Ingress
│   ├── monitoring/exporters/    ← reference values (charts are inline in cluster/)
│   ├── network-policies/        ← default-deny + allow-lists
│   ├── argocd-metrics/          ← metrics NodePorts (moved in HARD-18)
│   └── smoke-test/              ← KSOPS end-to-end check
└── apps/                        ← Phase 04 workloads
```
```
```
---

## Who owns what

| Directory | Who applies it | ArgoCD manages it? |
|-----------|----------------|---------------------|
| `bootstrap/` | Me manually (`task k8s:bootstrap-argocd`) | No — ArgoCD never watches this path |
| `cluster/` | Me manually (once), then ArgoCD self-manages | Yes — `root-apps` watches this |
| `platform/` | ArgoCD (via child Apps in `cluster/`) | Yes |
| `apps/` | ArgoCD (via child Apps in `cluster/`) | Yes |

> **`bootstrap/` must still be committed to Git.** ArgoCD does not manage it, but my disaster-recovery runbook relies on `values.yaml` being replayable from a fresh clone. If it is not in Git, a rebuild installs a stock ArgoCD with no KSOPS sidecar and no memory tuning. See **GITOPS-12**.

---

## Adding a new application

1. **Create the manifests** under `kubernetes/apps/<app-name>/`.
2. **Add a child `Application` CR** under `kubernetes/cluster/` pointing at that path:

   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: my-app
     namespace: argocd
   spec:
     project: default
     source:
       repoURL: https://github.com/ChetanThapliyal/Project-Aether.git
       targetRevision: main
       path: kubernetes/apps/my-app
     destination:
       server: https://kubernetes.default.svc
       namespace: apps
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
       syncOptions:
         - CreateNamespace=true
   ```

3. **Commit and push to `main`.** `root-apps` discovers the new CR and creates the child Application automatically.
4. **Watch it land:**
   ```bash
   kubectl get applications -n argocd
   ```

### Conventions for new applications

- Git-sourced Applications use `targetRevision: main`, never `HEAD`. `HEAD` silently means "whatever the default branch is" (HARD-18). Helm-sourced Applications pin the chart version instead.
- Do not set `plugin:` in `source`. The KSOPS CMP uses auto-discovery via `discover.find.glob: "**/ksops-*.yaml"`. Setting `plugin.name` alongside a `discover` block conflicts with ArgoCD v2.4+.
- Secrets must be SOPS-encrypted and named `*.sops.yaml`. The pre-commit hook `check-sops-encryption.sh` rejects unencrypted files.
- Set sync-wave annotations for anything that depends on a namespace, CRD, or operator. Namespaces are wave `-3`; CRDs and operators `-2`; shared secrets `-1`; controllers `0`; user apps `1+`.
- **Finalizer rule (HARD-18).** Leaf Applications carry `resources-finalizer.argocd.argoproj.io`, so deleting the Application also deletes what it deployed. `platform-namespaces` must **never** carry it: deleting that Application would cascade-delete every namespace, and everything in them.
  - Without the finalizer, deleting an Application only orphans its resources. That is what `platform-namespaces` relies on. Four older leaf apps also lack it (`cert-manager-issuers`, `gateway-instance`, `metallb-config`, `smoke-test`), so deleting them leaves their resources running.
  - `root-apps` carries the finalizer. Deleting it deletes every child Application, and each child that has the finalizer then deletes its workloads. Only the namespaces and the four apps above survive. Never delete `root-apps` to "reset" ArgoCD; see the recovery runbook instead.

---

## Secrets: the SOPS rules

| Rule | Detail |
|------|--------|
| Filename | Any secret must end in `.sops.yaml` |
| Location | `kubernetes/platform/<app>/` or `kubernetes/apps/<app>/` |
| Encryption | `task encrypt FILE=<path>` (SOPS + Age + GCP KMS, dual recipient) |
| Verification | `task decrypt FILE=<path>` or `kubectl get secret -n <ns> <name>` |
| Never | Commit plaintext secrets. Never commit the Age private key. |

The `.sops.yaml` creation rules set `encrypted_regex: '^(data|stringData)$'` for the fallback `*.sops.yaml` rule, so only secret *values* are encrypted. `apiVersion`, `kind`, and `metadata` stay plaintext, which Kustomize requires to validate the resource.

---

## Quick commands

```bash
# What is ArgoCD doing?
kubectl get applications -n argocd
kubectl get pods -n argocd -o wide          # repo-server MUST be 2/2 (sidecar present)

# Force a re-sync without the ArgoCD CLI
kubectl patch application -n argocd <name> --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Decrypt errors
kubectl logs -n argocd \
  $(kubectl get pod -n argocd -l app.kubernetes.io/name=argocd-repo-server -o name) \
  -c ksops-plugin

# Validate manifests before committing
pre-commit run --all-files
```

---

## Related documentation

- [Phase 02 — GitOps Foundation Deep-Dive](../docs/git-ignored/notes/architecture/phase-02-foundation.md) — how and why all of this works
- [Phase 02 Chores & Implementation Guide](../docs/git-ignored/misc/phase-02-chores.md) — the task-by-task execution log
- [ArgoCD Disaster Recovery Runbook](../docs/runbooks/argocd-recovery.md) — 3-level recovery procedure
- [ADR-005 — Monorepo Structure](../docs/adr/005-mono-repo-structure.md) · [ADR-007 — Secrets Management](../docs/adr/007-secrets-management.md) · [ADR-009 — GitOps Controller](../docs/adr/009-gitops-controller.md)

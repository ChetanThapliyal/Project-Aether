# INC-2026-005: GitOps showed four apps as healthy while it could no longer manage them

| Field | Value |
|-------|-------|
| Date found | 2026-11-02 |
| Severity | SEV2 |
| Found by | Audit |
| Duration | 2026-10-28 04:06 (one app never synced at all) to 2026-11-05 |
| Status | Fixed and verified; permanent fix scheduled (controller upgrade) |

## Summary

The K3s cluster is managed by ArgoCD, which applies what's in Git and corrects drift. After a Kubernetes upgrade, ArgoCD could no longer compare four apps with Git. They showed `Healthy`, which is what people look at, and `Sync: Unknown`, which meant ArgoCD had stopped auto-syncing and self-healing them. A configuration fix merged on 28 Oct never reached the cluster. Two apps were moved off the apply mode that triggered the bug, the other two switched to a diff mode that avoids it, and all four are managed again.

## Impact

For eight days, four platform apps (the certificate manager, the gateway controller, the overlay-network operator and a metrics exporter) were deployed but unmanaged. A change in Git did nothing, and a manual edit in the cluster would have stayed. One known change was lost this way: a fix that moved the network operator onto a dedicated node with resource limits was merged on 28 Oct, and the operator kept running on the wrong node with no limits until 5 Nov. No outage resulted.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-10-28 04:01 | The network operator app syncs for the first time |
| 2026-10-28 04:06 | Its next comparison fails with `.status.terminatingReplicas: field not declared in schema`. It stays `Unknown` from then on |
| 2026-10-28 04:20 | The operator placement fix is merged to Git. It never applies |
| 2026-11-02 | A phase-exit audit lists the apps, sees four `Unknown`, and traces the error |
| 2026-11-05 | Fix committed (`26c88ea`). After two refresh cycles all 16 apps are `Synced` and `Healthy`, and the operator has moved to its intended node with limits |

## Root cause

Kubernetes 1.33 added the `.status.terminatingReplicas` field to Deployments, and the cluster (1.36) fills it in. For apps that use server-side apply, ArgoCD builds its diff against a Kubernetes schema compiled into the ArgoCD binary. The running ArgoCD (2.14) predates the field, so it could not build a diff for any app containing a Deployment. Apps without server-side apply, or without Deployments, were unaffected. That split matched the four failing apps exactly.

## Contributing factors

- Server-side apply had been turned on for every Helm app, including two that didn't need it (it exists for very large CRDs).
- The status list puts `Healthy` next to `Unknown`, and `Healthy` reads as "fine".
- ArgoCD's app status was already being scraped into Prometheus, but no alert fired on `Unknown`.
- The ArgoCD version wasn't checked against the cluster version when the cluster was upgraded.

## What went well

- The audit counted `Unknown` as a failure.
- A table of which apps used server-side apply and contained Deployments explained the four failures and the twelve successes in one view.
- The fix was the smallest one that worked. Server-side apply was dropped only where CRD sizes showed it wasn't needed, and the diff-mode change was run as a test with a written decision gate.

## Where we got lucky

The only change lost to the drift was a resource placement fix. A security change in Git would have been just as silently ignored.

## Fix

Commit `26c88ea`.

- The network operator and the metrics exporter no longer use server-side apply. Their largest CRDs fit well within the client-side limit.
- The certificate manager and gateway controller keep server-side apply (their CRDs are too big without it) and use server-side diff, which asks the cluster for the schema instead of using the compiled one.

## Guardrails added

- Follow-up: an alert on any app not `Synced` for 30 minutes, using the metric that was already being collected.
- Follow-up: upgrade ArgoCD to a version that knows the 1.36 schema, then remove the server-side diff workaround.
- Follow-up: add a review condition to the GitOps controller's architecture decision record: re-check the controller's Kubernetes library version whenever the cluster's minor version changes.

## Lessons

- "Healthy" and "in sync" are different claims. A GitOps tool that can't diff will still report the workload as healthy.
- Collecting a metric does nothing until something alerts on it.
- Upgrading the cluster also means checking every tool that compiles in a schema for that cluster.

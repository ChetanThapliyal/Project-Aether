# INC-2026-013: The new GitHub webhook refreshed every app at once, and five apps went Unknown

| Field | Value |
|-------|-------|
| Date found | 2026-11-16 |
| Severity | SEV3 |
| Found by | Verification check (the Phase 02 re-verification, GOP-06) |
| Duration | 2026-11-16 02:46 to 02:53 UTC (about 6 minutes; no deploys were blocked) |
| Started | 2026-11-16 02:46 |
| Detected | 2026-11-16 02:48 |
| Resolved | 2026-11-16 02:59 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

GOP-04 added a signed GitHub webhook so that ArgoCD reconciles a push in about a second instead of on its 3-minute poll. On every push, ArgoCD's webhook handler asked for a refresh of every Application that tracks this repository: 10 apps, even for a commit that only touched docs. The repo server builds two manifests at a time, and two of the apps decrypt secrets through the KSOPS sidecar. The queue pushed some requests past the controller's 60-second deadline, ArgoCD cached the failures and paused retries, and five apps showed sync status `Unknown` until a hard refresh. Annotating the apps with `manifest-generate-paths` makes a push refresh only the apps whose own folder changed.

## Impact

Nothing was deployed wrongly and no data was at risk. For about 6 minutes, five apps (`root-apps`, `platform-namespaces`, `gateway-instance`, `smoke-test`, `tailscale-secret`) couldn't be compared with Git. A change pushed to one of them during that window would not have been applied until the error cleared. `Unknown` is the same signature as INC-2026-005, so a real fault there would also have been hidden behind it.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 02:29 | The GitHub webhook goes live (GOP-04). Ping returns 200 |
| 02:30 | First real push. ArgoCD refreshes all 10 repo apps; every one completes in time, and `root-apps` reconciles 1 s after the push |
| 02:46:09 | A redelivered push, sent to test the new WAF rule, refreshes all 10 apps |
| 02:46:47 | The next push arrives 38 s later and asks for all 10 again. Five manifest builds miss the 60 s deadline: `rpc error: code = DeadlineExceeded` |
| 02:48 | The GOP-06 check "every app is Synced and Healthy" fails on five `Unknown` apps |
| 02:49 to 02:52 | A hard refresh clears three. The KSOPS sidecar logs `Generating manifests with deadline -7s from now`: requests reach it after their deadline has passed. A KSOPS build run by hand inside the sidecar takes 2 s, so decryption itself isn't slow |
| 02:52 to 02:53 | The cached failures expire, the two KSOPS apps build, and all 17 apps are Synced and Healthy |
| 02:58 | Fix pushed: `argocd.argoproj.io/manifest-generate-paths: .` on the 10 repo apps (`a2b3aa5`) |
| 02:59:52 | Verified with a docs-only push (this review's commit, `7639a07`): ArgoCD logged the push event, requested no app refresh, and every app stayed Synced and Healthy |

## Root cause

ArgoCD's webhook handler refreshes every Application whose source is the pushed repository and branch, unless the Application declares which paths it depends on. None of ours did, so each push queued 10 manifest builds at once, regardless of what changed.

The repo server runs with `reposerver.parallelism.limit: 2`, sized for a 1 GB memory budget, and the two KSOPS apps go through a sidecar on top of that. Two refresh bursts 38 seconds apart filled the queue for longer than the controller's 60-second repo-server timeout. When a build fails a few times in a row, the repo server caches the error and stops retrying for a while, so the apps stayed `Unknown` after the queue had drained.

## Contributing factors

- The first push test passed. One push with nothing else queued fits within the deadline; it took two pushes close together, which the WAF test happened to produce.
- GOP-04's verification measured how fast one push reconciles. It never looked at what a push costs the repo server.
- The 3-minute poll spreads refreshes out, so the repo server's limits had never met a burst.

## What went well

- The sign-off checklist runs "every app is Synced and Healthy" as a hard check, and `Unknown` counts as a failure since INC-2026-005. It caught this within two minutes.
- The sidecar's own log line ("deadline -7s from now") separated a queueing problem from a slow-decryption problem quickly, and a 2-second manual build confirmed it.

## Where we got lucky

The burst happened while I was watching the cluster. With pushes spread over a normal day it would have been rare, and the cached error would have cleared on its own, so a later failure could easily have been put down to noise.

## Fix

`argocd.argoproj.io/manifest-generate-paths: .` on each of the 10 Applications sourced from this repository (`a2b3aa5`). A push now refreshes only the apps with a changed file under their own source path. `root-apps` covers `kubernetes/cluster/`, so editing any Application definition still refreshes it. The 3-minute poll is unchanged, so nothing is missed if a webhook is lost.

## Guardrails added

- The annotation is part of every repo-sourced Application. A new Application without it would bring back refresh-everything on push, so the Phase 02 sign-off checks that all of them carry it.
- The ArgoCD recovery runbook lists this signature next to the INC-2026-005 one.

## Lessons

- Moving from polling to push also changes the load on the repo server. Test with two events close together as well as one.
- Read the deadline in a timeout message. "Deadline in the past" means queueing; a slow operation would show a positive deadline running out.

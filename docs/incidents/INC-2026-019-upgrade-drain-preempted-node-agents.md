# INC-2026-019: The first K3s upgrade's drains pushed a node's load-balancer agent off it and left pods queued behind each other

| Field | Value |
|-------|-------|
| Date found | 2026-11-20 |
| Severity | SEV3 |
| Found by | Verification check |
| Duration | 2026-11-20 12:05 to 12:29 UTC (24 minutes; the node had no load-balancer agent for 4.5 of them) |
| Started | 2026-11-20 12:05 |
| Detected | 2026-11-20 12:07 |
| Resolved | 2026-11-20 12:29 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

The first run of the K3s upgrade playbook (5.59) moved the cluster from v1.36.4 to v1.36.6. When worker-02 was drained, the pods it held moved to worker-01. One of them, Paperless, filled worker-01's memory requests, and the scheduler made room by evicting the MetalLB speaker there: the per-node agent that answers for the cluster's LAN address. The speaker had no priority class, so it ranked below every app. Its replacement couldn't fit back, and worker-01, the node running the gateway that the LAN address points at, was left without anyone announcing that address. Apps kept answering because devices on the LAN still remembered the old announcement. Giving the per-node agents the priority Kubernetes reserves for them brought the speaker back in 4.5 minutes. Later, draining worker-01 queued pods behind each other the same way: Linkwarden landed on worker-02, where its image wasn't cached, and held the room ArgoCD needed, so its planned 5-minute outage lasted about 12. The upgrade also showed that the playbook's documented one-node-at-a-time commands didn't work.

## Impact

No data was lost. For 4.5 minutes worker-01 had no MetalLB speaker; LAN clients kept reaching the apps from their cached address entries, but any device that had to look the address up again in that window would have failed. Linkwarden was unreachable for about 12 minutes instead of the planned 5. ArgoCD's controller couldn't run for about 9 minutes (nothing to sync meanwhile). The database exporters were down for about a minute.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-20 12:00 | Control plane upgraded (2.5 minutes, snapshot `pre-upgrade-v1.36.4-k3s1` first). CoreDNS, a single replica, is replaced by K3s; cluster DNS is down for about 20 seconds |
| 2026-11-20 12:03 | `--limit k3s-worker-02` fails before touching the node: the workers' play read the target version from the control plane's play, which `--limit` skips |
| 2026-11-20 12:04 | Playbook fixed: each play reads the version pins itself |
| 2026-11-20 12:05 | worker-02 drained; Paperless moves to worker-01. The MetalLB speaker on worker-01 is evicted; its replacement stays Pending: "Insufficient memory" |
| 2026-11-20 12:07 | Seen in the post-step checks. Every app still answers on the LAN |
| 2026-11-20 12:08 | MetalLB speaker, node exporter and Alloy given `system-node-critical` (Git, ArgoCD) |
| 2026-11-20 12:10 | The speaker is back on worker-01, having evicted the database exporters (no priority class) to fit |
| 2026-11-20 12:11 | Paperless restarted; it goes back to worker-02, which it prefers, and the exporters schedule |
| 2026-11-20 12:16 | worker-01 drained (planned database outage). Linkwarden moves to worker-02 and evicts ArgoCD's pods there |
| 2026-11-20 12:21 | worker-01 back on v1.36.6; PostgreSQL ready at 12:20:58. Linkwarden still pulling its image on worker-02; ArgoCD Pending, pinned to the full worker-02 |
| 2026-11-20 12:28 | worker-02 cordoned for a moment, Linkwarden restarted onto worker-01 (image cached), worker-02 uncordoned: ArgoCD schedules |
| 2026-11-20 12:29 | All pods running, all ArgoCD apps Synced and Healthy, every app answers on the LAN and the tailnet |

## Root cause

A drain moves a node's pods onto the other worker, and the scheduler never moves them back. Each worker has about 2.5 GiB of allocatable memory and neither can hold the other's pods, which the drain check had already shown. What it didn't show is who loses when a node fills up: pods with a higher priority class evict lower ones, and the three per-node agents (MetalLB's speaker, node exporter and Alloy) had none, so they ranked below every app. A DaemonSet's pod can only run on its own node, so once evicted it waits there until room appears, and nothing makes room.

The same mechanism made the second drain slow: Linkwarden (priority `apps`) evicted ArgoCD (no priority class) on worker-02, and ArgoCD, pinned to worker-02, could only come back once Linkwarden left.

## Contributing factors

- **Priority classes were set for the apps (4.19) but never for the cluster's own agents.** The design covered who gets the room between apps, not whether the node's own agents could be pushed out.
- **The drain check reports what moves and what waits, not what gets evicted on the receiving node.**
- **Pods don't move back after an uncordon.** The runbook said so and called it fine; with two full workers it isn't.
- **The playbook's one-node commands had never been run.** The runbook documented `--limit k3s-worker-02`, which failed.
- **The hypervisor is at its memory ceiling.** The drains made every VM touch its full memory, and the host has stayed at about 440 MB available since (`ProxmoxMemoryCritical`). The RAM upgrade (5.57) is the fix.

## What went well

- Upgrading one node at a time, with checks between, found each problem while the next node was still untouched.
- The playbook stopped at the version check before touching a node, so its own bug cost nothing.
- The pre-upgrade etcd snapshot and the kept binaries meant a rollback was one command away throughout; none was needed.
- The cordon-and-restart move put every pod back where it belongs without another drain.

## Where we got lucky

The LAN address stayed reachable only because devices had cached it. Had a device's cache expired in those 4.5 minutes, LAN access to every app would have failed with nothing in the cluster reporting an error: MetalLB's controller was healthy, and only the missing speaker pod showed it.

## Fix

- MetalLB's speaker, node exporter and Alloy run at `system-node-critical`, so an app can't evict them and they evict lower-priority pods to come back.
- `k3s-upgrade.yml`: each play reads the pins itself, so one-node runs work.
- The runbooks now say to put moved pods back after each drain (section 4 of the K3s upgrade runbook).

## Guardrails added

- The priority classes above.
- The K3s upgrade runbook's checks now include "every DaemonSet has a pod on every node" and "pods are back on their preferred node".

## Lessons

- Give every per-node agent a node-critical priority: an app should never be able to take a node's networking, metrics or logs away.
- On a cluster with no spare capacity, a drain isn't over at the uncordon: put back what moved.
- Run every documented command form at least once before calling a runbook operational.

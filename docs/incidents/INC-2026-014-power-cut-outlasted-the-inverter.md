# INC-2026-014: A power cut outlasted the inverter and took the home lab down for 15 hours

| Field | Value |
|-------|-------|
| Date found | 2026-11-17 |
| Severity | SEV3 |
| Found by | Alert |
| Duration | 2026-11-17 15:13 to 2026-11-18 06:16 UTC (about 15 hours, the whole home lab) |
| Started | 2026-11-17 15:13 (mains power had been off since about 08:40) |
| Detected | 2026-11-17 15:14 |
| Resolved | 2026-11-18 06:32 (cluster healthy, data checked, backups caught up) |
| Cause | Platform |
| Status | Fixed and verified for the backup gap. Power resilience is open |

## Summary

A regional power cut lasted more than eight hours. The inverter carried the home lab for about six and a half, then ran out, and the hypervisor and its three VMs lost power with no warning, because the hypervisor is a laptop with no battery fitted. Recovery the next morning took about two hours longer than a plain power-on. A BIOS reset during troubleshooting had turned hardware virtualisation off, so the VMs could not start. Three smaller problems then showed up one after another: GitOps could not render the apps that hold secrets, a backup Job lost its first connection, and the etcd backup chain could not run because no snapshot had been taken that night. No data was lost.

## Impact

- Everything on the cluster was down for about 15 hours, including the three apps that had moved there that day (a notes app, a knowledge base and a developer toolbox).
- The cloud-hosted monitoring stayed up and paged at once.
- The nightly offsite copy of app data ran on boot and succeeded. The etcd offsite copy for that night was about ten hours late, and it ran only after a manual snapshot.
- No data was lost. A restore drill after recovery loaded every app database with row counts equal to the dump, and every app file was present.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-17 08:38 | The last hypervisor journal entry that survived. Its journal from here to the power loss was lost |
| 2026-11-17 ~08:40 | Mains power fails across the region. The inverter takes over |
| 2026-11-17 15:13 | The inverter runs out. The hypervisor and all three VMs lose power mid-write, on the day of the first app migrations |
| 2026-11-17 15:14 | The cloud monitoring alerts: hypervisor, nodes and apps down. The operator's workstation loses the cluster API |
| 2026-11-17 15:24 | The hypervisor has not come back. Its panic auto-reboot (INC-2026-012) cannot help, because no panic happened |
| 2026-11-18 03:28 | Power is back and the hypervisor boots. While troubleshooting, the operator had removed the CMOS battery, so the firmware is at its defaults and the clock reads April |
| 2026-11-18 03:28 | The missed backup timers catch up at once. The etcd offsite stage fails, with the control VM down and the clock wrong. The app data offsite stage succeeds at 03:31 |
| 2026-11-18 03:39, 04:03 | Two more power cycles while troubleshooting |
| 2026-11-18 04:05 | The VMs fail to start: "KVM virtualisation configured, but not available". The kernel log says VMX is disabled by the BIOS |
| 2026-11-18 06:10 | Virtualisation re-enabled in the BIOS. The host reboots and starts all three VMs |
| 2026-11-18 06:16 | All nodes Ready, all pods Running |
| 2026-11-18 06:20 | Six apps that render through the SOPS plugin show `Unknown`. Their manifest builds timed out during the cold start, and the repo server cached the failure |
| 2026-11-18 06:28 | Repo server restarted and the six apps refreshed one at a time. All 24 apps Synced and Healthy |
| 2026-11-18 06:30 | A manual database dump fails its first attempt (connection refused) and passes on retry |
| 2026-11-18 06:31 | Fix pushed: the dump Job waits for PostgreSQL (`2f2bce5`). The next dump passes on its first attempt, and the restore drill passes with 4 databases and 120 tables |
| 2026-11-18 06:32 | The etcd chain's own freshness check refuses it, since no snapshot is under 26 hours old. A manual snapshot is taken and all three stages pass |
| 2026-11-18 07:00 | Fix deployed: the sync stage waits for the clock and the control VM, and takes a snapshot when none is under a day old (`a947bb9`) |

## Root cause

The home lab runs from an inverter with about six and a half hours of runtime at this load, and the power cut lasted longer. The hypervisor has no battery of its own, so it lost power the moment the inverter stopped, with no shutdown.

## Contributing factors

- Nothing measures the inverter's charge, so nothing could shut the lab down cleanly before it went flat.
- Removing the CMOS battery during troubleshooting set the firmware to its defaults, and on this laptop that means virtualisation off. A simple power-on became two more hours of diagnosis.
- K3s takes its etcd snapshot only at 02:00. The cluster was down at that hour, so no snapshot existed for the day, and the chain's 26-hour freshness check would have refused every run until the next night.
- The backup timers catch up at boot, before the clock is synchronised and before the VMs are up. The etcd stage failed for that reason before anyone was looking.
- The SOPS plugin is slow on a cold start. Six apps now render through it, up from two at INC-2026-013. With every app reconciling at once, their builds ran past the controller's timeout and the repo server cached the error.
- A new pod's network policy takes a moment to apply, and a new backup pod had its first connection to PostgreSQL refused.
- The hypervisor's journal lost its last six and a half hours, so the logs could not show whether this was a crash or a power loss. The operator's report of the power cut settled it.

## What went well

- Monitoring on the cloud host paged within a minute and stayed up through the outage, which is why it does not run on the cluster.
- Every backup stage that could not run safely refused and said so. The freshness checks stopped the etcd stages, and the success-only heartbeats stayed silent. No stage wrote a stale copy and reported success.
- The data checks already existed as tools. `dr:drill:k8s` and the per-table row counts proved the restored state in under a minute.
- The app data offsite copy needed no help. It ran on boot from data already on disk and succeeded.

## Where we got lucky

- The power failed after the first two app migrations had finished and their data had been checked.
- The old copies of the moved apps were still on the cloud host, stopped but intact. They were the fallback if the cluster data had been damaged.

## Fix

- The etcd snapshot gap: `infrastructure/ansible/playbooks/proxmox-etcd-sync.yml` (`a947bb9`). The sync stage waits up to 15 minutes for the clock to synchronise and the control VM to answer. If the control VM has no snapshot from the last 24 hours, it takes one, named like the scheduled ones so the later stages count it.
- The dump Job: `kubernetes/platform/databases/backup.yaml` (`2f2bce5`). It waits up to 30 seconds for PostgreSQL before its first connection.
- Recovery: virtualisation re-enabled in the BIOS, the repo server restarted, and a manual etcd snapshot and chain run for the missed night.

## Guardrails added

- The sync stage takes its own snapshot when the scheduled one was missed, so one night of downtime no longer blocks the next day's offsite copy.
- The sync stage will not run on an unsynchronised clock.
- ArgoCD (18 Nov, `kubernetes/bootstrap/argocd/values.yaml`): the SOPS plugin's CPU limit went from 100m to 500m (request unchanged), the controller's repo-server timeout from 60 to 180 seconds, and the repo server's pause after failed builds from 60 to 5 minutes. Rehearsed: with the repo server restarted, all seven SOPS apps refreshed at once were Synced in 63 seconds, with builds of 2 to 8 seconds instead of 14 to 27.

Still open:

- Power: a UPS sized for the hypervisor and router, or a battery in the laptop, and a warning before the inverter runs out.
- Logs: flush the hypervisor's journal to disk more often and send kernel messages to another machine, so the next unexplained outage leaves evidence.
- Runbook: note in the hypervisor recovery runbook that a BIOS reset turns virtualisation off, with the kernel line that confirms it.

## Lessons

- Recovery problems show up in the order things come back. Firmware, GitOps, a backup Job and the backup chain each failed only once the layer below was up, and most of them appear only after a full cold start. A cold start is worth rehearsing on purpose.
- A freshness check that refuses is right, but it needs a way to catch up, or one missed night turns into a day without offsite copies.
- Before resetting hardware, check what the reset will undo. Here it was one BIOS setting, and it cost two hours.

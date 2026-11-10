# INC-2026-008: Starting a backup timer also ran its job, and the stages ran on two clocks

| Field | Value |
|-------|-------|
| Date found | 2026-11-05 (seen live; first described in the 2 Nov review) |
| Severity | SEV3 |
| Found by | Verification check |
| Duration | 2026-11-02, when the DR timers were created, to 2026-11-10, when two clean unattended nights were confirmed |
| Status | Fixed and verified |

## Summary

The etcd DR pipeline has three stages on the hypervisor: pull the snapshots from the control VM, back them up to a local encrypted restic repository, and copy that repository offsite to B2. Each stage has its own systemd timer. All three timer units declared `Requires=` on their service, which made systemd start the job whenever the timer itself started: on a `systemctl start`, a restart, or a boot. On 5 Nov that made two stages start at the same moment as a playbook's own runs, and the timer-started runs failed on the restic lock. The same review found two more faults in the pipeline. The restic stage exited 0 when there was nothing to back up, and the K3s snapshot ran on IST while the hypervisor's timers ran on UTC. The timers now carry no `Requires=`, all stages share one lock and one clock, and an empty input fails the run.

## Impact

No data was lost and every scheduled night produced a backup. Three runs failed on a lock (one on 2 Nov, two on 5 Nov) while a parallel run of the same stage succeeded, so each failure left a red unit beside a good copy.

What was at risk:

- After any reboot, all three stages would have started at once, with the restic and B2 copies racing the pull they depend on.
- The local copy ran six hours after the snapshot instead of 30 minutes, so the offsite copy could be up to about 31 hours old instead of 25.5.
- A restic run with no input reported success. Any heartbeat built on that exit code would have said "healthy" for a backup that never ran.

## Timeline

All times UTC. IST is UTC+5:30.

| Time | Event |
|------|-------|
| 2026-11-02 | The three DR stages are deployed with Ansible. Each timer has `Requires=` on its service, and the schedules are 02:30, 03:00 and 03:30 UTC. While the B2 stage is being set up, its timer start and the playbook's initial run collide on the restic lock |
| 2026-11-02 | The Phase 03 review lists `Requires=` on the timers (N1), the exit 0 on empty input (N2) and the clock mismatch, and links the B2 collision to N1 |
| 2026-11-05 | While the DR storage is moved to the ZFS pool (HARD-23), the timers are restarted. `Requires=` starts the restic and B2 jobs alongside the playbook's own runs. The timer-started runs fail with restic exit 11 (repository locked), and the playbook's runs succeed |
| 2026-11-05 15:55 | Fix applied (`778c9d0`): no `Requires=`, every timer on `Asia/Kolkata`, one shared `flock` for all stages, empty input fails. Checked: restarting a timer doesn't start its job, and a restic run queued at 15:57:51 waits on the held lock, then succeeds |
| 2026-11-06 21:00 to 22:00 | First unattended night on the new schedule. The timers fire in order at 02:30, 03:00 and 03:30 IST. The pull fails for an unrelated reason ([INC-2026-010](INC-2026-010-host-keys-regenerated-on-reboot.md)), and the restic and B2 stages succeed on the previous day's mirror |
| 2026-11-08 | Heartbeats and a snapshot-age check are added to the stages (`d0b8866`) to close the gap the 6 Nov night exposed |
| 2026-11-08 to 2026-11-10 | Two clean unattended nights. All three stages succeed on time, and every DR heartbeat monitor stays up |

## Root cause

In a `.timer` unit, `Requires=` doesn't mean "this timer needs the service to exist". It's an ordinary unit dependency, so starting the timer also starts the service it names. A timer already triggers the service with the same name, so the line added nothing except this side effect. Each playbook then started its timer and ran the stage once by hand, which put two runs of the same stage in flight at once. The service units' `After=` lines didn't help. They order jobs that systemd queues together, and they don't stop a manual run that is already holding the restic lock.

The clock mismatch had a separate cause. K3s takes its snapshot at 02:00 in the node's own time zone, which `common.yml` sets to IST. The hypervisor's timers were written in UTC.

## Contributing factors

- Each stage was written and tested on its own, so the clash only appeared when a playbook started a timer and ran the stage in the same few seconds.
- A failed run sitting next to a successful one looks like a one-off. The 2 Nov collision was linked to `Requires=` in review, but nothing was changed until the same failure came back on 5 Nov.
- The restic script treated an empty input directory as a warning, so no one looked at what "success" meant until the review.
- The schedules sat in three playbooks, and nothing compared them with the K3s snapshot time.

## What went well

- The restic repository lock did its job. Each colliding run failed cleanly, and no repository was corrupted.
- The review caught the clock mismatch and the empty-input exit before either caused a missing backup.
- The fix was checked with a deliberate collision: a held lock made a queued restic run wait instead of fail.

## Where we got lucky

A reboot is the case where `Requires=` starts every stage at once. The hypervisor's journal no longer covers 2 to 5 Nov, so we can't say whether that happened. If it did, the restic lock would have made the extra runs fail without damaging a repository. The unclean restarts later that week came after the fix.

## Fix

Commit `778c9d0`, in the three DR playbooks under `infrastructure/ansible/playbooks/`:

- The timers have no `Requires=`. They run at 02:30, 03:00 and 03:30 `Asia/Kolkata`, 30 to 90 minutes after the 02:00 IST snapshot. The offsite copy is now at most about 25.5 hours old.
- Every path that runs a stage, timer or playbook, takes `flock -w 3600 /run/lock/k3s-etcd-dr.lock` first, so stages queue instead of colliding.
- The restic stage exits 1 when the snapshot directory is empty.
- A playbook restarts a timer only when its unit file changed, and a restart no longer runs the job.

## Guardrails added

- Each stage pushes a heartbeat to the DMZ observer only after it succeeds, so a failed or missing run pages (HARD-06).
- The restic and B2 stages fail when the newest snapshot is more than 26 hours old, which covers what the empty-input check misses: a stale mirror (added after the 6 Nov night).
- The playbook comment on each timer explains why `Requires=` must stay out.

## Lessons

- In systemd, `Requires=` in a timer starts the service it names. A timer triggers its same-named service on its own, or the one named in `Unit=`, and needs no dependency on it.
- A pipeline split across machines needs one clock, written down next to the first stage.
- "Nothing to do" is a failure for a backup job. Exit non-zero and let the alerting decide.

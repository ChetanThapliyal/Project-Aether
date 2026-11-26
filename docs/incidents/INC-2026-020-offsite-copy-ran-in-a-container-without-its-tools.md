# INC-2026-020: The cloud host's nightly offsite copy failed for four nights because the scheduler's container lacked its tools

| Field | Value |
|-------|-------|
| Date found | 2026-11-25 |
| Severity | SEV3 |
| Found by | Alert (Kestra's failure notice; the offsite heartbeat monitor went down on 22 Nov) |
| Duration | 2026-11-21 03:00 to 2026-11-25 03:38 UTC (4 days; five nightly runs failed) |
| Started | 2026-11-21 03:00 |
| Detected | 2026-11-21 03:23 |
| Resolved | 2026-11-25 03:38 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

On 20 November the cloud host's nightly backup gained an offsite step: after the restic backup, a script restores the newest snapshot, compresses and encrypts it, and uploads it to the Object Lock bucket. The script needs `rclone`, `zstd` and `age`. I tested it by hand on the host, where all three are installed. The nightly run does not happen on the host: Kestra runs `run-backup.sh` inside a small Alpine container that installs only what the original backup needed. From the next night the offsite step exited with "command not found" (exit 127). The restic backup and its own heartbeat had already finished by then, so the local backup stayed healthy, but the run failed after three retries every night, no offsite copy was made, and the offsite heartbeat stopped. The flow now installs the missing tools and mounts the host's pinned `rclone`, and the script checks its tools first and says which one is missing.

## Impact

No data was lost and no service was affected. The cloud host's restic repository, which is in the same tenancy as the host, ran every night. The copy outside the tenancy was stale: the last good one was from 20 November, so for four nights losing the tenancy would have lost up to five days of changes instead of one. Each failed run also held a Kestra worker for about 23 minutes (three attempts, ten minutes apart) and sent a failure notice to Telegram.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-20 03:00 | Last nightly run before the change: succeeds |
| 2026-11-20 10:52 | First offsite copy into its own bucket, run by hand on the host (INC-2026-018 had just fixed the upload) |
| 2026-11-20 13:57 | The offsite step is added to the end of `run-backup.sh` |
| 2026-11-21 03:00 | First nightly run with the step: the restic backup and its heartbeat succeed; the offsite step fails with `rclone: command not found`, then `zstd` and `age` |
| 2026-11-21 03:23 | Third retry fails; Kestra sends its failure notice to Telegram |
| 2026-11-22 03:23 | Same failure again; no cause in the notice |
| 2026-11-22 14:56 | The offsite heartbeat monitor goes down |
| 2026-11-23, 24, 25 | The same failure each night |
| 2026-11-25 03:22 | Fifth failed run |
| 2026-11-25 03:25 | Cause read from Kestra's logs |
| 2026-11-25 03:28 | The offsite step run by hand inside the flow's exact container recipe, with `zstd` and `age` added and the host's `rclone` mounted: 17,912 files restored, 1.3 GB uploaded, object confirmed |
| 2026-11-25 03:35 | Fix committed (`48e4e97`), CI green, script redeployed, flow synced |
| 2026-11-25 03:38 | The real flow run through Kestra succeeds; both heartbeats are up |

## Root cause

The offsite script was written and tested in one environment and run in another. On the host, Ansible installs `rclone`, `zstd` and `age`. The scheduler runs the backup script in a throwaway `docker:cli` container whose package list (`bash restic curl util-linux`) predates the offsite step, and nothing connected the new script to that list. The script's shell options did the rest correctly: a missing command exited the run, so no false success was reported and no heartbeat was sent. The first scheduled run was also the first time the step ran under the scheduler.

## Contributing factors

- **The test used a different runtime.** The 20 November first run was watched by hand, as my own rule says, but on the host. The rule should have said: run the first time through the scheduler that will run it.
- **The failure notice carries no cause.** It names the flow and the execution, so finding the reason means reading Kestra's logs.
- **The retry is built for transient failures.** A missing command fails three times, ten minutes apart, and says the same thing each time.
- **Two signals, one real action.** The restic heartbeat stayed green (correctly: that backup worked), so the only signals were the Telegram notice and the offsite monitor going down a day later.
- **The container recipe was in a different file from the script.** The flow, the template and the Ansible task that installs the host's tools are three places, and a change to one doesn't point at the others.

## What went well

- The script refused to report success: no copy, no heartbeat, a failed run.
- The restic backup and its heartbeat ran first, so the local repository was never at risk.
- The previous offsite copy stayed in the bucket (the 3-day lifecycle had not yet removed it), so there was always one.
- Running the step by hand inside the flow's exact container recipe found nothing further missing before the real run.

## Where we got lucky

The bucket keeps copies for only about three to four days. Had the lifecycle removed the 20 November copy before the fix, the cloud host would have had no offsite copy at all for a night or two. It was still there at 03:38 on 25 November.

## Fix

- **`restic-nightly` flow:** installs `zstd` and `age` from Alpine, and mounts the host's pinned `rclone` (`/usr/local/bin/rclone`, which Ansible symlinks to the version in use). Alpine's own `rclone` is older, and B2's v1 API refuses bucket-scoped keys.
- **`offsite-b2.sh`:** checks for `restic`, `rclone`, `zstd`, `age`, `tar` and `curl` first and says which one is missing, and that the script runs inside the flow's container.

## Guardrails added

- The preflight check above, so the next missing tool is named instead of being an exit code.
- The comment in the flow explains why each tool is there and which file needs it, so a change to the script points at the flow.

## Lessons

- **Test a new job through the scheduler that will run it.** Running it by hand on the host proves the script, not the job. Do that first, and always do the scheduled path next.
- **A script that runs in a container needs its tool list next to it.** Whoever adds a command to the script owns the container's package list.
- **Say why in the failure notice, or make the failure visible where the cause is.**

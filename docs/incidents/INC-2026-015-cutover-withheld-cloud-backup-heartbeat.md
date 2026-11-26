# INC-2026-015: Moving two apps off the cloud host made its nightly backup report failure

| Field | Value |
|-------|-------|
| Date found | 2026-11-18 |
| Severity | SEV3 |
| Found by | Alert |
| Duration | 2026-11-18 03:00 to 07:49 UTC (one nightly run) |
| Started | 2026-11-18 03:00 |
| Detected | 2026-11-18 04:00 |
| Resolved | 2026-11-18 07:49 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

On 17 November two apps, a notes app and a knowledge base, moved from the cloud host to the cluster. Their old containers on the cloud host were stopped and kept for a week as a fallback. The cloud host's nightly backup script still dumped both of their databases with `docker exec`, which fails on a stopped container. The script did what it is designed to do on a failed dump: it finished the backup, then withheld its heartbeat, and the monitor went down. Removing the two dumps fixed it, and a manual run brought the heartbeat back.

## Impact

- No data went unprotected. The restic snapshot still ran and copied everything under the app directory, including the stopped databases' data directories, which are consistent while their containers are stopped. The last database dumps from the night before stayed in place.
- The backup monitor showed the cloud host's backup as failed for about five hours, and a real failure in that window would have looked the same.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-17 ~13:45, ~15:09 | The two apps' cloud-host stacks are stopped by Ansible after their data is restored on the cluster |
| 2026-11-18 03:00 | The nightly backup runs. Two of its database dumps fail on the stopped containers; restic still takes its snapshot; the heartbeat is withheld |
| 2026-11-18 04:00 | The edge Uptime Kuma marks the backup heartbeat down |
| 2026-11-18 07:45 | Found while checking how a new app would be backed up on the cloud host |
| 2026-11-18 07:46 | Fix deployed: the two dumps removed from the backup script (`afd39c0`) |
| 2026-11-18 07:49 | Manual run: snapshot saved, heartbeat received, monitor up |

## Root cause

The backup script names each database it dumps, by container. The migration plan listed what to stop on the cloud host and what to remove a week later (a cleanup list: compose project, Ansible block, proxy node, checks, secrets, directory), but not the backup script's dump list. Stopping the containers was the first step of the move, so the script broke a week before the plan expected to touch it.

## Contributing factors

- The cutover checklist treated "stop the old copy" as a no-op for everything else on the host. A stopped container is still referenced by other jobs.
- The failure surfaced only as a missing heartbeat. The alert came during the home lab outage of the same night (INC-2026-014) and went unnoticed among that outage's alerts.

## What went well

- The script refused to report success with two dumps failed. The heartbeat-on-success design (INC-2026-001) made a partial backup visible.
- The rest of the backup still ran, so the gap cost no protection.

## Where we got lucky

The alert overlapped with the home lab outage and could have been dismissed with it. It was noticed only because a new app's backup path was being checked the same morning.

## Fix

`infrastructure/ansible/templates/backup.sh.j2` (`afd39c0`): the dumps of the two moved databases are removed, with a note on why their data directories are still covered. Deployed with `oci-ops.yml --tags backup` and verified with a manual run.

## Guardrails added

- The cutover checklist for a moved app now includes "remove its database from the cloud host's backup script" at the moment the old copy is stopped, not at the later cleanup.

## Lessons

- Stopping something is a change for every job that refers to it. Before stopping a service, search the repository for its name.
- A heartbeat that goes quiet on partial failure is worth the occasional false alarm, but each one needs looking at even when something larger is going on.

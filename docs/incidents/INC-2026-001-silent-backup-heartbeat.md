# INC-2026-001: Nightly backups reported success while their heartbeat never arrived

| Field | Value |
|-------|-------|
| Date found | 2026-11-02 |
| Severity | SEV2 |
| Found by | Audit |
| Duration | Unknown start (the heartbeat monitor had never received a push) to 2026-11-03 |
| Status | Fixed; awaiting the first scheduled run to confirm |

## Summary

The app host backs up its databases and data to S3-compatible storage with restic every night. Success is meant to be confirmed by a push heartbeat to Uptime Kuma on the DMZ observer, which alerts if a day passes without one. The heartbeat had never arrived. A shell quoting bug turned the push URL into an empty string, and the script was written so that this failure, and several others, could not surface. The script now fails fast, sends the heartbeat only after every step succeeds, and refuses to run twice at once.

## Impact

Backups were being taken. Nothing proved they were good, and the monitor that should have proved it was red the whole time, so it carried no signal. Three silent failure paths existed:

1. The heartbeat was never sent, so a night with no backup looked the same as a night with one.
2. A failed `restic backup` still printed `Backup Complete!`.
3. Each `pg_dump` ended in `|| true`, so a failed dump would have backed up the previous day's SQL file without warning.

This review did not check past runs for failed dumps. No restore was needed during the incident.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| Unknown | The heartbeat monitor is created. It never receives a push |
| 2026-11-02 | A platform audit finds the monitor permanently DOWN and traces the cause to the env file |
| 2026-11-02 | The audit also finds two schedulers, a root cron job at 03:00 and a Kestra flow at 03:30, both running the backup every night |
| 2026-11-03 13:45 | The fixed script runs from Kestra. Snapshot saved, `restic check` clean, heartbeat received |
| 2026-11-03 13:54 | A negative test (a deliberately broken `pg_dump`) withholds the heartbeat as intended, but stops on a restic repository lock |
| 2026-11-03 | The lock is traced to the test being started twice, 11 seconds apart. A run lock is added to the script |

## Root cause

The env file was rendered by Ansible without quoting:

```bash
export UPTIME_KUMA_PUSH_URL=https://<observer>/api/push/<token>?status=up&msg=OK&ping=
```

When the script ran `source restic.env`, bash treated each `&` as "run in the background". The `export` received only the text before the first `&`, inside a background subshell, so the variable in the script stayed empty. The script then ran `curl -s ... "$UPTIME_KUMA_PUSH_URL" || true`, which failed silently on an empty URL.

## Contributing factors

- The script had no `set -e`, so a failed command did not stop it, and it ended with an unconditional success message.
- Every risky command ended in `|| true`, which hid exit codes by design.
- The monitor had been red since it was created. A permanently red monitor looks like a known issue, not an alert.
- Two schedulers ran the same job, so nothing stopped two backups from overlapping on the same repository.

## What went well

- The audit compared what the monitor reported with what the script did, and did not stop at "backups exist".
- The fix was proved with a negative test. That test found the next problem, overlapping runs.

## Where we got lucky

No restore was needed while the backups were unverified. The first `restic check`, on 3 Nov, found no errors in the repository.

## Fix

Commits `0826dc5` and `ffbc283`.

- [`oci-ops.yml`](../../infrastructure/ansible/playbooks/oci-ops.yml) renders every value in the env file with Ansible's `quote` filter. The same task now removes the legacy cron entry, leaving Kestra as the only scheduler.
- [`backup.sh.j2`](../../infrastructure/ansible/templates/backup.sh.j2) runs with `set -Eeuo pipefail` and stops at once if the push URL is empty. Each database dump goes to a temporary file and replaces the old one only on success. The script adds `restic check`, takes a `flock` run lock so a second run exits, clears stale restic locks, and sends the heartbeat only if every step passed.
- [`restic-nightly.yml`](../../automation/kestra/flows/ops/restic-nightly.yml) moves the schedule to 03:00 UTC, now the single run time, and installs `flock` in the task container.

## Guardrails added

- The heartbeat is the last step, so the 24-hour push monitor pages on a missed night and on a failed one.
- The negative test (break one dump, expect `heartbeat withheld` and exit code 1) is part of the runbook for any change to the script.
- The run lock makes a second, overlapping run exit with an error instead of contending for the repository.

## Lessons

- Quote everything that goes into a file other programs will `source`. A URL query string is shell syntax.
- `|| true` in a backup script turns every failure into a success. Fail fast, then decide in one place what counts as success.
- A monitor that has never been green is not monitoring. Treat "always red" as an incident.

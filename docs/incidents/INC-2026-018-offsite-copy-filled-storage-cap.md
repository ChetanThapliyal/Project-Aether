# INC-2026-018: The first offsite copy of the cloud host uploaded itself five times and filled the backup account's storage cap

| Field | Value |
|-------|-------|
| Date found | 2026-11-20 |
| Severity | SEV3 |
| Found by | Verification check |
| Duration | 2026-11-20 07:36 to 10:57 UTC (3 h 21 min; the account refused uploads from 08:11) |
| Started | 2026-11-20 07:36 |
| Detected | 2026-11-20 08:12 |
| Resolved | 2026-11-20 10:57 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

Task 5.61 added a nightly offsite copy of the cloud host's backup to the Object Lock bucket on Backblaze B2. On its first run, watched by hand, the upload tool sent the same 1.9 GiB file five times. Each finished upload became another version, and the bucket's 30-day lock meant none could be deleted. The sixth attempt was refused: the account had reached its storage cap, which had been left at the free 10 GB. Every upload to that account was blocked from then on, including the homelab's nightly etcd and app copies, which would have failed that night. A second limit showed up while checking the copy: downloading it to prove it could be restored used up the free daily download allowance, which would block a real restore the same way. Both caps were raised, the upload was fixed to make one attempt only, and the cloud host's copy moved to its own bucket with a 3-day lock.

## Impact

No data was lost and no service went down. For 2 h 46 min the backup account accepted no uploads; had it lasted into the night, the homelab's offsite etcd and app copies (03:30 and 04:00 IST) would have failed and paged. The five duplicates, 7.6 GiB, stay locked in the homelab bucket until about 20 Dec and keep the account above its free tier until then, at a cost of cents. Restores from B2 were blocked from about 08:25 until the download cap was raised.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-20 07:22 | First run of the new offsite copy: `restic dump` of the morning's snapshot, compressed and encrypted to a temp file |
| 2026-11-20 07:35 | Upload of the 1.9 GiB file starts |
| 2026-11-20 07:36 | The first complete version lands. rclone starts the whole copy again |
| 2026-11-20 07:42, 07:48, 07:54, ~08:00 | Four more complete versions of the same file |
| 2026-11-20 08:11 | The next attempt is refused: `storage_cap_exceeded`. The script stops without sending its heartbeat |
| 2026-11-20 08:12 | Seen in the run's output; the bucket's versions listed: five copies of one file, 9.6 GiB in the bucket against a 10 GB cap |
| 2026-11-20 08:15 | Downloading the copy to prove it decrypts starts; it completes at 08:28 (21,290 entries, 3.84 GiB) and exceeds the free 1 GB daily download allowance on the way |
| 2026-11-20 08:26 | Upload fixed (one stream, one whole-copy attempt) and deployed; a rerun finds the object present, skips the upload and sends the first heartbeat |
| 2026-11-20 before 10:51 | The owner raises the daily caps: storage to $0.01 (about 53 GB), downloads to $0.10 (about 11 GB) |
| 2026-11-20 10:51 | Terraform applied: a bucket of its own for the cloud host, `aether-oci-offsite-lock`, 3-day lock; the upload key moved to it |
| 2026-11-20 10:57 | First copy into the new bucket, metrics and logs left out: 1.25 GiB, exactly one version, 5.5 minutes in all |

## Root cause

The script uploads a temp file with `rclone copyto`. Above 200 MB, rclone switches to a multi-thread copy that sends the file in parallel parts. Something after each finished upload counted as a failure, so rclone's whole-copy retry ran the upload again, three retries by default and more on top. The log at the default level doesn't say what failed. A likely cause is a step after the upload that needs to read the object, which this key deliberately can't. On an ordinary bucket a repeated upload replaces the file. In this bucket every upload is a new version that the lock keeps for 30 days, so each retry added 1.9 GiB that no one could delete.

The homelab's uploads never hit this: its etcd copies are a few MB, below the multi-thread threshold, and its app copy is streamed with `rclone rcat`, which doesn't retry a whole stream.

## Contributing factors

- **The account caps had never been looked at.** Both were at the free tier, which the homelab's small copies had never come near. A 1.9 GiB copy was always going to cross the storage cap within a few nights, even without the duplicates.
- **A locked bucket turns retries into cost.** The settings that make the backup tamper-proof also make every duplicate permanent for the lock period.
- **One bucket for everything.** The cloud host's copy shared the homelab's bucket and its 30-day lock, so a mistake in the new job used up the space the existing jobs needed.
- **The restore path depended on an account setting nobody had written down.** No runbook mentioned the download cap.

## What went well

- The first run was watched rather than left for the night, so the problem was found within the hour and before it could break the homelab's backups.
- The script refused to report success: no heartbeat was sent while the copy wasn't confirmed.
- The temp-file design held: no partial object was ever stored.
- The check that skips an object already in the bucket made the rerun safe.

## Where we got lucky

The run was started by hand in the morning. As planned, it would have first run at the end of the 03:00 UTC backup, just before the homelab's copies, and the cap would have stopped those the same night. Each would have paged, but the cause, a different job in the same account, would not have been obvious from the homelab's side.

## Fix

- **Upload:** `rclone copyto --retries 1 --multi-thread-streams 0`: one stream, one whole-copy attempt. A failed run sends no heartbeat, and a rerun finds the object already there.
- **Its own bucket:** `aether-oci-offsite-lock`, with a 3-day lock, hidden on day 3, deleted a day later, so about four nightly copies are kept. This copy only covers losing the tenancy; the host's restic repository keeps the history. The homelab keeps its 30 days.
- **A smaller copy:** Prometheus and Loki data are left out (the script restores the snapshot without them, then tars it), from 1.9 to 1.25 GiB.
- **Caps:** storage $0.01/day, downloads $0.10/day, with the alert emails left on.

## Guardrails added

- The upload can no longer create more than one version per run.
- The account's caps are recorded in the DR README's known gaps, and every B2 restore step (Scenarios 02 and 03) now says to check the download cap first.
- The B2 alert emails at 75% and 100% of each cap stay on, now against caps sized for real use.

## Lessons

- In a locked bucket, a retry is never free: check that every upload path makes exactly one attempt before its first run.
- A new job in a shared account inherits that account's limits; check them before adding something ten times bigger than what is already there.
- A restore that has never been run from the account can depend on settings no runbook mentions. Downloading a copy is the test that finds them.

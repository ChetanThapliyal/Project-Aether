# INC-2026-010: An unclean hypervisor restart regenerated every VM's SSH host keys, and the DR sync failed silently

| Field | Value |
|-------|-------|
| Date found | 2026-11-07 |
| Severity | SEV2 |
| Found by | Verification check |
| Duration | 2026-11-06 08:13 to 2026-11-07 06:11 UTC (about 22 hours without a fresh local DR copy) |
| Status | Fixed and verified; silent-failure alerting tracked under the heartbeat work |

## Summary

The hypervisor lost power without a clean shutdown and came back about 70 minutes later. When the three K3s VMs booted, cloud-init decided each one was a new machine and generated new SSH host keys. That night the first stage of the etcd DR chain copies snapshots from the control VM over SSH. It saw a changed host key and refused to connect, which is the right behaviour. The two later stages, the encrypted restic copy and the offsite B2 upload, then ran on the previous day's data and reported success. Nothing alerted. The VMs now have a fixed DNS search domain, so cloud-init no longer sees a different machine after a restart.

## Impact

No data was lost. For one night the local and offsite DR copies were a day older than they should have been, and the dashboard showed two green stages after a red one. If the control VM had been lost that day, the newest restore point would have been a day old. Anyone who checked the job results would have seen "success" for the copies that matter.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-06 07:03 | The hypervisor's journal stops mid-stream, with no shutdown entries |
| 2026-11-06 08:13 | The hypervisor boots. cloud-init on each VM sees a new instance ID and regenerates its SSH host keys |
| 2026-11-06 21:00 | The DR sync stage fails with "host key has changed" |
| 2026-11-06 21:30 and 22:00 | The restic and B2 stages succeed on the unchanged snapshot mirror |
| 2026-11-07 morning | A routine check finds the failed unit. The new control VM key is compared over the encrypted overlay network, where the peer is authenticated, so it isn't an attacker in the middle. The key is trusted and the chain re-run cleanly |
| 2026-11-07 05:59 | Someone switches off the hypervisor's power plug during the fix rollout. It is back at 06:02 |
| 2026-11-07 06:04 to 06:10 | A fixed search domain is applied with Terraform, one VM at a time, each rebooted and back to Ready before the next |
| 2026-11-07 06:11 | The new control VM key is checked over the LAN, the overlay and from the hypervisor (all three match), then trusted. The DR chain runs: all three stages succeed with a fresh snapshot |

## Root cause

cloud-init picks the instance ID from a hash of the configuration the hypervisor hands the VM. When that ID changes, cloud-init treats the VM as new and regenerates its host keys. The VMs didn't set a DNS search domain. When a VM leaves it unset, Proxmox fills it in from the hypervisor's own `/etc/resolv.conf`. The overlay network's client rewrites that file, so its contents depend on whether the client has started yet and what it wrote. When the hypervisor booted unclean, the search domain handed to the VMs differed from the one baked into their last instance ID. All three VMs got a new instance ID and new keys at once.

The evidence: the VM definitions hadn't changed, the generated configuration for every VM contained the hypervisor's overlay search domain, and all three VMs regenerated keys on the same boot.

## Contributing factors

- The DR stages are independent timers. A later stage doesn't know an earlier one failed, so "success" only meant that the step had run.
- No heartbeat or freshness check covers the sync stage, so a failed unit sat unnoticed until someone looked.
- The hypervisor has restarted unclean several times since October without anyone checking what happened to the VMs.
- The root cause depends on host state, not VM configuration, so a review of the Terraform alone wouldn't have found it.

## What went well

- The sync refused the changed host key, so it failed safely.
- The new key was checked over an authenticated path before it was trusted.
- The fix was rolled out one VM at a time. When the hypervisor lost power mid-rollout, only one VM had changed and the cluster recovered without help.

## Where we got lucky

The control VM wasn't lost on the day the copies were stale, and the gap closed within a day.

## Fix

- Each VM's cloud-init sets `searchdomain` to `home.arpa` (RFC 8375). The configuration the hypervisor generates no longer depends on its own DNS state, so the instance ID stays the same across restarts.
- Applying it changed the instance ID one last time on purpose, during a controlled reboot. Known-hosts entries were refreshed after the keys were checked.
- The old SSD copy of the DR data, kept from [INC-2026-007](INC-2026-007-dr-copies-on-wrong-disk.md), was deleted once the chain ran clean.

## Guardrails added

- The Terraform carries a comment explaining why the search domain must stay set.
- Follow-up: heartbeat and freshness alerts for each DR stage, so a failed sync pages and later stages report stale input.
- Follow-up: the restic and B2 stages should check the newest snapshot's age and fail when it's older than a day.

## Lessons

- A blank setting gets filled by someone else's default. Here the default came from the host's runtime state.
- In a pipeline of separate jobs, one failed stage plus two green ones reads as mostly healthy. Check that the copy at the end of the pipeline is fresh.
- Treat a host-key mismatch as a possible attack until you have verified the new key over an authenticated path, even when the cause looks harmless.

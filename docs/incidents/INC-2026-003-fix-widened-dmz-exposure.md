# INC-2026-003: Restoring monitoring opened admin tools to the DMZ

| Field | Value |
|-------|-------|
| Date found | 2026-11-03 |
| Severity | SEV1 |
| Found by | Verification check |
| Duration | Several hours on 2026-11-03, from the retagging that morning until the corrected policy was live and verified |
| Status | Fixed and verified |

## Summary

The DMZ observer is a deliberately low-trust VM. Its access policy lets it probe a handful of services on the app host and nothing else. To fix a monitoring outage ([INC-2026-002](README.md#index)), every reverse-proxied service on the app host was tagged by hand with the app host's environment tag. An older access-policy grant still allowed the DMZ to reach anything with that tag. Monitoring came back, and so did DMZ access to admin tools. A planned "nothing new is reachable" check caught it the same day. The grant was removed, the probe targets were pinned, and policy tests now enforce the boundary on every save.

## Impact

For several hours the DMZ observer got an HTTP response from 16 of 17 proxied services on the app host. These included a Docker management UI, a container log viewer, the metrics server and the alert manager. The metrics dashboard redirected to its login page. The alert manager and the log viewer answered `200` straight away. The DMZ VM runs only monitoring and a dashboard, so an attacker would have needed to compromise it first. This review did not search the logs for signs of misuse.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-03 morning | To restore DMZ monitoring, all proxied services are tagged by hand with the environment tag |
| 2026-11-03 | DMZ monitors turn green. The verification step "the metrics dashboard must not answer from the DMZ" fails: it answers. A sweep finds 16 of 17 services reachable |
| 2026-11-03 | The cause is found: an older grant, DMZ to the environment tag on ports 80 and 443, still in the policy |
| 2026-11-03 | A corrected policy is written. The first save in the admin console leaves the old policy live: the file had picked up a stray paste and was invalid, and the policy that was actually saved was the old one |
| 2026-11-03 | The data-plane check shows the app host still admitting the DMZ on port 80, a port only the old grant allowed. The clean policy is pasted again |
| 2026-11-03 | Verified: the app host's packet filter admits the DMZ on 443 only, the three probe targets answer, and every admin tool times out from the DMZ. Committed as `13fca25` |

## Root cause

Access was granted by tag, and the tag meant two things. The old grant said "the DMZ may reach the environment tag on 80 and 443" back when only the app host itself carried that tag. Tagging every service with the same environment tag extended that grant to all of them. Nothing in the policy stated which services the DMZ was supposed to reach, so nothing failed when the set grew.

## Contributing factors

- The policy had no tests, so a change in who could reach what was invisible until someone probed it.
- The monitoring fix and the security boundary used the same tag, so fixing one moved the other.
- Tags on the proxied services reset whenever a container is recreated (part of INC-2026-002), which encouraged quick hand-tagging over a designed change.
- The admin console reported a successful save, but the policy that had been saved was the old one.

## What went well

- The fix plan included a negative check. "Nothing new is reachable" ran right after "monitoring works", and caught the exposure.
- The second check read the packet filter on the destination host. The console's "saved" message was not taken as proof.

## Where we got lucky

The DMZ VM was not compromised while the grant was open, and the window was hours, not weeks.

## Fix

Commit `13fca25`, in the encrypted Tailscale policy file.

- The broad DMZ grant to the environment tag was deleted.
- The DMZ may reach only services carrying a dedicated probe tag, plus two named host entries pinned by address. A container recreate resets the proxied services' tags but not their addresses, so the monitors keep working without widening access.
- A `tests` block was added. The admin console runs it on every save and rejects a policy where the DMZ can reach the environment tag on 80 or 443, or where the probe paths stop working.

## Guardrails added

- Policy tests encode the DMZ boundary, so a future grant that widens it fails at save time.
- Every access change is verified twice: once from the source (what answers from the DMZ), and once at the destination (what the packet filter admits).
- A follow-up moves tag assignment from the console into the reverse proxy's configuration, so tags can no longer drift or be fixed by hand.

## Lessons

- Every access fix needs a negative test. Showing that the thing you wanted to reach now works says nothing about what else became reachable.
- Don't let one tag mean both "where it runs" and "who may reach it".
- Verify policy changes in the data plane. A console's "saved" message shows what the console accepted, not what the nodes enforce.

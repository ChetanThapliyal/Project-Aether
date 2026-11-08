# INC-2026-004: The outside observer's alerts never left its host

| Field | Value |
|-------|-------|
| Date found | 2026-11-03 |
| Severity | SEV2 |
| Found by | Investigation |
| Duration | From the observer's first deployment (failures logged from 2026-10-28) to 2026-11-08 |
| Status | Fixed and verified |

## Summary

The DMZ observer runs Uptime Kuma outside the rest of the platform so it can raise an alarm when everything else is down. It was detecting failures correctly, but none of its Telegram alerts was ever delivered. The DMZ VM has no public IPv4 address and reaches the internet only over IPv6. Kuma's Docker network was IPv4-only, so the container had no route to the internet at all. Every notification timed out and was written to a log nobody read. The container network now has IPv6, and a Telegram message from Kuma arrived on the first try.

## Impact

For at least 11 days the observer of last resort could see an outage but couldn't tell anyone. Every DOWN and UP notification it attempted was lost, 15 failures in its log and no successful send. That covers the three days when the observer's own monitors were red in [INC-2026-002](INC-2026-002-observer-blind-to-app-host.md), so that incident couldn't have paged either. The primary alert path, Prometheus to Alertmanager to Telegram, runs on a different host and worked throughout. Anything that took that host down would have produced no alert from either path.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-10-28 04:09 | First logged failure: Kuma can't send a notification to Telegram |
| 2026-11-03 | An investigation finds the container network is IPv4-only on an IPv6-only host. A fix is planned as an extra step in the DMZ hygiene chore |
| 2026-11-08 03:30 | Watchdog drill for the new heartbeat alerting: the primary Alertmanager is stopped on purpose |
| 2026-11-08 03:35 | Kuma marks the Watchdog DOWN, five minutes after the stop, so detection works |
| 2026-11-08 03:37 | Kuma's Telegram send fails with `connect ETIMEDOUT` to Telegram's IPv4 address |
| 2026-11-08 | IPv6 is enabled on the container network and the DMZ stack is recreated. From inside Kuma, Telegram answers `302`. Kuma's Watchdog UP message arrives in Telegram, the first delivered Kuma alert |

## Root cause

The DMZ VM was built without a public IPv4 address to save cost, so its only route to the internet is IPv6. Docker networks are IPv4-only unless IPv6 is turned on, and the compose file never turned it on. Containers on that network could reach the tailnet through the host but had no route to the internet, so every call to Telegram's API timed out.

## Contributing factors

- Nobody had ever tested the alert path end to end. Kuma showed monitors going red in its UI, which looked like a working alarm.
- A failed notification goes to a log line only. Nothing watches for "the alerter can't alert".
- The host itself could reach the internet over IPv6, so checks run on the host passed. Only checks run inside the container showed the gap.

## What went well

- The fix was tested first with a throwaway IPv6 network running Kuma's own image, before the real network was recreated.
- The Watchdog drill reproduced the failure on demand, and the same drill then proved the fix.

## Where we got lucky

No real outage needed the observer to page anyone between 28 Oct and 8 Nov. The primary alert path delivered throughout.

## Fix

Commit `8767535`.

- The DMZ container network has IPv6 enabled with a ULA subnet, and Docker NATs it out through the host's IPv6. IPv4 inside the network is unchanged, so tailnet paths still work.
- The stack was recreated to apply it, since Docker can't change an existing network in place.

## Guardrails added

- The Watchdog heartbeat added in the same hardening pass makes Kuma alert when the primary Alertmanager goes silent. Each drill now tests delivery through both paths, not just detection.
- The DMZ hygiene chore's verification runs `curl https://api.telegram.org` from inside the Kuma container, so a network change that breaks egress shows up as a failed check.

## Lessons

- An alarm works only once a message has reached a person, so a drill has to end with the message arriving.
- On an IPv6-only host, Docker networks need IPv6 turned on explicitly, or containers have no route out.
- Check egress from where the sender runs. Here the host could reach Telegram and the container couldn't.

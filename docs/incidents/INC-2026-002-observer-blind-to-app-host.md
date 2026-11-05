# INC-2026-002: The outside observer could not see the services it monitored

| Field | Value |
|-------|-------|
| Date found | 2026-11-02 |
| Severity | SEV2 |
| Found by | Audit |
| Duration | At least 72 hours before 2026-11-02 (likely from 2026-10-28) to 2026-11-03 |
| Status | Mitigated and verified; durable fix tracked |

## Summary

The DMZ observer runs Uptime Kuma outside the app host, so it can raise an alarm when the app host can't. Its monitors for the app host had not passed a single check in three days. Each proxied service is its own node on the private overlay network. The services had lost the tag the access policy uses to make them visible to the DMZ, so the DMZ could not even resolve their names. The tags were being reset every time a container was recreated, and an image auto-updater recreated containers every night. The monitors now target fixed addresses that survive a recreate, and the nightly auto-update is off.

## Impact

For at least three days, the observer reported the app host's services as down whether they were up or not. A real outage on the app host would have looked the same as the false one. The backup heartbeat monitor ([INC-2026-001](INC-2026-001-silent-backup-heartbeat.md)) was already red for its own reason, so the observer gave no usable signal about the app host at all. This review did not check whether any service really went down in that window.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-10-28 04:05 | The nightly auto-updater starts recreating containers on the app host. Each recreated service loses its hand-set tag |
| ≤ 2026-10-30 | The DMZ's app-host monitors stop passing. Over the next 72 hours they pass 0 of about 2,600 checks |
| 2026-11-02 | An audit finds the monitors failing and traces it: untagged nodes are left out of the DMZ's network map, so DNS answers "no such host" |
| 2026-11-03 | The services are tagged by hand. Monitoring returns, but the tag also widens DMZ access ([INC-2026-003](INC-2026-003-fix-widened-dmz-exposure.md)) |
| 2026-11-03 | Tags are found to reset on container recreate. Monitors are moved to fixed addresses, the nightly auto-update is turned off, and the corrected policy goes live |
| 2026-11-03 | Verified: all app-host monitors on the observer are UP |

## Root cause

The overlay network only shows a node the peers that the access policy lets it reach. The policy let the DMZ reach nodes with one tag. The proxied services joined the network through a reverse proxy that signs each one in with a shared, untagged auth key, so they joined without a tag. Tags added later in the admin console held only until the next container recreate. On a recreate, the proxy signed the node in again with its untagged key, and the network reset the node's tags to the key's, which were none.

The evidence is the timing. The 11 services that lost their tags are exactly the 11 whose containers were recreated after 28 Oct 04:05. The 5 that kept them had not been recreated since.

## Contributing factors

- An auto-updater recreated containers every night at 04:00, which triggered the tag reset every night.
- The proxy writes no log when it signs a node back in, so the reset was invisible.
- The failing monitors were on the observer, and nothing watched the observer's own results from outside.
- The policy had no tests, so "the DMZ can see these services" was never checked after a change.

## What went well

- The audit followed the failure down through DNS to the network map before changing anything.
- The timing correlation (11 of 11) settled the cause, so there was no need to wait for the next reset to reproduce it.

## Where we got lucky

No real app-host outage is known from the window when the outside observer was blind.

## Fix

Commit `13fca25`, plus console changes.

- A dedicated probe tag, granting only the monitored services on 443.
- Two named host entries in the policy, pinned by address. A recreate resets a node's tags but keeps its address, so the monitors keep working through updates.
- The image auto-updater moved from auto-apply to notify-only.

## Guardrails added

- Policy tests check that the DMZ can reach the probe targets, so a policy change that breaks monitoring fails at save time.
- Follow-up: move to a proxy version that assigns tags from its own configuration through an OAuth client, so tags can't be lost or set by hand again.
- Follow-up: pin application images, so each update is a reviewed change.

## Lessons

- An observer that can't reach its targets reports the same thing as a real outage. Alert on "checks have not passed in N hours" as well as on "target is down".
- If an access decision depends on something that a routine operation can reset, that operation will eventually break the access. Find out what resets your tags.
- Unattended auto-updates turn every upstream change into a production change at 04:00.

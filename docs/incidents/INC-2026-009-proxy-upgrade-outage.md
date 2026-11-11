# INC-2026-009: A planned proxy upgrade took every tailnet service down for 30 minutes

| Field | Value |
|-------|-------|
| Date found | 2026-11-06 |
| Severity | SEV3 |
| Found by | Change (the proxy's own logs during the cut-over) |
| Duration | 2026-11-06 09:35 to 10:05 UTC for all 16 services. Five admin services stayed unreachable until 2026-11-07 00:12 UTC, waiting for TLS certificates |
| Status | Fixed and verified |

## Summary

The cloud app host publishes its 16 services on the tailnet through tsdproxy, which runs one Tailscale node per service. The upgrade from v1 to v2 moved the proxy from one untagged auth key to an OAuth client with three role providers, so each service could carry a role tag (app, admin or probe) that survives container updates. The upgrade replaced every node, so the services were down while the new nodes signed in.

That was meant to take a few minutes. It took 30, because the new credentials failed twice in a row and every proxy refused to start each time. First the OAuth client lacked a scope the proxy asks for. Then the tailnet policy didn't let the client mint keys for a subset of its own tags. After both were fixed, five services waited about 14 hours for TLS certificates, because the proxy didn't retry a failed certificate request until someone visited the service.

## Impact

No data was lost and nothing was exposed outside the tailnet. For 30 minutes, none of the 16 services on the app host could be reached over the tailnet, including the monitoring UIs and the public book library that two friends use. The outside observer's book library check timed out once, at 10:04.

Five admin services (Grafana, Kestra, Loki, Alertmanager and CouchDB) stayed unreachable by URL until the next night. Their containers ran and Prometheus kept collecting the whole time. Only browser access was missing.

For about 15 minutes, six admin services sat on the `app` role instead of `admin` because their new labels hadn't been deployed yet. The DMZ still couldn't reach them, so they were never more exposed than before.

While debugging the policy, a diagnostic command printed one app's session-signing secret into the operator's local terminal session. It went nowhere else. The secret was rotated on 10 Nov.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-06 00:35 | Planning. An upstream issue (#496) is found in which v2's generated defaults proxy every service to a host port. Here, 16 of 18 containers publish none, so the plan writes the v2 config explicitly |
| 2026-11-06 ~01:30 | The new policy tags, the OAuth client and the secrets are in place, and the proxy's state is backed up |
| 2026-11-06 ~09:35 | v1 is stopped, the 16 old nodes are deleted in the admin console, and v2 starts. Every proxy fails: `OAuth client cannot grant scopes "devices:core auth_keys"`. The outage starts |
| 2026-11-06 ~09:40 | A new OAuth client with both scopes is created (scopes can't be edited on an existing client). Every proxy now fails with `400 requested tags [tag:oci-app] are invalid or not permitted` |
| 2026-11-06 09:46 to 09:49 | Tested against the API: a key for all three of the client's tags succeeds, a key for one tag alone fails. Each role tag is made its own owner in the policy, and the policy is pasted again |
| 2026-11-06 09:50 | All 16 nodes sign in. Six admin services come up on `app` because their new labels aren't deployed yet |
| 2026-11-06 ~09:55 | The proxy is stopped again, the six wrong nodes and their state are deleted, and the labels are deployed |
| 2026-11-06 10:05 | All 16 nodes up with the right tags, no errors. The services are routable again |
| 2026-11-06 10:07 | Five certificate requests fail with `context deadline exceeded` while queued two at a time |
| 2026-11-06 10:27 | 11 of 16 services have certificates and answer |
| 2026-11-07 00:06 to 00:12 | The remaining five are visited, request their certificates again and get them. All 16 URLs answer |
| 2026-11-07 | A recreated container keeps its node, IP and tags, so tags no longer reset on updates |

## Root cause

Two credential mistakes, each of which stopped every proxy at once.

1. The OAuth client was missing a scope. tsdproxy 2.3.4 asks Tailscale for a token with `devices:core` and `auth_keys`. The plan only named `auth_keys`. OAuth scopes are fixed when a client is created, so the fix was a new client.
2. The policy didn't let the client mint keys for part of its tag set. One OAuth client holds all three role tags, and each provider asks for one or two of them. Tailscale lets a client mint a key for its exact set of tags without checking `tagOwners`. For a subset, each requested tag has to be owned by one of the client's own tags, and ownership by `autogroup:admin` doesn't count. The policy only had `autogroup:admin` as owner, so every request was refused. The fix makes each role tag its own owner as well (`"tag:oci-app": ["autogroup:admin", "tag:oci-app"]`). That lets no device gain extra tags.

The long tail came from certificates. Every node was new, so each needed its own certificate. The proxy issues them two at a time, five requests timed out in the queue, and it doesn't retry until a request for that service comes in.

## Contributing factors

- Every service changed provider, so all 16 nodes had to be replaced together. A canary wasn't possible: a second proxy instance would have claimed every labelled container on the same Docker socket. So any credential mistake took everything down.
- Nobody tested the credentials before the cut-over. Asking the API for one test key per provider would have caught both errors while v1 was still serving.
- The proxy was started before every service had its new provider label, so six services came up under the default provider and had to be moved by hand, which meant a second, shorter stop.
- Under time pressure, a quick inline script read the decrypted secrets file the wrong way, and its error message printed a secret.

## What went well

- Upstream issue #496 had broken this exact setup once before. Researching it before the upgrade meant the v2 config was written explicitly, and the 502-on-every-service failure never happened.
- The proxy state was backed up before the cut-over, so rolling back to v1 was always available.
- The error messages named the problem. The second one was then confirmed against the API in about three minutes, without guessing.
- The DMZ observer showed what users saw throughout, and confirmed recovery.

## Where we got lucky

The six admin services that came up on the wrong role landed on `app`, which the DMZ can't reach. Before the earlier DMZ fix ([INC-2026-003](INC-2026-003-fix-widened-dmz-exposure.md)), the same slip would have opened admin tools to the DMZ for 15 minutes. The leaked secret only reached a local terminal session. If the same script had run in CI, it would have ended up in a build log.

## Fix

- tsdproxy 2.3.4, pinned by digest, with an Ansible-rendered config: three OAuth providers (`app`, `admin`, `probe`), containers reached over the shared Docker network, and no auth key left in the environment (commit `fedf51c`).
- In the tailnet policy, each role tag lists itself as an owner, and a `tests` block runs on every save (commit `fedf51c`). ADR-013 records the role model, the tag ownership rule and the tests (commit `bfc9eb6`).
- Each service picks its provider with a label in its compose file.
- The leaked app secret was rotated (commit `3c9e72c`).

## Guardrails added

- The policy's `tests` block asserts which roles the DMZ and the cluster can and can't reach. A save that breaks those rules is rejected.
- The Ansible play refuses to run unless the OAuth client ID and secret exist in SOPS.
- The run order in the chores plan now says: give the OAuth client both scopes, make each tag its own owner, deploy the labels, then start the proxy.
- After a bulk re-create, request each service's URL once and check that every node has a certificate.
- Diagnostic scripts read secrets from a script file and print only key names and status codes.

## Lessons

- When one credential gates every node, prove it works (one test key per provider) before stopping the old version.
- Tailscale's OAuth tag rules are stricter than the console suggests. A client can mint its exact tag set freely, but a subset needs `tagOwners` entries that name the client's own tags.
- After the nodes are up, each one still needs a certificate, and this proxy only retries a failed request when someone visits the service. Check the certificates before calling the change done.

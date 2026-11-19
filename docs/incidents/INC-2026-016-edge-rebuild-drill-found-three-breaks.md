# INC-2026-016: The first timed rebuild of the edge VM took 48 minutes and found three breaks in the recovery path

| Field | Value |
|-------|-------|
| Date found | 2026-11-19 |
| Severity | SEV2 |
| Found by | Verification check |
| Duration | 2026-11-19 15:06 to 15:55 UTC (the drill's outage) |
| Started | unknown (latent: the full rebuild had never been run end to end) |
| Detected | 2026-11-19 15:11 |
| Resolved | 2026-11-19 16:34 |
| Cause | Change |
| Status | Fixed and verified |

## Summary

Phase 05 task 5.53 timed the edge VM's documented rebuild (DR Scenario 05) for the first time: delete the VM, recreate it with Terraform, deploy it with Ansible, restore Uptime Kuma. The target is 15 minutes; it took 48. Three things in the recovery path were broken, and none of them could have been seen without actually rebuilding: the mesh policy didn't let the enrollment credential give the VM its tag, a script crashed on a VM with no Kuma data yet, and every heartbeat sender was configured with the old VM's mesh address. Each was worked around during the drill and fixed the same day. The first also blocked a rebuilt cluster node from joining, which no drill had covered.

## Impact

- **During the drill (planned):** the public status page and the outside monitoring were down for 48 minutes. Monitoring on the cloud host stayed up and alerted, as designed.
- **What a real loss would have hit:** the same three breaks, under pressure. The worst was the address: a rebuilt edge VM would have looked healthy while every backup heartbeat (the cloud host's alert-path Watchdog, the hypervisor's four backup stages, the cloud host's prune job) failed to arrive. Each would then have raised a false "backup failed" alert overnight.
- No data was lost. The Kuma restore brought back all 22 monitors and their history up to the start of the drill.

## Timeline

All times UTC, 19 Nov 2026.

| Time | Event |
|------|-------|
| 15:03 | Pre-flight: Terraform plan clean; Kuma stopped for a few seconds for a consistent copy (SQLite integrity check OK, 22 monitors) |
| 15:06:53 | Owner deletes the VM (T0) |
| 15:07:51 | Terraform creates the new VM: private IPv4 and IPv6 only, still free |
| 15:11:24 | The startup script's `tailscale up` fails: `requested tags [tag:gcp-dmz] are invalid or not permitted`. The VM is up but not on the mesh |
| 15:17 | Found from the serial console after the VM didn't appear on the mesh |
| ~15:24 | Owner creates a one-time auth key tagged `tag:gcp-dmz`; joined through Google's IAP SSH. The VM is back on the mesh under its old name, with a new address |
| 15:26–15:42 | `task ansible:dmz`: images pulled on a fresh e2-micro (16 min), then fails at the last stage: `kuma-uptime.py` crashes, `kuma.db` doesn't exist yet |
| 15:43 | Kuma data restored from the pre-flight copy |
| 15:44–15:52 | Deploy rerun: no failures. Containers, the public page, the Kuma backup and the negative checks all pass |
| 15:53 | Every Kuma monitor is green except the Watchdog push. Alertmanager logs `contextDeadlineExceeded`: it is still posting to the old VM's mesh address |
| 15:55 | Owner sets the new VM's mesh address back to the old one in the Tailscale console |
| 15:55:18 | Watchdog heartbeat received. Recovery complete: 48 min 25 s after T0 |

## Root cause

Three independent breaks, each sitting in a step that only a real rebuild runs:

1. **The mesh policy didn't let the enrollment client tag a machine.** The edge VM and the cluster nodes join with one OAuth client, "Project Aether Node Enrollment", which holds three tags: `tag:gcp-dmz`, `tag:oci` and `tag:k3s`. Each machine asks for only one of them. Tailscale lets a client mint a key for a *subset* of its tags only if one of its tags owns each requested tag; an exact match of the full set needs no ownership. `tag:gcp-dmz` and `tag:k3s` were owned by the admins only, so every single-tag request was refused. The client was set up on 11 Oct, when the nodes joined for the first time. The same subset rule was found and fixed for the cloud host's tsdproxy client in FND-03 (11 Nov), but only for that client's tags: nobody checked whether another client relied on the same rule, because this one is used only when a machine is created. A test container reproduced the refusal for both tags before the fix.
2. **A deploy step assumed Kuma's database exists.** `kuma-uptime.py` (FND-23) reads Kuma's SQLite file for the status page's backup ages, and the deploy starts it once. On a fresh VM the file appears only after the restore, which the scenario runs after the deploy. The script raised `FileNotFoundError`, and the deploy stopped before its last tasks.
3. **Heartbeat senders were pinned to the VM's mesh address.** The shared secret `kuma_push_base` held the VM's mesh IP, rendered into Alertmanager, Kestra and four hypervisor scripts. A new VM gets a new address. The scenario said to check the mesh policy for the old IP, but the IP was also inside an encrypted secret, which a plain-text search doesn't see.

## Contributing factors

- The scenario had only ever been drilled as a "re-convergence" (stop the containers, redeploy on the same VM), which keeps the VM, its mesh identity and its address, and so skips all three steps that broke.
- The deploy on a fresh e2-micro takes 16 minutes, mostly image pulls. The 15-minute target was never achievable even without the breaks.

## What went well

- The pre-flight copy of Kuma's data was taken with Kuma stopped and checked with SQLite's integrity check. The restore was clean and lost no history.
- Google's IAP SSH worked when the mesh didn't, as the break-glass design intends.
- The heartbeat design made break 3 visible within minutes: a silent Watchdog is exactly what the push monitor is for.
- The deploy's negative checks and the public-page checks passed on the first try on a brand-new VM.

## Where we got lucky

Tailscale lets an admin give a machine a chosen address, so break 3 was fixed in the console in seconds, before any nightly heartbeat was due. In a real loss at night, the first sign would have been a run of false backup alerts.

## Fix

- **Break 2:** `infrastructure/ansible/templates/kuma-uptime.py` skips a run when Kuma's database is missing or empty, instead of crashing. Deployed in the rerun.
- **Break 3:** `kuma_push_base` now uses the VM's mesh name, `aether-gcp-dmz.<tailnet>.ts.net`, not its address. The name was checked to resolve and connect from every sender: the hypervisor, the cloud host and the Alertmanager and Kestra containers. Redeployed: OCI monitoring, Kestra, and the hypervisor's four backup playbooks.
- **Break 1:** in the mesh policy (`infrastructure/secrets/tailscale-policy.sops.yaml`), `tag:gcp-dmz` and `tag:k3s` now own themselves, as the OCI tags have since FND-03. Self-ownership only lets a holder of the tag mint that same tag. Applied in the admin console at about 16:30. Verified with an ephemeral test node in a container on the workstation, joining with the real enrollment secret: both tags were refused before the change and both joined after it. The test nodes logged out and were removed.
- **DR Scenario 05** now has the steps that were missing: the join fallback, the restore before the deploy's last stage, and the address check including encrypted secrets.

## Guardrails added

- The timed rebuild itself, recorded in the DR README and `objectives.yml` with what it measured, so the status page shows 48 minutes against the 15-minute target instead of an untested claim.
- No more mesh IPs in heartbeat URLs: senders use the mesh name, which survives a rebuild.
- `kuma-uptime.py` tolerates the fresh-VM state, so the deploy completes before the restore.
- The join test (an ephemeral Tailscale container logging in with the enrollment secret and one tag) is now a step in DR Scenarios 03 and 05: a cheap way to prove a node could rejoin, without rebuilding anything.

## Lessons

- A drill that keeps the machine tests the software, not the recovery. Identity, credentials and addresses only break when the machine is really replaced.
- A credential used only at creation time rots silently. When a fix changes how a rule works for one credential (FND-03), check every other credential that relies on the same rule, including the ones nothing uses day to day.
- Search for an address in the decrypted secrets too, not just in plain text.

# INC-2026-011: One worker's tailnet link to the cloud monitoring host fell back to a relay and kept dropping out

| Field | Value |
|-------|-------|
| Date found | 2026-11-08 |
| Severity | SEV3 |
| Found by | Alert (`HomelabNodeDown`, kube-state-metrics down) |
| Duration | 2026-11-08 01:02 to 12:14 UTC (about 11 hours of intermittent scrape gaps) |
| Status | Fixed and verified |

## Summary

The cloud host runs Prometheus and scrapes the homelab over the tailnet. After the lab was powered back on in the morning, one worker VM could no longer open a direct WireGuard path to the cloud host. Its traffic went through a Tailscale DERP relay instead. Every 20 to 60 minutes the TCP connection to the relay stalled, scrapes of that worker timed out, and alerts fired, then cleared on their own. The other worker, on the same LAN and behind the same NAT, stayed direct the whole time.

Packet captures on both ends showed that the worker's packets reached the cloud host and the cloud host's replies were sent, but the replies never came back to the worker. The home NAT was holding a one-way mapping for the worker's UDP port. Moving that worker to a different Tailscale port gave it a fresh mapping, and it went direct immediately.

## Impact

No data was lost. Metrics for one worker, and for kube-state-metrics when it ran there, had 17 gaps of 1 to 17 minutes. Each gap paged, and each page resolved without anyone acting on it. After a day of that, real node-down alerts start to look like noise.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-06 to 2026-11-07 | No scrape gaps for this worker apart from planned shutdowns and power loss |
| 2026-11-07 15:09 | The lab is shut down overnight because of a noisy server fan |
| 2026-11-08 00:58 | The lab boots. The home router has also been restarted several times over the previous days because it was struggling to hand out addresses |
| 2026-11-08 01:02 | First scrape gap. Gaps of 2 to 17 minutes follow through the morning, and alerts fire and resolve |
| 2026-11-08 07:04 | Restarting tailscaled on the worker doesn't help. `tailscale ping` reports "via DERP, direct connection not established" |
| 2026-11-08 ~10:20 | The cloud host's security list and host firewall are opened for UDP 41641. The worker's packets now reach the cloud host, but the path is still relayed |
| 2026-11-08 ~10:25 | Simultaneous captures: 14 packets out from the worker arrive at the cloud host, and 18 replies leave the cloud host. The worker receives none |
| 2026-11-08 12:14 | The worker's tailscaled is moved to UDP 41642. The first ping goes direct |

## Root cause

Tailscale opens direct paths by sending UDP from each side until the NAT mappings line up. The home network sits behind two NATs: the home router, and the ISP's carrier-grade NAT in front of it. After the morning's restarts, one of them kept a mapping for the worker's source port that let packets out but didn't let replies back in. The other worker had a different external mapping and worked normally. A new source port meant new mappings in both NATs, and that alone cleared the fault, so the cause was NAT state rather than anything configured on the hosts.

We can't tell which of the two NATs held the broken entry. Only the home router can be inspected or restarted from here.

Why the relay made it visible: a relayed path is a long-lived TCP connection to the relay server. On this line it stalled every 20 to 60 minutes and took several minutes to recover, longer than the scrape timeout.

## Contributing factors

- The cloud host only allowed TCP 22 and ICMP inbound. Peers that the cloud side couldn't reach first had no way in, so a bad NAT on the home side left nothing to fall back on except the relay.
- `tailscale status --json` on this Tailscale version leaves the peers' `Addrs` empty. Early in the investigation that looked like the worker wasn't advertising any endpoints, which was wrong. Packet captures settled it.
- The home router had been restarted several times in a few days, which churns NAT state at both layers.

## What went well

- The alerts fired and cleared correctly. The fault was in the transport, and the monitoring reported it accurately.
- Capturing on both ends at the same time placed the drop exactly. Without that, the next step would have been guesswork about the ISP.
- The port change was reversible and touched one node.

## Where we got lucky

The fault hit a worker. If it had been the control-plane VM, the same flapping would have hidden etcd and API server alerts behind the noise.

## Fix

- The cloud host allows UDP 41641 inbound, in both the Terraform security list and the Ansible-managed host firewall. Peers behind any NAT can now reach it first, and WireGuard authenticates every packet.
- The affected worker uses UDP 41642. Each node's `tailscale_port` lives in the Ansible inventory and is written to `/etc/default/tailscaled` by `common.yml`.

## Guardrails added

- The inventory comment on the port override points to this review.
- Follow-up: an alert on Tailscale peers that stay relayed for more than 30 minutes, so a lost direct path is caught before the scrapes start to suffer.
- Follow-up: ask the ISP about IPv6. A native IPv6 path would avoid both NATs.

## Lessons

- "On the tailnet" doesn't mean "has a direct path". Check `tailscale ping` for "via DERP" whenever tailnet-only scrapes flap.
- When two identical hosts behind one NAT behave differently, check for stale NAT state. A new source port is a cheap test.
- Capture at both ends at once before blaming the network in between.

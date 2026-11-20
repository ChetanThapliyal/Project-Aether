# INC-2026-017: The worker from INC-2026-011 fell back to a relay again after the ISP changed the home address

| Field | Value |
|-------|-------|
| Date found | 2026-11-19 |
| Severity | SEV3 |
| Found by | Alert (`KubeStateMetricsDown`, `HomelabNodeDown`) |
| Duration | 2026-11-19 23:24 to 23:59 UTC (35 minutes on the relay, 4 of them with failed scrapes) |
| Started | 2026-11-19 23:24 |
| Detected | 2026-11-19 23:46 |
| Resolved | 2026-11-19 23:59 |
| Cause | Platform |
| Status | Fixed and verified |

## Summary

The cloud monitoring host lost its direct tailnet path to one worker and went through a Tailscale relay instead. Four minutes later the relay connection stalled, every scrape of that worker timed out, and the node and kube-state-metrics alerts fired, then cleared on their own. It was the same worker and the same symptom as [INC-2026-011](INC-2026-011-worker-stuck-on-relay.md). That fix had moved the worker to a new UDP port, and the new port broke the same way, a few hours after the ISP changed the home network's public address. Moving the worker to another port brought the direct path back at once.

## Impact

No data was lost and no app went down: app traffic reaches the cluster through its own tailnet gateway, which wasn't affected. Metrics for the worker, kube-state-metrics, PostgreSQL and Redis (all scraped through that worker's tailnet name) had a 4-minute gap, and two alerts fired. Left alone, the gaps would have repeated, as they did every 20 to 60 minutes in INC-2026-011.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-19 11:42 | The ISP changes the home network's public IPv4 address. Every homelab scrape misses once; the three nodes and the cloud host find direct paths again within a minute |
| 2026-11-19 15:29 | Last time the cloud host confirms a direct path to the worker on UDP 41642 |
| 2026-11-19 23:24 | The cloud host starts contacting the worker through the Mumbai relay. Scrapes still succeed |
| 2026-11-19 23:45 | The relay connection stalls. Every scrape of the worker times out |
| 2026-11-19 23:46:59 | `KubeStateMetricsDown` fires; `HomelabNodeDown` follows at 23:47:44 |
| 2026-11-19 23:48 | The relay recovers and scrapes succeed. Both alerts resolve at 23:49 |
| ~2026-11-19 23:50 | The owner, paged, asks why kube-state-metrics and the worker were down |
| 2026-11-19 23:53 | `tailscale ping` from the worker: "via DERP, direct connection not established", to every peer including the other worker on the same LAN. The other two nodes are direct |
| 2026-11-19 23:59 | The worker's tailscaled moves to UDP 41643 (inventory, `common.yml`). The first ping to the cloud host goes direct |

## Root cause

The home network is behind two NATs: the home router and the ISP's carrier-grade NAT. Tailscale opens a direct path by sending UDP from both sides until the NAT mappings line up. After INC-2026-011 the worker used UDP 41642. When the ISP changed the public address, every node got new external mappings. The other two nodes, which go out through ports the NAT picks, kept working. The worker's fixed port 41642 ended up in the same broken state as 41641 had: a one-way mapping that lets packets out but never lets replies back in. The worker could still reach the relay over TCP, so it stayed on the tailnet, and the problem only showed when the relay connection stalled.

As in INC-2026-011, a new source port meant a fresh mapping in both NATs, and that alone cleared it. Which NAT holds the bad entry is still unknown.

## Contributing factors

- **The INC-2026-011 follow-up was never built.** That review promised an alert for a peer that stays relayed for more than 30 minutes. It would have fired at about 23:54, or earlier if the path had been lost sooner, instead of the first sign being a failed scrape.
- **The worker has a fixed port.** Fixing the port avoided the old bad mapping, but it also means the worker can't drift onto a fresh one when its mapping breaks.
- **Four other targets are scraped through the worker's tailnet name:** kube-state-metrics and the PostgreSQL and Redis exporters. One bad path made it look as if four services were down.

## What went well

- The alerts fired within two minutes and resolved on their own, and the scrape history placed the gap exactly.
- INC-2026-011's review named the symptom and the fix, so the diagnosis took minutes, not hours of packet captures.
- The port change is one inventory line and a tailscaled restart, and app traffic doesn't use that path.

## Where we got lucky

The relay stalled once in 35 minutes, and the page came while the owner was awake to ask about it. The alerts cleared on their own and every node looked healthy afterwards, so a page that arrived during the night would most likely have been put down to a network blip, and the next ones would have started to look like noise, as in INC-2026-011.

## Fix

- The worker's `tailscale_port` is now 41643 (`infrastructure/ansible/inventory/hosts.yml`), applied with `common.yml` on that node only. The cloud host, the other worker and the control plane are all reached directly from it again.

## Guardrails added

- **`TailnetPeerRelayed`,** the INC-2026-011 follow-up: a timer on the cloud host reads `tailscale status` every minute and writes, for each peer Prometheus scrapes (the three nodes and the hypervisor), whether the path is direct (`aether_tailscale_peer_direct`), through node exporter's textfile collector. The alert fires when a peer has been relayed for 30 minutes, and its description names the fix. The edge VM is left out: it has only a public IPv6 address and nothing else here has IPv6, so its path is always relayed by design.
- **`TailnetPathCheckStale`** fires if the check stops writing, so the new alert can't go quiet on its own.
- Both alerts have promtool tests in `alert-rules.test.yml`.

## Lessons

- A fix that pins a port moves the problem rather than removing it. When the public address changes, check the pinned node first.
- A follow-up written into a review isn't done until it's in the backlog. This one wasn't, and the same failure came back before it was built.
- When several targets go down together, check whether they share one network path before treating them as separate faults.

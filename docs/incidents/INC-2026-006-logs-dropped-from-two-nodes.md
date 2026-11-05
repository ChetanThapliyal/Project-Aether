# INC-2026-006: Two of three cluster nodes were sending their logs nowhere

| Field | Value |
|-------|-------|
| Date found | 2026-11-02 |
| Severity | SEV2 |
| Found by | Audit (phase exit gate) |
| Duration | One node since it was deployed, one since about 2026-10-30, to 2026-11-05 |
| Status | Fixed and verified; root-cause clean-up tracked |

## Summary

Every K3s node runs Promtail, which pushes container logs to a central Loki on the app host. Only one node's logs were arriving. One worker had never shipped a line, and the control-plane node had stopped around 30 Oct. The two failing nodes resolved Loki's private name through public DNS first, and public DNS returned addresses that aren't the app host. A setting meant to prevent this was silently ignored by the Helm chart. Promtail now pushes to Loki's fixed private address, and logs from all three nodes arrive.

## Impact

Logs from the control-plane node and one worker were dropped, including everything in `kube-system`. They can't be recovered: Promtail had already moved past the dropped batches, and only the few rotated log files still on each node could be re-read. The two failing Promtail pods sat at 57 to 59 MiB of a 64 MiB limit while their retry buffers grew, so out-of-memory restarts were close.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| Deployment of log shipping | One worker starts pushing to the wrong address. It never ships a line |
| ~2026-10-30 | The control-plane node stops shipping |
| 2026-11-02 | The phase exit gate asks "do all three nodes appear in Loki?" Only one does. The audit resolves Loki's name from each Promtail pod and gets the wrong answer on two of them |
| 2026-11-05 | Fix committed (`4aaba5a`). Within 10 minutes all three nodes appear in Loki, `kube-system` logs are arriving, and no pod reports a dropped batch |

## Root cause

Two defects compounded.

1. Promtail runs with `hostNetwork`, so it uses the node's resolver unless told otherwise. The Application set `dnsPolicy: ClusterFirstWithHostNet` to point it at cluster DNS, but the Promtail chart has no such value. Helm accepted the unknown key and dropped it without a warning.
2. The nodes' resolver lists differed. One worker listed the overlay network's DNS first. The other two listed public resolvers first, a leftover from their cloud-init. The app host also publishes a public DNS record for its private name (a side effect of a public-exposure feature on the same node). Public DNS answered with addresses that don't serve Loki, so the pushes timed out.

Fixing only the first defect would not have been enough. Cluster DNS forwards to the control-plane node's resolver, which has the same public-first order.

## Contributing factors

- Log shipping was verified when it was deployed, on the one node that worked, and never again.
- No alert checks that each node is still sending logs.
- Helm doesn't reject unknown values, so the dead `dnsPolicy` setting looked like protection.
- The nodes were configured by two different paths, so their resolver order drifted.

## What went well

- The exit gate checked each node separately, so one healthy node couldn't hide two silent ones.
- Resolving the name from inside each pod, against each resolver, showed the cause directly.

## Where we got lucky

As far as we know, nothing during the window needed logs from the two silent nodes.

## Fix

Commit `4aaba5a`.

- Promtail pushes to Loki by its private overlay address, which is stable for the node's identity, so DNS is out of the path.
- The dead `dnsPolicy` setting was removed so it can't mislead the next reader.
- The memory limit was raised from 64 to 128 MiB.

## Guardrails added

- Follow-up: a per-node "log shipping stalled" alert.
- Follow-up: lint Helm values against each chart's schema, so an unknown key fails in CI.
- Follow-up: make the overlay DNS authoritative for private names on every node through configuration management, and remove the public record that caused the wrong answer.

## Lessons

- A pipeline verified once is only known to have worked once. Check every source per node, continuously.
- Helm accepts unknown values without complaint. Treat any value you can't find in the chart's `values.yaml` as dead config.
- When the same name resolves differently depending on which resolver answers, check the resolver order on every machine.

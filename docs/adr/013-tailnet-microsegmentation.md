```text
================================================================================
ADR-013: Tailnet Micro-segmentation using Tailscale Grants
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect
- **Context:** Project Aether uses Tailscale for secure remote networking (per ADR-004). The network originally operated on an allow-all policy (`*:*`). As the deployment grew to include Oracle Cloud instances, a GCP DMZ, and a private Proxmox cluster, this flat layout created an unnecessary risk of lateral movement if a public cloud node were compromised.
- **Problem Statement:** How do we enforce least-privilege traffic boundaries between separate infrastructure environments without breaking administrative access?
- **Decision Drivers:**
  - Cryptographically isolate public cloud nodes (OCI/GCP) from internal homelab networks.
  - Require granular port-level rules (such as restricting DMZ access to specific monitoring ports).
  - Define policy centrally in version control.
- **Decision:** Enforce micro-segmentation within the Tailnet using Tailscale Grants instead of legacy ACL syntax.
- **Architecture Impact:**
  - Role-based tagging organizes devices (`tag:k3s`, `tag:oci`, `tag:gcp-dmz`, `tag:operator`, `tag:k8s-operator`, `tag:k8s`).
  - Network-layer capabilities (`ip`) are explicitly defined per source and destination tag.
  - The Tailnet transitions from a flat mesh to segmented network tiers.
- **Alternatives Considered:**
  - *Legacy Tailscale ACLs:* Rejected. The older ACL syntax couples targets and ports together, making complex rule tables harder to maintain. Tailscale recommends Grants for clear application capabilities and readability.
  - *Host-level Firewalls (UFW/iptables):* Rejected. Maintaining disparate host firewalls across multiple operating systems (Ubuntu, Debian, Proxmox) causes configuration drift. Enforcing rules centrally at the identity layer avoids local firewall management.
- **Decision Rationale:** Tailscale Grants define network capabilities explicitly per source and destination tag, avoiding the maintenance overhead of intertwined port matrices in legacy ACLs. Defining access rules centrally in Tailscale eliminates configuration drift across differing host firewalls (such as UFW and iptables) on disparate operating systems.
- **Consequences:**
  - *Positive:* Constrains lateral movement between environments, isolates homelab nodes from cloud instances, and documents network boundaries in Git.
  - *Negative:* New cross-environment connections require explicit policy updates.
  - *Risks:* Overly restrictive rules can disrupt metrics collection or service communications if not verified before deployment.
- **Security Considerations:**
  - The Tailscale policy file defines sensitive network topology and should be stored securely or encrypted via SOPS if committed to public repositories.
  - Cloud provider firewalls (such as GCP VPC firewall rules) should be restricted to allow inbound management connections only from Tailscale IPv6 CGNAT addresses (`fd7a:115c:a1e0::/48`).
- **Operational Considerations:** Newly provisioned nodes must be tagged properly to prevent the default-deny policy from blocking expected traffic.
- **Dependencies:** Tailscale Grants framework, SOPS.
- **Related ADRs:** ADR-004 (Secure Network Access Layer).

---

### Addendum: Kubernetes Tailscale Operator Integration (PLAT-06)
- **Date:** October 2026
- **Context:** To expose internal Kubernetes services (such as ArgoCD) as MagicDNS endpoints without opening firewall ports, Project Aether deploys the official Tailscale Kubernetes Operator.
- **Tagging & Ownership:**
  - `tag:k8s-operator`: Owned by `autogroup:admin`. Assigned to the operator's OAuth client in the Tailscale admin console.
  - `tag:k8s`: Owned by `tag:k8s-operator` and `autogroup:admin`. Automatically applied by the operator to ingress proxy pods.
- **Grants:**
  - Administrative operator devices (`tag:operator`) retain full access to `tag:k8s`.
  - Cluster nodes (`tag:k3s`) can communicate directly with `tag:k8s` proxies.
  - GCP DMZ monitoring (`tag:gcp-dmz`) is permitted on HTTP/HTTPS (`80, 443`) to probe `tag:k8s` MagicDNS endpoints.

---

### Addendum: Role Tags Set by Configuration, Policy Tests, and SSH (FND-03)
- **Date:** 2026-11-07
- **Context:** Three findings showed that the tag model above was not holding up.
  - Every service on the OCI host is its own tailnet node, published by tsdproxy. tsdproxy v1 signed each one in with a single untagged auth key and signed it in again on every container recreate, which reset any tag set by hand in the console. The DMZ observer could not see those nodes and went blind ([INC-2026-002](../incidents/INC-2026-002-observer-blind-to-app-host.md)).
  - `tag:oci` meant both "runs on OCI" and "the DMZ may reach it on 80/443". When every service was tagged `tag:oci` to restore monitoring, the DMZ could reach 16 of 17 services, including admin tools ([INC-2026-003](../incidents/INC-2026-003-fix-widened-dmz-exposure.md)).
  - The policy had no tests, so nothing failed when the set of reachable services grew.
- **Decision:** Tag OCI services by role, have tsdproxy set those tags from its configuration, and encode the security boundaries as policy tests.
- **Role tags:**

  | Tag | Carried by | Who may reach it |
  |-----|------------|------------------|
  | `tag:oci` | The OCI host's own node only | Operator; other `tag:oci`; K3s on 3100 (Loki) |
  | `tag:oci-app` | User-facing apps | Operator |
  | `tag:oci-probe` | The OCI services the DMZ monitors (with `tag:oci-app`) | Operator; DMZ on 443 |
  | `tag:oci-admin` | Docker UI, log viewer, workflow engine, Prometheus, Grafana, Loki, Alertmanager | Operator only, never the DMZ (ADR-020) |

  Each tag has one meaning. Location is never used to grant access.
- **Tags come from configuration:**
  - tsdproxy v2 signs nodes in through one OAuth client (scopes `devices:core` and `auth_keys`) holding all three role tags.
  - Each role has its own provider in `tsdproxy.yaml` (`app`, `probe`, `admin`), rendered by Ansible from SOPS. A container picks its provider with the label `tsdproxy.proxyprovider`, and the default is `app`.
  - Node state is kept per provider, so a container recreate keeps the node, its address and its tags.
  - Tags are not set in the console.
- **Tag ownership rule:** an OAuth client can mint a key for exactly its full tag set without consulting `tagOwners`. For a subset, each requested tag must be owned by one of the client's tags; `autogroup:admin` does not count. So each role tag also owns itself (`"tag:oci-app": ["autogroup:admin", "tag:oci-app"]`). This is the same pattern as `tag:k8s` being owned by `tag:k8s-operator` above. Self-ownership grants nothing new: a node can only advertise a tag it already has.
- **Grants removed:**
  - `tag:gcp-dmz → tag:oci` on 80/443: replaced by `tag:gcp-dmz → tag:oci-probe` on 443.
  - The temporary address aliases for the two probed services (added 2026-11-03, while tags still reset).
  - `autogroup:shared → tag:oci` on 443: no machine is shared. People outside the tailnet reach the one public app through Funnel (see ADR-004).
  - `tag:AIAgent`: no device carried it.
  - `tag:homelab-dc` was removed from the OCI host, which had carried three role tags at once.
  - Funnel is granted only through `tag:funnel`, no longer to every member device.
- **Policy tests:** the policy file has a `tests` block, which the admin console runs on every save, rejecting a policy that fails one. It checks that:
  - the DMZ reaches `tag:oci-probe:443`, `tag:k3s:443` and `tag:k8s:443`, and nothing on `tag:oci`, `tag:oci-app`, `tag:oci-admin`, the K3s API or the Proxmox UI;
  - OCI reaches the metrics ports and the DMZ's monitoring ports, and not the K3s API or SSH;
  - K3s reaches only Loki on OCI;
  - Proxmox reaches only the DMZ heartbeat port.

  An `sshTests` block checks the operator's SSH access to the DMZ.
- **Tailscale SSH:** only the DMZ runs Tailscale SSH today; other hosts use OpenSSH over the tailnet, which the grants govern.
  - `tag:operator` devices: `accept`, non-root and root.
  - Devices signed in as a user (`autogroup:member`): `check` every 12 h, non-root only.
  - Users to their own devices: `accept`.
- **Consequences:**
  - Positive: a container update can no longer move a security boundary or blind the observer. A grant that widens DMZ access fails at save time.
  - Negative: moving a service between roles creates a new node (state is per provider), so the old one must be removed first. A bulk re-create needs one certificate per node, and tsdproxy issues them slowly ([INC-2026-009](../incidents/README.md#index)).
- **Validation / Fitness Functions:**
  - `tailscale status --json` shows every OCI service node with exactly its role tags, and none untagged.
  - After `docker compose up -d --force-recreate` of a service, the same node keeps the same address and tags (verified 2026-11-07 on the Uptime Kuma node).
  - Every policy change is verified from the source (what answers from the DMZ) and at the destination (the packet filter on the target node).

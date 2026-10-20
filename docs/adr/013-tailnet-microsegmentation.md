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
  - Role-based tagging organizes devices (`tag:k3s`, `tag:oci`, `tag:gcp-dmz`, `tag:operator`).
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

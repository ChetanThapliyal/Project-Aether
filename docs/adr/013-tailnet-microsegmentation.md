```text
================================================================================
ADR-013: Tailnet Micro-segmentation using Tailscale Grants
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect
- **Context:** Project Aether utilizes Tailscale as its secure remote access layer (per ADR-004). Initially, the Tailnet operated on a default "allow-all" policy (`*:*`). As the infrastructure expanded across diverse environments—including public Oracle Cloud (OCI) instances, a GCP DMZ, and a private Proxmox/K3s homelab—this flat network topology presented a significant risk of lateral movement. A compromised public-facing instance could theoretically establish a direct WireGuard connection to the internal K3s control plane.
- **Problem Statement:** How do we restrict internal network routing and prevent unauthorized lateral movement across distinct infrastructure environments while maintaining unified administrative access?
- **Decision Drivers:**
  - Need to cryptographically isolate public cloud environments (OCI/GCP) from internal homelab infrastructure.
  - Granular, port-level access controls required (e.g., DMZ only needs ports 80/443 for monitoring).
  - Centralized, version-controlled policy definition.
- **Decision:** We will enforce micro-segmentation within the Tailnet using Tailscale's modern **Grants** framework, replacing the legacy `acls` syntax.
- **Architecture Impact:**
  - Strict Role-Based Access Control (RBAC) via device tags (`tag:k3s`, `tag:oci`, `tag:gcp-dmz`, `tag:operator`).
  - Network-layer capabilities (`ip`) are explicitly granted per source/destination pair.
  - The Tailnet is no longer a flat mesh; it is segmented based on the principle of least privilege.
- **Alternatives Considered:**
  - *Legacy Tailscale ACLs:* Rejected. While functional, the traditional `acls` syntax intertwines targets and ports, making complex matrices harder to maintain. Tailscale explicitly recommends migrating to Grants for superior application-layer capability support and readability.
  - *Host-level Firewalls (UFW/iptables):* Rejected. Relying on OS-level firewalls across diverse OS distributions (Ubuntu, Debian, Proxmox, Talos) creates immense configuration drift. Enforcing rules centrally at the identity/SDN layer via Tailscale is significantly more resilient.
- **Decision Rationale:** Tailscale Grants provide a modern, declarative, and highly readable syntax for defining network and application-level capabilities. By centralizing segmentation logic in the Tailscale policy, we achieve true Zero Trust boundaries without managing complex per-node firewall configurations.
- **Consequences:**
  - *Positive:* Reduced security blast radius. OCI compromises cannot pivot into the K3s environment. Clear, version-controlled definition of environment boundaries.
  - *Negative:* Adding new cross-environment services now requires updating the Tailscale policy.
  - *Risks:* Misconfiguring a grant could accidentally sever internal service communication or monitoring.
- **Security Considerations:**
  - The policy file itself is a sensitive architectural blueprint. It must be version-controlled in the Git repository but encrypted (e.g., via SOPS) to obscure internal routing topology and device tags.
  - To achieve true Defense-in-Depth, cloud provider firewalls (e.g., GCP VPC firewalls) must be locked down to only permit inbound SSH traffic originating from Tailscale's CGNAT IPv6 block (`fd7a:115c:a1e0::/48`). This ensures public IPs cannot even reach the SSH daemon over the public internet, preventing brute-force fatigue.
- **Operational Considerations:** Operators must remember to tag new instances appropriately upon provisioning, otherwise the implicit deny-by-default stance will block all inbound traffic.
- **Dependencies:** Tailscale Grants framework, SOPS (for secret management).
- **Related ADRs:** ADR-004 (Secure Network Access Layer).

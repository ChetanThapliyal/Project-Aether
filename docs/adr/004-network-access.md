```text
================================================================================
ADR-004: Secure Network Access Layer (Tailscale)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Remote administration of the Proxmox hypervisor, Kubernetes nodes, and internal services requires network access when operating outside the home LAN. Furthermore, many residential ISPs in India operate behind Carrier-Grade NAT (CGNAT), preventing inbound connections entirely.
- **Problem Statement:** How do we establish a zero-trust, location-agnostic remote administration channel for the infrastructure without exposing public ports on the home router and circumventing ISP CGNAT?
- **Decision Drivers:**
  - Zero open ports on the physical ISP router (minimize attack surface).
  - Ability to traverse CGNAT seamlessly.
  - Need for private, authenticated remote access, not public internet exposure.
- **Decision:** I will deploy **Tailscale** as the zero-trust mesh network layer.
- **Architecture Impact:** Tailscale daemons will be installed on the Proxmox host, all Kubernetes VMs, and operator devices. A Tailscale Operator will be deployed inside the cluster to expose specific services internally to the mesh via MagicDNS.
- **Alternatives Considered:**
  - *Port Forwarding (Router Level):* Rejected. Every open port is a direct, unauthenticated entry point from the internet into the home network. Additionally, it fundamentally breaks when the ISP uses CGNAT.
  - *Cloudflare Tunnels:* Rejected. While valid for zero-open-port architectures, Tunnels are designed for *ingress* (publishing internal services to the public internet via Cloudflare's edge). Our use case requires *private remote access* (acting as if the remote laptop is on the home LAN).
- **Decision Rationale:** Tailscale's mesh model (any-device-to-any-device via WireGuard) perfectly fits the requirement of "remote admin access to private infra." It solves the CGNAT problem automatically via NAT traversal and DERP relays. It provides MagicDNS, allowing seamless multi-device access (K3s API, Proxmox UI, SSH) over a single WireGuard interface without the need to configure per-service tunnels.
- **Consequences:**
  - *Positive:* 100% remote connectivity from any network; zero firewall ports exposed; automatic CGNAT traversal; built-in DNS resolution.
  - *Negative:* Dependency on a third-party SaaS coordination plane (Tailscale control plane).
  - *Risks:* Compromise of the operator's Tailscale identity (e.g., Google/GitHub SSO) grants direct access to the internal management subnet.
  - *Trade-offs:* Reliance on a managed coordination server in exchange for zero-maintenance NAT traversal and WireGuard key rotation.
- **Security Considerations:** Tailscale admin account must be secured with strict Multi-Factor Authentication (MFA). Key expiry is enforced on client machines.
- **Reliability Considerations:** If the Tailscale control plane goes down, existing established WireGuard tunnels continue passing peer-to-peer traffic, but new nodes cannot join.
- **Scalability Considerations:** The free personal tier easily supports the scale of this homelab.
- **Performance Considerations:** Direct peer-to-peer connections provide full local bandwidth. DERP relays are only utilized when direct UDP hole-punching fails.
- **Operational Considerations:** Installing the Tailscale daemon is a mandatory step in the VM bootstrap process via Ansible.
- **Cost Considerations:** Infrastructure: ₹0.00 (Tailscale Free Personal Plan).
- **Migration Plan:** N/A - Implemented via Ansible during Phase 1.
- **Validation / Fitness Functions:**
  - Operator must be able to SSH into a cluster node using its MagicDNS name from an external cellular network.
- **Dependencies:** Tailscale Coordination Server, WireGuard.
- **Open Questions:** None.
- **Related ADRs:** ADR-011 (Tailscale Operator Integration).
- **Review Conditions:** Review if Tailscale alters free-tier terms, or if full control plane sovereignty is required (e.g., migrating to self-hosted Headscale).

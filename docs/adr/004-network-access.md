```text
================================================================================
ADR-004: Secure Network Access Layer (Tailscale)
================================================================================
```
- **Status:** Accepted
- **Date:** May 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Remote administration of the Proxmox hypervisor, Kubernetes nodes, and internal services requires network access outside the home LAN. In addition, many residential ISPs in India operate behind Carrier-Grade NAT (CGNAT), preventing direct inbound connections.
- **Problem Statement:** How do we establish a zero-trust, location-agnostic remote administration channel for infrastructure without opening public ports on the home router or encountering CGNAT blocks?
- **Decision Drivers:**
  - Zero open ports on the physical ISP router to minimize attack surface.
  - Ability to traverse CGNAT automatically.
  - Private, authenticated remote administration without public exposure.
- **Decision:** Deploy Tailscale as the mesh network overlay.
- **Architecture Impact:** Tailscale daemons will be installed on the Proxmox host, all Kubernetes VMs, and operator devices. A Tailscale Operator inside the cluster exposes select internal services to the mesh via MagicDNS.
- **Alternatives Considered:**
  - *Port Forwarding (Router Level):* Rejected. Open router ports expose an unauthenticated entry point from the internet to the local network. Port forwarding also fails behind ISP CGNAT.
  - *Cloudflare Tunnels:* Rejected. While effective for zero-open-port ingress, Cloudflare Tunnels publish internal services to the public internet. This use case requires private operator access to internal nodes.
- **Decision Rationale:** Tailscale connects nodes through peer-to-peer WireGuard tunnels with NAT traversal and DERP relay fallback, bypassing residential CGNAT without opening firewall ports. MagicDNS routes requests to the Proxmox UI, K3s API, and SSH endpoints using stable hostnames over a single virtual interface.
- **Consequences:**
  - *Positive:* Encrypted remote connectivity without port forwarding, automatic CGNAT traversal, and built-in MagicDNS resolution.
  - *Negative:* Dependency on an external SaaS coordination plane (Tailscale control plane).
  - *Risks:* Compromise of the operator's SSO identity grants direct access to the management subnet.
  - *Trade-offs:* Relying on a managed coordination server in exchange for automated NAT traversal and key rotation.
- **Security Considerations:** The Tailscale admin account must require multi-factor authentication (MFA). Key expiry is enforced on client machines.
- **Reliability Considerations:** If the Tailscale coordination plane becomes unavailable, established peer-to-peer tunnels continue passing traffic, though new nodes cannot enroll.
- **Scalability Considerations:** The personal plan accommodates the node count of this homelab.
- **Performance Considerations:** Direct peer-to-peer connections use available local bandwidth. DERP relays are used only when direct UDP hole punching fails.
- **Operational Considerations:** Installing the Tailscale daemon is a required step during VM bootstrap with Ansible.
- **Cost Considerations:** Infrastructure: ₹0.00 (Tailscale personal plan).
- **Migration Plan:** N/A (installed via Ansible in Phase 1).
- **Validation / Fitness Functions:**
  - Operator must be able to SSH into a cluster node using its MagicDNS name from an external cellular network.
- **Dependencies:** Tailscale Coordination Server, WireGuard.
- **Open Questions:** None.
- **Related ADRs:** ADR-011 (Tailscale Operator Integration).
- **Review Conditions:** Review if Tailscale plan terms change, or if full control plane sovereignty requires self-hosted Headscale.

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

---

### Addendum: Public Entry Points (2026-11-12)
Operator access stays on Tailscale, as decided above. The project now has exactly one intended public entry point, and it's read-only:

| Public name | Path | Serves |
|-------------|------|--------|
| `status.chetan-thapliyal.cloud` | Cloudflare edge → Cloudflare Tunnel (outbound-only `cloudflared` on the GCP DMZ) | The Glance status page only ([ADR-020](020-public-observability-data-diode.md)) |

The tunnel was rejected above for *operator* access, and it still isn't used for that: it routes one hostname to one container, opens no inbound port, and reaches nothing on the tailnet. Any other way in from the internet is a defect, with one recorded exception: a Tailscale Funnel on the app host still publishes one app (BookOrbit) because it has a user. The hardening pass limited the Funnel permission to that one tagged node. Closing it is scheduled for the Phase 05 close-out (re-audit sign-off, 15 Nov 2026).

### Addendum: A Second Public Hostname for GitOps Webhooks (2026-11-16)
The tunnel now publishes a second hostname, `argocd-hook.chetan-thapliyal.cloud`, with one path, `^/api/webhook$`. It forwards GitHub's push notifications to the ArgoCD server over the tailnet, so a push syncs in seconds instead of on the 3-minute poll.

| Public name | Path | Serves |
|-------------|------|--------|
| `argocd-hook.chetan-thapliyal.cloud` | Cloudflare edge → Tunnel → `cloudflared` on the GCP DMZ → tailnet (`tag:gcp-dmz → tag:k8s:443`) → ArgoCD's Tailscale ingress | `POST /api/webhook` only. Every other path is the tunnel's catch-all 404 |

This changes one statement in the addendum above: the tunnel now reaches one thing on the tailnet, ArgoCD's webhook endpoint, over a grant that already existed. The limits:

- ArgoCD rejects any payload that isn't signed with the shared secret (HMAC-SHA256). The secret lives in SOPS and is injected at install; it is never in Git in plaintext. An unsigned or wrongly signed request gets 400 (tested 16 Nov).
- A Cloudflare WAF custom rule blocks the hostname for every source outside GitHub's published webhook ranges (`hooks` in `https://api.github.com/meta`, checked 16 Nov). Other sources get 403 at Cloudflare's edge before reaching the tunnel. Review the ranges when GitHub announces changes; a missing range shows up as failed deliveries in the repository's webhook settings.
- A valid webhook can only make ArgoCD re-read Git. It can't change what gets deployed: that is still whatever is on `main`.
- The ArgoCD UI and API stay tailnet-only: `/`, `/applications` and `/api/v1/...` return 404 on the public hostname (tested 16 Nov).

Rollback: delete the GitHub webhook and the tunnel route. ArgoCD falls back to polling on its own.

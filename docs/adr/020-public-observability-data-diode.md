```text
================================================================================
ADR-020: Public Observability Architecture, Glance Dashboard, and Push Data Diode
================================================================================
```
- **Status:** Accepted (diode built as a pull of one sanitised file; see the addenda)
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether requires a unified, public-facing platform dashboard and operational status view accessible over the public internet via Cloudflare Tunnel (`status.chetanthapliyal.com`) and privately over the Tailscale mesh (`http://aether-gcp-dmz:3000`). The edge observer environment runs on a Google Cloud Platform (GCP) Always-Free `e2-micro` instance (`aether-gcp-dmz`), strictly constrained to 1 GB of physical memory and 2 shared vCPUs. The initial implementation utilized Homepage (`gethomepage/homepage:v2.5.0`), which had a Node.js runtime footprint of 150–250 MiB RSS and relied on direct outbound API calls to backend platform services.
- **Problem Statement:** How do we present rich, real-time platform telemetry (Kubernetes cluster status, node health, GitOps sync state, upstream release feeds) on an internet-facing DMZ without exhausting the 1 GB physical memory ceiling of the `e2-micro` instance, leaking sensitive internal network metadata, or creating inbound network ingress routes from the public DMZ into the private core infrastructure?
- **Decision Drivers:**
  - *Strict Edge RAM Budget (< 50 MiB Target):* The GCP DMZ instance possesses only 969 MiB of usable physical RAM shared across the Linux OS, systemd, Tailscale, Docker daemon, Uptime Kuma, Hawser, Cloudflared, and the Docker socket proxy. Allocating 150–250 MiB to Homepage represented ~25% of total system memory, inducing swap thrashing and out-of-memory (OOM) instability.
  - *Strict Network Segmentation & Blast Radius Containment:* The DMZ is exposed to the public internet via Cloudflare Tunnel. Under the Project Aether Zero-Trust threat model ([ADR-004](004-network-access.md), [ADR-013](013-tailnet-microsegmentation.md)), the DMZ is considered untrusted. An attacker achieving remote code execution (RCE) in a public web container must have zero network routes to query internal Prometheus (`:9090`), Kubernetes API (`:6443`), ArgoCD (`:8080`), or internal databases.
  - *Unidirectional Push Data Diode Model:* Telemetry data must flow strictly outward from the secure core (OCI/Homelab) to the edge (GCP DMZ). The edge must never pull from or query the core.
  - *Sanitized Public Contract:* Telemetry rendered on the public dashboard must never leak RFC1918 private IPs, Tailscale CGNAT IPs, internal cluster DNS names (`.svc.cluster.local`), Kubernetes secret names, or raw token identifiers. Metrics must be aggregated into an abstract, high-level summary.
  - *Partition Tolerance & Cold-Start Resilience:* The public status dashboard must remain fully responsive and serve cached status even during inter-cloud WAN outages, OCI reboots, or temporary Prometheus scrape hiccups without throwing 500/502 gateway errors.
  - *Zero Infrastructure Cost:* ₹0.00 / $0.00 monthly cost constraint across all cloud tiers.
- **Decision:**
  1. *Decommission Homepage:* Retire Homepage from `aether-gcp-dmz`. The Node.js architecture and active polling model are unsuitable for resource-constrained edge environments.
  2. *Adopt Glance (`glanceapp/glance:latest`):* Deploy Glance as the platform status dashboard. Glance is a compiled Go binary that runs at ~35–45 MiB RSS (~75% memory reduction compared to Homepage), offers sub-millisecond static page rendering, and natively supports customizable YAML-driven pages, HSL color theming, Atom/RSS feeds, and local static data ingestion.
  3. *Enforce the Push Data Diode Architecture:*
     - Reject all pull-based queries from `tag:gcp-dmz` to internal telemetry endpoints. Tailscale ACLs explicitly prohibit `tag:gcp-dmz` from accessing port 9090 (Prometheus), port 6443 (Kubernetes API), or port 8080 (ArgoCD) on `tag:oci` or `tag:k3s`.
     - Implement an out-of-band scheduled telemetry exporter on OCI (`bookorbit`). A scheduled Python script/Kestra workflow queries local Prometheus (`http://localhost:9090`), aggregates platform metrics into an abstract schema (`summary.json`), sanitizes all internal identifiers, and pushes the payload to `/opt/dmz/glance/data/summary.json` on GCP DMZ over an authenticated Tailscale SSH / SCP channel.
     - Glance reads this local, static `summary.json` file on disk. The DMZ container has zero network listeners or outbound sockets connected to private infrastructure.
  4. *Port and Route Parity (Port 3000):* Map Glance external port `3000` to container port `8080` in `docker-compose.yml`, preserving existing Cloudflare Tunnel routes, Tailscale Serve mappings, and Uptime Kuma monitoring probes without requiring edge reconfiguration.
  5. *Multi-Tab Information Architecture:*
     - **Tab 1: Overview** — Real-time clock (IST/UTC), architecture overview card, curated public repository bookmarks, and high-level platform vitals.
     - **Tab 2: Infrastructure** — Multi-tier infrastructure topology matrix (GCP DMZ, OCI Core, On-Prem Homelab K3s), resource budgets, and clickable links to Architecture Decision Records.
     - **Tab 3: Feeds & Upstream** — Live release tracking via Atom feeds for core platform dependencies (Glance, K3s, ArgoCD, Envoy Gateway).
- **Architecture Impact:**
  - Memory consumption for the dashboard service on GCP DMZ drops from ~180 MiB to ~40 MiB, freeing >140 MiB of physical RAM for system stability and Uptime Kuma probes.
  - The attack surface of the public DMZ is strictly severed from the internal control planes. An RCE in Glance yields access only to a static JSON file on disk, with no credentials and no network routes to internal clusters.
  - Dashboard updates are decoupled from real-time Prometheus query latency, guaranteeing instant page loads regardless of internal TSDB load.
- **Alternatives Considered:**
  - *Keep Homepage (`gethomepage/homepage`):* Rejected. High memory consumption (150–250 MiB RSS) frequently threatened the 1 GB physical RAM limit on `e2-micro`. Furthermore, Homepage's widget design encourages direct outbound API connections to Docker, Kubernetes, and Prometheus, conflicting with the required zero-trust push data diode architecture.
  - *Pull-Based Telemetry via Tailscale (DMZ Queries OCI Prometheus):* Rejected. Granting `tag:gcp-dmz` network access to `tag:oci:9090` violates the principle of least privilege. If the DMZ container or host were compromised, the attacker could execute arbitrary PromQL queries, extract internal network topologies, or exploit Prometheus API vulnerabilities to pivot deeper into the environment.
  - *Public Grafana Dashboard on OCI:* Rejected. Exposing Grafana to the public internet creates significant attack surface (Grafana CVEs, session hijacking, denial of service against the TSDB). Hosting the public dashboard in an isolated, stateless DMZ keeps OCI completely private.
  - *Static Site Generator (Hugo / Astro generated via CI/CD):* Evaluated. While static sites offer minimal memory overhead, rebuilding and deploying a full static website every 60 seconds introduces unnecessary CI/CD churn and git commit noise for ephemeral operational telemetry. Glance provides the benefits of static serving with dynamic in-place YAML/JSON reloads.
- **Decision Rationale:** Glance delivers the optimal compromise between ultra-low resource utilization (<50 MiB RAM), modern aesthetic presentation, and architectural security. Combining Glance with a push-based data diode model enforces strict zero-trust isolation: internal systems push sanitized snapshots outward, ensuring that even a total compromise of the public DMZ leaves the internal Kubernetes cluster and telemetry TSDB completely inaccessible and unexposed.
- **Consequences:**
  - *Positive:*
    - Edge RAM footprint reduced by >70% (~40 MiB vs ~180 MiB).
    - Zero network routes from public DMZ to internal Kubernetes API or Prometheus.
    - Zero sensitive internal IP addresses, cluster DNS names, or auth tokens present in DMZ configuration.
    - Instant dashboard rendering from local disk cache with zero upstream query latency.
    - Automatic in-place configuration reload without container restarts when `glance.yml` changes.
  - *Negative:*
    - Dashboard telemetry reflects a 60-second polling resolution determined by the OCI push schedule rather than live real-time websocket streams.
    - An additional cron/Kestra flow must be maintained on OCI to aggregate and push `summary.json`.
  - *Risks:*
    - If the OCI push workflow fails, `summary.json` becomes stale. Mitigated by Glance displaying the `generated_at` timestamp and fallback handling for missing metric fields.
  - *Trade-offs:* Trading 60-second telemetry staleness for absolute network isolation and 140 MiB of reclaimed edge RAM.
- **Security Considerations:**
  - The Glance container runs rootless where possible, with configuration directories mounted read-only (`:ro`).
  - Tailscale ACL policies explicitly block traffic from `tag:gcp-dmz` to all internal management ports.
  - The `summary.json` aggregator script explicitly filters out node names, internal IP ranges (`192.168.1.0/24`, `10.42.0.0/16`, `100.64.0.0/10`), pod UUIDs, and secret references before pushing to DMZ.
- **Reliability Considerations:**
  - Glance serves static content from `/app/config/glance.yml` and `/app/data/summary.json`. If OCI is unreachable, Glance continues serving the last valid snapshot with zero downtime or gateway errors.
- **Performance Considerations:**
  - Glance static asset requests execute in < 2ms, significantly outperforming Homepage's Node.js SSR pipeline on single-core ARM/x86 shared compute.
- **Operational Considerations:**
  - Managed via GitOps and Ansible: `infrastructure/docker/gcp-dmz/glance/glance.yml` is version-controlled and deployed via `task ansible:dmz`.
- **Cost Considerations:**
  - ₹0.00 / $0.00. Fully conforms to Always-Free tier compute and memory boundaries on GCP and OCI.
- **Validation / Fitness Functions:**
  - `docker stats glance` confirms memory usage remains below 50 MiB RSS.
  - `curl -I http://127.0.0.1:3000` returns HTTP 200 within 5 seconds of container launch.
  - Tailscale ACL test confirms traffic from `tag:gcp-dmz` to `tag:oci:9090` is dropped.
- **Dependencies:** Docker Compose, Glance (`glanceapp/glance`), Tailscale, Cloudflare Tunnel, OCI Prometheus.
- **Related ADRs:**
  - [ADR-004](004-network-access.md) (Network Access via Tailscale)
  - [ADR-013](013-tailnet-microsegmentation.md) (Tailnet Microsegmentation)
  - [ADR-014](014-infrastructure-environment-isolation-strategy.md) (Infrastructure Environment Isolation Strategy)
  - [ADR-019](019-centralized-logging-architecture.md) (Centralized Logging Architecture)
- **Review Conditions:** Re-evaluate if GCP DMZ instance is upgraded to a dedicated tier, or if custom real-time websocket status streaming is required.

---

### Addendum: Implementation Status (2026-11-12, HARD-17)
- **Glance replacing Homepage:** delivered on 2026-11-02 (Glance v0.8.7, pinned by digest). Homepage's files and the Docker socket proxy it needed were removed on 2026-11-12 (FND-08).
- **Data diode:** built on 2026-11-12 (FND-20) as a *pull of a single sanitised file*, not the SSH push described above. See the second addendum.
- **Sanitised public contract:** enforced from 2026-11-12. The page carries no tailnet hostnames or links, and no LAN or cluster addresses. Operator consoles are named, never linked. `glance.yml` opens with these rules, and DR scenario 05 checks them.
- **Public hostname:** live on 2026-11-12 at `https://status.chetan-thapliyal.cloud` (FND-10). `status.chetanthapliyal.com` in the Context above never existed. Path: Cloudflare edge (Universal SSL, `*.chetan-thapliyal.cloud`) → Cloudflare Tunnel → `cloudflared` on the DMZ (outbound only, QUIC over IPv6, no inbound port) → `http://glance:8080` on `dmz-net`. The tunnel publishes only Glance.

---

### Addendum: The Feed as Built (2026-11-12, FND-20)
- **Generator.** A container `public-feed` in the OCI monitoring stack (`legacy-docker/oci-services/public-feed/feed.py`, standard-library Python, non-root, read-only filesystem, 64 MiB) queries Prometheus every 5 minutes. It builds an allow-listed summary: node, app, pod, target and alert counts; six capacity gauges; four 6-hour series (cluster CPU and memory, cloud host CPU, hypervisor temperature); and container image names and tags from kube-state-metrics.
- **Allow-list.** Before publishing, the whole summary is checked against a deny pattern (tailnet names, `192.168.`, cluster and tailnet address ranges, node and host names, `:9100`). A summary that fails is never served. The last good one stays up and goes stale.
- **Numbers only.** Charts are sent as pre-scaled coordinates, and gauges as arc lengths. Every SVG element is drawn by the template in `glance.yml`, and Glance's HTML escaping applies to every value, so a compromised feed can't inject markup into the public page.
- **Transport: pull instead of push.** tsdproxy publishes the feed on the tailnet under the `probe` role. The DMZ already had exactly one path into OCI, `tag:gcp-dmz → tag:oci-probe:443`, covered by a policy test, and Glance fetches the file over it server-side. This replaced the SSH push: Tailscale SSH can't restrict a key to one file, and a push would have needed a new OCI → DMZ:22 grant. Compromising the DMZ yields the same public summary it already displays. Grafana, Prometheus and the other admin nodes don't even resolve from the DMZ.
- **Freshness.** The feed reports `age_seconds` and `fresh` (under 15 minutes old). The page shows "Live · updated N ago" or "Data delayed since …". A JSON-query monitor in the DMZ's Uptime Kuma goes DOWN and alerts on Telegram when `fresh` isn't true.
- **Backups and alerting list.** It comes from the DMZ's own Uptime Kuma, through a status page (`public`) that holds only monitors whose names are safe to publish, read over the DMZ's Docker network.
- **Not done:** Grafana panels as images and live Grafana. The option of Grafana shared dashboards behind a second tunnel connector on OCI is deferred until after Phase 04.

```text
================================================================================
ADR-019: Centralized Logging Architecture & In-Cluster Log Forwarding Ruling
================================================================================
```
- **Status:** Accepted
- **Date:** October 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Project Aether operates a hybrid multi-cloud infrastructure spanning a physical 3-node K3s cluster on a 12 GB RAM notebook (1 control plane, 2 worker VMs with ~3.5 GB allocatable RAM each), an Always-Free Oracle Cloud (OCI A1.Flex) instance (`bookorbit`), and an Always-Free GCP DMZ instance. Container workloads on K3s output application logs to stdout/stderr, which containerd writes to `/var/log/pods/` on node SSDs.
- **Problem Statement:** How do we establish centralized log aggregation, historical search, and automated log correlation with Prometheus metrics without depleting the physical 12 GB RAM ceiling on the notebook, inducing severe SSD write amplification, or compromising cluster stability?
- **Decision Drivers:**
  - *Strict Homelab Memory Budget:* 12 GB total RAM on notebook; worker nodes are capped at ~3.5 GB allocatable memory and must prioritize core platform ingress and stateful application workloads.
  - *SSD Write Churn & I/O Protection:* In-cluster log indexing engines (e.g. Lucene/Elasticsearch or in-cluster Loki TSDB) cause continuous write amplification and heavy I/O churn on consumer SATA/NVMe SSDs.
  - *Portfolio & Industry Standard Recognition:* Observability stack must align with cloud-native engineering standards (Prometheus, Loki, Grafana - PLG stack) for professional portfolio evaluation.
  - *Unified Metric-to-Log Correlation:* Operators must be able to navigate seamlessly between Prometheus metrics (alerts, CPU spikes, 5xx rate) and container log streams in a single Grafana interface without manual terminal context-switching.
  - *Zero-Trust Network Transit:* All log forwarding across infrastructure boundaries must transit encrypted peer-to-peer tunnels governed by least-privilege access controls.
  - *Zero Infrastructure Cost:* ₹0.00 / $0.00 monthly cost requirement across all platforms.
- **Decision:**
  1. *Reject In-Cluster Log Aggregators (Elasticsearch / In-Cluster Loki):* Neither Elasticsearch, OpenSearch, nor an in-cluster Loki chunk store shall be deployed on K3s. In-cluster aggregation engines require 1.0–2.5 GB of RAM baseline and cause relentless SSD wear.
  2. *Adopt Hybrid Out-of-Band Log Architecture:* Centralized log storage, indexing, and LogQL query execution are externalized to the OCI Always-Free instance (`bookorbit`: 2 ARM vCPU, 12 GB RAM, 100 GB boot volume), co-located with central Prometheus and Grafana.
  3. *Deploy Stateless Promtail DaemonSet on K3s (PLAT-09):* K3s nodes run only a lightweight, stateless log-forwarding agent (`promtail` DaemonSet). Promtail mounts `/var/log/pods/` as read-only, enriches raw log streams with Kubernetes metadata labels (`namespace`, `pod`, `container`, `app`), and streams compressed log batches across Tailscale.
  4. *Enforce Low-Footprint Agent Budget (< 25 MiB RAM per node):* Promtail is constrained to `requests: 10m CPU / 24Mi RAM` and `limits: 50m CPU / 64Mi RAM` with CRI parsing enabled, keeping in-cluster logging overhead under 0.8% of worker memory.
  5. *Single-Binary Grafana Loki on OCI with Filesystem Storage:* OCI deploys a single-binary Grafana Loki container via Docker Compose with a local filesystem chunk store and a strict 14-day retention period (`retention_period: 336h`), bounding disk growth to < 15 GB.
  6. *Tailscale Micro-Segmentation (Port 3100):* Log traffic travels strictly over the Tailscale WireGuard mesh. A dedicated Tailscale ACL grant authorizes `tag:k3s` nodes to reach `tag:oci` exclusively on TCP port 3100 (`src: ["tag:k3s"], dst: ["tag:oci"], ip: ["3100"]`), maintaining zero public ingress exposure.
- **Architecture Impact:**
  - In-cluster K3s overhead for logging is limited to ~70 MiB RAM across the entire 3-node cluster.
  - Container logs survive local pod terminations, restarts, and node reboots.
  - OCI Grafana gains native Loki datasource provisioning (`http://loki:3100`), unlocking the Grafana "Explore" split-view feature where clicking any Prometheus metric graph directly opens correlated log streams via matched labels.
  - No public ports or external internet traffic are opened for log collection.
- **Alternatives Considered:**
  - *Elasticsearch / OpenSearch (EFK/ECK Stack):* Rejected. Requires minimum 2–4 GB JVM heap, extensive CPU for inverted full-text indexing, and heavy storage overhead. Completely incompatible with 12 GB homelab constraints.
  - *In-Cluster Loki (Single-Binary on K3s):* Rejected. While lighter than Elasticsearch, running Loki's TSDB and chunk store in-cluster consumes ~500 MiB RAM and creates heavy SSD write churn, violating ADR-016 storage guidelines.
  - *VictoriaLogs on OCI:* Evaluated as an alternative. VictoriaLogs delivers exceptional compression (up to 10x less disk) and low memory (~100 MiB). However, it lacks native out-of-the-box Grafana integration (requires third-party datasource plugin) and deviates from the industry-standard PLG stack expected in professional platform engineering reviews. Loki's resource footprint on OCI (250–350 MiB) is well within OCI's 12 GB RAM budget.
  - *Pure CLI-Driven Logging (`stern` / `kubectl logs` without Centralized Storage):* Rejected. While zero-cost on memory, ephemeral container logs are permanently lost when pods crash, restart, or get rescheduled during incidents. Centralized retention is mandatory for post-mortem analysis and recruiter showcase.
  - *Third-Party SaaS (Datadog / Loggly / Grafana Cloud):* Rejected. Incurs paid egress or subscription tiers, conflicts with self-hosted sovereignty, and defeats the goal of building a production-grade bare-metal platform.
- **Decision Rationale:** The hybrid architecture achieves the optimal balance between strict homelab physical resource constraints and enterprise-grade observability. Offloading Loki to OCI leverages free cloud compute and block storage, while keeping K3s completely stateless regarding log storage. Aligning with Grafana Loki preserves native metric-to-log correlation in Grafana and demonstrates standard industry best practices.
- **Consequences:**
  - *Positive:* Homelab memory consumption for logging is < 25 MiB per node; zero local SSD wear from log databases; historical log search available up to 14 days; native Grafana LogQL exploration and metric correlation; zero cloud costs.
  - *Negative:* Log shipping depends on Tailscale mesh availability; if the homelab loses WAN connectivity, logs are buffered in Promtail memory/disk temporarily up to buffer limits before dropping.
  - *Risks:* Uncapped container log generation from runaway application loops could fill OCI disk. Mitigated by Promtail client-side rate limiting and Loki 14-day retention pruning.
  - *Trade-offs:* Trading in-cluster log independence for 1.5 GB of preserved worker RAM and zero SSD wear.
- **Security Considerations:**
  - Promtail mounts `/var/log/pods` with read-only permissions (`readOnly: true`).
  - Promtail runs with restricted capabilities, dropping all Linux capabilities except those necessary for file reading.
  - Log ingestion endpoint on OCI (`:3100`) is bound exclusively to the Docker internal network and Tailscale interface; never exposed to public internet.
  - Tailscale ACL micro-segmentation permits traffic from `tag:k3s` to `tag:oci` strictly on port 3100.
- **Reliability Considerations:**
  - If Loki on OCI becomes temporarily unreachable, Promtail buffers log entries locally and executes exponential backoff retries.
  - Container logs continue to rotate locally on node SSDs via containerd independent of Promtail status.
- **Scalability Considerations:**
  - Retention is enforced via Loki Compactor (`retention_enabled: true`, `retention_period: 336h`).
  - Chunk storage utilizes local directory on OCI boot volume with room to expand to external OCI block volumes if retention needs increase.
- **Performance Considerations:**
  - Promtail batches log entries into compressed gzip payloads before transmission, minimizing WireGuard bandwidth consumption.
  - Label cardinality is restricted to high-level Kubernetes metadata (`namespace`, `app`, `pod`, `container`), avoiding dynamic high-cardinality labels (e.g. user IDs or IP addresses) that bloat Loki indices.
- **Operational Considerations:**
  - Managed via GitOps: Promtail deployed via ArgoCD Application in `kubernetes/cluster/promtail.yaml`.
  - OCI Loki and Grafana datasource managed via Ansible playbook `infrastructure/ansible/playbooks/oci-monitoring.yml`.
- **Cost Considerations:**
  - ₹0.00 / $0.00. Operates within OCI Always-Free tier and existing homelab hardware.
- **Validation / Fitness Functions:**
  - Promtail DaemonSet scheduled on all 3 nodes with steady-state memory < 30 MiB.
  - Live log ingestion confirmed in OCI Grafana Explore querying `{namespace="argocd"}` within 10 seconds of pod output.
  - Tailscale drop rules confirmed: non-3100 traffic from K3s to OCI remains blocked.
- **Dependencies:** Tailscale WireGuard mesh, OCI A1.Flex Compute, ArgoCD, Grafana.
- **Related ADRs:**
  - ADR-001 (Hypervisor Selection)
  - ADR-002 (Dual-Tier Storage Topology)
  - ADR-003 (Kubernetes Distribution - K3s)
  - ADR-004 (Network Access via Tailscale)
  - ADR-010 (Orchestration Migration)
  - ADR-013 (Tailnet Micro-segmentation)
  - ADR-016 (Kubernetes Storage Strategy)
- **Review Conditions:** Re-evaluate if log ingestion volume exceeds 20 GB/week or if homelab hardware is upgraded to a dedicated 64 GB multi-node cluster.

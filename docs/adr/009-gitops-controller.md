```text
================================================================================
ADR-009: GitOps Controller Selection (ArgoCD vs Flux)
================================================================================
```
- **Status:** Proposed
- **Date:** September 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** When I started Project Aether, my goal was to build a robust, production-grade Kubernetes homelab to run my personal services using GitOps best practices. I knew I had a really tight RAM budget—my two worker nodes only have about 3.0 GB of allocatable RAM each. Worker-01 is tied up with my monitoring and platform services, which leaves Worker-02 to handle my actual applications and the GitOps controller itself. Recently, I made the hard decision to aggressively cut down my self-hosted apps from 34 to just 5 or 6 core services, offloading the rest to an external OCI server. Suddenly, I have a lot more breathing room on my memory budget.
- **Problem Statement:** How do we establish a declarative GitOps synchronization loop for cluster applications and infrastructure without exhausting the ~3.0 GB memory budget on Worker-02?
- **Decision Drivers:**
  - Need for hands-on experience with industry-standard, enterprise-grade GitOps tooling.
  - Strict RAM capping on Worker-02.
  - Desire for high visibility into deployment health and Kubernetes object status.
- **Decision:** I will deploy **ArgoCD** as the core GitOps controller for Project Aether.
- **Architecture Impact:** ArgoCD will manage all application deployments, monitoring stacks, and platform services within the cluster. It will pull manifests directly from the GitHub repository and run on Worker-02.
- **Alternatives Considered:**
  - *Flux v2:* Rejected. While incredibly lightweight (~150MB RAM) and technically superior for constrained environments, it lacks a native Web UI out-of-the-box (requiring Weave GitOps). It does not provide the same visual learning experience and enterprise adoption recognition as ArgoCD.
- **Decision Rationale:** With the reduction in hosted applications, the memory budget constraint was significantly relaxed. The visual management, troubleshooting ease, and industry standard alignment of ArgoCD far outweighed the RAM savings provided by Flux.
- **Consequences:**
  - *Positive:* Hands-on experience with an industry-standard tool; excellent visual representation of application health.
  - *Negative:* Higher baseline memory consumption.
  - *Risks:* ArgoCD components (Redis, Dex, Repo Server) could spike in memory usage and cause OOM evictions if not properly tuned.
  - *Trade-offs:* Sacrificing ~500MB of RAM for better developer experience and observability.
- **Security Considerations:** ArgoCD Web UI will be exposed via internal ingress and secured. No public exposure of the GitOps control plane.
- **Reliability Considerations:** If ArgoCD goes down, currently running workloads are unaffected, but no new changes will sync until it recovers.
- **Scalability Considerations:** Can easily handle the scale of 5-6 applications and cluster infrastructure manifests.
- **Performance Considerations:** Will consume a substantial portion of Worker-02's memory (estimated 500Mi+ limit required).
- **Operational Considerations:** Requires aggressive tuning of resource requests/limits in the `values.yaml` to prevent resource starvation for other apps.
- **Cost Considerations:** Infrastructure: ₹0.00 (Open-source).
- **Migration Plan:** Install manually via Helm for the initial bootstrap, then adopt the "App of Apps" pattern to manage itself and the rest of the cluster.
- **Validation / Fitness Functions:**
  - ArgoCD components must not exceed 1GB combined RAM usage under steady state.
  - Git commits to the `main` branch must reflect in the cluster within 3 minutes.
- **Dependencies:** GitHub repository, K3s Cluster, Helm.
- **Open Questions:** How exactly will we handle secrets decryption (KSOPS or SOPS plugin) within ArgoCD?
- **Related ADRs:** ADR-007 (Secrets Management), ADR-008 (Operational Toolchain).
- **Review Conditions:** Review if Worker-02 frequently encounters MemoryPressure or OOMKills after all 5-6 apps are deployed.

```text
================================================================================
ADR-017: Automation and Scheduling: Kestra on the Cloud Host, Jobs Where They Live
================================================================================
```
- **Status:** Accepted (in place since the November 2026 hardening pass; recorded 18 Nov 2026)
- **Date:** November 2026
- **Owner:** Principal Architect / Homelab Owner
- **Context:** Scheduled work runs in three places: the cloud host (Oracle), the K3s cluster and the hypervisor. The cloud host started with root crontabs. Then Kestra arrived as a workflow engine and n8n as an integration tool, and for a while the same job ran from both cron and Kestra. The nightly backup had two schedulers (INC-2026-001), and the weekly Docker prune raced itself in the same minute (Kestra's run on 8 Nov failed). Without one rule, every new job raised the same question again: which scheduler, and from which machine?
- **Problem Statement:** Which tool schedules which job, and on which machine does a job run, so that each job has exactly one scheduler, fails loudly, and needs no network access it wouldn't otherwise have?
- **Decision Drivers:**
  - *One scheduler per job:* two schedulers for one job gave duplicate backups and a racing prune.
  - *Run where the data is:* a job that runs on the machine holding its data needs no new tailnet grant and keeps working when the other sites are down.
  - *Blast radius:* the cloud host runs many apps and Kestra holds its Docker socket. Anything that host may reach, a compromise of it may reach too.
  - *Everything as code:* jobs live in Git, not only in a tool's UI.
  - *Memory:* the cluster has no room for another orchestrator.
- **Decision:**
  1. *Cloud host jobs: Kestra.* Kestra (OSS, with its own PostgreSQL) is the only scheduler on the cloud host. Flows live in `automation/kestra/flows/` and a `SyncFlows` flow pulls them from `main` every six hours. Today these are the nightly restic backup (03:00 UTC, with database dumps and a success-only heartbeat) and the weekly Docker prune (Sunday 04:00 UTC). Tasks run in short-lived containers through the host's Docker socket. The root crontab holds no jobs: the backup cron was removed in the hardening pass and the prune cron on 18 Nov.
  2. *Cluster jobs: Kubernetes CronJobs,* in Git next to the app they serve, for example the nightly app database dump (ADR-022).
  3. *Hypervisor jobs: systemd timers,* managed by Ansible: the etcd snapshot sync, local restic, the offsite copies and ZFS metrics (ADR-018, ADR-022). Timers use `Persistent=true` so a missed run catches up after a reboot, and each job checks its own preconditions (clock, mounts, freshness) before writing anything (INC-2026-014).
  4. *n8n is for integrations, not infrastructure.* It stays for webhook-driven glue between apps. It schedules no backups, maintenance or deployments.
  5. *The cloud host gets no reach into the home lab beyond metrics.* Its tailnet grant to the cluster and hypervisor stays limited to the metrics ports (ADR-013). Home lab jobs are never triggered from Kestra, because that would need SSH or API access from the most exposed host into the home lab.
  6. *Every scheduled job reports success,* not just failure: a heartbeat to the edge Uptime Kuma on success only, so a job that stops running, or a scheduler that stops, pages by silence.
- **Alternatives Considered:**
  - *Root cron and systemd timers on the cloud host too:* rejected. Kestra gives run history, retries with limits, logs per run and flows in Git. Cron gives none of these, and two cron entries had already duplicated Kestra's work.
  - *Kestra for everything, including home lab jobs:* rejected. It needs SSH or kube API grants from the cloud host into the home lab (blast radius), and it fails while the home lab is down. The power cut of INC-2026-014 showed the value of jobs that catch up locally when their machine comes back.
  - *n8n as the scheduler:* rejected. Its workflows live in its database and UI, not in Git, and it has no run-level retry or timeout semantics for long shell jobs.
  - *Argo Workflows or a cluster-wide orchestrator:* rejected for memory (ADR-016) and because the cloud host's jobs can't run in the cluster.
- **Consequences:**
  - *Positive:* each job has one scheduler, defined in Git next to what it touches. No new tailnet grants were needed for automation. Home lab jobs survive a cloud outage and the reverse.
  - *Negative:* three scheduling mechanisms to know, each with its own logs: the Kestra UI, `kubectl get cronjobs`, `systemctl list-timers`. Kestra uses about 1.3 GB of memory on the cloud host, plus its own PostgreSQL.
  - *Risks:* Kestra mounts the Docker socket, so it has root-equivalent access to the cloud host. Its UI is reachable only on the mesh under the `oci-admin` role with basic auth. A flow without a heartbeat fails silently, which is how the prune flow's 8 Nov failure went unnoticed. Every scheduled flow now has one.
- **Security Considerations:** Kestra's credentials and the backup repository's credentials are in SOPS and rendered by Ansible. The restic flow mounts the backup configuration read-only. Flows sync from the repository over HTTPS with a token kept as a Kestra secret; the sync only reads.
- **Validation / Fitness Functions (18 Nov 2026):**
  - The root crontab on the cloud host has no jobs (`crontab -l` empty after 4.13; the Ansible task is idempotent).
  - The Kestra backup flow's heartbeat is green on the edge Uptime Kuma, and its last run saved a snapshot.
  - The cloud host's tailnet grant to the home lab lists metrics ports only, and its policy tests deny the next port up.
  - Hypervisor timers recovered on their own after the power cut, apart from the missed-snapshot gap fixed in INC-2026-014.
- **Follow-up done (18 Nov 2026):** the prune flow now pushes a success heartbeat (an edge Uptime Kuma monitor with an 8-day window) and sends a Telegram message on failure, like the backup flow.
- **Dependencies:** ADR-008 (operational toolchain), ADR-012 (cloud host monorepo), ADR-013 (tailnet segmentation), ADR-018 and ADR-022 (backup jobs), ADR-020 (edge Uptime Kuma).
- **Review Conditions:** a job needs to coordinate across sites (for example a restore drill spanning the cloud host and the cluster); Kestra's memory becomes a problem on the cloud host; or n8n starts carrying anything that must not fail silently.

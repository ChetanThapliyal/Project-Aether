#!/usr/bin/env python3
"""Builds docs/diagrams/project-aether-architecture.svg: the target architecture
of the whole project as it runs today. A chip is a label, or (label, True) for a
planned item, drawn dashed (none since 19 Nov 2026). Edit the lists below and
run:  python3 docs/diagrams/build_architecture.py
Role-level only: no IP addresses or hostnames (the repo is public)."""
from pathlib import Path

from aether_style import *   # palette, font, rect/text/chips/label/zone/actor/arrow, wrap

W, H = 1600, 1040


# ── title and legend ──────────────────────────────────────────────────────────
text(40, 46, "Project Aether", 30, TEXT, 800)
text(262, 46, "architecture", 22, "#FB923C", 700)
rect(1196, 24, 92, 30, 7, NODE, LINE); text(1242, 44, "running", 14, TEXT, 600, "middle")

# ── public internet ───────────────────────────────────────────────────────────
actor(40, 76, 150, "Visitors", "any browser")
actor(210, 76, 250, "Cloudflare", "DNS · TLS · firewall · tunnel")
actor(480, 76, 390, "GitHub", "repo · Actions CI · drift check · Renovate")
actor(890, 76, 150, "Telegram", "alerts")
actor(1060, 76, 290, "Backblaze B2", "offsite backups · locked 30 days")
actor(1370, 76, 206, "Operator", "laptop + phone, on the mesh")
arrow(190, 108, 208, 108)
arrow(480, 108, 462, 108)
arrow(335, 140, 335, 180)
text(347, 166, "outbound tunnel: the only public path", 13, DIM)

# ── DMZ and the Google Cloud control plane ────────────────────────────────────
zone(40, 196, 760, 140, DMZ, "DMZ", "Google Cloud e2-micro · least trusted · no open ports")
chips(60, 232, 790, ["cloudflared tunnel", "Glance status page", "Uptime Kuma (outside-in)", "node exporter"])
text(60, 298, "Serves the public status page, probes everything from outside,", 14, DIM)
text(60, 318, "relays signed GitHub webhooks to the cluster.", 14, DIM)

rect(820, 196, 756, 140, 14, PANEL, LINE)
text(840, 222, "Google Cloud control plane", 15, TEXT, 600)
chips(840, 236, 1566, ["GCS · Terraform state", "GCS · Kuma backups (create-only)", "Cloud KMS · second SOPS key", "Workload identity · keyless CI"])

# ── mesh ──────────────────────────────────────────────────────────────────────
rect(40, 358, 1536, 38, 10, MESH, MESH, 1.5, opacity="0.14")
text(808, 383, "PRIVATE MESH · Tailscale (WireGuard) · role tags, deny by default, policy tests on every change · no inbound TCP anywhere", 14, TEXT, 600, "middle")
for x, y1, y2 in ((420, 336, 358), (470, 396, 430), (1252, 396, 430)):
    out.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{MESH}" stroke-width="3"/>')

# ── on-prem ───────────────────────────────────────────────────────────────────
zone(40, 430, 870, 470, HOME, "ON-PREM", "home lab · Proxmox VE on one 2015 laptop (12 GB) · behind CGNAT")
rect(60, 468, 600, 416, 10, "none", HOME, 1.5, opacity=None)
text(76, 494, "K3s v1.36 · 1 control plane + 2 workers · embedded etcd", 15, TEXT, 600)
y = 520
label(76, y, "PLATFORM · RECONCILED BY ARGOCD FROM GIT")
y = chips(76, y + 10, 650, ["ArgoCD + KSOPS", "MetalLB", "Envoy Gateway", "cert-manager PKI", "Tailscale operator", "NetworkPolicies"]) + 26
label(76, y, "OBSERVABILITY")
y = chips(76, y + 10, 650, ["Alloy (logs out)", "node exporter", "kube-state-metrics"]) + 26
label(76, y, "APPS · PHASE 04, MOVED FROM ORACLE CLOUD OR NEW")
y = chips(76, y + 10, 650, ["IT-Tools", "Blinko", "AFFiNE", "CouchDB", "Paperless", "Linkwarden"]) + 26
label(76, y, "DATA AND STORAGE")
chips(76, y + 10, 650, ["PostgreSQL + Redis", "local-path · databases", "nfs-zfs · files"])

rect(680, 468, 212, 300, 10, "none", HOME, 1.5)
text(696, 494, "ZFS pool · second disk", 15, TEXT, 600)
yy = 508
for it in ("etcd snapshots", "restic repository", "nightly to B2", "app-data backups", "NFS · app files"):
    yy = chips(696, yy, 890, [it]) + 10
text(696, 800, "VMs built by Terraform", 14, DIM)
text(696, 820, "and cloud-init;", 14, DIM)
text(696, 840, "hosts by Ansible.", 14, DIM)

# ── Oracle Cloud ──────────────────────────────────────────────────────────────
zone(930, 430, 646, 470, OCI, "OCI", "Oracle Cloud core · ARM VM (12 GB) · Docker · no open ports")
y = 482
label(950, y, "MONITORING")
y = chips(950, y + 10, 1566, ["Prometheus", "Loki", "Alertmanager to Telegram", "Grafana"]) + 26
label(950, y, "AUTOMATION")
y = chips(950, y + 10, 1566, ["Kestra", "n8n", "backup + prune flows"]) + 26
label(950, y, "APPS · STAYING ON THE CLOUD HOST")
y = chips(950, y + 10, 1566, ["BookOrbit", "Navidrome", "NextExplorer", "Anytype sync", "openGym", "CouchDB (until decided)"]) + 26
label(950, y, "EDGE OF THE HOST")
y = chips(950, y + 10, 1566, ["tsdproxy · a mesh node per service", "public-feed", "Dockhand"]) + 26
label(950, y, "STORAGE")
chips(950, y + 10, 1566, ["OCI Object Storage · restic nightly, restore-drilled"])

# ── everything as code ────────────────────────────────────────────────────────
rect(40, 920, 1536, 100, 14, PANEL, LINE)
label(60, 946, "ONE REPOSITORY, EVERYTHING AS CODE")
chips(60, 958, 1566, ["Terraform · machines", "Ansible · hosts", "ArgoCD · cluster", "SOPS (age + KMS) · secrets", "GitHub Actions · validate + drift",
                      "Renovate + Dependabot · updates", "branch protection"])

ARIA = ("Architecture of Project Aether: a public internet row, a Google Cloud DMZ, a private Tailscale mesh, the on-prem K3s home lab, "
        "the Oracle Cloud monitoring core, and the tools that manage it all as code.")
svg = wrap(W, H, ARIA)
Path(__file__).with_name("project-aether-architecture.svg").write_text(svg)
print("wrote project-aether-architecture.svg", len(svg), "bytes")

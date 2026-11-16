#!/usr/bin/env python3
"""Builds docs/diagrams/project-aether-architecture.svg: the target architecture
of the whole project. Solid boxes run today; dashed boxes are planned (Phase 04
moves the apps onto the cluster, Phase 05 finishes CI). Edit the lists below and
run:  python3 docs/diagrams/build_architecture.py
Role-level only: no IP addresses or hostnames (the repo is public)."""
from html import escape
from pathlib import Path

W, H = 1600, 1040
BG, PANEL, NODE, LINE, TEXT, DIM = "#1C1917", "#231F1D", "#292524", "#57534E", "#F5F5F4", "#A8A29E"
HOME, OCI, DMZ, MESH, PLAN = "#EA580C", "#D97706", "#E11D48", "#78716C", "#A8A29E"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Helvetica, Arial, sans-serif"
out = []


def rect(x, y, w, h, r=8, fill="none", stroke=LINE, sw=1.5, dash=None, opacity=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' fill-opacity="{opacity}"' if opacity else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{o} stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=15, fill=TEXT, weight=400, anchor="start", spacing=None):
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{sp}>{escape(s)}</text>')


def chip_w(label):
    return round(len(label) * 8.0 + 22)


def chips(x, y, max_x, items, gap=10, h=34):
    """Lays chips out left to right, wrapping at max_x. An item is a label or (label, True) for planned."""
    cx = x
    for it in items:
        label, planned = (it, False) if isinstance(it, str) else it
        w = chip_w(label)
        if cx + w > max_x and cx > x:
            cx, y = x, y + h + gap
        rect(cx, y, w, h, 7, "none" if planned else NODE, PLAN if planned else LINE, 1.5, "6 5" if planned else None)
        text(cx + w / 2, y + 22, label, 15, DIM if planned else TEXT, 400 if planned else 600, "middle")
        cx += w + gap
    return y + h


def label(x, y, s):
    text(x, y, s, 12.5, DIM, 700, spacing="0.08em")


def zone(x, y, w, h, color, tag, sub):
    rect(x, y, w, h, 14, color, color, 3, opacity="0.08")
    tw = round(len(tag) * 11.5 + 26)
    out.append(f'<rect x="{x + 16}" y="{y - 15}" width="{tw}" height="30" rx="8" fill="{color}"/>')
    text(x + 16 + tw / 2, y + 6, tag, 17, BG, 800, "middle")
    sw = round(len(sub) * 7.6 + 20)   # a strip of background so the border doesn't run through the text
    out.append(f'<rect x="{x + 16 + tw + 4}" y="{y - 12}" width="{sw}" height="24" fill="{BG}"/>')
    text(x + 16 + tw + 14, y + 6, sub, 15, TEXT, 600)


def actor(x, y, w, name, sub):
    rect(x, y, w, 64, 9, NODE, LINE)
    text(x + w / 2, y + 27, name, 16, TEXT, 700, "middle")
    text(x + w / 2, y + 48, sub, 13, DIM, 400, "middle")


def arrow(x1, y1, x2, y2, color=DIM, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2"{d} marker-end="url(#arr)"/>')


# ── title and legend ──────────────────────────────────────────────────────────
text(40, 46, "Project Aether", 30, TEXT, 800)
text(262, 46, "architecture", 22, "#FB923C", 700)
rect(1196, 24, 92, 30, 7, NODE, LINE); text(1242, 44, "running", 14, TEXT, 600, "middle")
rect(1300, 24, 276, 30, 7, "none", PLAN, 1.5, "6 5"); text(1438, 44, "planned (Phases 04 and 05)", 14, DIM, 400, "middle")

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
label(76, y, "APPS · PHASE 04, MOVING FROM ORACLE CLOUD")
y = chips(76, y + 10, 650, [(a, True) for a in ("AFFiNE", "Blinko", "BookOrbit", "CouchDB", "Navidrome", "IT-Tools", "NextExplorer")]) + 26
label(76, y, "STORAGE")
chips(76, y + 10, 650, ["local-path volumes", ("NFS media from ZFS", True)])

rect(680, 468, 212, 300, 10, "none", HOME, 1.5)
text(696, 494, "ZFS pool · second disk", 15, TEXT, 600)
yy = 508
for it in ("etcd snapshots", "restic repository", "nightly to B2", ("app-data backups", True), ("NFS export", True)):
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
y = chips(950, y + 10, 1566, ["Kestra", "n8n", ("alert + incident flows", True)]) + 26
label(950, y, "APPS TODAY · 7 MOVE TO THE CLUSTER IN PHASE 04")
y = chips(950, y + 10, 1566, ["AFFiNE", "Blinko", "BookOrbit", "CouchDB", "Navidrome", "IT-Tools", "NextExplorer", "Anytype sync"]) + 26
label(950, y, "EDGE OF THE HOST")
y = chips(950, y + 10, 1566, ["tsdproxy · a mesh node per service", "public-feed", "Dockhand"]) + 26
label(950, y, "STORAGE")
chips(950, y + 10, 1566, ["OCI Object Storage · restic nightly, restore-drilled"])

# ── everything as code ────────────────────────────────────────────────────────
rect(40, 920, 1536, 100, 14, PANEL, LINE)
label(60, 946, "ONE REPOSITORY, EVERYTHING AS CODE")
chips(60, 958, 1566, ["Terraform · machines", "Ansible · hosts", "ArgoCD · cluster", "SOPS (age + KMS) · secrets", "GitHub Actions · validate + drift",
                      "Renovate + Dependabot · updates", ("branch protection", True)])

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}" role="img" '
       f'aria-label="Architecture of Project Aether: a public internet row, a Google Cloud DMZ, a private Tailscale mesh, the on-prem K3s home lab, the Oracle Cloud monitoring core, and the tools that manage it all as code. Dashed boxes are planned.">'
       f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{DIM}"/></marker></defs>'
       f'<rect width="{W}" height="{H}" fill="{BG}"/>' + "".join(out) + "</svg>\n")
Path(__file__).with_name("project-aether-architecture.svg").write_text(svg)
print("wrote project-aether-architecture.svg", len(svg), "bytes")

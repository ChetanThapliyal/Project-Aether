#!/usr/bin/env python3
"""Builds docs/diagrams/flow-monitoring.svg: monitoring and alerting.
Sources: ADR-019, ADR-020, legacy-docker/oci-services/prometheus.yml and alert-rules.yml,
infrastructure/ansible/templates/alertmanager.yml.j2, playbooks/deploy-dmz.yml (push monitors),
docs/incidents/INC-2026-014. Run:  python3 docs/diagrams/build_flow_monitoring.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *

W, H = 1600, 890
METRICS, LOGS, ALERTS, BEAT, CHECKS = SKY, VIOLET, SNOW, LIME, TEAL


def tint(c):
    return blend(c, BG, 0.4)


title_row("monitoring and alerting", "Monitoring runs on the cloud host, off the cluster, so it still works when the home lab doesn't.")
leg = legend([("metrics", METRICS), ("logs", LOGS), ("alerts", ALERTS), ("heartbeats", BEAT), ("outside checks", CHECKS)], 1576, 72)

for x, w, s in ((40, 520, "WATCHED · home lab and edge VM"), (700, 540, "WATCHING · the cloud host, off the cluster"), (1290, 286, "PEOPLE")):
    rect(x, 96, w, 34, 9, PANEL, LINE)
    text(x + 16, 118, s, 14, TEXT, 600)

# ── zones and the mesh ────────────────────────────────────────────────────────
zone(40, 160, 520, 462, HOME, "ON-PREM", "home lab")
zone(40, 668, 520, 170, DMZ, "EDGE VM", "Google Cloud")
zone(700, 160, 540, 530, OCI, "OCI", "cloud host · Oracle Cloud · Docker")
BX, BW = 590, 56   # the mesh, as a vertical band every scrape and push crosses
rect(BX, 160, BW, 678, 10, MESH, MESH, 1.5, opacity="0.14")
band = (BX, 160, BW, 678)
out.append(f'<text transform="translate({BX + BW / 2 + 5} 499) rotate(-90)" font-size="14" font-weight="600" fill="{TEXT}" text-anchor="middle">PRIVATE MESH · scrapes and pushes only, nothing inbound</text>')

# ── sources on the home lab ───────────────────────────────────────────────────
SX, SW, SH = 60, 440, 74
s1 = node(SX, 198, SW, SH, "Alloy on every cluster node", ["reads the pod logs", "ships them to Loki"])
s2 = node(SX, 280, SW, SH, "Cluster nodes", ["node exporter on the control VM", "and on both workers"])
s3 = node(SX, 362, SW, SH, "Cluster services", ["kube-state-metrics · ArgoCD", "PostgreSQL and Redis exporters"])
s4 = node(SX, 444, SW, SH, "Hypervisor", ["node exporter", "plus ZFS pool and dataset metrics"])
s5 = node(SX, 526, SW, SH, "Apps", ["served through the app gateway", "checked from outside by Uptime Kuma"])

# ── the edge VM ───────────────────────────────────────────────────────────────
bj = node(60, 700, 170, 64, "Backup jobs", ["hypervisor, cloud host"])
kuma = node(280, 696, 260, 96, "Uptime Kuma", ["checks the apps over HTTPS", "waits for heartbeats and Watchdog", "silence means an alert"])
ne = node(60, 792, 170, 36, "node exporter")

# ── the cloud host ────────────────────────────────────────────────────────────
loki = node(720, 200, 220, 90, "Loki", ["logs · 14 days", "searched from Grafana"])
graf = node(990, 200, 220, 170, "Grafana", ["dashboards", "metrics and log search", "reads Prometheus and Loki"])
prom = node(720, 310, 220, 100, "Prometheus", ["scrapes every 15 s", "rules include Watchdog,", "a rule that always fires"])
am = node(720, 450, 220, 96, "Alertmanager", ["groups and routes", "Watchdog goes to Kuma,", "never to Telegram"])
rect(990, 540, 220, 130, 9, "none", LINE, 1.5, dash="6 5")
label(1006, 564, "WHY IT SITS HERE")
for i, s in enumerate(["Not on the cluster: a power", "cut at home stopped the", "cluster but not monitoring,", "which paged within a minute."]):
    text(1006, 588 + i * 19, s, 13, DIM)

actor(1290, 236, 286, "Operator", "laptop and phone, on the mesh")
tg = node(1290, 468, 286, 64, "Telegram", ["alerts on my phone"])

# ── routes ────────────────────────────────────────────────────────────────────
mid = lambda b: (b[0] + b[2] / 2, b[1] + b[3] / 2)
r_logs_in = route([(SX + SW, 235), (BX, 235)], tint(LOGS))
r_logs_out = route([(BX + BW, 245), (720, 245)], tint(LOGS))
r_logs_graf = route([(940, 245), (990, 245)], tint(LOGS))
srcs = []
for b in (s2, s3, s4):
    y = b[1] + SH / 2
    srcs.append(route([(SX + SW, y), (BX, y)], tint(METRICS)))
r_ne = route([(230, 810), (BX, 810)], tint(METRICS))
r_m_out = route([(BX + BW, 345), (720, 345)], tint(METRICS))
r_m_graf = route([(940, 345), (990, 345)], tint(METRICS))
r_alert = route([(830, 410), (830, 450)], tint(ALERTS))
r_tg = route([(940, 500), (1290, 500)], tint(ALERTS))
r_wd = route([(830, 546), (830, 722), (540, 722)], tint(BEAT))
r_bj = route([(230, 732), (280, 732)], tint(BEAT))
r_chk = route([(410, 696), (410, 600)], tint(CHECKS))
r_page = route([(540, 764), (1433, 764), (1433, 532)], tint(ALERTS), dash="6 5")
route([(1290, 268), (1210, 268)], DIM)

# labels
for x, y, s in ((SX + SW + 42, 224, "logs"), (SX + SW + 42, 306, "metrics"), (SX + SW + 42, 388, "metrics"), (SX + SW + 42, 470, "metrics"), (SX + SW + 20, 799, "metrics")):
    text(x, y, s, 13, DIM, 400, "middle")
text(683, 234, "logs", 13, DIM, 400, "middle")
text(683, 334, "scrape", 13, DIM, 400, "middle")
text(965, 234, "query", 13, DIM, 400, "middle")
text(965, 334, "query", 13, DIM, 400, "middle")
text(842, 436, "firing alerts", 13, DIM)
text(1115, 492, "alerts", 13, DIM, 400, "middle")
text(1265, 261, "view", 13, DIM, 400, "middle")
text(660, 714, "Watchdog, every minute", 13, DIM)
text(255, 724, "beat", 13, DIM, 400, "middle")
text(420, 654, "HTTPS from outside", 13, DIM)
text(900, 756, "silence pages: a missing heartbeat becomes an alert", 13, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
ne_box = (60, 792, 170, 36)
a = Anim()
a.story(METRICS, [s2, s3, s4, ne_box], [list(zip(srcs, [band] * 3)) + [(r_ne, band)], (r_m_out, prom), (r_m_graf, graf)], leg[0])
a.story(LOGS, s1, [(r_logs_in, band), (r_logs_out, loki), (r_logs_graf, graf)], leg[1])
a.story(ALERTS, prom, [(r_alert, am), (r_tg, tg)], leg[2])
a.story(BEAT, [prom, bj], [[(r_alert, am), (r_bj, kuma)], (r_wd, kuma)], leg[3])
a.story(CHECKS, kuma, [(r_chk, s5)], leg[4])
layer, style = a.render()

ARIA = ("Monitoring and alerting in Project Aether. Prometheus, Loki, Alertmanager and Grafana run on the cloud host, off the cluster. "
        "Prometheus scrapes node exporters on the cluster nodes, the hypervisor (with ZFS metrics) and the edge VM, plus kube-state-metrics, ArgoCD and the "
        "PostgreSQL and Redis exporters, all over the private mesh. Grafana Alloy on every cluster node ships logs to Loki. Alertmanager sends alerts to Telegram. "
        "A Watchdog alert that always fires goes to Uptime Kuma on the edge VM, which also receives backup heartbeats and checks the apps over HTTPS from outside; "
        "if a heartbeat stops, Uptime Kuma alerts Telegram.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-monitoring.svg").write_text(svg)
print("wrote flow-monitoring.svg", len(svg), "bytes")

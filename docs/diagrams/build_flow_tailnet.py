#!/usr/bin/env python3
"""Builds docs/diagrams/flow-tailnet.svg: mesh segmentation, role tags and the flows they allow.
Sources: ADR-013 and its addenda; the live policy (infrastructure/secrets/tailscale-policy.sops.yaml) was
read in memory for tag names and grants. Only tag roles and port roles appear here, never the policy text.
Run:  python3 docs/diagrams/build_flow_tailnet.py
Role-level only: no IP addresses, hostnames, port numbers or tailnet names (the repo is public)."""
from pathlib import Path

from aether_style import *

W, H = 1600, 920
METRICS, LOGS, CHECKS, BEAT = SKY, VIOLET, TEAL, LIME


def tint(c):
    return blend(c, BG, 0.4)


title_row("mesh segmentation", "Every tag is a role. An arrow points from the side that may open the connection, and anything without an arrow is denied.")
leg = legend([("metrics", METRICS), ("logs", LOGS), ("health checks", CHECKS), ("heartbeats", BEAT)], 1576, 72, head="ALLOWED FLOWS")

# ── people ────────────────────────────────────────────────────────────────────
for x, w, t, ls in ((40, 500, "tag:operator", ["my laptop and phone:", "every tag, every port."]),
                    (560, 520, "Signed-in devices (autogroup:member)", ["HTTPS to the apps and admin tools;", "SSH and monitoring on the edge VM."]),
                    (1100, 460, "Everything else is denied", ["The policy file carries tests. The admin console", "runs them on every save and rejects a failing policy."])):
    rect(x, 100, w, 84, 9, PANEL, MESH, 2)
    text(x + 16, 128, t, 16, TEXT, 700)
    for i, s in enumerate(ls):
        text(x + 16, 150 + i * 18, s, 13, DIM)

# ── Oracle (top) ──────────────────────────────────────────────────────────────
zone(60, 250, 1090, 242, OCI, "OCI", "cloud host · Oracle Cloud")
adm = node(80, 292, 240, 82, "tag:oci-admin", ["Docker UI, log viewer, Grafana,", "Prometheus, Loki, Alertmanager"])
app = node(340, 292, 240, 82, "tag:oci-app", ["user-facing apps", "operator and members only"])
prb = node(930, 292, 200, 82, "tag:oci-probe", ["what the edge VM checks,", "and the public feed"])
oci = node(80, 402, 1050, 64, "tag:oci", ["the cloud host's own node: scrapes, alerts and heartbeats leave from here"])

# ── Home (bottom left) ────────────────────────────────────────────────────────
zone(40, 580, 550, 320, HOME, "ON-PREM", "home lab")
hyp = node(340, 620, 230, 70, "tag:homelab-dc", ["the hypervisor"])
k3s = node(340, 710, 230, 70, "tag:k3s", ["the K3s nodes"])
k8s = node(340, 800, 230, 70, "tag:k8s", ["app gateway and ingress proxies"])
node(60, 800, 240, 70, "tag:k8s-operator", ["creates the tag:k8s proxies"])

# ── Google Cloud (bottom right) ───────────────────────────────────────────────
zone(670, 580, 910, 320, DMZ, "GOOGLE CLOUD", "edge VM")
dmz = node(740, 620, 400, 250, "tag:gcp-dmz", ["the edge VM", "public status page, outside checks,", "receives the heartbeats"])
rect(1200, 620, 350, 250, 9, "none", LINE, 1.5, dash="6 5")
label(1216, 646, "THE EDGE VM CAN'T REACH")
for i, s in enumerate(["the admin tools", "the apps", "the cluster API", "the hypervisor console", "SSH on any other host", "", "Policy tests check each of these."]):
    text(1216, 674 + i * 24, s, 14, DIM if i < 5 else TEXT, 400 if i < 5 else 600)

# ── how to read ───────────────────────────────────────────────────────────────
rect(1190, 250, 370, 242, 9, "none", LINE, 1.5, dash="6 5")
label(1206, 276, "HOW TO READ IT")
for i, s in enumerate(["Boxes are role tags. Each tag has one", "meaning, and location never grants access.", "", "Labels name the port role: metrics, logs,", "web, monitoring. No port numbers here.", "", "Arrows cross the mesh. Nothing else does."]):
    text(1206, 304 + i * 22, s, 13.5, DIM)

# ── flows ─────────────────────────────────────────────────────────────────────
r_oh = route([(455, 466), (455, 620)], tint(METRICS))
r_ok = route([(310, 466), (310, 722), (340, 722)], tint(METRICS))
r_ko = route([(340, 748), (270, 748), (270, 466)], tint(LOGS))
r_ho = route([(540, 620), (540, 466)], tint(LOGS))   # the hypervisor's journal (INC-2026-014)
r_od_m = route([(1060, 466), (1060, 620)], tint(METRICS))
r_od_c = route([(1100, 466), (1100, 620)], tint(CHECKS))
r_dp = route([(1140, 650), (1178, 650), (1178, 333), (1130, 333)], tint(CHECKS))
r_dk = route([(740, 745), (570, 745)], tint(CHECKS))
r_d8 = route([(740, 835), (570, 835)], tint(CHECKS))
r_hd = route([(570, 655), (740, 655)], tint(BEAT))
for x, y, s, a in ((467, 540, "metrics", "start"), (318, 540, "metrics", "start"), (262, 540, "logs", "end"), (548, 510, "logs", "start"), (1052, 540, "metrics", "end"), (1107, 560, "monitoring", "start"),
                   (1170, 515, "web", "end"), (630, 736, "web", "middle"), (630, 826, "web", "middle"), (630, 646, "heartbeat", "middle")):
    text(x, y, s, 13, DIM, 400, a)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(METRICS, oci, [[(r_oh, hyp), (r_ok, k3s), (r_od_m, dmz)]], leg[0])
a.story(LOGS, [k3s, hyp], [[(r_ko, oci), (r_ho, oci)]], leg[1])
a.story(CHECKS, dmz, [[(r_dp, prb), (r_dk, k3s), (r_d8, k8s), (r_od_c, oci)]], leg[2])
a.story(BEAT, hyp, [(r_hd, dmz)], leg[3])
layer, style = a.render()

ARIA = ("Mesh segmentation in Project Aether. Role tags are boxes, grouped by site: home lab, Oracle Cloud and Google Cloud, plus the operator and signed-in devices. "
        "The operator reaches every tag. Signed-in devices reach the apps and admin tools over HTTPS and the edge VM over SSH and monitoring. "
        "The cloud host scrapes metrics from the K3s nodes, the hypervisor and the edge VM and runs monitoring checks on the edge VM. The K3s nodes and the hypervisor send logs to the cloud host. "
        "The edge VM may check the monitored services and the public feed on the cloud host and the web ports of the cluster. The hypervisor sends heartbeats to the edge VM. "
        "Everything else is denied, and policy tests run on every save.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-tailnet.svg").write_text(svg)
print("wrote flow-tailnet.svg", len(svg), "bytes")

#!/usr/bin/env python3
"""Builds docs/diagrams/flow-app-request.svg: how a request reaches an app.
Sources: ADR-021 and its 4.16 addendum, ADR-022, kubernetes/platform/gateway/, kubernetes/platform/network-policies/.
Run:  python3 docs/diagrams/build_flow_app_request.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *

W, H = 1600, 810
LOOKUP, CONNECT, DATA, CERT = SKY, TEAL, VIOLET, LIME


def tint(c):
    return blend(c, BG, 0.4)


def ns(x, y, w, h, name):
    rect(x, y, w, h, 12, "none", HOME, 1.5)
    text(x + 16, y + 26, name, 15, TEXT, 600)
    text(x + 16 + round(len(name) * 8.4) + 8, y + 26, "namespace", 13, DIM)


title_row("how a request reaches an app", "The name resolves publicly but only works on the mesh. Every hop inside the cluster is denied by default.")
leg = legend([("name lookup", LOOKUP), ("connection", CONNECT), ("app and data", DATA), ("certificate", CERT)], 1576, 72)

# ── left: the lookup, the phone, public DNS ───────────────────────────────────
rect(40, 110, 330, 122, 10, "none", LINE, 1.5, dash="6 5")
label(56, 134, "WHAT THE LOOKUP RETURNS")
for i, s in enumerate(["<app>.lab.<domain> is a wildcard record.", "It answers with the gateway's mesh address.", "Anyone can look it up; only mesh members", "can connect to it."]):
    text(56, 158 + i * 20, s, 13, DIM)
phone = (40, 262, 230, 76); actor(*phone[:3], "Phone on the mesh", "or any signed-in device")
dns = (40, 520, 330, 70); actor(*dns[:3], "Cloudflare DNS", "public records, one wildcard")

# ── the mesh ──────────────────────────────────────────────────────────────────
BX = 410
rect(BX, 120, 56, 380, 10, MESH, MESH, 1.5, opacity="0.14")
mesh = (BX, 120, 56, 380)
# Split around the step-3 arrow (y=295) so the arrow never crosses the words.
out.append(f'<text transform="translate({BX + 33} 208) rotate(-90)" font-size="14" font-weight="600" fill="{TEXT}" text-anchor="middle">PRIVATE MESH</text>')
out.append(f'<text transform="translate({BX + 33} 400) rotate(-90)" font-size="14" font-weight="600" fill="{TEXT}" text-anchor="middle">only members get in</text>')

# ── the cluster ───────────────────────────────────────────────────────────────
zone(500, 120, 1060, 640, HOME, "ON-PREM", "home lab · K3s cluster")
ns(520, 170, 520, 210, "gateway-system")
proxy = node(540, 250, 200, 90, "Tailscale proxy", ["a mesh node, tag:k8s", "forwards TCP only"])
envoy = node(800, 250, 220, 90, "Envoy Gateway", ["terminates HTTPS with the", "wildcard Let's Encrypt cert"])
ns(1080, 170, 220, 210, "apps")
pod = node(1096, 250, 188, 90, "App pod", ["picked by the HTTPRoute", "for the app's name"])
ns(1340, 170, 200, 210, "databases")
pg = node(1356, 204, 168, 76, "PostgreSQL", ["one database per app"])
rd = node(1356, 292, 168, 76, "Redis", ["queues and caches"])

# ── certificate lane ──────────────────────────────────────────────────────────
cm = node(540, 480, 220, 90, "cert-manager", ["asks for the wildcard", "certificate and renews it"])
le = (820, 480, 240, 90)
rect(*le[:2], le[2], le[3], 9, NODE, LINE)
text(940, 508, "Let's Encrypt", 16, TEXT, 700, "middle"); text(940, 530, "reads the TXT record in public DNS,", 13, DIM, 400, "middle"); text(940, 548, "then issues. No inbound access.", 13, DIM, 400, "middle")

# ── network policies panel ────────────────────────────────────────────────────
rect(1100, 480, 440, 250, 12, PANEL, LINE)
label(1116, 506, "NETWORK POLICIES · DEFAULT DENY, THEN OPT IN")
rows = [("Into apps", "only Envoy's proxy pods."), ("Out of an app", "only what its pod labels ask for:"), ("", "PostgreSQL, Redis, or the internet"), ("", "on web ports, never the LAN or mesh."), ("Into databases", "only the apps namespace.")]
for i, (b, s) in enumerate(rows):
    if b:
        text(1116, 538 + i * 26, b, 13, TEXT, 700)
    text(1226, 538 + i * 26, s, 13, DIM)

# ── routes ────────────────────────────────────────────────────────────────────
r_q = route([(130, 338), (130, 520)], tint(LOOKUP)); text(122, 420, "1", 14, TEXT, 700, "end")
r_a = route([(210, 520), (210, 338)], tint(LOOKUP)); text(220, 420, "2", 14, TEXT, 700)
r_c1 = route([(270, 295), (540, 295)], tint(CONNECT)); text(300, 285, "3 · HTTPS", 13, DIM)
r_c2 = route([(740, 295), (800, 295)], tint(CONNECT)); text(770, 282, "4", 14, TEXT, 700, "middle")
r_c3 = route([(1020, 295), (1096, 295)], tint(DATA)); text(1058, 282, "5", 14, TEXT, 700, "middle")
r_d1 = route([(1284, 278), (1356, 244)], tint(DATA)); r_d2 = route([(1284, 312), (1356, 330)], tint(DATA)); text(1320, 262, "6", 14, TEXT, 700, "middle")
r_dns = route([(540, 540), (370, 540)], tint(CERT)); text(378, 530, "adds a TXT record", 13, DIM)
# The token note sits under the DNS box: on the arrow it crossed the on-prem border.
text(44, 604, "cert-manager's Cloudflare token: DNS edit on one zone only", 12.5, DIM)
r_cm = route([(760, 525), (820, 525)], tint(CERT)); text(790, 513, "orders", 13, DIM, 400, "middle")
r_ce = route([(650, 480), (650, 440), (910, 440), (910, 340)], tint(CERT)); text(670, 432, "wildcard certificate, kept as a Secret", 13, DIM)

# ── the steps, in words ───────────────────────────────────────────────────────
rect(40, 620, 430, 140, 12, PANEL, LINE)
label(56, 646, "STEP BY STEP")
for i, s in enumerate(["1 · The phone asks public DNS for the app's name.", "2 · A wildcard record answers with the gateway's mesh address.", "3 · The phone opens HTTPS to it, over the mesh.", "4 · The proxy hands the connection to Envoy.", "5 · Envoy matches the HTTPRoute and calls the app pod.", "6 · The pod reaches a database only if its labels opt in."]):
    text(56, 670 + i * 15.5, s, 12.5, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(LOOKUP, phone, [(r_q, dns), (r_a, phone)], leg[0])
a.story(CONNECT, phone, [(r_c1, proxy), (r_c2, envoy)], leg[1])
a.story(DATA, envoy, [(r_c3, pod), [(r_d1, pg), (r_d2, rd)]], leg[2])
a.story(CERT, cm, [[(r_dns, dns), (r_cm, le)], (r_ce, envoy)], leg[3])
layer, style = a.render()

ARIA = ("How a request reaches an app in Project Aether. A phone on the mesh asks public DNS for the app's name; a wildcard record answers with the gateway's mesh address, "
        "which is unusable off the mesh. The phone connects over the mesh to a Tailscale proxy, which hands the connection to Envoy Gateway. Envoy terminates HTTPS with a wildcard Let's Encrypt "
        "certificate that cert-manager obtains through DNS-01 using a token scoped to one DNS zone. An HTTPRoute sends the request to the app pod, which reaches the shared PostgreSQL and Redis in their own namespace. "
        "Default-deny network policies apply everywhere, only Envoy may reach the apps, and each app opts in to the outbound access it needs.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-app-request.svg").write_text(svg)
print("wrote flow-app-request.svg", len(svg), "bytes")

#!/usr/bin/env python3
"""Builds docs/diagrams/flow-status-page.svg: the public status page's one-way data path.
Sources: ADR-020 and its "Feed as Built" addendum (FND-20) and FND-22 addendum,
legacy-docker/oci-services/public-feed/, infrastructure/docker/gcp-dmz/ (glance.yml, docker-compose.yml),
infrastructure/ansible/playbooks/deploy-dmz.yml (freshness monitor, public status page).
Run:  python3 docs/diagrams/build_flow_status_page.py
Role-level only: no IP addresses, hostnames, tailnet names or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *

W, H = 1600, 830
FEED, PULL, PAGE, CHECK = SKY, TEAL, VIOLET, LIME


def tint(c):
    return blend(c, BG, 0.4)


title_row("the public status page", "One sanitised file leaves the cloud host. The edge pulls it, draws the page, and nothing flows back.")
leg = legend([("sanitised feed", FEED), ("pulled by the edge", PULL), ("public page", PAGE), ("freshness check", CHECK)], 1576, 72)

# ── zones and the mesh ────────────────────────────────────────────────────────
zone(40, 160, 520, 440, OCI, "OCI", "cloud host · Oracle Cloud")
zone(680, 160, 500, 440, DMZ, "EDGE VM", "Google Cloud · the public side")
BX, BW = 590, 56
rect(BX, 160, BW, 440, 10, MESH, MESH, 1.5, opacity="0.14")
out.append(f'<text transform="translate({BX + BW / 2 + 5} 300) rotate(-90)" font-size="14" font-weight="600" fill="{TEXT}" text-anchor="middle">PRIVATE MESH · one grant</text>')

# ── the cloud host ────────────────────────────────────────────────────────────
prom = node(60, 200, 200, 84, "Prometheus", ["metrics from every site"])
feed = node(300, 200, 240, 84, "public-feed", ["builds summary.json", "every 5 minutes"])
chk = node(300, 318, 240, 100, "Deny-pattern check", ["names or addresses found?", "then it is never served;", "the last good copy goes stale"])
tsd = node(300, 450, 240, 96, "tsdproxy", ["serves the file on the mesh", "to the probe role only"])
rect(60, 318, 210, 228, 10, "none", LINE, 1.5, dash="6 5")
label(76, 342, "WHAT THE FEED HOLDS")
for i, s in enumerate(["Counts: nodes, apps,", "pods, targets, alerts", "Six capacity gauges", "Four 6-hour charts", "Image names and tags"]):
    text(76, 368 + i * 20, s, 13, DIM)
text(76, 482, "Never: host names,", 13, TEXT, 600)
text(76, 502, "addresses or ports.", 13, TEXT, 600)
text(76, 522, "Charts are numbers only.", 13, DIM)

# ── the edge VM ───────────────────────────────────────────────────────────────
kuma = node(720, 280, 260, 96, "Uptime Kuma", ["checks the feed is under 15 min old", "public status page: backup", "and alerting heartbeats"])
glance = node(720, 450, 260, 96, "Glance", ["fetches the feed server-side", "draws every chart itself", "and escapes every value"])
cfd = node(1010, 450, 150, 96, "cloudflared", ["tunnel opened", "from inside,", "no open ports"])

rect(720, 196, 440, 58, 10, "none", LINE, 1.5, dash="6 5")
text(736, 220, "Runs only the public-facing containers, managed by", 13, DIM)
text(736, 240, "Ansible alone. No Docker agent on the host.", 13, DIM)

# ── outside ───────────────────────────────────────────────────────────────────
phone = (1240, 296, 320, 64); actor(*phone[:3], "Owner's phone", "Telegram alert")
cf = node(1240, 450, 320, 96, "Cloudflare", ["the only public entry", "holds the tunnel's other end"])
vis = (1240, 600, 320, 64); actor(*vis[:3], "Visitor", "any browser, read-only")

# ── routes ────────────────────────────────────────────────────────────────────
r_f1 = route([(260, 242), (300, 242)], tint(FEED))
r_f2 = route([(420, 284), (420, 318)], tint(FEED))
r_f3 = route([(420, 418), (420, 450)], tint(FEED))
r_g = route([(540, 504), (720, 504)], tint(PULL))
r_k = route([(540, 472), (700, 472), (700, 328), (720, 328)], tint(CHECK))
r_kg = route([(850, 376), (850, 450)], tint(PULL)); text(862, 418, "status list", 13, DIM)
r_t = route([(980, 328), (1240, 328)], tint(CHECK)); text(1000, 318, "alerts if the feed goes stale", 13, DIM)
r_p1 = route([(980, 498), (1010, 498)], tint(PAGE))
r_p2 = route([(1160, 498), (1240, 498)], tint(PAGE))
r_p3 = route([(1400, 546), (1400, 600)], tint(PAGE))

# ── what the design rules out, and what happens when it breaks ────────────────
rect(40, 640, 700, 150, 12, PANEL, LINE)
label(56, 666, "NOTHING FLOWS BACK")
for i, s in enumerate(["The edge has one grant into the cloud host: the probe role, over HTTPS.",
                       "Grafana, Prometheus and the admin tools don't even resolve from it.",
                       "No path from the edge, or from a visitor, to the cluster or the hypervisor.",
                       "Taking over the edge VM yields the same summary the page already shows."]):
    text(56, 694 + i * 24, s, 13.5, DIM)
rect(780, 640, 420, 150, 12, PANEL, LINE)
label(796, 666, "IF THE FEED BREAKS")
for i, s in enumerate(["A summary that fails the check is never served.",
                       "Older than 15 minutes, the page says \"Data delayed\"",
                       "and Uptime Kuma alerts the owner on Telegram.",
                       "The page never shows numbers it can't vouch for."]):
    text(796, 694 + i * 24, s, 13.5, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(FEED, prom, [(r_f1, feed), (r_f2, chk), (r_f3, tsd)], leg[0])
a.story(PULL, tsd, [(r_g, glance), (r_kg, glance)], leg[1])
a.story(PAGE, glance, [(r_p1, cfd), (r_p2, cf), (r_p3, vis)], leg[2])
a.story(CHECK, tsd, [(r_k, kuma), (r_t, phone)], leg[3])
layer, style = a.render()

ARIA = ("The public status page of Project Aether and its one-way data path. On the cloud host, a public-feed container queries Prometheus every five minutes and builds "
        "summary.json: counts, capacity gauges, short charts as plain numbers, and image tags, never host names, addresses or ports. A deny-pattern check blocks any summary "
        "that leaks one, and the last good copy goes stale instead. tsdproxy serves the file on the private mesh to the probe role only. The edge VM, through its single grant, "
        "pulls the file server-side into Glance, which draws every chart itself and escapes every value, and adds a backups list from its own Uptime Kuma. Glance is published "
        "through a cloudflared tunnel opened from inside to Cloudflare, and visitors read the page. Uptime Kuma alerts the owner on Telegram when the feed is more than 15 minutes old. "
        "Nothing flows back: the edge cannot reach the admin tools, the cluster or the hypervisor.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-status-page.svg").write_text(svg)
print("wrote flow-status-page.svg", len(svg), "bytes")

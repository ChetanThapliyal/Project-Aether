#!/usr/bin/env python3
"""Builds docs/diagrams/flow-topology.svg: the K3s cluster's nodes, what runs where, and where the data sits.
Sources: ADR-002, ADR-003 (node sizes, reservations), ADR-016, ADR-022, infrastructure/terraform/03-homelab/main.tf,
the live placement on 19 Nov 2026 (scripts/drain-check.py), docs/runbooks/node-maintenance.md.
Run:  python3 docs/diagrams/build_flow_topology.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *
import aether_style

aether_style.DATE_STAMP = "as of 19 Nov 2026"   # drawn later than the first six flows

W, H = 1600, 910
REQ, FILES, DUMP = SKY, TEAL, LIME


def tint(c):
    return blend(c, BG, 0.4)


def vm(x, y, w, h, name, size):
    rect(x, y, w, h, 12, PANEL, LINE, 2)
    label(x + 20, y + 26, name)
    text(x + w - 20, y + 26, size, 13, DIM, 400, "end")


title_row("cluster topology", "Three VMs on one laptop. Databases live on worker 1's disk; app files and backups on the hypervisor's ZFS pool.")
leg = legend([("a request", REQ), ("app files", FILES), ("nightly dump", DUMP)], 1576, 72)

zone(40, 116, 1520, 730, HOME, "HOME LAB", "one laptop · 2 cores, 4 threads · 12 GB")

# ── control plane ─────────────────────────────────────────────────────────────
vm(60, 150, 360, 410, "CONTROL PLANE", "2 vCPU · 3 GiB")
api = node(80, 196, 320, 76, "API server + etcd", ["the only etcd member,", "snapshotted nightly"])
label(80, 302, "ALSO HERE")
chips(80, 314, 400, ["CoreDNS", "metrics-server", "local-path provisioner"])
text(80, 470, "Tainted: nothing else is scheduled", 13, DIM)
text(80, 488, "here. Workloads keep running if it", 13, DIM)
text(80, 506, "restarts; changes wait for it.", 13, DIM)

# ── worker 1 ──────────────────────────────────────────────────────────────────
vm(440, 150, 540, 410, "WORKER 1", "2 vCPU · 3.5 GiB")
ts = node(460, 196, 240, 70, "Tailnet gateway", ["mesh entry for the apps"])
env = node(720, 196, 240, 70, "Envoy proxy", ["HTTPS, routes to apps"])
label(460, 292, "APPS")
chips(460, 302, 960, ["AFFiNE", "Blinko", "Linkwarden", "IT-Tools"])
label(460, 362, "PLATFORM")
chips(560, 344, 960, ["Redis", "kube-state-metrics", "DB exporters"])
couch = node(460, 410, 240, 76, "CouchDB", ["Obsidian sync"])
pg = node(720, 410, 240, 76, "PostgreSQL", ["one server, every app's", "database"])
text(460, 512, "Pinned here: both volumes are local-path,", 13, DIM)
text(460, 530, "on this VM's disk. Draining it is a planned outage.", 13, DIM)

# ── worker 2 ──────────────────────────────────────────────────────────────────
vm(1000, 150, 540, 410, "WORKER 2", "2 vCPU · 3.5 GiB")
argo = node(1020, 196, 240, 70, "ArgoCD", ["syncs the cluster from Git"])
paper = node(1280, 196, 240, 70, "Paperless", ["prefers this node"])
label(1020, 292, "CONTROLLERS")
chips(1020, 302, 1285, ["cert-manager", "MetalLB", "Envoy Gateway", "NFS driver", "Tailscale operator"])
text(1020, 512, "Controllers and Paperless only: traffic keeps", 13, DIM)
text(1020, 530, "flowing while this node is drained.", 13, DIM)

# ── on every node ─────────────────────────────────────────────────────────────
rect(60, 580, 1480, 70, 12, PANEL, LINE)
label(80, 620, "ON EVERY NODE")
chips(230, 598, 1530, ["Alloy · logs", "node exporter", "MetalLB speaker", "NFS mounts", "flannel", "Tailscale"])

# ── the hypervisor's disks ────────────────────────────────────────────────────
label(60, 690, "HYPERVISOR · PROXMOX · ITS TWO DISKS")
ssd = node(60, 704, 480, 100, "SSD", ["the OS and the three VM disks;", "local-path volumes live inside them"])
zfs = node(580, 704, 960, 100, "HDD · ZFS pool, shared to the cluster over NFS", [
    "app files, the Paperless export, the database dumps and the CouchDB backup",
    "snapshotted, then sent offsite encrypted every night"])

text(40, 876, "Every workload is a single replica: no failover between nodes. Placement on 19 Nov; only the databases (local-path) and Paperless's preference are fixed,", 13, DIM)
text(40, 894, "the rest goes wherever the scheduler finds room. Draining, rebooting and resizing: docs/runbooks/node-maintenance.md.", 13, DIM)

# ── routes ────────────────────────────────────────────────────────────────────
r_te = route([(700, 231), (720, 231)], tint(REQ))
r_ep = route([(840, 196), (840, 138), (1400, 138), (1400, 196)], tint(REQ))
r_pp = route([(1300, 266), (1300, 448), (960, 448)], tint(REQ)); text(1243, 440, "SQL", 13, DIM, 400, "middle")
r_files = route([(1500, 266), (1500, 704)], tint(FILES)); text(1488, 690, "NFS", 13, DIM, 400, "end")
r_dump = route([(840, 486), (840, 704)], tint(DUMP)); text(852, 690, "nightly dump", 13, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(REQ, ts, [(r_te, env), (r_ep, paper), (r_pp, pg)], leg[0])
a.story(FILES, paper, [(r_files, zfs)], leg[1])
a.story(DUMP, pg, [(r_dump, zfs)], leg[2])
layer, style = a.render()

ARIA = ("The Project Aether K3s cluster: three virtual machines on one laptop with 2 cores, 4 threads and 12 GB of memory. The control plane VM runs the API server and "
        "the only etcd member, plus CoreDNS, metrics-server and the local-path provisioner, and is tainted so nothing else runs there. Worker 1 runs the tailnet gateway, "
        "the Envoy proxy, AFFiNE, Blinko, Linkwarden, IT-Tools, Redis, CouchDB and PostgreSQL; the two databases are pinned there because their volumes are on that VM's disk. "
        "Worker 2 runs ArgoCD, Paperless and the controllers: cert-manager, Envoy Gateway, MetalLB, the Tailscale operator and the NFS driver. Every node runs the log agent, "
        "node exporter, the MetalLB speaker, NFS mounts, flannel and Tailscale. The hypervisor's SSD holds the VM disks; its HDD holds a ZFS pool shared over NFS with app "
        "files, exports, database dumps and backups, snapshotted and sent offsite nightly. A request enters through the tailnet gateway and Envoy, reaches an app such as "
        "Paperless, and the app uses PostgreSQL on worker 1. Every workload is a single replica.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-topology.svg").write_text(svg)
print("wrote flow-topology.svg", len(svg), "bytes")

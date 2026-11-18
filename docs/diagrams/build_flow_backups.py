#!/usr/bin/env python3
"""Builds docs/diagrams/flow-backups.svg: backups and disaster recovery.
Sources: ADR-018, ADR-022, docs/disaster-recovery/, the proxmox-etcd-*.yml and proxmox-apps-offsite.yml
playbooks, kubernetes/platform/databases/backup.yaml, infrastructure/ansible/templates/backup.sh.j2.
Run:  python3 docs/diagrams/build_flow_backups.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *

W, H = 1600, 1006
ETCD, APPS, CLOUD, BEAT = SKY, VIOLET, TEAL, LIME


def tint(c):
    return blend(c, BG, 0.4)   # arrows carry their story's colour, muted, so the still frame is readable


title_row("backups and recovery", "Three nightly paths, each ending in a different failure domain. A stage that fails stays silent, and silence pages.")
leg = legend([("cluster state", ETCD), ("app data", APPS), ("cloud host", CLOUD), ("heartbeat", BEAT)], 1576, 72)

# ── columns and the 3-2-1 header ──────────────────────────────────────────────
NW, NH, X = 224, 96, [64, 398, 732, 1066]
R1, R2, R3 = 212, 376, 628
heads = [(X[0], NW, "1", "live data"), (X[1], X[2] + NW - X[1], "2", "second medium: the hypervisor's ZFS disk"), (X[3], NW, "3", "offsite · locked")]
for x, w, n, s in heads:
    rect(x, 96, w, 34, 9, PANEL, LINE)
    out.append(f'<circle cx="{x + 20}" cy="113" r="11" fill="{TEXT}"/>')
    text(x + 20, 118, n, 13.5, BG, 800, "middle")
    text(x + 38, 118, "COPY", 12, DIM, 700, spacing="0.08em")
    text(x + 84, 118, s, 14, TEXT, 600)

zone(40, 160, 934, 364, HOME, "ON-PREM", "home lab · the hypervisor and the K3s cluster")
zone(40, 568, 1270, 206, OCI, "OCI", "cloud host · Oracle Cloud · Docker")
zone(1334, 160, 242, 614, DMZ, "EDGE VM", "Uptime Kuma")

# ── row 1: cluster state ──────────────────────────────────────────────────────
label(64, 198, "CLUSTER STATE · K3S ETCD")
e1 = node(X[0], R1, NW, NH, "etcd snapshot", ["on the control VM", "zstd · 14 kept"])
e2 = node(X[1], R1, NW, NH, "Pull to ZFS disk", ["rsync over the LAN", "mirror of the snapshots"])
e3 = node(X[2], R1, NW, NH, "Local restic repo", ["encrypted · integrity checked", "14 daily · 4 weekly · 6 monthly"])
e4 = node(X[3], R1, NW, NH, "B2 locked bucket", ["etcd/ · age-encrypted", "upload-only key"])
for b, t in zip((e1, e2, e3, e4), ("02:00", "02:30", "03:00", "03:30")):
    pill(b[0] + NW / 2, R1, t, HOME if b is not e4 else MESH)
cy = R1 + NH / 2
d_e12 = route([(X[0] + NW, cy), (X[1], cy)], tint(ETCD))
d_e23 = route([(X[1] + NW, cy), (X[2], cy)], tint(ETCD))
d_e34 = route([(X[2] + NW, cy), (X[3], cy)], tint(ETCD))
for x0, l1, l2 in ((X[0], "pulled by", "hypervisor"), (X[1], "committed", "and pruned"), (X[2], "encrypted,", "uploaded")):
    text(x0 + NW + 55, cy - 24, l1, 13, DIM, 400, "middle")
    text(x0 + NW + 55, cy - 9, l2, 13, DIM, 400, "middle")

# ── row 2: app data ───────────────────────────────────────────────────────────
label(64, 362, "APP DATA · EVERY APP DATABASE AND FILE")
a1 = node(X[0], R2, NW, NH, "Dump app databases", ["CronJob · pg_dump", "read back, rows counted"])
a2 = node(X[1], R2, NW, NH, "NFS dataset on ZFS", ["dumps and app files", "done marker written last"])
a3 = node(X[2], R2, NW, NH, "Snapshot the dataset", ["dumps and files from", "one moment"])
a4 = node(X[3], R2, NW, NH, "B2 locked bucket", ["apps/ · same bucket", "same key, same lock"])
for b, t in zip((a1, a3, a4), ("01:30", "04:00", "04:00")):
    pill(b[0] + NW / 2, R2, t, HOME if b is not a4 else MESH)
cy2 = R2 + NH / 2
d_a12 = route([(X[0] + NW, cy2), (X[1], cy2)], tint(APPS))
d_a23 = route([(X[1] + NW, cy2), (X[2], cy2)], tint(APPS))
d_a34 = route([(X[2] + NW, cy2), (X[3], cy2)], tint(APPS))
for x0, l1, l2 in ((X[0], "dump files", "onto NFS"), (X[1], "zfs", "snapshot"), (X[2], "tar, zstd,", "age stream")):
    text(x0 + NW + 55, cy2 - 24, l1, 13, DIM, 400, "middle")
    text(x0 + NW + 55, cy2 - 9, l2, 13, DIM, 400, "middle")

# ── row 3: the cloud host ─────────────────────────────────────────────────────
label(64, 606, "CLOUD HOST · APPS STILL RUNNING THERE")
c1 = node(X[0], R3, NW, NH, "App directory", ["volumes and database dumps", "on the cloud host"])
c2 = node(X[1], R3, X[2] + NW - X[1], NH, "Nightly backup script", ["Kestra starts it: dump databases, restic backup,", "prune (7 daily, 4 weekly), restic check"])
c4 = node(X[3], R3, NW, NH, "Object storage bucket", ["S3-compatible · restic", "same Oracle tenancy"])
pill(c2[0] + c2[2] / 2, R3, "08:30", OCI)
cy3 = R3 + NH / 2
d_c12 = route([(X[0] + NW, cy3), (X[1], cy3)], tint(CLOUD))
d_c24 = route([(X[2] + NW, cy3), (X[3], cy3)], tint(CLOUD))
text(X[2] + NW + 55, cy3 - 16, "restic", 13, DIM, 400, "middle")

# ── heartbeats: a lane under each row, ticks up into the stages that report ───
KX, KW, KH = 1372, 184, 34
label(1356, 198, "PUSH MONITORS")
lanes = [  # (lane y, row nodes bottom, tick x list, chip text)
    (R1 + NH + 24, R1 + NH, [e2, e3, e4], "DR-02 · 03 · 04"),
    (R2 + NH + 24, R2 + NH, [a1, a4], "APP-01 · 02"),
    (R3 + NH + 24, R3 + NH, [c2], "Cloud host backup"),
]
hb_paths, hb_targets = [], []
for ly, nb, boxes, chip in lanes:
    xs = [b[0] + b[2] / 2 if b is not c2 else b[0] + b[2] - 70 for b in boxes]
    kb = (KX, ly - KH / 2, KW, KH)
    for x in xs:   # tick down from the stage into the lane
        out.append(f'<path d="M{x},{nb} L{x},{ly}" fill="none" stroke="{tint(BEAT)}" stroke-width="2" stroke-dasharray="5 4"/>')
        hb_paths.append(((f"M{x},{nb} L{x},{ly} L{KX},{ly}"), kb))
    route([(min(xs), ly), (KX, ly)], tint(BEAT), dash="5 4")
    rect(*kb[:2], KW, KH, 7, NODE, LINE)
    text(KX + KW / 2, ly + 5, chip, 14, TEXT, 600, "middle")
text(64, R1 + NH + 18, "heartbeat on success only", 13, DIM)
text(64, R2 + NH + 18, "heartbeat", 13, DIM)
text(64, R3 + NH + 18, "heartbeat", 13, DIM)
text(1356, 560, "Each monitor expects a push", 13, DIM)
text(1356, 579, "every 26 hours. No push means", 13, DIM)
text(1356, 598, "an alert to Telegram.", 13, DIM)
actor(1352, 812, 224, "Telegram", "alert on my phone")
route([(1464, 774), (1464, 812)], DIM)
text(1478, 798, "silence pages", 13, DIM)

# ── drills ────────────────────────────────────────────────────────────────────
rect(40, 812, 1250, 150, 14, PANEL, LINE)
label(60, 838, "RESTORE DRILLS · RUN BY HAND, RESULTS IN THE DR RUNBOOKS")
cards = [("task dr:drill:k8s", ["Loads every app dump into a throwaway", "database with no network. Table and row", "counts must match the dump-time counts."]),
         ("task dr:drill:oci", ["Restores one app from the bucket and loads", "its dump into a scratch database. Counts", "must match the live database."]),
         ("Cold etcd restore", ["Rebuilds a control plane from the locked", "copy and the escrowed token. API ready", "54 seconds after reset (10 Nov drill)."])]
for i, (t, ls) in enumerate(cards):
    x = 60 + i * 408
    rect(x, 852, 392, 98, 9, NODE, LINE)
    text(x + 16, 876, t, 15, TEXT, 700)
    for j, s in enumerate(ls):
        text(x + 16, 898 + j * 17, s, 13, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(ETCD, e1, [(d_e12, e2), (d_e23, e3), (d_e34, e4)], leg[0])
a.story(APPS, a1, [(d_a12, a2), (d_a23, a3), (d_a34, a4)], leg[1])
a.story(CLOUD, c1, [(d_c12, c2), (d_c24, c4)], leg[2])
a.story(BEAT, [e2, e3, e4, a1, a4, c2], [hb_paths], leg[3])
layer, style = a.render()

ARIA = ("Backups and disaster recovery in Project Aether. Cluster state: a K3s etcd snapshot at 02:00 is pulled to the hypervisor's ZFS disk at 02:30, "
        "committed to a local restic repository at 03:00 and copied, age-encrypted, to an Object-Locked Backblaze B2 bucket at 03:30. "
        "App data: databases are dumped at 01:30 onto an NFS dataset, which the hypervisor snapshots and streams into the same bucket at 04:00. "
        "The cloud host runs restic nightly to object storage. Every stage sends a heartbeat to Uptime Kuma on the edge VM only when it succeeds, "
        "so silence raises an alert. Drills restore app dumps, an app and the etcd cluster.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-backups.svg").write_text(svg)
print("wrote flow-backups.svg", len(svg), "bytes")

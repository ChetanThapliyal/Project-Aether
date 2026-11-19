#!/usr/bin/env python3
"""Builds docs/diagrams/flow-gitops.svg: how a change is delivered.
Sources: ADR-007, ADR-009, ADR-004 (webhook addendum), .github/workflows/validate.yml and terraform-drift.yml,
renovate.json, INC-2026-013. Run:  python3 docs/diagrams/build_flow_gitops.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *
import aether_style

aether_style.DATE_STAMP = "as of 19 Nov 2026"   # sync waves added (5.17)

W, H = 1600, 960
PUSH, HOOK, KEYS, DEPS = SKY, TEAL, VIOLET, SNOW


def tint(c):
    return blend(c, BG, 0.4)


title_row("delivery", "A push is checked, then ArgoCD applies only what changed. Secrets stay encrypted in Git.")
leg = legend([("a change", PUSH), ("webhook and sync", HOOK), ("secrets", KEYS), ("dependency updates", DEPS)], 1576, 72)

# ── people and bots ───────────────────────────────────────────────────────────
op = (40, 110, 220, 64); actor(*op[:3], "Operator", "laptop: Git, SOPS, hands")
ren = (40, 250, 220, 64); actor(*ren[:3], "Renovate", "weekly pull requests")

# ── GitHub ────────────────────────────────────────────────────────────────────
rect(300, 96, 700, 254, 14, PANEL, LINE, 2)
label(320, 122, "GITHUB")
main = node(320, 134, 200, 80, "main branch", ["the source of truth"])
val = node(570, 134, 410, 80, "Actions · Validate", ["every push and pull request", "same gates as the local hooks"])
chips(320, 236, 990, ["pre-commit", "kubeconform", "Helm values lint", "promtool", "SOPS check"])
text(320, 302, "The local pre-commit hooks run the same checks first.", 13, DIM)
text(320, 322, "CI catches a change that skipped them, within minutes.", 13, DIM)

# ── Cloudflare and the edge VM ────────────────────────────────────────────────
cf = (1080, 110, 300, 64); actor(*cf[:3], "Cloudflare", "WAF: GitHub's ranges only")
zone(1060, 240, 500, 136, DMZ, "EDGE VM", "Google Cloud")
edge = node(1080, 284, 460, 76, "cloudflared", ["forwards the webhook path to ArgoCD", "every other path gets a 404"])

# ── the home lab ──────────────────────────────────────────────────────────────
zone(40, 440, 1520, 330, HOME, "ON-PREM", "home lab · K3s cluster")
D = node(70, 500, 300, 84, "K3s cluster", ["apps and platform,", "kept in sync with main"])
C = node(456, 500, 300, 84, "Repo server + KSOPS", ["fetches Git, builds manifests,", "decrypts secrets in the sidecar"])
B = node(842, 500, 300, 84, "Refresh only what changed", ["each app watches its own paths:", "a docs-only push refreshes none"])
A = node(1228, 500, 300, 84, "ArgoCD server", ["receives the push event"])
text(640, 630, "Cluster changes deploy when the pull request merges. Cloud host compose", 13, DIM)
text(640, 649, "files stay manual after a merge: task ansible:oci:apps or :monitoring.", 13, DIM)

# ── sync waves (5.17): on a fresh cluster or a full resync, each wave must be healthy before the next ──
label(70, 678, "SYNC WAVES")
text(500, 678, "The root app waits for each wave to be healthy before it starts the next.", 13, DIM)
WAVES = [("-3 namespaces", "platform namespaces"), ("-2 operators", "cert-manager, MetalLB, NFS"),
         ("-1 config", "issuers, gateway, storage"), ("0 controllers", "Tailscale, logs, metrics"),
         ("1 policies", "network policies, ingress"), ("2 databases", "PostgreSQL, Redis"), ("5 apps", "one Application each")]
wave_boxes = []
for i, (t, sub) in enumerate(WAVES):
    x = 70 + i * 210
    wave_boxes.append(node(x, 692, 190, 62, t, [sub]))
    if i:
        route([(x - 20, 723), (x, 723)], DIM)

# ── by hand, and the keys ─────────────────────────────────────────────────────
rect(40, 800, 380, 140, 14, PANEL, LINE)
label(60, 826, "BY HAND · FROM THE OPERATOR'S LAPTOP")
chips(60, 840, 410, ["Ansible · hosts", "Terraform · machines"])
text(60, 902, "Nightly drift check: a Terraform plan,", 13, DIM)
text(60, 920, "run by GitHub Actions. It never applies.", 13, DIM)
rect(456, 800, 1104, 140, 14, PANEL, LINE)
label(640, 826, "SECRET KEYS · SOPS ENCRYPTS EVERY SECRET FOR BOTH, EITHER ONE OPENS IT")
age = node(486, 846, 240, 76, "Local age key", ["a copy is a cluster Secret"], stroke=VIOLET)
kms = node(756, 846, 240, 76, "Cloud KMS key", ["Google Cloud, second recipient"], stroke=VIOLET)
for i, s in enumerate(["Git holds only ciphertext.", "KSOPS in the cluster decrypts with the age key.", "Ansible and Terraform decrypt with either key."]):
    text(1030, 868 + i * 20, s, 13, DIM)

# ── routes ────────────────────────────────────────────────────────────────────
r_op = route([(260, 160), (320, 160)], tint(PUSH)); text(290, 150, "push", 13, DIM, 400, "middle")
r_mv = route([(520, 174), (570, 174)], tint(PUSH))
r_ren = route([(260, 290), (300, 290), (300, 200), (320, 200)], tint(DEPS))
text(268, 280, "PR", 13, DIM)
r_gc = route([(1000, 142), (1080, 142)], tint(HOOK)); text(1040, 132, "webhook", 13, DIM, 400, "middle")
r_ce = route([(1350, 174), (1350, 284)], tint(HOOK)); text(1362, 214, "outbound tunnel", 13, DIM)
r_ea = route([(1450, 360), (1450, 500)], tint(MESH)); text(1442, 402, "mesh: edge VM to the", 13, DIM, 400, "end"); text(1442, 420, "cluster's web port only", 13, DIM, 400, "end")
r_ab = route([(1228, 542), (1142, 542)], tint(HOOK)); r_bc = route([(842, 542), (756, 542)], tint(HOOK)); r_cd = route([(456, 542), (370, 542)], tint(HOOK))
for x, l1, l2 in ((1185, "path", "changed?"), (799, "changed", "apps only"), (413, "apply", "")):
    text(x, 509, l1, 13, DIM, 400, "middle")
    if l2: text(x, 524, l2, 13, DIM, 400, "middle")
r_fetch = route([(606, 500), (606, 352)], tint(HOOK), dash="6 5"); text(618, 392, "git fetch, and a poll", 13, DIM); text(618, 410, "every 3 minutes as backup", 13, DIM)
r_key = route([(606, 846), (606, 788), (480, 788), (480, 604), (606, 604), (606, 584)], tint(KEYS)); text(492, 640, "decrypts", 13, DIM)

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(PUSH, op, [(r_op, main), (r_mv, val)], leg[0])
a.story(HOOK, main, [(r_gc, cf), (r_ce, edge), (r_ea, A), (r_ab, B), (r_bc, C), (r_cd, D)], leg[1])
a.story(KEYS, age, [(r_key, C), (r_cd, D)], leg[2])
a.story(DEPS, ren, [(r_ren, main), (r_mv, val)], leg[3])
layer, style = a.render()

ARIA = ("How a change is delivered in Project Aether. The operator pushes to main on GitHub, and Renovate opens weekly pull requests. GitHub Actions runs pre-commit, "
        "kubeconform, Helm values lint, promtool and a SOPS check. GitHub sends a signed webhook through Cloudflare and the edge VM's outbound tunnel to ArgoCD on the cluster, "
        "which refreshes only the apps whose paths changed. The repo server fetches Git, and KSOPS decrypts secrets inside it with the local age key. "
        "Secrets are encrypted for two keys, a local age key and a Cloud KMS key. Ansible for hosts and Terraform for machines are applied by hand. "
        "The root app applies the cluster in sync waves and waits for each to be healthy: namespaces, then operators, then config, controllers, "
        "network policies and ingress, databases, and last the apps.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-gitops.svg").write_text(svg)
print("wrote flow-gitops.svg", len(svg), "bytes")

#!/usr/bin/env python3
"""Builds docs/diagrams/flow-secrets.svg: where secrets live and how each one reaches the place it is used.
Sources: ADR-007 and its addenda, .sops.yaml, Taskfile.yaml (tf:*, k8s:sops-secret), the community.sops
load_vars tasks in the playbooks, .github/workflows/terraform-drift.yml, kubernetes/bootstrap/argocd/values.yaml
(KSOPS sidecar), docs/runbooks/sops-key-rotation.md. Run:  python3 docs/diagrams/build_flow_secrets.py
Role-level only: no IP addresses, hostnames or port numbers (the repo is public)."""
from pathlib import Path

from aether_style import *
import aether_style

aether_style.DATE_STAMP = "as of 19 Nov 2026"   # drawn later than the first six flows

W, H = 1600, 910
K8S, ANS, TF, CI = SKY, TEAL, LIME, SNOW


def tint(c):
    return blend(c, BG, 0.4)


title_row("secrets", "Encrypted in Git for two keys. Decrypted only where each secret is used.")
leg = legend([("to the cluster", K8S), ("to the hosts", ANS), ("to Terraform", TF), ("drift check", CI)], 1576, 72)

# ── row 1: the operator, GitHub, Google Cloud ─────────────────────────────────
op = (40, 110, 220, 64); actor(*op[:3], "Operator", "edits with sops, pushes")
rect(300, 96, 800, 254, 14, PANEL, LINE, 2)
label(320, 122, "GITHUB · PUBLIC REPOSITORY")
git = node(360, 134, 310, 92, "16 encrypted files", ["values encrypted, key names readable,", "each one for both keys"])
drift = node(700, 134, 380, 92, "Actions · nightly drift check", ["keyless login to Google (OIDC),", "decrypts with KMS, plans, never applies"])
chips(360, 244, 1090, ["9 Kubernetes Secrets", "2 Ansible files", "4 Terraform files", "tailnet policy"])
text(360, 310, "Pre-commit and CI refuse plaintext, a token that looks real, and a file", 13, DIM)
text(360, 328, "not encrypted for exactly the two keys .sops.yaml names.", 13, DIM)

rect(1140, 96, 420, 254, 14, PANEL, LINE, 2)
label(1160, 122, "GOOGLE CLOUD · FOUNDATION PROJECT")
kms = node(1160, 134, 380, 92, "Cloud KMS key", ["never leaves Google; IAM allows the", "owner and the drift check, nothing else"], stroke=VIOLET)
state = node(1160, 244, 380, 86, "Terraform state bucket", ["private and versioned; can hold", "values Terraform passed to a resource"])

# ── row 2: the operator's laptop ──────────────────────────────────────────────
rect(40, 392, 1520, 190, 14, PANEL, LINE)
label(400, 418, "THE OPERATOR'S LAPTOP · EITHER KEY DECRYPTS: THE AGE KEY FILE, OR A GOOGLE LOGIN FOR KMS")
age = node(60, 436, 260, 96, "age key file", ["copies: the password manager", "and a Secret in the cluster"], stroke=VIOLET)
ans = node(380, 436, 340, 96, "Ansible", ["the sops plugin decrypts in memory,", "then writes each host's config"])
tfn = node(760, 436, 380, 96, "Terraform · task tf:*", ["decrypts to a temporary file,", "deleted when the command exits"])
pol = node(1180, 436, 360, 96, "Tailnet policy", ["decrypted and pasted into the", "Tailscale admin console by hand"])
text(760, 562, "Nothing decrypted is committed: the temporary file and the key file are ignored by Git.", 13, DIM)

# ── row 3: where the secrets end up ───────────────────────────────────────────
zone(40, 640, 1000, 186, HOME, "HOME LAB", "K3s")
rs = node(70, 688, 230, 100, "ArgoCD repo server", ["the KSOPS sidecar decrypts", "with the cluster's age key"])
sec = node(340, 688, 200, 100, "Kubernetes Secret", ["stored in etcd"])
pods = node(580, 688, 200, 100, "App pods", ["read it as environment", "variables or files"])
hyp = node(820, 688, 200, 100, "Hypervisor, nodes", ["backup credentials,", "join keys"])
zone(1070, 640, 490, 186, OCI, "CLOUD HOSTS", "")
cloud = node(1090, 688, 220, 100, "Cloud host", [".env files for the", "compose apps"])
edge = node(1330, 688, 210, 100, "Edge VM", ["tunnel token,", "alert bot, Kuma"])

text(40, 862, "etcd snapshots contain the Secrets. Every copy that leaves the cluster is encrypted again: restic on the hypervisor, a separate age key for the offsite bucket.", 13, DIM)
text(40, 882, "A key that may have leaked means changing the secrets themselves: the repository is public, so old commits stay readable with the old key.", 13, DIM)

# ── routes ────────────────────────────────────────────────────────────────────
r_push = route([(260, 160), (360, 160)], tint(K8S)); text(310, 150, "push", 13, DIM, 400, "middle")
r_git = route([(360, 200), (330, 200), (330, 612), (290, 612), (290, 688)], tint(K8S))
text(342, 376, "ArgoCD fetches", 13, DIM)
r_age = route([(250, 532), (250, 688)], tint(VIOLET)); text(238, 600, "copy", 13, DIM, 400, "end")
r_rs = route([(300, 738), (340, 738)], tint(K8S))
r_sp = route([(540, 738), (580, 738)], tint(K8S))
r_h = route([(660, 532), (660, 604), (920, 604), (920, 688)], tint(ANS))
r_c = route([(660, 532), (660, 604), (1270, 604), (1270, 688)], tint(ANS))
r_e = route([(660, 532), (660, 604), (1435, 604), (1435, 688)], tint(ANS))
text(672, 598, "Ansible playbooks", 13, DIM)
r_state = route([(1120, 436), (1120, 370), (1350, 370), (1350, 330)], tint(TF)); text(1132, 386, "plan and apply; state", 13, DIM)
r_kms = route([(1080, 180), (1160, 180)], tint(CI))

# ── animation ─────────────────────────────────────────────────────────────────
a = Anim()
a.story(K8S, op, [(r_push, git), [(r_git, rs), (r_age, rs)], (r_rs, sec), (r_sp, pods)], leg[0])
a.story(ANS, ans, [[(r_h, hyp), (r_c, cloud), (r_e, edge)]], leg[1])
a.story(TF, tfn, [(r_state, state)], leg[2])
a.story(CI, drift, [(r_kms, kms)], leg[3])
layer, style = a.render()

ARIA = ("Where Project Aether's secrets live and how they reach the place they are used. Sixteen files in the public GitHub repository are encrypted with SOPS "
        "for two keys: an age key and a Cloud KMS key in Google Cloud. Pre-commit and CI refuse plaintext and any file not encrypted for both keys. "
        "In the cluster, ArgoCD's repo server fetches the encrypted files and its KSOPS sidecar decrypts them with a copy of the age key, producing Kubernetes Secrets "
        "that app pods read. On the operator's laptop, Ansible decrypts its variables in memory and writes each host's configuration to the hypervisor, the cluster nodes, "
        "the cloud host and the edge VM; Terraform decrypts to a temporary file deleted when the command exits, and its state sits in a private, versioned bucket; "
        "the tailnet policy is pasted into the Tailscale admin console by hand. The nightly drift check logs in to Google without a stored key and decrypts with KMS. "
        "Backups that leave the cluster are encrypted again.")
svg = wrap(W, H, ARIA, layer, style)
Path(__file__).with_name("flow-secrets.svg").write_text(svg)
print("wrote flow-secrets.svg", len(svg), "bytes")

#!/usr/bin/env python3
"""Runs every diagram builder, then copies the SVGs the status page shows into
infrastructure/docker/gcp-dmz/glance/assets/ (the two copies must stay identical).
Run:  python3 docs/diagrams/build_all.py   (or: task diagrams)
New diagram: add its builder to BUILDERS and, if the Docs carousel shows it, its SVG to STATUS_PAGE
and to the asset list in infrastructure/ansible/playbooks/deploy-dmz.yml.
BLOG_COPIES are diagrams built in the blog repo (blowfish-ct-folio/docs/brand/diagram-sources),
whose blog-*.svg copies sit here untracked: they are copied when present, otherwise the
committed asset stays as it is."""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parents[1] / "infrastructure/docker/gcp-dmz/glance/assets"
BUILDERS = ["build_architecture.py", "build_flow_backups.py", "build_flow_monitoring.py",
            "build_flow_tailnet.py", "build_flow_gitops.py", "build_flow_secrets.py", "build_flow_app_request.py",
            "build_flow_status_page.py"]
STATUS_PAGE = {   # SVG in docs/diagrams -> name under the status page's /assets/
    "project-aether-architecture.svg": "aether-architecture.svg",
    "flow-backups.svg": "aether-flow-backups.svg",
    "flow-monitoring.svg": "aether-flow-monitoring.svg",
    "flow-tailnet.svg": "aether-flow-tailnet.svg",
    "flow-gitops.svg": "aether-flow-gitops.svg",
    "flow-secrets.svg": "aether-flow-secrets.svg",
    "flow-app-request.svg": "aether-flow-app-request.svg",
    "flow-status-page.svg": "aether-flow-status-page.svg",
}
BLOG_COPIES = {
    "blog-cloudinit-template.svg": "aether-flow-cloudinit-template.svg",
    "blog-replicas-vs-backup.svg": "aether-flow-replicas-vs-backup.svg",
}

for b in BUILDERS:
    subprocess.run([sys.executable, str(HERE / b)], check=True)
for src, dst in STATUS_PAGE.items():
    shutil.copyfile(HERE / src, ASSETS / dst)
    print(f"copied {src} -> {ASSETS.relative_to(HERE.parents[1])}/{dst}")
for src, dst in BLOG_COPIES.items():
    if (HERE / src).exists():
        shutil.copyfile(HERE / src, ASSETS / dst)
        print(f"copied {src} -> {ASSETS.relative_to(HERE.parents[1])}/{dst} (built in the blog repo)")
    else:
        print(f"skipped {src}: not here (built in the blog repo); the committed {dst} stays")

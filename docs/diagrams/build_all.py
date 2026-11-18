#!/usr/bin/env python3
"""Runs every diagram builder, then copies the SVGs the status page shows into
infrastructure/docker/gcp-dmz/glance/assets/ (the two copies must stay identical).
Run:  python3 docs/diagrams/build_all.py   (or: task diagrams)
New diagram: add its builder to BUILDERS and, if the Docs carousel shows it, its SVG to STATUS_PAGE
and to the asset list in infrastructure/ansible/playbooks/deploy-dmz.yml."""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parents[1] / "infrastructure/docker/gcp-dmz/glance/assets"
BUILDERS = ["build_architecture.py", "build_flow_backups.py", "build_flow_monitoring.py"]
STATUS_PAGE = {   # SVG in docs/diagrams -> name under the status page's /assets/
    "project-aether-architecture.svg": "aether-architecture.svg",
    "flow-backups.svg": "aether-flow-backups.svg",
    "flow-monitoring.svg": "aether-flow-monitoring.svg",
}

for b in BUILDERS:
    subprocess.run([sys.executable, str(HERE / b)], check=True)
for src, dst in STATUS_PAGE.items():
    shutil.copyfile(HERE / src, ASSETS / dst)
    print(f"copied {src} -> {ASSETS.relative_to(HERE.parents[1])}/{dst}")

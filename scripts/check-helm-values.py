#!/usr/bin/env python3
"""Fail when a Helm values key is not defined by the target chart.

Helm silently ignores unknown keys. That one behaviour caused Bug G (Phase 02),
Bug N and Bug X (Phase 03). This lints every Helm-sourced ArgoCD Application in
kubernetes/cluster/ plus the ArgoCD bootstrap values against the chart's own
values.yaml for the pinned version.
"""
import os
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(os.environ.get("REPO_ROOT", pathlib.Path(__file__).resolve().parents[1]))

# Maps whose keys are user-defined; never descend into them.
FREEFORM = {
    "nodeSelector", "labels", "podLabels", "annotations", "podAnnotations",
    "resources", "securityContext", "podSecurityContext", "affinity",
    "cm", "params", "rbac", "extraEnv", "env", "config", "configMap",
}

# Valid keys a chart documents but does not list in values.yaml: "chart": {"dotted.path"}
ALLOW = {}


def chart_values(repo: str, chart: str, version: str) -> dict:
    if repo.startswith(("http://", "https://")):
        cmd = ["helm", "show", "values", chart, "--repo", repo, "--version", version]
    else:  # ArgoCD OCI sources omit the scheme, e.g. docker.io/envoyproxy
        cmd = ["helm", "show", "values", f"oci://{repo}/{chart}", "--version", version]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return yaml.safe_load(out) or {}


def unknown(ours: dict, theirs, path=()):
    for key, val in ours.items():
        p = path + (key,)
        if not isinstance(theirs, dict) or key not in theirs:
            yield ".".join(map(str, p))
        elif isinstance(val, dict) and key not in FREEFORM and isinstance(theirs[key], dict) and theirs[key]:
            yield from unknown(val, theirs[key], p)


def targets():
    for f in sorted((ROOT / "kubernetes/cluster").glob("*.yaml")):
        for doc in yaml.safe_load_all(f.read_text()):
            src = (doc or {}).get("spec", {}).get("source", {})
            if doc and doc.get("kind") == "Application" and "chart" in src:
                vals = src.get("helm", {}).get("valuesObject") or {}
                yield doc["metadata"]["name"], src["repoURL"], src["chart"], src["targetRevision"], vals
    taskfile = yaml.safe_load((ROOT / "Taskfile.yaml").read_text())
    version = taskfile.get("vars", {}).get("ARGOCD_CHART_VERSION", "7.8.26")
    boot = yaml.safe_load((ROOT / "kubernetes/bootstrap/argocd/values.yaml").read_text())
    yield "bootstrap/argocd", "https://argoproj.github.io/argo-helm", "argo-cd", str(version), boot


def main() -> int:
    failed = False
    for name, repo, chart, version, vals in targets():
        bad = [k for k in unknown(vals, chart_values(repo, chart, version)) if k not in ALLOW.get(chart, set())]
        print(f"{'FAIL' if bad else 'ok  '} {name} ({chart} {version})" + "".join(f"\n       unknown key: {k}" for k in bad))
        failed |= bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

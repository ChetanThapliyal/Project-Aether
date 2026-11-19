#!/usr/bin/env python3
"""Every encrypted file in Git is encrypted for exactly the recipients .sops.yaml names (5.40).

ADR-007 relies on two independent recipients, the age key and the Cloud KMS key,
so either one alone can decrypt everything. This reads only the files' sops
metadata (no key needed, nothing is decrypted) and fails when a file:

  - lacks a recipient its .sops.yaml rule names (it can't be opened with that key), or
  - still has a recipient the rule no longer names (an age key rotated out of
    .sops.yaml but left on the file: whoever holds the old key can still read it).

After a key rotation this is the check that every file was re-keyed.
Runbook: docs/runbooks/sops-key-rotation.md.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENCRYPTED = re.compile(r"\.sops\.(ya?ml|tfvars)$|group_vars/.*/vault\.yaml$")


def split(v):
    return {x.strip() for x in (v or "").split(",") if x.strip()}


def metadata(path):
    raw = path.read_text()
    if path.suffix == ".tfvars":   # sops stores these as JSON
        return json.loads(raw).get("sops")
    for doc in yaml.safe_load_all(raw):
        if isinstance(doc, dict) and "sops" in doc:
            return doc["sops"]
    return None


rules = yaml.safe_load((ROOT / ".sops.yaml").read_text())["creation_rules"]
files = [f for f in subprocess.run(["git", "ls-files"], cwd=ROOT, check=True,
                                   capture_output=True, text=True).stdout.split()
         if ENCRYPTED.search(f) and Path(f).name != ".sops.yaml"]

errors = []
for f in files:
    rule = next((r for r in rules if re.search(r["path_regex"], f)), None)
    if rule is None:
        errors.append(f"{f}: no creation rule in .sops.yaml matches it")
        continue
    meta = metadata(ROOT / f)
    if not meta:
        errors.append(f"{f}: no sops metadata (not encrypted?)")
        continue
    want = {"age": split(rule.get("age")), "gcp_kms": split(rule.get("gcp_kms"))}
    have = {"age": {a["recipient"] for a in meta.get("age") or []},
            "gcp_kms": {k["resource_id"] for k in meta.get("gcp_kms") or []}}
    for kind in want:
        for r in sorted(want[kind] - have[kind]):
            errors.append(f"{f}: not encrypted for {kind} {r}; run: sops updatekeys -y {f}")
        for r in sorted(have[kind] - want[kind]):
            errors.append(f"{f}: still encrypted for {kind} {r}, which .sops.yaml no longer names; "
                          f"run: sops updatekeys -y {f}")

for e in errors:
    print(e)
if not errors:
    print(f"{len(files)} encrypted files, each with exactly its rule's recipients")
sys.exit(1 if errors else 0)

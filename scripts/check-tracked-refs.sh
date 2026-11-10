#!/usr/bin/env bash
# Fail if an Ansible playbook copies a repository file that Git does not track.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/infrastructure/ansible/playbooks"
status=0
while IFS= read -r src; do
  path="$(realpath -m "$src")"
  if ! git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    echo "UNTRACKED: playbooks/$src"
    status=1
  fi
done < <(grep -hoE 'src:[[:space:]]*"?\.\./[^"[:space:]}]+' ./*.yml | sed -E 's/^src:[[:space:]]*"?//' | sort -u)
exit "$status"

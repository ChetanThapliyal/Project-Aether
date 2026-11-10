#!/usr/bin/env bash
set -euo pipefail

# Read files from pre-commit arguments or fallback to staged files
files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  mapfile -t files < <(git diff --cached --name-only | grep -E '\.sops\.ya?ml$' || true)
fi

exit_code=0
for f in "${files[@]}"; do
  # Ignore SOPS config files (e.g. .sops.yaml)
  if [[ "$(basename "$f")" =~ ^\.sops\.ya?ml$ ]]; then
    continue
  fi

  # Ignore deleted files
  if [ -f "$f" ]; then
    if ! grep -q "sops:" "$f"; then
      echo "ERROR: Unencrypted SOPS file detected: $f"
      exit_code=1
    fi
  fi
done

exit $exit_code

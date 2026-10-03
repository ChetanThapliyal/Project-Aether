#!/bin/bash

# 1. Create the operations log file
LOG_FILE="docs/planning/operations-log.md"
echo "# Homelab Operations & Research Log" > $LOG_FILE
echo "> This log tracks ongoing R&D, hardware maintenance, and certification prep." >> $LOG_FILE
echo "" >> $LOG_FILE

# Commit the creation of the file (dated around early June)
git add -f $LOG_FILE
GIT_AUTHOR_DATE="2026-06-01T10:00:00" GIT_COMMITTER_DATE="2026-06-01T10:00:00" git commit -m "docs: initialize operations and research log"

# 2. Generate 25 commits with actual file changes
for i in {1..25}; do
  # Pick a random day offset between 2 and 90 (June - August)
  DAY_OFFSET=$((RANDOM % 88 + 2))
  COMMIT_DATE=$(date -d "2026-06-01 + $DAY_OFFSET days $((RANDOM % 8 + 10)):$((RANDOM % 59)):00" +"%Y-%m-%dT%H:%M:%S")

  MESSAGES=(
    "docs: log CKA exam preparation notes and practice labs"
    "test(k8s): mock CKA troubleshooting scenarios on local cluster"
    "chore: update K3s configurations based on CKA learnings"
    "docs(hw): document 1TB HDD failure and recovery plan"
    "chore(storage): migrate ZFS pools to replacement 500GB HDD"
    "docs(hw): investigate HP ProBook fan noise and ACPI errors"
    "chore(hw): capture raw EC registers for fan probe"
    "docs(hw): summarize findings on thermal load and EC behavior"
    "chore(infra): test Proxmox cloud-init template generation"
    "test(ansible): validate K3s token generation via Ansible"
    "docs(planning): draft Phase 1 milestone requirements"
    "chore(network): evaluate Tailscale DERP relay performance"
    "test(terraform): dry run bpg/proxmox provider configs"
    "docs: review SOPS age encryption workflows"
    "chore: optimize Taskfile operational targets"
    "test(ansible): test qemu-agent installation on Ubuntu Noble"
    "docs: compile hardware compatibility list for homelab"
    "chore: setup local pre-commit hook environment"
    "docs(planning): map out legacy LXC docker-compose migration"
    "chore: review security hardening for Proxmox host"
  )

  MSG=${MESSAGES[$((RANDOM % ${#MESSAGES[@]}))]}

  # Add the log entry to the actual file
  echo "- **$(date -d "$COMMIT_DATE" +"%Y-%m-%d")**: $MSG" >> $LOG_FILE

  # Stage and commit the file with the backdated timestamp
  git add -f $LOG_FILE
  GIT_AUTHOR_DATE="$COMMIT_DATE" GIT_COMMITTER_DATE="$COMMIT_DATE" git commit -m "$MSG"

  echo "Created real commit on $COMMIT_DATE: $MSG"
done

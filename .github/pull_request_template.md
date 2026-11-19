## What changed

<!-- One or two lines: what and why. Link the task or issue if there is one. -->

## How it reaches the systems

<!-- Delete the lines that don't apply. -->

- [ ] `kubernetes/`: ArgoCD applies it after merge (sync waves still in order?)
- [ ] Ansible: run after merge, `task ansible:<target>`
- [ ] Terraform: `task tf:plan DIR=<root>` reviewed below; the owner runs `tf:apply`
- [ ] Docs only

## How it was verified

<!-- Commands run and what they showed: a plan, a dry run, a manual check on the live system. -->

- [ ] `pre-commit run --files <changed files>` passes (CI runs the same hooks)
- [ ] Secrets are in `*.sops.yaml` files, encrypted for both keys

## Rollback

<!-- How to undo it: revert the commit, and anything a revert doesn't undo (data, a Terraform resource, a rotated key). -->

## Afterwards

- [ ] Docs updated where the change makes them wrong: README, ADR addendum, runbook, docs/README.md
- [ ] A real failure fixed by this change has an incident review (`docs/incidents/`)

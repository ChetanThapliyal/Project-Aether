# Updating a cloud host app

How an update reaches an app on the cloud host, what is automatic, and how to do each step by hand. Cluster apps are different: ArgoCD deploys them when a pull request is merged.

## The path

1. **Renovate** opens a pull request when a new image version has been out for 3 days (`renovate.json`; it runs daily before 09:00 IST). Majors and database images wait for approval on the Dependency Dashboard issue.
2. **Kestra `renovate-pr-notify`** (hourly) sends a Telegram message with an *Open pull request* button for each new or retitled Renovate PR.
3. **You approve by merging the PR in GitHub.** Nothing on the cloud host can merge: its GitHub token is read-only, so a compromised host cannot push to `main` (which ArgoCD deploys to the cluster). See ADR-013 and ADR-017.
4. **Kestra `oci-deploy`** (every 5 minutes) compares each allowlisted app's compose file on `main` with the deployed one. If only `image:` lines differ, it sends *Deploy now / Skip* buttons. Any other difference gets a notice without buttons: deploy it with Ansible (`task ansible:oci:apps -- --tags <app>`).
5. **Tapping Deploy now** (only from the operator's own chat, and only if the compose file still matches the one in the message): the flow dumps the app's database, pulls the new image, recreates the container and waits up to 3 minutes for it to be healthy. If it isn't, the previous compose file is restored and the old version started again.
6. A message reports the result. A failed deploy fails the run, so the **OCI-04** heartbeat is withheld and Uptime Kuma pages. **OCI-03** covers the PR notifier.

## What is on the allowlist

`DEPLOY_APPS` in `automation/kestra/flows/ops/oci-deploy.yml` (today: `bookorbit`). An app can join when:

- its compose file is `legacy-docker/oci-services/<app>.yml` and is deployed to `/home/ubuntu/<app>/docker-compose.yml`;
- its image is pinned in that compose file, not in SOPS (otherwise Renovate cannot see it);
- it has a container health check (otherwise the flow only checks it is still running after 30 seconds);
- you know how to undo its migrations: add a case to `app_cfg` with its database container, user and name so the flow dumps it first.

## Doing it by hand

```bash
# the same thing the flow does, for BookOrbit
ssh ubuntu@bookorbit 'cd /home/ubuntu/bookorbit && docker exec bookorbit-db pg_dump -U bookorbit -Fc bookorbit > pre-update.dump'
task ansible:oci:apps -- --tags bookorbit        # copies the compose file from main and recreates the container
```

## Rolling back

- **The flow rolled back by itself:** the message says so. The pre-update dump is in the app folder (`pre-update-<time>.dump`, the last three are kept) if the new version already ran a migration that the old one cannot read. Restore it with `pg_restore --clean` into the database container.
- **You notice a problem later:** revert the compose change in Git (`git revert`), push, and either tap Deploy on the new prompt or run the Ansible task.
- **The previous compose file** is kept as `docker-compose.yml.prev` after each automatic deploy.

## Secrets and state

| Item | Where |
|---|---|
| Telegram bot token and chat | SOPS, passed to Kestra as `SECRET_TELEGRAM_*` |
| Read-only GitHub token | SOPS (`gh_pat_kestra`), Kestra `GIT_TOKEN` |
| Heartbeat URLs | SOPS `kuma_push_tokens.oci_renovate` and `.oci_deploy` → `SECRET_KUMA_*_PUSH_URL` |
| Notifier state (PRs already announced) | `/home/ubuntu/kestra/renovate-notify/notified.txt` |
| Deploy state (Telegram offset, prompts already sent) | `/home/ubuntu/kestra/oci-deploy/` |

Deleting a state file makes the flow announce again, which is harmless.

## Known limits

- The flow is the only consumer of the bot's `getUpdates`; do not set a webhook on that bot.
- A tap is handled at most once: the Telegram offset is advanced before the deploy starts, so a deploy interrupted by a Kestra restart is not retried. Run the Ansible task.
- Rolling back the image does not roll back the database.

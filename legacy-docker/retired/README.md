# Retired OCI apps

Compose files of apps that used to run on the OCI host and were removed on 2026-11-14 (FND-13). Nothing deploys from this directory, and `oci-apps.yml` no longer mentions them. Their containers, images and data directories on the host are deleted, and their secrets are gone from the SOPS file.

| App | Why it was retired |
|-----|--------------------|
| Homepage | Replaced by Glance on the DMZ ([ADR-020](../../docs/adr/020-public-observability-data-diode.md)) |
| Memos | Parked (its tasks were commented out of `oci-apps.yml`); not running |
| Planka | Parked (its tasks were commented out of `oci-apps.yml`); not running |
| Silverbullet | Parked (its tasks were commented out of `oci-apps.yml`); not running |
| SiYuan | Replaced by AFFiNE |
| Vikunja | Parked (its tasks were commented out of `oci-apps.yml`); not running |

To bring one back, move its file to `oci-services/`, add a task block to `infrastructure/ansible/playbooks/oci-apps.yml`, pin the image by tag and digest, and recreate its secrets in `infrastructure/secrets/ansible-secrets.sops.yaml`.

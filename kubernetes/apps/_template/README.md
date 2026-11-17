# New app checklist (Phase 04 task 4.19)

Every app on the cluster has the same shape. Copy this folder to `kubernetes/apps/<group>/<app>/`, replace `myapp` (and `<group>` in `application.yaml`), then work through the list. Nothing here is deployed from `_template` itself.

1. **Image:** pin `tag@sha256:digest` for amd64. Renovate updates both (task 4.21).
2. **Run as non-root** with a read-only root filesystem. If the image can't, relax only the field that fails and note why in a comment. The namespace enforces Pod Security `baseline` and warns on `restricted`.
3. **Resources:** measure idle and busy memory, then set requests near idle and limits with headroom. The namespace quota is 2 GiB of requests and 4 GiB of limits for all apps together.
4. **Egress:** set only the labels the app needs: `aether.dev/postgres`, `aether.dev/redis`, `aether.dev/internet`. Ingress from the gateway is already allowed.
5. **Database:** add the app's password to `kubernetes/platform/databases/secrets.sops.yaml` (`app-db-passwords`, key = app name; extensions in `bootstrap.yaml`). Put a copy in the app's own SOPS Secret (`secret.sops.yaml` plus a `ksops-*.yaml` generator). Host: `postgres.databases.svc.cluster.local`.
6. **Files:** a PVC on `nfs-zfs` (survives a worker loss; snapshotted; shipped offsite nightly). Databases never go on NFS.
7. **Backups:** if the app has data the database dump doesn't cover (an exporter, a search index you can't rebuild), add it to the nightly Job (`databases/backup.yaml`), then run `task dr:drill:k8s`.
8. **Route:** `myapp.lab.chetan-thapliyal.cloud` on the `https` listener. The wildcard certificate and DNS already cover it.
9. **Register:** copy `application.yaml` to `kubernetes/cluster/app-<app>.yaml`.
10. **After it's up:** add an outside check (task 4.20), a row in `docs/disaster-recovery/objectives.yml` if it holds data, and a restore drill before real data moves in.

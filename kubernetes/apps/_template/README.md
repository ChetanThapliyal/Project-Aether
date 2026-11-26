# New app checklist

Every app on the cluster has the same shape. Copy this folder to `kubernetes/apps/<group>/<app>/`, replace `myapp` (and `<group>` in `application.yaml`), then work through the list. Nothing here is deployed from `_template` itself.

1. **Image:** pin `tag@sha256:digest` for amd64. Renovate updates both.
2. **Run as non-root** with a read-only root filesystem. The namespace enforces Pod Security `restricted`, so a pod that isn't non-root, without privilege escalation, with all capabilities dropped and the `RuntimeDefault` seccomp profile is refused. A read-only root isn't part of `restricted`: if the image can't run with one, mount an emptyDir where it writes, or relax only that field and note why in a comment.
3. **Resources:** measure idle and busy memory, then set requests near idle and limits with headroom. The namespace quota is 2.5 GiB of requests and 6 GiB of limits for all apps together (`kubernetes/platform/guardrails/apps-namespace.yaml`).
4. **Egress:** set only the labels the app needs: `aether.dev/postgres`, `aether.dev/redis`, `aether.dev/internet`. Ingress from the gateway is already allowed.
5. **Database:** add the app's password to `kubernetes/platform/databases/secrets.sops.yaml` (`app-db-passwords`, key = app name; extensions in `bootstrap.yaml`). Put a copy in the app's own SOPS Secret (`secret.sops.yaml` plus a `ksops-*.yaml` generator). Host: `postgres.databases.svc.cluster.local`.
6. **Files:** a PVC on `nfs-zfs` (survives a worker loss; snapshotted; shipped offsite nightly). Databases never go on NFS.
7. **Backups:** if the app has data the database dump doesn't cover (an exporter, a search index you can't rebuild), add it to the nightly Job (`databases/backup.yaml`), then run `task dr:drill:k8s`.
8. **Route:** `myapp.lab.chetan-thapliyal.cloud` on the `https` listener. The wildcard certificate and DNS already cover it.
9. **Register:** copy `application.yaml` to `kubernetes/cluster/app-<app>.yaml`.
10. **After it's up:** add an outside check, a row in `docs/disaster-recovery/objectives.yml` if it holds data, and a restore drill before real data moves in.

# DR Scenario 05: GCP DMZ Node Loss & Zero-Cost Rebuild

**Severity:** SEV2 (my outside observer is blind; a SEV1 elsewhere could go unnoticed)
**Target RTO:** 15 minutes for the VM and stack; monitors need a manual rebuild on top
**Target RPO:** Uptime Kuma data is **not backed up**. Everything else is in Git.

---

## 1. Trigger & Symptoms

* **Alerts:**
  * OCI Uptime Kuma marks its probes of the DMZ DOWN: Glance on port 3000 and Uptime Kuma on 3001.
  * Dockhand on OCI shows the Hawser agent offline.
* **Symptoms:**
  * `tailscale ping aether-gcp-dmz` fails.
  * The GCP console shows the instance as `TERMINATED`, or it doesn't boot.

---

## 2. Blast Radius

| Component | Status | Impact |
|---|---|---|
| **Homelab K3s** | Up | Unaffected |
| **OCI applications** | Up | Unaffected. Backups still run, but their heartbeat has nowhere to go |
| **Outside monitoring** | Down | DMZ Kuma, the Glance status page and the Cloudflare tunnel (if enabled) |
| **Cost** | Must stay $0.00 | No public IPv4 on the rebuilt VM |

### What Lives Only on the VM

`/opt/dmz/uptime-kuma/` holds every DMZ monitor, its history, and the push token for "OCI Nightly Restic Backup". `/opt/dmz/.env` holds the Hawser and Cloudflare tunnel tokens. I can recreate the `.env` from SOPS and Cloudflare. **The Kuma database I can't recreate.** If the disk still works, I copy it off first:

```bash
gcloud compute ssh aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap \
  --command "sudo tar -C /opt/dmz -czf - uptime-kuma" > dmz-kuma-$(date +%F).tgz   # or over the tailnet: ssh owl@aether-gcp-dmz
```

---

## 3. Rebuild Procedure

### Step 3.1: Try the Cheap Fix First

```bash
gcloud compute instances reset aether-gcp-dmz --zone=us-central1-a
```

If the VM comes back, I skip to §4.

### Step 3.2: Replace the VM

The instance has `prevent_destroy = true`, so Terraform won't replace one that still exists. I delete it outside Terraform; Terraform then sees it's gone and creates a new one:

```bash
gcloud compute instances delete aether-gcp-dmz --zone=us-central1-a
task tf:init  DIR=02-gcp-dmz
task tf:plan  DIR=02-gcp-dmz     # expect: 1 instance to add, nothing to destroy
task tf:apply DIR=02-gcp-dmz
```

Before the new VM boots, I delete the old `aether-gcp-dmz` machine in the Tailscale console so the name stays the same. The startup script joins the tailnet with an auth key; if that key has expired, I follow [tailscale-auth-key-rotation.md](../../runbooks/tailscale-auth-key-rotation.md).

### Step 3.3: Check That It's Still Free

```bash
gcloud compute instances describe aether-gcp-dmz --zone=us-central1-a \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

The output must be empty: a private IPv4 plus an external IPv6, so no $3.65/month IPv4 charge.

### Step 3.4: Deploy the Stack

The compose and Glance files must be in Git. Until HARD-03 is done, `infrastructure/docker/gcp-dmz/glance/` exists only on my workstation, so a rebuild from a fresh clone fails.

```bash
task ansible:dmz
```

The playbook:
1. Adds a Docker drop-in that waits for `tailscaled`.
2. Creates a 2 GB swapfile (the e2-micro has 1 GB RAM).
3. Deploys Uptime Kuma (3001), Glance (3000) and Hawser (2376) on `dmz-net`, from images pinned by tag and digest. A fresh VM pulls them on first run (`pull: missing`; Docker Hub works over IPv6, and the GHCR-hosted Hawser image is copied over by the playbook).
4. Starts `cloudflared` only with the compose profile `tunnel` and a `CLOUDFLARE_TUNNEL_TOKEN`.
5. Provisions the Telegram notification channel in Kuma.

### Step 3.5: Restore or Rebuild the Monitors

* **I have a copy** from §2: stop Kuma, unpack the copy into `/opt/dmz/uptime-kuma/`, and start Kuma again.
* **I don't have a copy:** recreate the monitors by hand (the OCI probe targets, the homelab endpoints, and the "OCI Nightly Restic Backup" push monitor with a 24 h interval). The push monitor gets a **new token**, so then:
  ```bash
  sops infrastructure/secrets/ansible-secrets.sops.yaml     # update oci_backup_kuma_push_url
  task ansible:oci:ops -- --tags backup                     # re-render /opt/backup/restic.env
  ```
  If I skip this, every backup run withholds its heartbeat and the monitor stays red.

### Step 3.6: Check the Tailnet Policy

The new VM has a new tailnet IP. I check `tailscale-policy.sops.yaml` for any `hosts` entry pinned to the old DMZ IP, and check that the policy tests still pass. The DMZ must reach **only** its probe targets (INC-2026-003).

---

## 4. Post-Recovery Verification

1. `tailscale status | grep aether-gcp-dmz`: online, with the original name.
2. Containers:
   ```bash
   ssh owl@aether-gcp-dmz "sudo docker ps --format '{{.Names}}\t{{.Status}}'"
   ```
   I expect `uptime-kuma`, `glance`, `hawser`, and `cloudflared` once the public tunnel is on (FND-10). No `socket-proxy`: FND-08 removed it.
3. The public page leaks nothing from the tailnet (HARD-17):
   ```bash
   curl -s http://aether-gcp-dmz:3000 | grep -c tail7067ab   # → 0
   ```
4. Kuma can send alerts: use *Test* on the Telegram notification. If it hangs, the DMZ containers have no internet route out (INC-2026-004 / FND-08).
5. Both Kuma instances (OCI → DMZ, DMZ → OCI) are green again, and the next backup run turns the push monitor UP.
6. **Negative check** from the DMZ: admin tools on OCI (Dockhand, Grafana, Prometheus, Alertmanager) don't answer.

---

## 5. Simulation Drill (Re-convergence)

Without destroying the VM:

1. Back up the Kuma data as shown in §2.
2. `ssh owl@aether-gcp-dmz "cd /opt/dmz && sudo docker compose down"`
3. `task ansible:dmz` from a **fresh clone** of the repo. This also proves the deploy doesn't depend on untracked files.
4. Check that every container and monitor recovers, then run the §4 checks.
5. Record the date in the [DR README](../README.md#4-scenarios--drills).

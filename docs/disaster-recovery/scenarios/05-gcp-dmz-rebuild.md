# DR Scenario 05: GCP DMZ Node Loss & Zero-Cost Rebuild

**Severity:** SEV2 (my outside observer is blind; a SEV1 elsewhere could go unnoticed)
**Target RTO:** 15 minutes for the VM and stack; monitors need a manual rebuild on top. **Measured 19 Nov 2026: 48 min** (INC-2026-016): the first deploy on a fresh e2-micro alone takes 16 min.
**Target RPO:** Uptime Kuma data is **not backed up**. Everything else is in Git.

---

## 1. Trigger & Symptoms

* **Alerts:**
  * OCI Uptime Kuma marks its probes of the DMZ DOWN: Glance on port 3000 and Uptime Kuma on 3001.
  * OCI Prometheus fires `DMZNodeDown` (the DMZ node exporter stops answering).
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

`/opt/dmz/uptime-kuma/` holds every DMZ monitor, its history, and the push tokens other hosts report to (among them "OCI Nightly Restic Backup"). `/opt/dmz/.env` holds the Hawser and Cloudflare tunnel tokens, which I recreate from SOPS and Cloudflare. Kuma is copied every night at 01:30 UTC to `gs://gcs-oci-homelab-controlplane-dmz-backups/kuma/` (FND-17), so I lose at most a day of monitor history. If the disk still works, a fresh copy is better than last night's, so I take one first:

```bash
gcloud compute ssh owl@aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap --ssh-key-file ~/.ssh/homelab \
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

Before the new VM boots, I delete the old `aether-gcp-dmz` machine in the Tailscale console so the name stays the same. The startup script joins the tailnet with an OAuth client secret and asks for `tag:gcp-dmz`.

**If it doesn't appear on the tailnet within 5 minutes**, I read the serial console:

```bash
gcloud compute instances get-serial-port-output aether-gcp-dmz --zone=us-central1-a | grep -i -E "tailscale|startup-script" | tail
```

`requested tags [tag:gcp-dmz] are invalid or not permitted` means the tailnet policy no longer lets the enrollment client mint that tag on its own: `tag:gcp-dmz` must own itself in `tagOwners` (INC-2026-016, fixed 19 Nov). Until that is fixed, the quick way back in is a one-time auth key from the console (not reusable, 1 day, tag `tag:gcp-dmz`), used through IAP so it never lands in the shell history:

```bash
read -rs "KEY?Tailscale auth key: " && echo && \
gcloud compute ssh owl@aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap \
  --ssh-key-file ~/.ssh/homelab --strict-host-key-checking=no \
  --command "sudo tailscale up --authkey=$KEY --hostname=aether-gcp-dmz --advertise-tags=tag:gcp-dmz --ssh --accept-routes=true" ; unset KEY
```

Other key problems: [tailscale-auth-key-rotation.md](../../runbooks/tailscale-auth-key-rotation.md).

**Then I give the machine its old tailnet address back** (console: Machines → `aether-gcp-dmz` → Edit machine IPv4 → `100.115.221.103`), so anything still pointing at the address keeps working. Heartbeat senders use the tailnet name since INC-2026-016, but the address is cheap insurance. On my workstation: `ssh-keygen -R aether-gcp-dmz` (the host key is new).

### Step 3.3: Check That It's Still Free

```bash
gcloud compute instances describe aether-gcp-dmz --zone=us-central1-a \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

The output must be empty: a private IPv4 plus an external IPv6, so no $3.65/month IPv4 charge.

### Step 3.4: Deploy the Stack

```bash
task ansible:dmz
```

The playbook:
1. Adds a Docker drop-in that waits for `tailscaled`.
2. Creates a 2 GB swapfile (the e2-micro has 1 GB RAM).
3. Deploys Uptime Kuma (3001), Glance (3000) and the node exporter (9100, host network), from images pinned by tag and digest. A fresh VM pulls them on first run (`pull: missing`; every image is on Docker Hub, which works over IPv6). There is no Docker management agent on the DMZ since FND-22.
4. Starts `cloudflared` only with the compose profile `tunnel` and a `CLOUDFLARE_TUNNEL_TOKEN`.
5. Provisions the Telegram notification channel in Kuma.

### Step 3.5: Restore the Monitors

After `task ansible:dmz`, Kuma runs empty. (The deploy completes on an empty Kuma since INC-2026-016; before that, the status page's backup-age script crashed it at the last stage.) If I take a fresh copy from a still-working disk, I stop Kuma first: its SQLite database has a write-ahead log, and a copy of a running database can be inconsistent. I restore last night's backup, or the fresher copy from §2 if I took one. The VM can't read the bucket (its account is create-only), so the copy goes through my workstation:

```bash
obj=$(gcloud storage ls gs://gcs-oci-homelab-controlplane-dmz-backups/kuma/ | sort | tail -1); echo "$obj"
gcloud storage cp "$obj" kuma.tgz                 # or use dmz-kuma-<date>.tgz from §2
scp kuma.tgz owl@aether-gcp-dmz:/tmp/kuma.tgz
ssh owl@aether-gcp-dmz 'cd /opt/dmz && docker compose stop uptime-kuma \
  && sudo rm -rf uptime-kuma && sudo tar -xzf /tmp/kuma.tgz -C /opt/dmz && rm /tmp/kuma.tgz \
  && docker compose start uptime-kuma'
```

The push tokens come back with the database, so `oci_backup_kuma_push_url` and the Proxmox DR heartbeats keep working without changes. Then `sudo systemctl start kuma-backup.service` on the VM, and the OCI monitor "DMZ Kuma Backup" turns UP.

**If no backup exists at all**, I recreate the monitors by hand (the OCI probe targets, the homelab endpoints, and the "OCI Nightly Restic Backup" push monitor with a 24 h interval), and `task ansible:dmz` recreates the push monitors it owns. The hand-made push monitor gets a **new token**, so then:
```bash
sops infrastructure/secrets/ansible-secrets.sops.yaml     # update oci_backup_kuma_push_url
task ansible:oci:ops -- --tags backup                     # re-render /opt/backup/restic.env
```
If I skip this, every backup run withholds its heartbeat and the monitor stays red.

### Step 3.6: Check the Tailnet Policy

If I didn't restore the old address in §3.2, the new VM has a new tailnet IP. I search for the old one in the plain files **and in the decrypted secrets** (INC-2026-016 found it in `kuma_push_base`, which a plain-text search can't see), check `tailscale-policy.sops.yaml` for any `hosts` entry pinned to it, and check that the policy tests still pass. The DMZ must reach **only** its probe targets (INC-2026-003).

---

## 4. Post-Recovery Verification

1. `tailscale status | grep aether-gcp-dmz`: online, with the original name.
2. Containers:
   ```bash
   ssh owl@aether-gcp-dmz "sudo docker ps --format '{{.Names}}\t{{.Status}}'"
   ```
   I expect `uptime-kuma`, `glance`, `node-exporter` and `cloudflared`. No `socket-proxy` (FND-08) and no `hawser` (FND-22).
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

**Can a rebuilt VM still join the tailnet?** The re-convergence drill keeps the VM, so it never tests this (INC-2026-016). Quarterly, and after any change to the tailnet policy's `tagOwners` or to the enrollment OAuth client:

```bash
scripts/check-tailnet-join.sh dmz    # an ephemeral container logs in with the DMZ's secret and tag:gcp-dmz
```

It prints `OK` or the refusal, and leaves nothing behind.

# DR Scenario 02: OCI Instance Loss & Restic Restore

**Severity:** SEV1 (every OCI service is down; data at risk)
**Target RTO:** < 45 minutes
**Target RPO:** ≤ 24 hours (nightly restic run at 03:00 UTC / 08:30 IST, scheduled by the Kestra flow `aether.ops.restic-nightly`)

> **Scope:** This runbook assumes the instance is gone. If the OCI tenancy and its `dr-backups` bucket survive, restore from restic (Step 3.5). If the tenancy is gone too, restore last night's offsite copy from Backblaze B2 instead (Step 3.5b, since 20 Nov 2026, task 5.61); [Scenario 06](06-account-and-workstation-loss.md) covers replacing the tenancy itself.

---

## 1. Trigger & Symptoms

* **Alerts:**
  * DMZ Uptime Kuma marks every OCI monitor DOWN.
  * The push monitor "OCI Nightly Restic Backup" goes DOWN when no heartbeat has arrived within 24 h of the last successful run.
* **Symptoms:**
  * `ssh bookorbit` (tailnet) and SSH to the public IPv4 both fail.
  * The OCI console shows the instance as `Terminated`, or stuck in `Stopped`.

---

## 2. Blast Radius

| Component | Status | Impact |
|---|---|---|
| **OCI workloads** | Down | Kestra, n8n, Affine, Blinko, BookOrbit, Anytype, Uptime Kuma (OCI), Prometheus, Grafana, Loki and the rest |
| **Nightly backups** | Stopped | Kestra is the only scheduler, and it runs on this host |
| **Homelab K3s** | Up | Cross-cloud scraping and log shipping pause |
| **GCP DMZ** | Up | Keeps alerting |
| **Backup data** | Safe, if the tenancy survives | Last snapshot in `dr-backups`. `calibre-library/` and `navidrome/` were never backed up, so I re-source that media |

---

## 3. Restore Procedure

All commands run from my workstation at the repo root unless a step says otherwise.

### Step 3.1: Choose the Fastest Path

If the boot volume backup `bookorbit-pre-upgrade` is recent enough to be useful, I can create the instance from it in the OCI console and skip to Step 3.6 to bring the data up to date. Otherwise I rebuild from Terraform.

### Step 3.2: Re-provision the Instance

Public SSH is closed in the security list (FND-04), and a new instance isn't on the tailnet yet. So I open TCP 22 to my own address for this one run, with a variable that defaults to off:

```bash
task tf:init  DIR=01-oci-compute
MYIP=$(curl -s4 https://api.ipify.org); echo "$MYIP"
export TF_VAR_bootstrap_ssh_cidr="$MYIP/32"
task tf:plan  DIR=01-oci-compute     # expect the instance (and anything attached to it) to be created, plus the SSH rule
task tf:apply DIR=01-oci-compute
IP=$(terraform -chdir=infrastructure/terraform/01-oci-compute output -raw bookorbit_public_ip); echo "$IP"
```

### Step 3.3: Rejoin the Tailnet

Ansible's inventory reaches `bookorbit` through `~/.ssh/config`, which points at the tailnet name `bookorbit-net.tail7067ab.ts.net`. Until the new instance is on the tailnet, I use the public IP. The base playbook installs Tailscale and joins the node (FND-18), so nothing is typed on the host.

1. In the Tailscale admin console I delete the old `bookorbit-net` machine, plus the old tsdproxy service nodes. That way the new nodes keep their names, rather than becoming `*-1`.
2. In the console I create a new auth key: **pre-authorised, not reusable, tag `tag:oci` only**. A key that was used once, or has passed its 90 days, can't be used again, so I make a fresh one for every rebuild. I store it, without pasting it anywhere else:
   ```bash
   sops infrastructure/secrets/ansible-secrets.sops.yaml     # set oci_host_tailscale_auth_key
   ```
   If the key can't be created or has expired, I follow [tailscale-auth-key-rotation.md](../../runbooks/tailscale-auth-key-rotation.md).
3. First run over the public IP. The play installs Tailscale, joins as `bookorbit-net` and then carries on with the base setup:
   ```bash
   task ansible:oci:base -- -e ansible_host="$IP" -e ansible_ssh_private_key_file=~/.ssh/oci_bookorbit
   ```
4. From now on the host answers on the tailnet. `ssh bookorbit true` confirms it. I close the temporary rule:
   ```bash
   unset TF_VAR_bootstrap_ssh_cidr
   task tf:plan  DIR=01-oci-compute     # expect one in-place change: the SSH rule goes
   task tf:apply DIR=01-oci-compute
   ```
5. The new node has a new tailnet IP. In `tailscale-policy.sops.yaml` I update every `hosts` entry pinned to the old OCI IPs (FND-01 §8), then paste the policy into the console. I check that the policy tests pass.

The host joins with `tag:oci` only. A hand-joined host may carry extra tags, and the live one carries `tag:funnel` and `tag:oci-probe`. Neither is needed on the host: the DMZ's probes go to the tsdproxy service nodes, and Funnel is being closed.

### Step 3.4: Base System, Then Backup Credentials

The backup credentials file `/opt/backup/restic.env` is written by the `backup` tag of the ops playbook, not by the base playbook. So I run both before restoring:

```bash
task ansible:oci:base
task ansible:oci:ops -- --tags backup     # /opt/backup/restic.env + run-backup.sh
```

### Step 3.5: Restore the Data from Restic

On `bookorbit`:

```bash
sudo bash -c 'source /opt/backup/restic.env && restic snapshots --latest 3'
sudo bash -c 'source /opt/backup/restic.env && restic restore latest --target /'   # paths in the snapshot are absolute (/home/ubuntu/...)
sudo chown -R ubuntu:ubuntu /home/ubuntu
sudo chown -R 1000:1000 /home/ubuntu/n8n/data && sudo chmod 755 /home/ubuntu/n8n/data   # SEC-03 UID mapping
```

> If `restic snapshots` fails, I **must not** run `run-backup.sh`. It runs `restic init` when it can't read the repo config, so with a wrong endpoint or empty bucket it would quietly start a new, empty repository.

### Step 3.5b: If the Whole Tenancy Is Gone: Restore from Backblaze B2

Every night, after the restic run, `run-backup.sh` copies the newest snapshot to the Object Lock bucket as one file: `oci/<YYYY-MM-DD>.tar.zst.age` (tar, zstd, then age to the DR recipient; locked 30 days; heartbeat "OCI-02 OCI backup → B2" in DMZ Kuma). The cloud host can only write it. Reading needs the restore key and the DR identity, which are only in SOPS:

```bash
# From my workstation, at the repo root. rclone v1.75.2 (Debian's older rclone can't use these keys).
V=infrastructure/ansible/group_vars/proxmox/vault.yaml
export RCLONE_B2_ACCOUNT=$(sops -d --extract '["b2_offsite_restore_key_id"]' $V)
export RCLONE_B2_KEY=$(sops -d --extract '["b2_offsite_restore_key"]' $V)
rclone lsl :b2:aether-etcd-offsite-lock/oci/ | sort -k2 | tail -3     # newest night; ignore "-v<timestamp>" duplicates
ID=$(mktemp); chmod 600 "$ID"
sops -d --extract '["dr_offsite_age_identity"]' infrastructure/secrets/ansible-secrets.sops.yaml > "$ID"
rclone cat :b2:aether-etcd-offsite-lock/oci/<date>.tar.zst.age | age -d -i "$ID" | zstd -dc \
  | ssh ubuntu@<new host> 'sudo tar -x -C /'      # paths are home/ubuntu/...
rm -f "$ID"
```
Then the same ownership fixes as Step 3.5 (`chown -R ubuntu:ubuntu /home/ubuntu`, the n8n UID mapping), and continue with Step 3.6. The copy holds everything the restic snapshot does, including the database dumps of Step 3.7.

Checked 20 Nov 2026 on the first copy: 1.9 GiB downloaded, decrypted and listed in 12.5 minutes: 21,290 entries, 3.84 GiB, with `bookorbit/db.sql`, `kestra/db.sql`, `anytype/mongo.archive` and Grafana's database present. Not yet unpacked onto a host.

### Step 3.6: Redeploy the Stacks

```bash
task ansible:oci:apps
task ansible:oci:monitoring
task ansible:oci:ops          # Telegram channel on OCI Kuma; weekly prune; removes any legacy cron
```

### Step 3.7: Load the Database Dumps

The restored Postgres data directories were copied while the databases were running, so they may not be consistent. Kestra's raw directory is excluded on purpose. The nightly dumps are the consistent copies. For each database, I stop the app container (but not its database container), load the dump, and start the app again.

**Kestra** (required: its data directory isn't in the backup):

```bash
docker stop kestra
docker exec kestra-postgres psql -U kestra -d postgres -c 'DROP DATABASE IF EXISTS kestra;'
docker exec kestra-postgres psql -U kestra -d postgres -c 'CREATE DATABASE kestra OWNER kestra;'
docker exec -i kestra-postgres psql -U kestra -d kestra < /home/ubuntu/kestra/db.sql
docker start kestra
```

**Blinko, BookOrbit, Affine** (only if the app fails to start or its data looks wrong):

```bash
# restore_pg <db container> <user> <database> <dump file>
restore_pg() {
  docker exec "$1" psql -U "$2" -d template1 -c "DROP DATABASE IF EXISTS \"$3\" WITH (FORCE);"
  docker exec "$1" psql -U "$2" -d template1 -c "CREATE DATABASE \"$3\" OWNER \"$2\";"
  docker exec -i "$1" psql -U "$2" -d "$3" < "$4"
}
restore_pg blinko-postgres postgres  postgres  /home/ubuntu/blinko/db.sql
restore_pg bookorbit-db    bookorbit bookorbit /home/ubuntu/bookorbit/db.sql
restore_pg affine-postgres affine    affine    /home/ubuntu/affine/db.sql
```

**Anytype** (the coordinator's MongoDB; the sync-node and Garage data are plain files restored in Step 3.5):

```bash
docker exec -i anytype-mongo-1-1 mongorestore --port 27001 --archive --drop < /home/ubuntu/anytype/mongo.archive
```

Then I open `https://kestra.tail7067ab.ts.net/` and check that the flows and execution history are there. The flows also re-sync from Git through `system/git-sync-flows`.

### Step 3.8: Fix tsdproxy Node Tags

When tsdproxy service nodes are recreated, their tags reset (INC-2026-003, M11), and the DMZ can't see untagged nodes. Until FND-03 makes tsdproxy set the tags itself, I re-apply the probe tags in the console. Then I check from the DMZ that only the probe targets answer, and nothing else (the negative check from INC-2026-003).

---

## 4. Post-Recovery Verification

1. `ssh bookorbit "docker ps --format '{{.Names}}\t{{.Status}}'"`: everything is `Up` or `healthy`.
2. `tailscale status | grep -E 'bookorbit|kestra|uptimekuma'`: the nodes are online under their old names.
3. DMZ Uptime Kuma: every OCI monitor is green.
4. Run one backup **through Kestra** (UI → `aether.ops.restic-nightly` → *Execute*). It must finish with a new snapshot and a clean `restic check`, and "OCI Nightly Restic Backup" in DMZ Kuma must turn UP.

---

## 5. Simulation Drill (Single-App Restore)

Without touching running services:

```bash
task dr:drill:oci
```

[`scripts/dr-drill-oci.sh`](../../../scripts/dr-drill-oci.sh) runs on the OCI host as root and:

1. Runs `restic check` reading 5% of the data.
2. Restores BookOrbit's directory and OCI Uptime Kuma's data from the latest snapshot into `/var/tmp/dr-drill`.
3. Starts a throwaway Postgres from BookOrbit's exact image, with no network, loads the restored nightly dump into it, and compares the tables and row counts with the live database. The live side is a read-only count. Rows can differ by what changed since the snapshot, and the drill prints those tables.
4. Runs `PRAGMA integrity_check` on the restored Kuma database.

Everything is removed on exit, including on failure. The last line reads `DRILL OK …` with the timings. I don't run it near the 03:00 UTC backup.

**Last result (15 Nov 2026):** snapshot `71315ec6` from 03:00 UTC. Check took 5 s, 988 MB restored in 11 s, database ready in 8 s, dump loaded in 4 s, 176 tables and 39,599 rows matched live, Kuma integrity ok. Total 29 s. This proves the data path. The full instance rebuild (Steps 3.2 to 3.8) hasn't been timed.

**Heartbeat negative test** (from INC-2026-001; run it after any change to `backup.sh.j2`): break one `pg_dump` on purpose, run the backup, and check that it prints `heartbeat withheld` and exits 1. Then revert, and check that a clean run turns the push monitor UP.

I record the date in the [DR README](../README.md#4-scenarios--drills).

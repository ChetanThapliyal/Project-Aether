# DR Scenario 01: Tailscale Control Plane & DERP Outage

**Severity:** SEV3 (management access degraded; no data at risk)
**Target RTO:** < 10 minutes to be working over break-glass routes
**Target RPO:** 0 (no data loss)

---

## 1. Trigger & Symptoms

* **Alerts:** DMZ Uptime Kuma marks the OCI and homelab monitors DOWN, because it probes them over the tailnet. Telegram delivery from the DMZ depends on INC-2026-004 being fixed, so the OCI Uptime Kuma alerts may reach me first.
* **What I see on the CLI:**
  * `ssh bookorbit`, `ssh homelab` or `ssh k3s-control-01` time out when I'm off the home LAN.
  * `tailscale status` reports that the coordination server is unreachable, or hangs.
  * Services behind tsdproxy (`https://<service>.tail7067ab.ts.net`) don't load.

Connections that are already up often keep working through a control-plane outage. New connections and DERP-relayed paths fail first.

---

## 2. Blast Radius

| Component | Status | Impact |
|---|---|---|
| **Homelab K3s cluster** | Up | The pods and etcd talk over the LAN (`192.168.1.0/24`) |
| **OCI applications** | Up | The containers keep running. Only access through tsdproxy is gone |
| **GCP DMZ** | Up, but blind | Kuma can't reach its tailnet probe targets |
| **Cross-cloud telemetry** | Degraded | OCI Prometheus can't scrape the homelab. Alloy can't push to Loki, which is on a tailnet IP |
| **My remote access** | Blocked over the tailnet | Use the break-glass routes below |

---

## 3. Break-Glass Access

### Step 3.1: Homelab (from the home LAN)

```bash
ssh -i ~/.ssh/homelab root@192.168.1.200     # Proxmox host (web UI: https://192.168.1.200:8006)
ssh -i ~/.ssh/homelab owl@192.168.1.51       # k3s-control-01
ssh -i ~/.ssh/homelab owl@192.168.1.51 "kubectl get nodes -o wide"
```

My `~/.ssh/config` already maps `homelab` and `k3s-*` to these LAN addresses, so the short names also work from home.

### Step 3.2: OCI (`bookorbit`) over its public IPv4

```bash
IP=$(terraform -chdir=infrastructure/terraform/01-oci-compute output -raw bookorbit_public_ip)
ssh -i ~/.ssh/oci_bookorbit ubuntu@"$IP"
docker ps --format "table {{.Names}}\t{{.Status}}"
```

If I've closed public port 22 (FND-04 option A), I first re-add the ingress rule (TCP 22) in the OCI console under *Networking → VCN `dockerTailscale` → Security Lists*, and remove it again afterwards.

To reach a web UI, I use an SSH tunnel:

```bash
ssh -i ~/.ssh/oci_bookorbit -L 5678:localhost:5678 ubuntu@"$IP"   # n8n → http://localhost:5678
```

### Step 3.3: GCP DMZ

```bash
gcloud compute ssh aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap
```

This only works after FND-12 adds the IAP firewall rule. Until then I have no way into the DMZ without the tailnet. That's acceptable, because the DMZ holds no data I need during a tailnet outage.

---

## 4. Post-Recovery Verification

Once Tailscale has recovered:

1. On my workstation and on each node: `tailscale status` and `tailscale netcheck`.
2. Check peers: `tailscale ping bookorbit-net`, `tailscale ping aether-gcp-dmz`, `tailscale ping homelab`.
3. DMZ Uptime Kuma monitors are green again.
4. Prometheus targets are healthy again (the API reports `"health":"up"`):
   ```bash
   ssh bookorbit "curl -s localhost:9090/api/v1/targets" \
     | jq -r '.data.activeTargets[] | "\(.health)\t\(.scrapeUrl)"' | sort | uniq -c
   ```
   If Prometheus isn't published on the host's port 9090, I open the same `/api/v1/targets` URL through `https://prometheus.tail7067ab.ts.net`.
5. Logs in Loki resume. Alloy retries a failed push for several minutes, so a short outage leaves no gap. After a longer one, lines it gave up on are missing.

---

## 5. Simulation Drill

During a maintenance window, from my workstation on the home LAN:

1. `sudo tailscale down`
2. SSH to `192.168.1.200` and `192.168.1.51` over the LAN.
3. SSH to OCI over its public IPv4, and open one service through an SSH tunnel.
4. *(After FND-12)* `gcloud compute ssh aether-gcp-dmz --zone=us-central1-a --tunnel-through-iap --command hostname`
5. `sudo tailscale up && tailscale status`
6. Record the date in the [DR README](../README.md#4-scenarios--drills).

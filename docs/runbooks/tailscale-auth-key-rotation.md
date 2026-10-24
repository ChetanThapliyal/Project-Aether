# Tailscale auth key management and OAuth client runbook

> **Scope:** Standard operating procedure for managing and rotating Tailscale authentication keys in Project Aether (GCP DMZ and homelab).
> **Status:** Operational runbook (OPS-06)
> **Reference documentation:** [Tailscale OAuth Clients](https://tailscale.com/docs/features/oauth-clients)
> **Target environments:** GCP DMZ (`02-gcp-dmz`), Homelab K3s nodes (`03-homelab`)

## 1. Overview and architectural context

In Project Aether, Tailscale connects compute nodes across GCP, OCI, and the Proxmox homelab into an encrypted overlay network ([ADR-013](../adr/013-tailnet-microsegmentation.md)).

Automated node enrollment relies on auth keys passed during bootstrap:
- GCP DMZ: Injected via Compute Engine startup script ([`startup.sh.tftpl`](../../infrastructure/terraform/02-gcp-dmz/templates/startup.sh.tftpl)) from `02-gcp-dmz/terraform.sops.tfvars`.
- Homelab K3s nodes: Injected via Ansible playbook ([`common.yml`](../../infrastructure/ansible/playbooks/common.yml)) from `infrastructure/secrets/ansible-secrets.sops.yaml`.

### Limitations of pre-auth keys (`tskey-auth-...`)

Standard Tailscale pre-auth keys expire after 90 days.

> [!IMPORTANT]
> Key expiry does not affect active nodes. Connected machines store long-lived WireGuard machine keys in `/var/lib/tailscale/tailscaled.state` and remain on the tailnet. However, if a node is rebuilt or reprovisioned during disaster recovery, the bootstrap script fails because an expired key cannot register new machines.

## 2. Where keys are stored in the repository

| Component | Storage path | Format / Variable | Encryption |
| --- | --- | --- | --- |
| GCP DMZ | `infrastructure/terraform/02-gcp-dmz/terraform.sops.tfvars` | `tailscale_auth_key = "..."` | SOPS (GCP KMS + Age) |
| Ansible (K3s) | `infrastructure/secrets/ansible-secrets.sops.yaml` | `tailscale_auth_key: "..."` | SOPS (GCP KMS + Age) |

## 3. How Tailscale OAuth clients work

Tailscale OAuth clients implement the OAuth 2.0 Client Credentials Grant flow ([RFC 6749 §4.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4)) to give automated systems long-term access to the tailnet without relying on interactive user sessions.

### Client properties

An OAuth client uses a client ID (`k...`) and a secret (`tskey-client-...`). The secret stays valid until manually revoked.

Because OAuth clients belong to the tailnet itself, changes to individual admin accounts or SSO logins do not disrupt node enrollment.

Node enrollment and key generation require only the `auth_keys` write scope.

Devices registered through an OAuth client are tag-owned. The client needs permission for each tag it assigns (`tag:gcp-dmz`, `tag:k3s`, and `tag:oci`).

## 4. Method A: Direct node registration via OAuth secret

Tailscale CLI 1.54 and later accepts an OAuth client secret directly through the `--auth-key` flag. The client authenticates with the coordination server and registers the machine.

### Step 1: Create the OAuth client in the Tailscale console

1. In the Tailscale admin console, go to **Settings > OAuth clients** (or **Trust credentials**).
2. Click **Generate credential > OAuth**.
3. Configure the client:
   - Description: `Project Aether Node Enrollment`
   - Scopes: Select `auth_keys` with write permission.
   - Tags: Select the tags used by Project Aether nodes:
     - `tag:gcp-dmz`
     - `tag:k3s`
     - `tag:oci`
4. Click **Generate credential**.
5. Save the client ID and client secret:
   ```text
   Client ID:     <your-client-id>
   Client Secret: tskey-client-<your-client-id>-<secret>
   ```

> [!CAUTION]
> Tailscale registers machines as ephemeral by default when authenticated directly with an OAuth secret. If an ephemeral node disconnects or reboots, Tailscale removes it from the tailnet.
> For persistent nodes, append `?ephemeral=false&preauthorized=true` to the secret string:
> ```text
> tskey-client-<your-client-id>-<secret>?ephemeral=false&preauthorized=true
> ```

### Step 2: Update secrets in SOPS

Store the full key string with its parameters in SOPS for each environment:

**GCP DMZ Terraform variables:**
```bash
sops infrastructure/terraform/02-gcp-dmz/terraform.sops.tfvars
```
Update `tailscale_auth_key`:
```hcl
tailscale_auth_key = "tskey-client-<your-client-id>-<secret>?ephemeral=false&preauthorized=true"
```

**Homelab Ansible secrets:**
```bash
sops infrastructure/secrets/ansible-secrets.sops.yaml
```
Update `tailscale_auth_key`:
```yaml
tailscale_auth_key: "tskey-client-<your-client-id>-<secret>?ephemeral=false&preauthorized=true"
```

### Step 3: Confirm tag flags on node enrollment

Nodes authenticating with an OAuth client must advertise a tag permitted on that client:

```bash
# GCP DMZ (configured in startup script templates/startup.sh.tftpl):
tailscale up --auth-key="tskey-client-...?... " --advertise-tags=tag:gcp-dmz --hostname=aether-gcp-dmz --accept-routes=true

# Homelab K3s nodes (configured in Ansible playbooks/common.yml):
tailscale up --authkey="{{ tailscale_auth_key }}" --advertise-tags=tag:k3s --accept-routes=true
```

## 5. Method B: Dynamic key generation via API

To generate short-lived pre-auth keys (`tskey-auth-...`) dynamically in CI/CD or automation scripts, use the Tailscale OAuth API.

### Step 1: Request an access token

The token endpoint returns an access token valid for one hour (3600 seconds):

```bash
# Request short-lived Bearer access token
export TS_CLIENT_ID="<your-client-id>"
export TS_CLIENT_SECRET="tskey-client-<your-client-id>-<secret>"

ACCESS_TOKEN=$(curl -s -d "client_id=${TS_CLIENT_ID}" \
  -d "client_secret=${TS_CLIENT_SECRET}" \
  "https://api.tailscale.com/api/v2/oauth/token" | jq -r .access_token)
```

### Step 2: Generate a pre-auth key

Use `-` as the tailnet identifier to target the default tailnet (`/api/v2/tailnet/-/keys`):

```bash
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "devices": {
        "create": {
          "reusable": true,
          "ephemeral": false,
          "preauthorized": true,
          "tags": ["tag:gcp-dmz"]
        }
      }
    },
    "expirySeconds": 7776000
  }' \
  "https://api.tailscale.com/api/v2/tailnet/-/keys" | jq -r .key
```

### Alternative: Generate keys with the `get-authkey` utility

Tailscale provides a Go CLI utility to generate keys directly:

```bash
export TS_API_CLIENT_ID="<your-client-id>"
export TS_API_CLIENT_SECRET="tskey-client-<your-client-id>-<secret>"

# Generates a reusable, pre-authorized key tagged for GCP DMZ:
go run tailscale.com/cmd/get-authkey@latest -reusable -preauth -tags tag:gcp-dmz
```

## 6. Method C: Manual 90-day pre-auth key rotation

If you generate standard 90-day pre-auth keys manually:

### Step 1: Generate key in admin console

1. In the Tailscale admin console, go to **Settings > Keys**.
2. Click **Generate auth key**.
3. Configure the key:
   - Reusable: Yes
   - Expiration: 90 days
   - Ephemeral: No
   - Tags: Select the target tag (`tag:gcp-dmz` or `tag:k3s`).
4. Copy the key (`tskey-auth-...`).

### Step 2: Update secrets in SOPS

```bash
sops infrastructure/terraform/02-gcp-dmz/terraform.sops.tfvars
# Update tailscale_auth_key = "tskey-auth-..."

sops infrastructure/secrets/ansible-secrets.sops.yaml
# Update tailscale_auth_key: "tskey-auth-..."
```

### Step 3: Verify and apply

- GCP DMZ: Run `task tf:plan DIR=02-gcp-dmz`. The running instance shows no pending changes because of `ignore_changes = [metadata_startup_script]`.
- Homelab K3s: Run `task ansible:common` to supply the new key to future node provisioning.

## 7. Verification and health checks

### On the host

```bash
# 1. Check Tailscale mesh status
tailscale status

# Expected output shows node name, Tailscale IPv4/IPv6, and online peers:
# 100.x.y.z   aether-gcp-dmz       chetan-thapliyal@ linux   -
# 100.x.y.w   k3s-control-01       chetan-thapliyal@ linux   -

# 2. Check latency and DERP relay connectivity
tailscale netcheck
```

### In the Tailscale admin console

1. Open **Machines**.
2. Verify that the node shows as connected.
3. Confirm machine tags match ACL definitions (`tag:gcp-dmz`, `tag:k3s`, `tag:oci`).
4. In the machine details, verify that key expiry is disabled.

## 8. Revocation and secret lifecycle

If an OAuth client secret is compromised, open **Settings > OAuth clients**, locate the client, and click **Revoke**. All access tokens issued by that client expire immediately.

Revoking an OAuth client or letting a pre-auth key expire does not disconnect running machines. Tailscale nodes only use auth keys during initial enrollment. Once enrolled, nodes communicate using their local WireGuard machine key.

Tailscale sends reminder emails 14 days and 7 days before pre-auth keys expire. An Uptime Kuma monitor also alerts to Telegram on expiration ([OPS-02](monitoring-setup.md)).

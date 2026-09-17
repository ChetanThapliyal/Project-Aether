# ADR 006 - Proxmox VM Provisioning Strategy

| Field        | Value                    |
| ------------ | ------------------------ |
| **Status**   | Accepted                 |
| **Date**     | 2026-05-09               |
| **Deciders** | Chetan Thapliyal         |
| **Area**     | Infrastructure / Proxmox |

---

## Context

The homelab runs on a single Proxmox VE node. As the infrastructure grows - Kubernetes cluster nodes, utility VMs, dev environments - a consistent, repeatable approach to VM provisioning is required.

The key question: **how do we go from "bare Proxmox" to "running, configured VM" with the least friction and the most consistency?**

Several approaches exist, each with different trade-offs.

---

## Decision Drivers

- **Repeatability** - provisioning a new VM should produce the same result every time
- **Speed** - spinning up a new node should take minutes, not the length of a manual install
- **GitOps compatibility** - the process should be automatable via Terraform and trackable in Git
- **Simplicity** - avoid tooling that adds complexity without proportional value at homelab scale
- **Secrets hygiene** - SSH keys and credentials must never be hardcoded or committed in plaintext

---

## Options Considered

### Option 1 - Manual Installation (ISO)

Boot each VM from an Ubuntu ISO and run through the installer manually.

**Pros:**

- No tooling knowledge required
- Works offline

**Cons:**

- Not repeatable - every VM is a snowflake
- Slow (~10–15 minutes per VM)
- No automation path
- Human error in configuration

**Verdict:** Rejected. Incompatible with GitOps and does not scale beyond a handful of VMs.

---

### Option 2 - Packer + Custom Image Build

Use HashiCorp Packer to build a fully customised golden image from an ISO, baking in all packages, users, and config at build time.

**Pros:**

- Maximum control over the base image
- Image is fully pre-configured before deployment
- Industry-standard for production environments

**Cons:**

- Significant complexity for homelab scale
- Packer requires a build pipeline and careful maintenance
- Image rebuilds needed for every OS/package update
- Slower iteration cycle

**Verdict:** Rejected for now. The added complexity is not justified at single-node homelab scale. Revisit if the lab grows to multi-node Proxmox clusters or a need for air-gapped provisioning arises.

---

### Option 3 - Cloud-Init Template (Chosen)

Download Ubuntu's official cloud image, import it into Proxmox as a VM template, and use Cloud-Init to inject per-VM configuration (hostname, SSH keys, network) at first boot. Clones of the template are provisioned via Terraform.

**Pros:**

- Ubuntu cloud images are maintained, minimal, and security-patched by Canonical
- Cloud-Init is a mature, widely-adopted standard - behaviour is well-documented
- Cloning a template is near-instant (thin provisioning via LVM)
- Per-VM config is injected declaratively - no interactive steps
- Integrates directly with Terraform (`proxmox_vm_qemu` resource)
- Aligns with how cloud providers (GCP, AWS, Azure) provision VMs - skills transfer

**Cons:**

- First boot has a ~30 second Cloud-Init initialisation delay
- Template must be manually updated when a new Ubuntu point release is preferred
- Less control over baked-in packages vs. Packer (mitigated by Ansible post-provisioning)

**Verdict:** Accepted.

---

## Decision

Use **Ubuntu 24.04 LTS cloud images + Proxmox Cloud-Init templates** as the standard VM provisioning strategy.

The provisioning stack is:

```
Ubuntu Cloud Image (Canonical)
        ↓
Proxmox Template (VM 9000)        ← created once, maintained
        ↓
qm clone / Terraform              ← per-VM provisioning
        ↓
Cloud-Init                        ← per-VM configuration injection
        ↓
Ansible                           ← post-boot configuration management
```

---

## Implementation

Template VM ID `9000` is the single source of truth for the base image. It is:

- Built from the official `noble-server-cloudimg-amd64.img`
- Configured with virtio-scsi storage controller and virtio network driver for performance
- Equipped with a serial console (`serial0`) for headless web UI access
- Frozen as a Proxmox template - cannot be started, only cloned

See `docs/runbooks/proxmox-ubuntu-cloudinit-template.md` for the full build procedure.

### Secrets handling

SSH public keys injected via Cloud-Init are stored in the repository encrypted with SOPS + age (see ADR to be written: secrets management strategy). The age public key is registered in `.sops.yaml` at the repo root.

### Template lifecycle

| Trigger                        | Action                                                                   |
| ------------------------------ | ------------------------------------------------------------------------ |
| New Ubuntu 24.04 point release | Re-download cloud image, rebuild template, delete old VM 9000, re-create |
| Ubuntu 26.04 LTS available     | Create new template (VM 9001), migrate new VMs, deprecate 9000           |
| Critical CVE in base image     | Treat same as point release - rebuild template                           |

Existing running VMs are **not** automatically affected by a template rebuild - they are independent clones. Updates to running VMs are handled by Ansible or standard `apt upgrade`.

---

## Consequences

**Positive:**

- All VMs are traceable to a known base image
- Provisioning new Kubernetes nodes takes ~2 minutes end-to-end
- The entire provisioning process is codified in Terraform and auditable in Git
- Consistent with cloud-native practices - reduces cognitive overhead when working across homelab and cloud

**Negative / Watch points:**

- Template maintenance is a manual step - no automated rebuild pipeline yet
- Cloud-Init config surface is limited; complex post-boot configuration still requires Ansible
- Single Proxmox node means no HA for the template itself (acceptable at current scale)

---

## Related

- `docs/runbooks/proxmox-ubuntu-cloudinit-template.md` - step-by-step build procedure
- `docs/adr/005-mono-repo-structure.md` - repository layout rationale
- `infrastructure/terraform/` - Terraform resources for VM provisioning
- `.sops.yaml` - encryption policy for secrets committed to this repo

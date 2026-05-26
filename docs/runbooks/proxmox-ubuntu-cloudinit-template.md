# Proxmox Cloud-Init Template Setup

> **Scope:** Creating a reusable Ubuntu 24.04 VM template on Proxmox VE using Cloud-Init for automated, repeatable VM provisioning.
> **VM ID:** 9000 (convention: high IDs reserved for templates)
> **Base Image:** Ubuntu 24.04 LTS "Noble Numbat" - official cloud image

---

## Overview

Rather than installing Ubuntu manually for every new VM, we create a single **golden template** once. Every future VM is a clone of this template - inheriting a clean, pre-installed Ubuntu 24.04 base - with per-VM configuration (hostname, SSH keys, IP address) injected automatically at first boot via **Cloud-Init**.

This approach gives us:

- **Consistency** - every VM starts from the same known-good base
- **Speed** - clone + boot in under a minute vs. a 10-minute manual install
- **Automation-readiness** - plugs directly into Terraform, Ansible, and GitOps workflows

---

## Prerequisites

- Proxmox VE installed and accessible
- Storage pool available: `local-lvm`
- Network bridge configured: `vmbr0`
- Internet access from the Proxmox host (or the image transferred manually)

---

## Step 1 - Download the Ubuntu 24.04 Cloud Image

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

### Why this image?

Ubuntu publishes **cloud images** - minimal, pre-installed disk images specifically designed for virtual machines and cloud environments. These are different from ISO installers:

|                       | Cloud Image               | ISO Installer                |
| --------------------- | ------------------------- | ---------------------------- |
| Format                | `.img` (qcow2 internally) | `.iso` bootable installer    |
| Size                  | ~600 MB                   | ~1.5 GB                      |
| Installation required | No - already installed    | Yes - interactive or preseed |
| Cloud-Init support    | Built-in                  | Requires manual setup        |
| Use case              | Templates, automation     | One-off installs             |

The image is **sparse** - the `.img` file is ~600 MB on disk but represents a 3.5 GiB virtual disk with mostly empty space pre-allocated for the OS.

> **"Noble"** is the Ubuntu codename for 24.04 LTS. The `current/` path always points to the latest build of that release.

### DNS Note

On a fresh Proxmox host with Tailscale installed, `resolv.conf` is managed by Tailscale's MagicDNS (`100.100.100.100`). If public DNS resolution fails, temporarily override it:

```bash
echo "nameserver 8.8.8.8" > /etc/resolv.conf
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
# Restore resolv.conf afterwards
```

The permanent fix is adding a global fallback nameserver (e.g. Google Public DNS) in the Tailscale admin console under **DNS → Global nameservers**, with **Override DNS servers** enabled.

---

## Step 2 - Create the VM Shell

```bash
qm create 9000 \
  --name "ubuntu-2404-cloudinit" \
  --memory 2048 \
  --cores 2 \
  --net0 virtio,bridge=vmbr0
```

### What this does

Creates an empty VM with ID `9000` - no disk attached yet, just the configuration skeleton.

| Parameter       | Value           | Reason                                                                                                                                               |
| --------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `9000`          | VM ID           | High number by convention - keeps templates visually separated from real VMs (typically 100–899)                                                     |
| `--memory 2048` | 2 GB RAM        | Baseline for the template; clones can override this                                                                                                  |
| `--cores 2`     | 2 vCPUs         | Baseline; clones can override                                                                                                                        |
| `--net0 virtio` | Network adapter | `virtio` is a paravirtualized driver - significantly faster than emulated e1000/rtl8139 because the guest OS cooperates directly with the hypervisor |
| `bridge=vmbr0`  | Network bridge  | Proxmox's default Linux bridge; connects VMs to the physical network                                                                                 |

---

## Step 3 - Import the Disk into Proxmox Storage

```bash
qm importdisk 9000 noble-server-cloudimg-amd64.img local-lvm
```

### What this does

Converts the `.img` file and writes it into Proxmox's LVM storage as a proper LVM logical volume named `vm-9000-disk-0`. The original `.img` file is no longer needed after this step.

**Why LVM?** LVM (Logical Volume Manager) gives Proxmox fine-grained control over disk allocation, snapshots, and cloning - all of which are used heavily when you clone templates. The `local-lvm` pool is the default thin-provisioned storage on most Proxmox installs.

The import output shows the actual 3.5 GiB being transferred - the difference from the 601 MB download is because qcow2 stores sparse data compressed; LVM expands it to full size.

---

## Step 4 - Attach the Disk to the VM

```bash
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
```

### What this does

Attaches the imported disk to the VM via a **virtio-scsi** controller.

| Part                       | Explanation                                                                                                                                                             |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--scsihw virtio-scsi-pci` | Sets the SCSI controller type. virtio-scsi-pci is paravirtualized - better performance and supports more features (trim/discard, hot-plug) vs. emulated LSI controllers |
| `--scsi0`                  | The slot on the controller. This disk appears as `/dev/sda` inside the guest OS                                                                                         |
| `local-lvm:vm-9000-disk-0` | References the LVM volume created in Step 3                                                                                                                             |

---

## Step 5 - Attach the Cloud-Init Drive

```bash
qm set 9000 --ide2 local-lvm:cloudinit
```

### What this does

Creates a small virtual CD-ROM drive (`vm-9000-cloudinit`) and attaches it as `ide2`. Proxmox generates a **Cloud-Init ISO** and burns it to this virtual drive.

### How Cloud-Init works

On first boot, the `cloud-init` service inside the Ubuntu image:

1. Detects the virtual CD-ROM
2. Reads the configuration from it (hostname, users, SSH keys, network config)
3. Applies the configuration to the running system
4. Marks itself as complete - **never runs again** on subsequent boots

This is the mechanism that turns a generic base image into a configured, named VM with your SSH key and correct IP address - without any manual interaction.

> The `ide2` slot is used (rather than scsi) because Cloud-Init drives are CD-ROMs, and IDE is the standard interface for optical drives in Proxmox VMs.

---

## Step 6 - Configure Boot Order

```bash
qm set 9000 --boot c --bootdisk scsi0
```

Tells the VM to boot from `scsi0` (the Ubuntu disk). `--boot c` is the legacy Proxmox syntax for "boot from first hard disk." Without this, the VM might try to PXE boot or fail to find its boot device.

---

## Step 7 - Enable Serial Console

```bash
qm set 9000 --serial0 socket --vga serial0
```

### Why this is necessary

Ubuntu cloud images are built without a graphical framebuffer - they expect to run headless. Without a serial console configured:

- The Proxmox web UI console shows a **black screen**
- There's no way to interact with the VM during or after boot

This command adds a serial port (`serial0`) and redirects VGA output to it. Proxmox then exposes this as an interactive terminal in the web UI under the **Console** tab (xterm.js).

---

## Step 8 - Convert to Template

```bash
qm template 9000
```

Freezes VM 9000 as a **template**. Proxmox renames the disk from `vm-9000-disk-0` to `base-9000-disk-0` - marking it as a base image that cannot be modified directly.

A template **cannot be started**. It can only be cloned. This is intentional - it protects the clean base image from accidental modification.

---

## Resulting State

After all steps, Proxmox has:

```
VM 9000 (template)
├── scsi0     → base-9000-disk-0  (3.5 GiB, Ubuntu 24.04 root disk)
├── ide2      → vm-9000-cloudinit (Cloud-Init ISO, ~1 MB)
├── net0      → virtio, vmbr0
├── serial0   → socket (console access)
└── [frozen - clone-only]
```

---

## Using the Template - Provisioning a New VM

```bash
# 1. Clone the template
qm clone 9000 <vm-id> --name <hostname> --full

# 2. Configure Cloud-Init for this specific VM
qm set <vm-id> --ciuser owl
qm set <vm-id> --sshkeys ~/.ssh/id_ed25519.pub
qm set <vm-id> --ipconfig0 ip=dhcp          # or ip=192.168.1.x/24,gw=192.168.1.1

# 3. Resize the disk (3.5 GiB base is too small for real use)
qm resize <vm-id> scsi0 +20G

# 4. Start the VM
qm start <vm-id>
```

First boot takes ~30 seconds as Cloud-Init runs. SSH will be available once it completes.

---

## Secrets & GitOps Integration

This template setup is the foundation for the broader homelab GitOps workflow:

- **SOPS + age** encrypts secrets (SSH keys, kubeconfigs, API tokens) committed to Git
- **Terraform** automates `qm clone` and Cloud-Init configuration at scale
- **Flux / ArgoCD** deploys workloads onto VMs provisioned from this template

The age public key registered in `.sops.yaml` before this step ensures all secrets generated from this point forward are encrypted to the correct recipient.

---

## References

- [Ubuntu Cloud Images](https://cloud-images.ubuntu.com/)
- [Proxmox VE - Cloud-Init Support](https://pve.proxmox.com/wiki/Cloud-Init_Support)
- [Mozilla SOPS](https://github.com/getsops/sops)
- [age encryption](https://github.com/FiloSottile/age)

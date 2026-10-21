# Proxmox Cloud-Init template setup

> **Scope:** Creating a reusable Ubuntu 24.04 VM template on Proxmox VE using Cloud-Init for automated VM provisioning.
> **VM ID:** 9000 (high IDs reserved for templates)
> **Base Image:** Ubuntu 24.04 LTS "Noble Numbat" official cloud image

## Overview

A golden template avoids manual Ubuntu installations for each new VM. New instances clone this template to get a clean Ubuntu 24.04 base, while Cloud-Init sets hostnames, SSH keys, and network addressing on first boot. This keeps VM base images consistent and supports automated provisioning through Terraform and Ansible.

## Prerequisites

- Proxmox VE installed and accessible
- Storage pool available: `local-lvm`
- Network bridge configured: `vmbr0`
- Outbound network access from the Proxmox host (or image transferred locally)

## Step 1: Download the Ubuntu 24.04 cloud image

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

### Cloud image characteristics

Ubuntu publishes cloud images as minimal disk images intended for virtual machines. Unlike ISO installers, they require no interactive installation and include cloud-init:

| Property | Cloud image | ISO installer |
| --- | --- | --- |
| Format | `.img` (qcow2 internally) | `.iso` bootable installer |
| Download size | ~600 MB | ~1.5 GB |
| Installation required | No (pre-installed) | Yes (interactive or preseed) |
| Cloud-Init support | Built-in | Requires manual setup |
| Typical use | Templates, automation | Standalone installs |

The downloaded `.img` file is sparse: roughly 600 MB on disk, expanding to a 3.5 GiB virtual disk with pre-allocated OS partitions.

Noble is the Ubuntu release codename for 24.04 LTS. The `current/` directory points to the latest build of that release.

### DNS configuration note

On a fresh Proxmox host with Tailscale installed, `resolv.conf` is managed by Tailscale MagicDNS (`100.100.100.100`). If public DNS resolution fails during download, temporarily specify an external resolver:

```bash
echo "nameserver 8.8.8.8" > /etc/resolv.conf
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
# Restore resolv.conf afterwards
```

For a permanent resolution, configure a global fallback nameserver (such as Google Public DNS) in the Tailscale admin console under DNS > Global nameservers with Override DNS servers enabled.

## Step 2: Create the VM shell

```bash
qm create 9000 \
  --name "ubuntu-2404-cloudinit" \
  --memory 2048 \
  --cores 2 \
  --net0 virtio,bridge=vmbr0
```

This creates an empty VM shell with ID 9000 before attaching storage:

| Parameter | Value | Details |
| --- | --- | --- |
| `9000` | VM ID | High number convention; keeps templates visually separate from standard VM IDs (typically 100 to 899) |
| `--memory 2048` | 2 GB RAM | Template default; overridden by clones as needed |
| `--cores 2` | 2 vCPUs | Template default; overridden by clones as needed |
| `--net0 virtio` | Network adapter | Paravirtualized driver with lower overhead than emulated e1000 or rtl8139 adapters |
| `bridge=vmbr0` | Network bridge | Default Proxmox bridge attached to the host physical interface |

## Step 3: Import the disk into Proxmox storage

```bash
qm importdisk 9000 noble-server-cloudimg-amd64.img local-lvm
```

This imports the `.img` file into Proxmox LVM storage as a logical volume named `vm-9000-disk-0`. The original `.img` file can be removed after import.

LVM provides snapshotting and thin-provisioned cloning for VM templates. The import command expands the compressed 601 MB sparse qcow2 image to its full 3.5 GiB disk allocation in `local-lvm`.

## Step 4: Attach the disk to the VM

```bash
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
```

| Parameter | Details |
| --- | --- |
| `--scsihw virtio-scsi-pci` | Sets the SCSI controller type. The paravirtualized virtio-scsi-pci controller provides better performance and feature support (trim/discard, hot-plug) than emulated LSI controllers |
| `--scsi0` | Slot on the controller; maps to `/dev/sda` inside the guest OS |
| `local-lvm:vm-9000-disk-0` | Points to the LVM volume created in step 3 |

## Step 5: Attach the Cloud-Init drive

```bash
qm set 9000 --ide2 local-lvm:cloudinit
```

This attaches a virtual CD-ROM drive (`vm-9000-cloudinit`) on interface `ide2`. Proxmox generates a Cloud-Init ISO image and maps it to this drive.

During first boot, the Ubuntu `cloud-init` service:
1. Detects the virtual CD-ROM drive.
2. Reads the configuration (hostname, users, SSH keys, network settings).
3. Applies configuration to the operating system.
4. Completes initialization and skips execution on subsequent boots.

This configures the guest VM automatically without manual console setup. Proxmox attaches the Cloud-Init ISO as `ide2` because IDE is its standard interface for optical media.

## Step 6: Configure boot order

```bash
qm set 9000 --boot c --bootdisk scsi0
```

Sets the VM to boot from `scsi0` (the Ubuntu disk). `--boot c` is the Proxmox syntax for booting from the primary disk, preventing the VM from attempting network PXE boot.

## Step 7: Enable serial console

```bash
qm set 9000 --serial0 socket --vga serial0
```

Ubuntu cloud images run headless without a graphical framebuffer. Without a serial console, the Proxmox web console displays a blank screen.

This configuration creates a serial socket (`serial0`) and routes VGA output to it, allowing console access through the Proxmox web UI terminal (xterm.js).

## Step 8: Convert to template

```bash
qm template 9000
```

Converts VM 9000 into a template and renames the disk from `vm-9000-disk-0` to `base-9000-disk-0`. Templates cannot be booted directly; they serve as read-only base disks for new clones.

## Resulting state

```
VM 9000 (template)
├── scsi0     → base-9000-disk-0  (3.5 GiB, Ubuntu 24.04 root disk)
├── ide2      → vm-9000-cloudinit (Cloud-Init ISO, ~1 MB)
├── net0      → virtio, vmbr0
├── serial0   → socket (console access)
└── [frozen - clone-only]
```

## Using the template to provision a new VM

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

Initial boot takes roughly 30 seconds while Cloud-Init configures the guest. SSH becomes available once initialization finishes.

## Secrets and GitOps integration

VM provisioning from this template integrates with repository automation:
- SOPS and age encrypt secrets (SSH keys, kubeconfigs, API tokens) committed to git.
- Terraform provisions VMs and applies Cloud-Init configurations.
- GitOps controllers (Flux or ArgoCD) deploy cluster workloads onto running nodes.

The age public key configured in `.sops.yaml` encrypts secrets generated for these instances.

## References

- [Ubuntu Cloud Images](https://cloud-images.ubuntu.com/)
- [Proxmox VE - Cloud-Init Support](https://pve.proxmox.com/wiki/Cloud-Init_Support)
- [Mozilla SOPS](https://github.com/getsops/sops)
- [age encryption](https://github.com/FiloSottile/age)

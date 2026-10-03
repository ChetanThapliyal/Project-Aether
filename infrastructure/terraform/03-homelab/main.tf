# -----------------------------------------------------------------------------
# K3s Cluster Nodes — Provisioned from Cloud-Init Template (VM 9000)
# -----------------------------------------------------------------------------

locals {
  nodes = {
    "k3s-control-01" = { vmid = 101, cores = 2, memory = 2048, ip = "192.168.1.51/24", role = "control" }
    "k3s-worker-01"  = { vmid = 102, cores = 2, memory = 3584, ip = "192.168.1.52/24", role = "worker" }
    "k3s-worker-02"  = { vmid = 103, cores = 2, memory = 3584, ip = "192.168.1.53/24", role = "worker" }
  }

  gateway     = var.network_gateway
  nameservers = ["1.1.1.1", "8.8.8.8"]
}

resource "proxmox_virtual_environment_vm" "k3s_nodes" {
  for_each = local.nodes

  name        = each.key
  node_name   = "homelab"
  vm_id       = each.value.vmid
  description = "K3s ${each.value.role} node — Managed by Terraform"
  tags        = ["terraform", "k3s", each.value.role]

  on_boot = true
  started = true

  # Clone from our Cloud-Init template
  clone {
    vm_id   = 9000
    retries = 3 # Proxmox can timeout when cloning multiple VMs concurrently
  }

  agent {
    enabled = true
  }

  cpu {
    cores = each.value.cores
    type  = "host" # Single Proxmox node — no migration concerns, max performance
  }

  memory {
    dedicated = each.value.memory
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 30
    file_format  = "raw"
    discard      = "on" # Enable TRIM — extends SSD lifespan
    iothread     = true # Dedicated IO thread per disk — better throughput
  }

  network_device {
    bridge = "vmbr0"
  }

  # Cloud-Init configuration
  initialization {
    ip_config {
      ipv4 {
        address = each.value.ip
        gateway = local.gateway
      }
    }

    dns {
      servers = local.nameservers
    }

    user_account {
      username = "owl"
      keys     = [var.ssh_public_key]
    }
  }

  # Prevent Terraform from fighting with Cloud-Init drift after first boot
  lifecycle {
    ignore_changes = [
      initialization[0].user_account,
      network_device,
    ]
  }
}

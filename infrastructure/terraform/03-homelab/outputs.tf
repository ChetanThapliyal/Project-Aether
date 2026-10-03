# -----------------------------------------------------------------------------
# Outputs — consumed by Ansible inventory and operational scripts
# -----------------------------------------------------------------------------

output "node_ips" {
  description = "Map of node name → IP address (without CIDR suffix)"
  value = {
    for name, cfg in local.nodes :
    name => split("/", cfg.ip)[0]
  }
}

output "node_vmids" {
  description = "Map of node name → Proxmox VM ID"
  value = {
    for name, cfg in local.nodes :
    name => cfg.vmid
  }
}

output "control_plane_ip" {
  description = "IP of the K3s control plane node — used for agent join and kubeconfig"
  value       = split("/", local.nodes["k3s-control-01"].ip)[0]
}

output "worker_ips" {
  description = "List of worker node IPs — used for Ansible workers group"
  value = [
    for name, cfg in local.nodes :
    split("/", cfg.ip)[0]
    if cfg.role == "worker"
  ]
}

output "ssh_connection_strings" {
  description = "Quick-reference SSH commands for each node"
  value = {
    for name, cfg in local.nodes :
    name => "ssh owl@${split("/", cfg.ip)[0]}"
  }
}

# =============================================================================
# GCP DMZ Observability Node — Outputs
# =============================================================================

output "instance_name" {
  description = "The name of the provisioned GCP compute instance"
  value       = google_compute_instance.dmz.name
}

output "instance_id" {
  description = "The unique server-assigned ID of the compute instance"
  value       = google_compute_instance.dmz.instance_id
}

output "public_ipv6" {
  description = "The public external IPv6 address assigned to the DMZ node ($0.00 cost)"
  value       = try(google_compute_instance.dmz.network_interface[0].ipv6_access_config[0].external_ipv6, null)
}

output "private_ipv4" {
  description = "The internal VPC IPv4 address assigned to the DMZ node"
  value       = google_compute_instance.dmz.network_interface[0].network_ip
}

output "ssh_command_ipv6" {
  description = "Direct SSH command to connect to the DMZ node over external IPv6"
  value       = "ssh ${var.ssh_user}@${try(google_compute_instance.dmz.network_interface[0].ipv6_access_config[0].external_ipv6, "PENDING")}"
}

output "tailscale_access_note" {
  description = "Primary secure access method"
  value       = "Primary access: 'ssh ${var.ssh_user}@${var.instance_name}' via Tailnet mesh."
}

output "vpc_name" {
  description = "The VPC network hosting the DMZ"
  value       = google_compute_network.dmz_vpc.name
}

output "subnet_name" {
  description = "The Subnet hosting the DMZ"
  value       = google_compute_subnetwork.dmz_subnet.name
}

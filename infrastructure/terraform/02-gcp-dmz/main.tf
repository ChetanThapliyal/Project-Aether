# =============================================================================
# GCP DMZ Observability Node — Main Infrastructure
# =============================================================================
# Provisions:
#   1. Dedicated VPC & Dual-Stack Subnet (External IPv6 enabled, strictly $0.00)
#   2. Restricted Firewall Rules (inbound SSH & ICMPv6 only)
#   3. e2-micro Compute Instance (Always Free Tier) with Tailscale Bootstrap
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Networking (Isolated DMZ VPC with Dual-Stack IPv4/IPv6)
# -----------------------------------------------------------------------------
resource "google_compute_network" "dmz_vpc" {
  name                    = "${var.instance_name}-vpc"
  auto_create_subnetworks = false
  description             = "Dedicated VPC network for Aether Observability DMZ"
}

resource "google_compute_subnetwork" "dmz_subnet" {
  name             = "${var.instance_name}-subnet"
  ip_cidr_range    = "10.10.0.0/24"
  region           = var.region
  network          = google_compute_network.dmz_vpc.id
  description      = "Dual-stack regional subnet for DMZ compute workloads"
  stack_type       = "IPV4_IPV6"
  ipv6_access_type = "EXTERNAL"
}

# -----------------------------------------------------------------------------
# 2. Firewall Rules (Zero-Trust Inbound)
# -----------------------------------------------------------------------------
# In GCP, all inbound traffic not explicitly permitted by an ingress firewall
# rule is implicitly denied by the default priority-65535 drop rule.

resource "google_compute_firewall" "allow_ssh_ipv6" {
  name        = "${var.instance_name}-allow-ssh-ipv6"
  network     = google_compute_network.dmz_vpc.name
  description = "Permit inbound SSH connections over IPv6"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["fd7a:115c:a1e0::/48"] # Tailscale CGNAT IPv6 block
  target_tags   = ["ssh-allowed"]
}

resource "google_compute_firewall" "allow_icmp_ipv6" {
  name        = "${var.instance_name}-allow-icmp-ipv6"
  network     = google_compute_network.dmz_vpc.name
  description = "Permit ICMPv6 echo requests (ping) for latency & diagnostic checks"

  allow {
    protocol = "58" # IPv6-ICMP protocol number
  }

  source_ranges = ["::/0"]
  target_tags   = ["dmz-observer"]
}

# -----------------------------------------------------------------------------
# 3. Compute Engine Instance (e2-micro Always Free)
# -----------------------------------------------------------------------------
resource "google_compute_instance" "dmz" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  description  = "GCP DMZ node running Uptime Kuma, Homepage, and Cloudflared"

  tags = ["dmz-observer", "ssh-allowed"]

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [metadata_startup_script]
  }

  boot_disk {
    auto_delete = true

    initialize_params {
      image = var.boot_disk_image
      size  = var.boot_disk_size
      type  = var.boot_disk_type
    }
  }

  network_interface {
    network    = google_compute_network.dmz_vpc.id
    subnetwork = google_compute_subnetwork.dmz_subnet.id
    stack_type = "IPV4_IPV6"

    # External IPv6 is completely free ($0.00) in Google Cloud.
    # No public IPv4 access_config is configured, completely avoiding the $0.005/hr (~$3.65/mo) charge.
    ipv6_access_config {
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    ssh-keys               = "${var.ssh_user}:${var.ssh_public_key}"
    block-project-ssh-keys = "true"
  }

  metadata_startup_script = templatefile("${path.module}/templates/startup.sh.tftpl", {
    tailscale_auth_key = var.tailscale_auth_key
    hostname           = var.instance_name
    ssh_user           = var.ssh_user
  })

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # Ensure networking & firewall rules are established before VM creation
  depends_on = [
    google_compute_firewall.allow_ssh_ipv6,
    google_compute_firewall.allow_icmp_ipv6,
    google_compute_subnetwork.dmz_subnet
  ]
}

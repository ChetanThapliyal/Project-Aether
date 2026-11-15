# =============================================================================
# GCP DMZ Observability Node — Main Infrastructure
# =============================================================================
# Provisions:
#   1. Dedicated VPC & Dual-Stack Subnet (External IPv6 enabled, strictly $0.00)
#   2. Restricted Firewall Rules (break-glass SSH via IAP, ICMPv6 only)
#   3. e2-micro Compute Instance (Always Free Tier) with Tailscale Bootstrap
#   4. Kuma backup bucket and the VM's write-only identity (FND-17)
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

  # FND-17: the VM has no public IPv4, so it reaches Cloud Storage (Kuma
  # backups) through Private Google Access on its internal address.
  private_ip_google_access = true
}

# -----------------------------------------------------------------------------
# 2. Firewall Rules (Zero-Trust Inbound)
# -----------------------------------------------------------------------------
# In GCP, all inbound traffic not explicitly permitted by an ingress firewall
# rule is implicitly denied by the default priority-65535 drop rule.

# Break-glass SSH (FND-12). Everyday access is Tailscale SSH, which arrives inside
# WireGuard and needs no VPC rule (the old rule for the fd7a: tailnet range could
# never match: those addresses never appear on the VPC interface). This rule is
# for when the tailnet is down: Google IAP TCP forwarding reaches the VM's
# internal IPv4 from Google's own range, gated by IAM (the project owner, or
# roles/iap.tunnelResourceAccessor), not by network position. Nothing here is
# reachable from the internet.
resource "google_compute_firewall" "allow_ssh_iap" {
  name        = "${var.instance_name}-allow-ssh-iap"
  network     = google_compute_network.dmz_vpc.name
  description = "Break-glass SSH through Google IAP TCP forwarding (tailnet-down access)"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"] # Google IAP TCP forwarding
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

  # FND-17: changing the service account needs a stop/start, not a rebuild.
  allow_stopping_for_update = true

  # The VM's only Google identity: create-only on the Kuma backup bucket.
  # The scope allows storage calls; IAM below decides what they may do.
  service_account {
    email  = google_service_account.dmz_vm.email
    scopes = ["https://www.googleapis.com/auth/devstorage.read_write"]
  }

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
    google_compute_firewall.allow_ssh_iap,
    google_compute_firewall.allow_icmp_ipv6,
    google_compute_subnetwork.dmz_subnet
  ]
}

# -----------------------------------------------------------------------------
# 4. Uptime Kuma Backups (FND-17)
# -----------------------------------------------------------------------------
# /opt/dmz/uptime-kuma holds every DMZ monitor and the push tokens other hosts
# report to. A nightly job on the VM copies it here. The VM can create objects
# but not read, overwrite or delete them, so a compromised DMZ can't erase its
# own history; the lifecycle rule handles retention. A separate bucket from the
# Terraform state, which the least-trusted host must never touch.
resource "google_storage_bucket" "dmz_backups" {
  name                        = "${var.project_id}-dmz-backups"
  location                    = "US-CENTRAL1" # Always Free storage region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "dmz_vm" {
  account_id   = "aether-dmz-vm"
  display_name = "GCP DMZ VM (backup writer only)"
  description  = "Identity of aether-gcp-dmz: create-only on the Kuma backup bucket (FND-17)"
}

resource "google_storage_bucket_iam_member" "dmz_backup_writer" {
  bucket = google_storage_bucket.dmz_backups.name
  role   = "roles/storage.objectCreator" # create only: no read, overwrite, delete or list
  member = "serviceAccount:${google_service_account.dmz_vm.email}"
}

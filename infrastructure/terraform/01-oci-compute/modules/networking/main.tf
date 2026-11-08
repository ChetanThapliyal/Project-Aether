resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.0.0.0/24"
  display_name   = "dockerTailscale"
  dns_label      = "dockertailscale"
}

resource "oci_core_subnet" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  cidr_block     = "10.0.0.0/24"
  display_name   = "public-subnet"
  dns_label      = "publicsubnet"
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "bookorbit-igw"
  enabled        = true
}

resource "oci_core_security_list" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "Default Security List for dockerTailscale"

  egress_security_rules {
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "all"
    stateless        = false
  }

  ingress_security_rules {
    protocol    = "1"
    source      = "10.0.0.0/24"
    source_type = "CIDR_BLOCK"
    stateless   = false
    icmp_options {
      type = 3
    }
  }

  ingress_security_rules {
    protocol    = "1"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    stateless   = false
    icmp_options {
      type = 3
      code = 4
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    stateless   = false
    tcp_options {
      min = 22
      max = 22
    }
  }

  # Tailscale direct paths. The homelab sits behind ISP carrier-grade NAT whose
  # mapping varies by destination, so hole-punching from home fails and
  # tailnet traffic falls back to the DERP relay. With this port open, the
  # home side can always reach the host directly. WireGuard authenticates
  # every packet, so nothing else is exposed.
  ingress_security_rules {
    protocol    = "17"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    stateless   = false
    description = "Tailscale WireGuard (direct paths)"
    udp_options {
      min = 41641
      max = 41641
    }
  }
}

variable "compartment_ocid" {}
variable "subnet_ocid" {}
variable "image_ocid" {}
variable "ssh_public_key" {}

resource "oci_core_instance" "bookorbit" {
  availability_domain = "jXeI:AP-MUMBAI-1-AD-1"
  compartment_id      = var.compartment_ocid
  display_name        = "bookorbit"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  create_vnic_details {
    subnet_id        = var.subnet_ocid
    assign_public_ip = true
    display_name     = "bookorbit-net"
    hostname_label   = "bookorbit-net"
  }

  source_details {
    source_type             = "image"
    source_id               = var.image_ocid
    boot_volume_size_in_gbs = 100
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "oci_core_boot_volume_backup" "bookorbit_pre_upgrade" {
  boot_volume_id = oci_core_instance.bookorbit.boot_volume_id
  display_name   = "bookorbit-pre-upgrade"
  type           = "FULL"
}

output "instance_id" {
  value = oci_core_instance.bookorbit.id
}
output "public_ip" {
  value = oci_core_instance.bookorbit.public_ip
}
output "private_ip" {
  value = oci_core_instance.bookorbit.private_ip
}
output "backup_id" {
  value = oci_core_boot_volume_backup.bookorbit_pre_upgrade.id
}

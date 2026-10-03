
module "compute" {
  source           = "./modules/compute"
  compartment_ocid = var.compartment_ocid
  subnet_ocid      = var.subnet_ocid
  image_ocid       = var.image_ocid
  ssh_public_key   = var.ssh_public_key
}

module "storage" {
  source           = "./modules/storage"
  compartment_ocid = var.compartment_ocid
}

moved {
  from = oci_core_instance.bookorbit
  to   = module.compute.oci_core_instance.bookorbit
}

moved {
  from = oci_core_boot_volume_backup.bookorbit_pre_upgrade
  to   = module.compute.oci_core_boot_volume_backup.bookorbit_pre_upgrade
}

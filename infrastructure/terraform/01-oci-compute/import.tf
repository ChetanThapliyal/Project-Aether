import {
  to = module.networking.oci_core_vcn.main
  id = var.vcn_ocid
}

import {
  to = module.networking.oci_core_subnet.public
  id = var.subnet_ocid
}

import {
  to = module.networking.oci_core_internet_gateway.igw
  id = var.igw_ocid
}

import {
  to = module.networking.oci_core_security_list.main
  id = var.sl_ocid
}

# The instance's boot volume. Never imported before, so every plan tried to
# create a second volume (a clone) instead of managing this one.
import {
  to = module.compute.oci_core_boot_volume.bookorbit_boot_volume
  id = module.compute.boot_volume_id
}

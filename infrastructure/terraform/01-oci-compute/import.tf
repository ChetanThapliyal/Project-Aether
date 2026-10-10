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

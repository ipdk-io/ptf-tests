# Copyright (c) 2022 Intel Corporation.
#
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
DPDK Port Dump Test - Link Port Only Scenario
DPDK Port Dump Test - TAP only scanario
    1. Verify that TAP port can be created separately.
    2. Verify that "tdi-portin-id" and "tdi-portout-id" are same unique postive integer.
    3. Verify that "tdi-portin-id" and "tdi-portout-id" for each port are created in incremental order 
       according to creating sequence not link port self index regardless of link port self index.

"""

# in-built module imports
import time
import sys

# Unittest related imports
import unittest
import common.utils.log as log

# ptf related imports
import ptf
import ptf.dataplane as dataplane
from ptf.base_tests import BaseTest
from ptf.testutils import *
from ptf import config

# scapy related imports
from scapy.packet import *
from scapy.fields import *
from scapy.all import *

# framework related imports
import common.utils.p4rtctl_utils as p4rt_ctl
import common.utils.test_utils as test_utils
from common.utils.config_file_utils import (
    get_config_dict,
    get_gnmi_params_simple,
    get_interface_ipv4_dict,
)
from common.utils.gnmi_ctl_utils import (
    gnmi_ctl_set_and_verify,
    gnmi_get_params_elemt_value,
    gnmi_set_params,
    ip_set_ipv4,
    gnmi_get_params_verify,
)
from common.lib.port_config import PortConfig


class Port_dump_link_port_only(BaseTest):
    def setUp(self):
        BaseTest.setUp(self)
        self.result = unittest.TestResult()
        config[
            "relax"
        ] = True  # for verify_packets to ignore other packets received at the interface
        test_params = test_params_get()
        config_json = test_params["config_json"]
        pci_bdf = test_params["pci_bdf"]
        self.config_data = get_config_dict(config_json, pci_bdf=pci_bdf)

        self.gnmictl_params = get_gnmi_params_simple(self.config_data)
        self.totalPorts = len(self.gnmictl_params)

    def runTest(self):
        if not test_utils.gen_dep_files_p4c_tdi_pipeline_builder(self.config_data):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to generate P4C artifacts or pb.bin")

        if not gnmi_ctl_set_and_verify(self.gnmictl_params):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to configure gnmi ctl ports")

        if not gnmi_get_params_verify(self.gnmictl_params):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to verify gnmi ctl ports")

        # verify port id formation
        tdi_in_id_list = gnmi_get_params_elemt_value(
            self.gnmictl_params, "tdi-portin-id"
        )
        if not tdi_in_id_list:
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to verify tdi-portin-id ")

        tdi_out_id_list = gnmi_get_params_elemt_value(
            self.gnmictl_params, "tdi-portout-id"
        )
        if not tdi_out_id_list:
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to verify tdi-portout-id")

        log.info(
            f"Verify that in id {tdi_in_id_list} and out id {tdi_in_id_list} must be same"
        )
        if tdi_out_id_list != tdi_in_id_list:
            self.result.addFailure(self, sys.exc_info())
            self.fail(
                f"Failed: in id {tdi_in_id_list} and out id {tdi_in_id_list} must be in same order"
            )

        log.info(f"Verify that out id {tdi_in_id_list} no duplication")
        if len(tdi_out_id_list) != len(set(tdi_out_id_list)):
            self.result.addFailure(self, sys.exc_info())
            self.fail(f"Failed: {tdi_in_id_list} has duplicated id ")

        log.info(
            f"Verify if the number of ports {self.totalPorts} created is same as defined"
        )
        if self.totalPorts != len(tdi_in_id_list):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to verify the number of port created is same as defined")

        # the value tdi_in_id_list is in string foramt
        # covert them to integer in order to check incremental order
        port_id_list = []
        for id in tdi_in_id_list:
            try:
                if int(id) < 0:
                    self.result.addFailure(self, sys.exc_info())
                    self.fail(f"Failed: {tdi_in_id_list} has negative integer")
                port_id_list.append(int(id))
            except ValueError:
                self.result.addFailure(self, sys.exc_info())
                self.fail(f"Failed: {tdi_in_id_list} has negative integer")
        log.info(f"verify all ports id are integer as {port_id_list} ")

        log.info(f"check if port id is created in incremental order as {port_id_list}")
        if sorted(port_id_list) != port_id_list:
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to verify port ids are created in incremental order")

        log.info("verify pipe can be set after port configured")
        if not p4rt_ctl.p4rt_ctl_set_pipe(
            self.config_data["switch"],
            self.config_data["pb_bin"],
            self.config_data["p4_info"],
        ):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to set pipe")

    def tearDown(self):
        if self.result.wasSuccessful():
            log.passed("Test has PASSED")
        else:
            log.failed("Test has FAILED")

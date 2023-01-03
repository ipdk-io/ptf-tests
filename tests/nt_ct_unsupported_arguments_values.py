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
DPDK Connection Tracking Negative Test case with Link and Tap Ports
"""

# in-built module imports
import time
import sys

# Unittest related imports
import unittest

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
import common.utils.log as log
import common.utils.test_utils as test_utils
from common.utils.config_file_utils import get_config_dict, get_gnmi_params_simple, get_interface_ipv4_dict
from common.utils.gnmi_ctl_utils import gnmi_ctl_set_and_verify, gnmi_set_params, ip_set_ipv4


class Connection_Track(BaseTest):

    def setUp(self):
        BaseTest.setUp(self)
        self.result = unittest.TestResult()
        config["relax"] = True # for verify_packets to ignore other packets received at the interface
        
        test_params = test_params_get()
        config_json = test_params['config_json']
        self.dataplane = ptf.dataplane_instance
        ptf.dataplane_instance = ptf.dataplane.DataPlane(config)
        self.capture_port = test_params['pci_bdf'][:-1] + "1"
        self.config_data = get_config_dict(config_json, test_params['pci_bdf'])
        self.gnmictl_params = get_gnmi_params_simple(self.config_data)
        self.interface_ip_list = get_interface_ipv4_dict(self.config_data)


    def runTest(self):
        if not test_utils.gen_dep_files_p4c_dpdk_pna_tdi_pipeline_builder(self.config_data):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to generate P4C artifacts or pb.bin")
        
        if not gnmi_ctl_set_and_verify(self.gnmictl_params):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to configure gnmi ctl ports")

        ip_set_ipv4(self.interface_ip_list)

        # get port list and add to dataplane
        port_list = self.config_data['port_list']
        port_list[0] = test_utils.get_port_name_from_pci_bdf(self.capture_port)
        port_ids = test_utils.add_port_to_dataplane(port_list)
        
        for port_id, ifname in config["port_map"].items():
            device, port = port_id
            self.dataplane.port_add(ifname, device, port)

        if not p4rt_ctl.p4rt_ctl_set_pipe(self.config_data['switch'], self.config_data['pb_bin'], self.config_data['p4_info']):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to set pipe")

        table = self.config_data['table'][2]
        log.info(f"Rule Creation : {table['description']}")
        log.info(f"Adding {table['description']} rules")
        log.info("Expecting fail for Negative Test scenario:")
        for match_action in table['match_action']:
            if not p4rt_ctl.p4rt_ctl_add_entry(table['switch'],table['name'], match_action):
                   log.info("------------------------------------------------------")
                   log.info("Above Fail is  as expected for Negative Test Execution")
                   log.info("------------------------------------------------------")
           

        table = self.config_data['table'][3]
        log.info(f"Rule Creation for Negative Test case : {table['description']}")
        log.info(f"Adding {table['description']} rules")
        log.info("Expecting fail for Negative Test scenario:")
        log.info(f"{table['match_action']}")
        for match_action in table['match_action']:
            log.info(match_action)
            if not p4rt_ctl.p4rt_ctl_add_entry(table['switch'],table['name'], match_action):
                   log.info("------------------------------------------------------")
                   log.info("Above Fail is  as expected for Negative Test Execution")
                   log.info("------------------------------------------------------")
                   
       
        # Adding correct Rules 
        table = self.config_data['table'][0]
        log.info(f"Rule Creation : {table['description']}")
        log.info(f"Adding {table['description']} rules")
        for match_action in table['match_action']:
            if not p4rt_ctl.p4rt_ctl_add_entry(table['switch'],table['name'], match_action):
                self.result.addFailure(self, sys.exc_info())
                self.fail(f"Failed to add table entry {match_action}")

        table = self.config_data['table'][1]
        log.info(f"Rule Creation : {table['description']}")
        log.info(f"Adding {table['description']} rules")
        for match_action in table['match_action']:
            if not p4rt_ctl.p4rt_ctl_add_entry(table['switch'],table['name'], match_action):
                self.result.addFailure(self, sys.exc_info())
                self.fail(f"Failed to add table entry {match_action}")
        
        # Required 5 sec sleep
        time.sleep(5)

        log.info("-----------------------------------------------------------------")
        log.info("Scenario : Connection should Establish after Adding correct Rules")
        log.info("-----------------------------------------------------------------")
        log.info("sending SYN packet: A->B")
        pkt = simple_tcp_packet(eth_src=self.config_data['traffic']['in_pkt_header']['eth_mac'][0], eth_dst=self.config_data['traffic']['in_pkt_header']['eth_mac'][1], ip_src=self.config_data['traffic']['in_pkt_header']['ip_address'][0] , ip_dst=self.config_data['traffic']['in_pkt_header']['ip_address'][1], tcp_sport=self.config_data['traffic']['in_pkt_header']['tcp_port'][0], tcp_dport=self.config_data['traffic']['in_pkt_header']['tcp_port'][1])
        send_packet(self, port_ids[self.config_data['traffic']['send_port'][0]], pkt)
        try:
            verify_packets(self, pkt, device_number=0, ports=[port_ids[self.config_data['traffic']['receive_port'][0]][1]])              
            log.passed(f" Verification of packets passed, Syn packet received")
        except Exception as err:
            self.result.addFailure(self, sys.exc_info())
            log.failed(f" Verification of Syn packet sent failed with exception {err}")
        

        self.dataplane.kill()


    def tearDown(self):
        for index,table in enumerate (self.config_data['table']):
            if index in range(0,2):
               log.info(f"Deleting {table['description']} rules")
               for del_action in table['del_action']:
                   p4rt_ctl.p4rt_ctl_del_entry(table['switch'], table['name'], del_action)

        if self.result.wasSuccessful():
            log.passed("Test has PASSED")
        else:
            log.failed("Test has FAILED")
        

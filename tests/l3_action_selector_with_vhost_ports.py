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
DPDK L3 Exact Match (match fields, actions) with vHost

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

# framework related imports
import common.utils.log as log
import common.utils.p4rtctl_utils as p4rt_ctl
import common.utils.test_utils as test_utils
from common.utils.config_file_utils import get_config_dict, get_gnmi_params_simple
from common.utils.gnmi_ctl_utils import gnmi_ctl_set_and_verify
from common.lib.telnet_connection import connectionManager


class L3_Action_Selector_Vhost(BaseTest):
    def setUp(self):
        BaseTest.setUp(self)
        self.result = unittest.TestResult()

        test_params = test_params_get()
        config_json = test_params["config_json"]

        try:
            self.vm_cred = test_params["vm_cred"]
        except KeyError:
            self.vm_cred = ""

        self.config_data = get_config_dict(
            config_json,
            vm_location_list=test_params["vm_location_list"],
            vm_cred=self.vm_cred,
        )
        self.gnmictl_params = get_gnmi_params_simple(self.config_data)

    def runTest(self):
        # Compile p4 file using p4c compiler and generate binary using tdi pipeline builder
        if not test_utils.gen_dep_files_p4c_tdi_pipeline_builder(self.config_data):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to generate P4C artifacts or pb.bin")

        # Create ports using gnmi-ctl
        if not gnmi_ctl_set_and_verify(self.gnmictl_params):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to configure gnmi ctl ports")

        # Run Set-pipe command for set pipeline
        if not p4rt_ctl.p4rt_ctl_set_pipe(
            self.config_data["switch"],
            self.config_data["pb_bin"],
            self.config_data["p4_info"],
        ):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to set pipe")

        # Create VMs
        result, vm_name = test_utils.vm_create(self.config_data["vm_location_list"])
        if not result:
            self.result.addFailure(self, sys.exc_info())
            self.fail(f"VM creation failed for {vm_name}")

        # create telnet instance for VMs created
        time.sleep(30)
        vm_id = 0
        for vm, port in zip(self.config_data["vm"], self.config_data["port"]):
            globals()["conn" + str(vm_id + 1)] = connectionManager(
                "127.0.0.1",
                f"655{vm_id}",
                vm["vm_username"],
                vm["vm_password"],
                timeout=30,
            )
            globals()["vm" + str(vm_id + 1) + "_command_list"] = [
                f"ip addr add {port['ip']} dev {port['interface']}",
                f"ip link set dev {port['interface']} up",
                f"ip link set dev {port['interface']} address {port['mac']}",
                f"ip route add 0.0.0.0/0 via {vm['dst_gw']} dev {port['interface']}",
            ]
            vm_id += 1

        # add action_selector rules

        table = self.config_data["table"][0]

        log.info(f"##########  Scenario : {table['description']} ##########")
        # Add action profile members
        log.info("Add action profile members")
        for member in table["member_details"]:
            p4rt_ctl.p4rt_ctl_add_member_and_verify(
                table["switch"], table["name"], member
            )
        # Adding action selector groups
        log.info("Adding action selector groups")
        group_count = 0
        for group in table["group_details"]:
            p4rt_ctl.p4rt_ctl_add_group_and_verify(
                table["switch"], table["name"], group
            )
            group_count += 1

        log.info(f"Setting up rule for : {table['description']}")
        table = self.config_data["table"][1]
        for match_action in table["match_action"]:
            p4rt_ctl.p4rt_ctl_add_entry(table["switch"], table["name"], match_action)

        # configuring VMs
        log.info("Configuring VM0 ....")
        test_utils.configure_vm(conn1, vm1_command_list)

        log.info("Configuring VM1 ....")
        test_utils.configure_vm(conn2, vm2_command_list)

        # Verify Unicast Traffic VM0 to VM1
        log.info("Verify Unicast Traffic from VM0 to VM1")
        dst_ip = self.config_data["traffic"]["in_pkt_header"]["ip_dst"][0]
        result = test_utils.vm_to_vm_ping_test(conn1, dst_ip)
        if not result:
            self.result.addFailure(self, sys.exc_info())
            log.failed("Unicast traffic not received on VM1")

        # Verify Unicast Traffic VM1 to VM0
        log.info("Verify Unicast Traffic from VM1 to VM0")
        dst_ip = self.config_data["traffic"]["in_pkt_header"]["ip_src"][0]
        result = test_utils.vm_to_vm_ping_test(conn2, dst_ip)
        if not result:
            self.result.addFailure(self, sys.exc_info())
            log.failed("Unicast traffic not received on VM0")

        log.info("Verify Multicast Traffic")
        sender_vm_id = self.config_data["traffic"]["send_port"][1]
        receiver_vm_id = self.config_data["traffic"]["receive_port"][1]
        sender_conn, receiver_conn = eval("conn" + str(sender_vm_id + 1)), eval(
            "conn" + str(receiver_vm_id + 1)
        )
        # verify Multicast Traffic
        send_result = test_utils.send_scapy_traffic_from_vm(
            sender_vm_id, sender_conn, receiver_conn, self.config_data, "multicast"
        )
        if send_result:
            result = test_utils.verify_scapy_traffic_from_vm(
                receiver_vm_id, receiver_conn, self.config_data, "multicast"
            )
            if not result:
                self.result.addFailure(self, sys.exc_info())
                log.failed("Multicast Traffic not received")
            else:
                log.passed(
                    f"Multicast Traffic received on receiver_vm VM{receiver_vm_id}"
                )
        else:
            log.failed(
                f"Multicast Packets are not sent from Sender_vm VM{sender_vm_id}"
            )
            self.result.addFailure(self, sys.exc_info())

        time.sleep(3)

        # verify Broadcast Traffic
        log.info("Verify Broadcast Traffic")
        sender_vm_id = self.config_data["traffic"]["send_port"][2]
        receiver_vm_id = self.config_data["traffic"]["receive_port"][2]
        sender_conn, receiver_conn = eval("conn" + str(sender_vm_id + 1)), eval(
            "conn" + str(receiver_vm_id + 1)
        )
        send_result = test_utils.send_scapy_traffic_from_vm(
            sender_vm_id, sender_conn, receiver_conn, self.config_data, "broadcast"
        )
        if send_result:
            result = test_utils.verify_scapy_traffic_from_vm(
                receiver_vm_id, receiver_conn, self.config_data, "broadcast"
            )
            if not result:
                self.result.addFailure(self, sys.exc_info())
                log.failed("Broadcast Traffic not received")
            else:
                log.info(
                    f"Broadcast Traffic received on receiver_vm VM{receiver_vm_id}"
                )
        else:
            log.failed(
                f"Broadcast Packets are not sent from sender_vm with id {sender_vm_id}"
            )
            self.result.addFailure(self, sys.exc_info())

        # Close telnet connections
        log.info(f"close VM telnet session")
        conn1.close()
        conn2.close()

    def tearDown(self):
        table = self.config_data["table"][0]
        log.info("Deleting groups")
        for del_group in table["del_group"]:
            p4rt_ctl.p4rt_ctl_del_group(table["switch"], table["name"], del_group)

        log.info("Deleting members")
        for del_member in table["del_member"]:
            p4rt_ctl.p4rt_ctl_del_member(table["switch"], table["name"], del_member)

        if self.result.wasSuccessful():
            log.info("Test has PASSED")
        else:
            log.info("Test has FAILED")

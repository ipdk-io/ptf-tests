# Copyright (c) 2022 Intel Corporation.
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
DPDK L3EM Indirect counter

"""
# in-built module imports
import time
import sys

# Unittest related imports
import unittest

# ptf related imports
from ptf.base_tests import BaseTest
from ptf.testutils import *

# framework related imports
import common.utils.log as log
import common.utils.p4rtctl_utils as p4rt_ctl
import common.utils.test_utils as test_utils
from common.utils.config_file_utils import get_config_dict, get_gnmi_params_simple
from common.utils.gnmi_ctl_utils import gnmi_ctl_set_and_verify
from common.lib.telnet_connection import connectionManager


class IPDK_L3EM_INDIRECT_COUNTER(BaseTest):
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
        # Create Ports using gnmictl
        if not gnmi_ctl_set_and_verify(self.gnmictl_params):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to configure gnmi ctl ports")

        # Create binary from p4 program using pna and psa arch
        if self.config_data["p4arctype"] == "pna":
            if not test_utils.gen_dep_files_p4c_dpdk_pna_tdi_pipeline_builder(
                self.config_data
            ):
                self.result.addFailure(self, sys.exc_info())
                self.fail("Failed to generate P4C artifacts or pb.bin")
        elif self.config_data["p4arctype"] == "psa":
            if not test_utils.gen_dep_files_p4c_tdi_pipeline_builder(self.config_data):
                self.result.addFailure(self, sys.exc_info())
                self.fail("Failed to generate P4C artifacts or pb.bin")
        else:
            self.result.addFailure(self, sys.exc_info())
            self.fail("FAIL: Please specify p4 artifacts, pna or psa?")

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

        # Create telnet instance for VMs created
        self.conn_obj_list = []
        vm_cmd_list = []
        vm_id = 0
        for vm, port in zip(self.config_data["vm"], self.config_data["port"]):
            globals()["conn" + str(vm_id + 1)] = connectionManager(
                "127.0.0.1", f"655{vm_id}", vm["vm_username"], vm["vm_password"]
            )
            self.conn_obj_list.append(globals()["conn" + str(vm_id + 1)])
            globals()["vm" + str(vm_id + 1) + "_command_list"] = [
                f"ip addr add {port['ip_address']} dev {port['interface']}",
                f"ip link set dev {port['interface']} up",
                f"ip link set dev {port['interface']} address {port['mac_local']}",
                f"ip route add {vm['dst_nw']} via {vm['dst_gw']} dev {port['interface']}",
                f"ip neigh add dev {port['interface']} {vm['remote_ip']} lladdr {vm['mac_remote']}",
            ]

            vm_cmd_list.append(globals()["vm" + str(vm_id + 1) + "_command_list"])
            vm_id += 1

        # configuring VMs
        for i in range(len(self.conn_obj_list)):
            log.info(f"Configuring VM{i}....")
            test_utils.configure_vm(self.conn_obj_list[i], vm_cmd_list[i])

        # add  forward rules
        for table in self.config_data["table"]:
            log.info(f"Scenario : {table['description']}")
            log.info(f"Adding {table['description']} rules")
            for match_action in table["match_action"]:
                if not p4rt_ctl.p4rt_ctl_add_entry(
                    table["switch"], table["name"], match_action
                ):
                    self.result.addFailure(self, sys.exc_info())
                    self.fail(f"Failed to add table entry {match_action}")

        # prepare to triger traffic
        time.sleep(10)
        # for counter accuracy, to skip intial failure or traffic noise
        log.info(
            f"send intital {self.config_data['counter']['num_ping'][1]} ping to trigger arp etc."
        )
        if not test_utils.vm_to_vm_ping_test(
            self.conn_obj_list[0],
            self.config_data["vm"][0]["remote_ip"],
            count=self.config_data["counter"]["num_ping"][1],
        ):
            self.result.addFailure(self, sys.exc_info())
            log.failed("FAIL: failed to inital ping")

        cnt1, cnt2 = {}, {}
        cnt_table_name_and_id = p4rt_ctl.p4rt_ctl_get_counter_table_and_id()
        if not cnt_table_name_and_id:
            self.result.addFailure(self, sys.exc_info())
            log.failed("failed to get counter table name and id")

        # get counter before sending traffic
        for i in range(len(cnt_table_name_and_id)):
            counter_id = cnt_table_name_and_id[i][1]
            cnt_table_name = cnt_table_name_and_id[i][0]
            cnt1[cnt_table_name] = []
            for j in self.config_data["counter"]["index"]:
                flow = f"counter_id={counter_id},index={j}"
                data = p4rt_ctl.p4rt_ctl_get_counter_data(
                    self.config_data["switch"], cnt_table_name, flow
                )
                if not data:
                    self.result.addFailure(self, sys.exc_info())
                    log.info("FAIL: failed to get counter data")
                cnt1[cnt_table_name].append(data)
        log.info(f"The counter before sending traffic is {cnt1}")

        log.info("Ping test from VM0 to VM1 to triger counter")
        if not test_utils.vm_to_vm_ping_test(
            self.conn_obj_list[0],
            self.config_data["vm"][0]["remote_ip"],
            count=self.config_data["counter"]["num_ping"][0],
        ):
            self.result.addFailure(self, sys.exc_info())
            log.info("FAIL: Ping test failed for VM0")

        # Get counter after sending traffic
        for i in range(len(cnt_table_name_and_id)):
            counter_id = cnt_table_name_and_id[i][1]
            cnt_table_name = cnt_table_name_and_id[i][0]
            cnt2[cnt_table_name] = []
            for j in range(len(self.config_data["counter"]["index"])):
                flow = f"counter_id={counter_id},index={self.config_data['counter']['index'][j]}"
                data = p4rt_ctl.p4rt_ctl_get_counter_data(
                    self.config_data["switch"], cnt_table_name, flow
                )
                if not data:
                    self.result.addFailure(self, sys.exc_info())
                    log.info("FAIL: failed to get counter data")

                cnt2[cnt_table_name].append(data)

                if cnt_table_name == "ipv4_host_tbl_flow_counter_bytes":
                    log.info(
                        f"The curent counter of {cnt_table_name} after sending traffic is {cnt2[cnt_table_name][j]}"
                    )
                    # Check counter update
                    cnt_change = (
                        cnt2[cnt_table_name][j]["bytes"]
                        - cnt1[cnt_table_name][j]["bytes"]
                    )
                    # there is a double dumy ping in vm_to_vm_ping_tes
                    expected_bytes = (
                        2
                        * self.config_data["counter"]["num_ping"][0]
                        * self.config_data["counter"]["default_byte"]
                    )
                    # verify counter changes
                    if cnt_change >= expected_bytes:
                        log.info(
                            f"PASS: bytes counter is changed by {cnt_change} in flow {flow}"
                        )
                    else:
                        self.result.addFailure(self, sys.exc_info())
                        log.info(
                            f"FAIL: The {cnt_change} is less than expected {expected_bytes} in flow {flow}"
                        )

                if cnt_table_name == "ipv4_host_tbl_flow_counter_packets":
                    log.info(
                        f"The curent counter of {cnt_table_name} after sending traffic is {cnt2[cnt_table_name][j]}"
                    )
                    # Check counter update
                    cnt_change = (
                        cnt2[cnt_table_name][j]["packets"]
                        - cnt1[cnt_table_name][j]["packets"]
                    )
                    # Verify counter changes
                    # there is a double dumy ping in vm_to_vm_ping_tes
                    if cnt_change >= 2 * self.config_data["counter"]["num_ping"][0]:
                        log.passed(
                            f"packets counter is changed by {cnt_change} in flow {flow}"
                        )
                    else:
                        self.result.addFailure(self, sys.exc_info())
                        log.info(
                            f"FAIL: The {cnt_change} is less than expected {2*self.config_data['counter']['num_ping'][0]}"
                        )
        # closing telnet session
        log.info("close VM telnet session")
        for conn in self.conn_obj_list:
            conn.close()

    def tearDown(self):
        log.info("delete table entries")
        for table in self.config_data["table"]:
            log.info(f"Deleting {table['description']} rules")
            for del_action in table["del_action"]:
                p4rt_ctl.p4rt_ctl_del_entry(table["switch"], table["name"], del_action)

        if self.result.wasSuccessful():
            log.info("Test has PASSED")
        else:
            log.info("Test has FAILED")

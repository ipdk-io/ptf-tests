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
DPDK K8S: service traffic test
"""

# in-built module imports
import time
import sys

# Unittest related imports
import unittest

# ptf related imports
import ptf
from ptf.base_tests import BaseTest
from ptf.testutils import *
from ptf import config

# framework related imports
import common.utils.log as log
import common.utils.k8_utils as k8_utils
from common.utils.test_utils import git_clone_remote_repo


class K8_DPDK_service_traffic(BaseTest):
    def setUp(self):
        BaseTest.setUp(self)
        self.result = unittest.TestResult()
        config[
            "relax"
        ] = True  # for verify_packets to ignore other packets received at the interface
        test_params = test_params_get()
        self.kube_iperf_path = test_params["kube_iperf_path"]

    def runTest(self):
        # git clone kube iperf repo: https://github.com/Pharb/kubernetes-iperf3.git
        repo = "github.com/Pharb/kubernetes-iperf3.git"
        if not git_clone_remote_repo(repo, self.kube_iperf_path):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to clone git repo")

        # Execute ./steps/setup.sh from https://github.com/Pharb/kubernetes-iperf3.git
        if not k8_utils.execute_iperf_setup(self.kube_iperf_path):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to run setup.sh")

        # Check if iperf3-server is running
        if not k8_utils.check_service_status("iperf3-server"):
            self.result.addFailure(self, sys.exc_info())
            self.fail("iperf3-server not running")

        time.sleep(5)

        # Start iperf client and check rx tx pkt > 0
        log.info("Starting iperf client")
        rx_pkt, tx_pkt = k8_utils.execute_iperf_client(self.kube_iperf_path)
        log.info(f"Sent {rx_pkt} MBytes, Received {tx_pkt} MBytes")
        if not (rx_pkt & tx_pkt):
            self.result.addFailure(self, sys.exc_info())
            self.fail("rx/tx pkt is equal to 0")

    def tearDown(self):
        # Execute ./steps/cleanup.sh from https://github.com/Pharb/kubernetes-iperf3.git
        if not k8_utils.execute_iperf_cleanup(self.kube_iperf_path):
            self.result.addFailure(self, sys.exc_info())
            self.fail("Failed to run cleanup.sh")

        # Check if iperf3-server is not running
        if not k8_utils.check_service_status("iperf3-server", expected_status=False):
            self.result.addFailure(self, sys.exc_info())
            self.fail("iperf3-server is still running")

        if self.result.wasSuccessful():
            log.info("Test has PASSED")
        else:
            log.info("Test has FAILED")

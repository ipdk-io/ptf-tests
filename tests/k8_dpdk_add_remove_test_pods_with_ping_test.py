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
DPDK K8S: add/remove test pods with ping test
"""

# in-built module imports
import time

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
from common.utils.config_file_utils import convert_yaml_to_dict_from_file


class K8_DPDK(BaseTest):
    def setUp(self):
        BaseTest.setUp(self)
        self.result = unittest.TestResult()
        config[
            "relax"
            ] = True  # for verify_packets to ignore other packets received at the interface
        test_params = test_params_get()
        yaml_files = test_params['yaml_files'].split(',')
        self.pod_bodies = []
        for yaml_file in yaml_files:
            pod_body = convert_yaml_to_dict_from_file(yaml_file)
            if pod_body:
                self.pod_bodies.append(pod_body)

    def runTest(self):
        # Create 4 test pods and verify if running
        assert len(self.pod_bodies) == 4
        for pod_body in self.pod_bodies:
            k8_utils.create_pod(pod_body['metadata']['name'], pod_body)
            time.sleep(5)
            if not k8_utils.verify_pod_running(pod_body['metadata']['name']):
                self.result.addFailure(self, sys.exc_info())
                self.fail(f"{pod_body['metadata']['name']} not running")

        log.info("4 Pods created")

        # Get IP address of each pod
        pod_ip_dict = {}
        for pod_body in self.pod_bodies:
            pod_ip_dict[pod_body['metadata']['name']] = k8_utils.find_pod_ip(pod_body['metadata']['name'])

        log.info(f"Pod name and Pod IP mapping: {pod_ip_dict}")

        # Ping each pod from another
        for src_pod in pod_ip_dict.keys():
            for dst_pod, dst_ip in pod_ip_dict.items():
                if src_pod == dst_pod:
                    continue
                log.info(f"{src_pod} > ping -c 10 {dst_ip}")
                cmds = ['/bin/sh', '-c', f'ping -c 10 {dst_ip}']
                resp = k8_utils.execute_command(src_pod, cmds)
                log.info(resp)

        # Delete 4 Pods
        for pod_body in self.pod_bodies:
            k8_utils.delete_pod(pod_body['metadata']['name'])
            time.sleep(5)

        # Ping each pod from another -- expect failure
        for src_pod in pod_ip_dict.keys():
            for dst_pod, dst_ip in pod_ip_dict.items():
                if src_pod == dst_pod:
                    continue
                log.info(f"{src_pod} > ping -c 10 {dst_ip}")
                cmds = ['/bin/sh', '-c', f'ping -c 10 {dst_ip}']
                try:
                    resp = k8_utils.execute_command(src_pod, cmds)
                except Exception as err:
                    log.info(f"Ping Failed as expected: {err}")

    def tearDown(self):
        if self.result.wasSuccessful():
            log.info("Test has PASSED")
        else:
            log.info("Test has FAILED")


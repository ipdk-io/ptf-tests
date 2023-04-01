# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from pathlib import Path
from typing import Optional

from paramiko.client import AutoAddPolicy, SSHClient

from system_tools.errors import CommandException


class SSHTerminal:
    """A class used to represent a session with an SSH server"""

    def __init__(self, config, *args, **kwargs):
        self.config = config
        self.client = SSHClient()

        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(AutoAddPolicy)
        self.client.connect(
            config.ip_address,
            config.port,
            config.username,
            config.password,
            *args,
            **kwargs,
        )

    def execute(self, cmd: str, timeout: int = None) -> Optional[str]:
        """Simple function executes a command on the SSH server
        Returns list of the lines output
        """
        _, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)  # nosec
        if stdout.channel.recv_exit_status():
            raise CommandException(stderr.read().decode())
        # if command is executed in the background don't wait for the output
        return (
            None if cmd.rstrip().endswith("&") else stdout.read().decode().rstrip("\n")
        )


class UnixSocketTerminal:
    def __init__(self, ssh_terminal, sock):
        self.ssh_terminal = ssh_terminal
        self.sock = sock
        tmp_path = Path("/tmp")
        self._filename = "socket_functions.py"
        self._dest_file = tmp_path.joinpath(self._filename)
        self._src_file = Path(__file__).parent.joinpath(self._filename)

    def _save_tmp_file(self):
        ssh_client = self.ssh_terminal.client
        sftp = ssh_client.open_sftp()
        sftp.put(str(self._src_file), str(self._dest_file))
        sftp.close()

    def _delete_tmp_file(self):
        self.ssh_terminal.execute(f"rm -rf {self._dest_file}")

    def _execute(self, cmd, wait_for_secs=2):
        cmd = (
            f"""cd /tmp && sudo python -c 'from socket_functions import *; """
            f"""out = send_command_over_unix_socket("{self.sock}", "{cmd}", {wait_for_secs}); """
            f"""print(out)'"""
        )
        return self.ssh_terminal.execute(cmd)

    @staticmethod
    def _clean_out(out):
        split_out = out.split("\r\n\x1b[?2004l\r")
        return split_out[0].replace("\r" "") if len(split_out) == 3 else out

    def execute(self, cmd, wait_for_secs=2):
        self._save_tmp_file()
        out = self._execute(cmd, wait_for_secs)
        self._delete_tmp_file()
        return self._clean_out(out)

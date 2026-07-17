# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-strict

"""
TAAC Task for configuring bgpcpp startup flags on EOS devices.

This task modifies the /usr/sbin/run_bgpcpp.sh script to add or update
bgpcpp startup flags. Changes are idempotent - safe to run multiple times.

Usage in test configs:
    Task(
        task_name="configure_bgpcpp_startup",
        params=Params(
            json_params=json.dumps({
                "hostname": "eb03.lab.ash6",
                "flags": {
                    "agent_thrift_recv_timeout_ms": "160000",
                    "bgp_policy_cache_size": "400000",
                },
                "ssh_user": "admin",
                "ssh_password": "password",
            }),
        ),
    )
"""

import os
import typing as t

TAAC_OSS = os.environ.get("TAAC_OSS", "").lower() in ("1", "true", "yes")

# AristaSSHHelper lives under taac/internal/tasks/, a Meta-internal
# subpackage not shipped in the OSS slice. The task class itself is
# still registered in OSS mode (see tasks/registry.py), but invoking
# run() requires the Meta-internal SSH helper and will raise below.
if not TAAC_OSS:
    from taac.internal.tasks.bgp_weight_policy_task import (
        AristaSSHHelper,
    )
from taac.tasks.base_task import BaseTask
from taac.utils.driver_factory import async_get_device_driver


# Path to bgpcpp startup script on EOS devices
RUN_BGPCPP_SCRIPT_PATH = "/usr/sbin/run_bgpcpp.sh"


def _build_flag_sed_commands(flag_name: str, flag_value: str) -> t.List[str]:
    """
    Build the idempotent seds that add/update one bgpcpp gflag in
    run_bgpcpp.sh, in order:
      1. drop any stale line mentioning the flag (idempotent cleanup),
      2. ensure the --max_rss_size line ends with a line continuation,
      3. insert --{flag}={value} right after the --max_rss_size line.

    Shared by the raw-SSH and managed-shell execution paths so the sed
    logic has a single source of truth.
    """
    return [
        f"bash sudo sed -i '/{flag_name}/d' {RUN_BGPCPP_SCRIPT_PATH}",
        f"bash sudo sed -i '/--max_rss_size/s/[^\\\\]$/& \\\\/' "
        f"{RUN_BGPCPP_SCRIPT_PATH}",
        f"bash sudo sed -i '/--max_rss_size/a\\      "
        f"--{flag_name}={flag_value}' {RUN_BGPCPP_SCRIPT_PATH}",
    ]


class ConfigureBgpcppStartupTask(BaseTask):
    """
    TAAC Task to configure bgpcpp startup flags in run_bgpcpp.sh.

    This task modifies the bgpcpp startup script to add or update
    command-line flags passed to the bgpcpp process. The modification
    is idempotent - existing flags are removed before being re-added.

    After modifying the script, the BGP daemon is optionally restarted
    so the new flags take effect.

    Parameters:
        hostname: Device hostname
        flags: Dictionary of flag names to values (e.g., {"agent_thrift_recv_timeout_ms": "160000"})
        ssh_user: SSH username (default: admin)
        ssh_password: SSH password
        restart_bgp: Whether to restart BGP daemon after applying (default: False)
    """

    NAME = "configure_bgpcpp_startup"

    async def run(self, params: t.Dict[str, t.Any]) -> None:
        """Run the task to configure bgpcpp startup flags."""
        hostname = params["hostname"]
        flags = params["flags"]
        restart_bgp = params.get("restart_bgp", False)
        use_managed_shell = params.get("use_managed_shell", False)

        self.logger.info(f"Configuring bgpcpp startup flags on {hostname}: {flags}")

        if use_managed_shell:
            await self._apply_flags_managed(hostname, flags, restart_bgp)
        else:
            self._apply_flags_ssh(hostname, flags, params, restart_bgp)

    async def _apply_flags_managed(
        self,
        hostname: str,
        flags: t.Dict[str, str],
        restart_bgp: bool,
    ) -> None:
        """
        Apply the run_bgpcpp.sh gflag edits over the managed device driver
        (async shell), for pipelines that run under a netcastle reservation
        rather than raw SSH (e.g. the perf-scaling sweep).
        """
        driver = await async_get_device_driver(hostname)
        for flag_name, flag_value in flags.items():
            self.logger.info(f"  Setting --{flag_name}={flag_value}")
            for cmd in _build_flag_sed_commands(flag_name, flag_value):
                await driver.async_run_cmd_on_shell(cmd)

        # A BGP restart is needed for the new flags to take effect; over the
        # managed shell the caller sequences that separately (the perf-scaling
        # sweep restarts BGP per stage), so we only warn if asked to do it here.
        if restart_bgp:
            self.logger.warning(
                "restart_bgp is not supported in managed-shell mode; the caller "
                "must restart the BGP daemon separately."
            )

        self.logger.info("Successfully configured bgpcpp startup flags")

    def _apply_flags_ssh(
        self,
        hostname: str,
        flags: t.Dict[str, str],
        params: t.Dict[str, t.Any],
        restart_bgp: bool,
    ) -> None:
        """Apply the run_bgpcpp.sh gflag edits over raw SSH (AristaSSHHelper)."""
        if TAAC_OSS:
            raise NotImplementedError(
                "ConfigureBgpcppStartupTask raw-SSH mode requires the "
                "Meta-internal AristaSSHHelper and cannot run under TAAC_OSS=1. "
                "Use use_managed_shell=True instead."
            )
        ssh_user = params.get("ssh_user", "admin")
        ssh_password = params.get("ssh_password", "")

        ssh_helper = AristaSSHHelper(
            hostname=hostname,
            username=ssh_user,
            password=ssh_password,
        )

        for flag_name, flag_value in flags.items():
            self.logger.info(f"  Setting --{flag_name}={flag_value}")
            remove_cmd, add_continuation_cmd, insert_cmd = _build_flag_sed_commands(
                flag_name, flag_value
            )

            # Step 1: Remove any existing line with this flag (idempotent cleanup)
            success, output = ssh_helper.run_command(remove_cmd)
            if not success:
                self.logger.warning(f"Failed to remove existing {flag_name}: {output}")

            # Step 2: Add line continuation to the max_rss_size line
            # (only if it doesn't already have one)
            success, output = ssh_helper.run_command(add_continuation_cmd)
            if not success:
                self.logger.warning(f"Failed to add line continuation: {output}")

            # Step 3: Insert the new flag after max_rss_size line
            success, output = ssh_helper.run_command(insert_cmd)
            if not success:
                raise Exception(f"Failed to add --{flag_name}={flag_value}: {output}")

        self.logger.info("Successfully configured bgpcpp startup flags")

        # Verify the script
        verify_cmd = f"bash grep -E '{'|'.join(flags.keys())}' {RUN_BGPCPP_SCRIPT_PATH}"
        success, output = ssh_helper.run_command(verify_cmd)
        if success:
            self.logger.info(f"Verification:\n{output.strip()}")
        else:
            self.logger.warning("Could not verify script changes")

        if restart_bgp:
            self.logger.info("Restarting BGP daemon to apply new flags...")
            if ssh_helper.reload_bgp_daemon():
                self.logger.info("BGP daemon restarted successfully")
            else:
                self.logger.warning("BGP daemon restart may have failed")

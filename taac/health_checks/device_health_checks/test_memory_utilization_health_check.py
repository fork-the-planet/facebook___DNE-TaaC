# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for MemoryUtilizationHealthCheck -- specifically the Arista VmHWM
(absolute peak resident memory) branch and its factory serialization."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.memory_utilization_health_check import (
    MemoryUtilizationHealthCheck,
)
from taac.health_checks.healthcheck_definitions import (
    create_memory_utilization_check,
)
from taac.health_check.health_check import types as hc_types


_FIND_PID = (
    "neteng.test_infra.dne.taac.health_checks.device_health_checks."
    "memory_utilization_health_check.find_process_pid"
)
# 10 GiB, the UG-spec VmHWM ceiling. PASS iff (VmHWM kB) * 1024 < this, i.e.
# VmHWM must be below 10 * 1024**2 = 10_485_760 kB.
TEN_GIB = 10 * (1024**3)


class TestMemoryUtilizationVmHwmArista(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        self.health_check = MemoryUtilizationHealthCheck(logger=self.logger)
        self.health_check.driver = AsyncMock()
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "bag011.ash6"
        self.input = hc_types.BaseHealthCheckIn()

    def _set_proc_output(self, output):
        self.health_check.driver.async_run_cmd_on_shell = AsyncMock(return_value=output)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_below_threshold_pass(self, mock_find):
        mock_find.return_value = "12345"
        self._set_proc_output("VmHWM:\t 5000000 kB")  # ~4.77 GiB < 10 GiB
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        # 5_000_000 kB * 1024 = 5_120_000_000 bytes surfaced in the message.
        self.assertIn("5120000000", result.message)
        self.assertIn("within limit", result.message)
        # Read the correct pid's /proc entry.
        self.health_check.driver.async_run_cmd_on_shell.assert_awaited_once_with(
            "bash grep VmHWM /proc/12345/status"
        )

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_above_threshold_fail(self, mock_find):
        mock_find.return_value = "12345"
        self._set_proc_output("VmHWM:\t 11000000 kB")  # ~10.49 GiB > 10 GiB
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("EXCEEDED", result.message)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_at_threshold_boundary_fail(self, mock_find):
        """Exactly at the ceiling is NOT below it -> FAIL (strict <)."""
        mock_find.return_value = "12345"
        self._set_proc_output(f"VmHWM:\t {10 * 1024 * 1024} kB")  # exactly 10 GiB
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_process_not_found_fail(self, mock_find):
        """bgpcpp not in 'show processes' -> FAIL (never SKIP)."""
        mock_find.return_value = None
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("not found", result.message)
        self.assertIn("bgpcpp", result.message)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_unparseable_output_fail(self, mock_find):
        mock_find.return_value = "12345"
        self._set_proc_output("grep: /proc/12345/status: No such file or directory")
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("could not parse", result.message)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_vmhwm_shell_error_fail(self, mock_find):
        mock_find.return_value = "12345"
        self.health_check.driver.async_run_cmd_on_shell = AsyncMock(
            side_effect=RuntimeError("fcr timeout")
        )
        result = await self.health_check._check_vmhwm_arista(self.device, TEN_GIB)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("could not read", result.message)
        self.assertIn("fcr timeout", result.message)

    @patch(_FIND_PID, new_callable=AsyncMock)
    async def test_run_arista_dispatches_to_vmhwm(self, mock_find):
        """_run_arista with a vmhwm_threshold routes to the VmHWM check."""
        mock_find.return_value = "12345"
        self._set_proc_output("VmHWM:\t 5000000 kB")
        result = await self.health_check._run_arista(
            self.device, self.input, {"vmhwm_threshold": TEN_GIB}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_run_arista_without_vmhwm_still_skips(self):
        """No vmhwm_threshold and no delta -> the existing SKIP behavior holds."""
        result = await self.health_check._run_arista(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.SKIP)


class TestCreateMemoryUtilizationCheck(unittest.TestCase):
    """Tests for the create_memory_utilization_check factory (VmHWM param)."""

    def test_factory_serializes_vmhwm_threshold(self):
        check = create_memory_utilization_check(vmhwm_threshold=TEN_GIB)
        payload = json.loads(check.check_params.json_params)
        self.assertEqual(payload["vmhwm_threshold"], TEN_GIB)

    def test_factory_omits_vmhwm_when_unset(self):
        """Omitted -> key absent, so existing factory snapshots stay stable."""
        check = create_memory_utilization_check(
            threshold=5 * (1024**3), start_time_jq_var="test_case_start_time"
        )
        payload = json.loads(check.check_params.json_params)
        self.assertNotIn("vmhwm_threshold", payload)


if __name__ == "__main__":
    unittest.main()

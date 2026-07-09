# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.device_core_dumps_health_check import (
    DeviceCoreDumpsHealthCheck,
)
from taac.health_check.health_check import types as hc_types

MODULE = (
    "neteng.test_infra.dne.taac.health_checks.device_health_checks."
    "device_core_dumps_health_check"
)

# Fixed "now" the check will observe when it calls time.time().
NOW = 1_782_954_918
# Test window opened 100s before now.
TEST_START = NOW - 100
# A core that predates the test window by days (the regression that used to FAIL).
ANCIENT_TS = NOW - 5 * 24 * 3600
# A core created inside the window (a real crash the check must catch).
IN_WINDOW_TS = NOW - 50
# A core with a future mtime (clock skew / bad %T@ parse).
FUTURE_TS = NOW + 500


def _make_device(name: str) -> MagicMock:
    device = MagicMock(spec=TestDevice)
    device.name = name
    return device


class DeviceCoreDumpsWindowTest(unittest.IsolatedAsyncioTestCase):
    """The check must only flag cores whose mtime is in (start_time, end_time]."""

    def setUp(self) -> None:
        self.check = DeviceCoreDumpsHealthCheck(
            logger=MagicMock(spec=ConsoleFileLogger)
        )
        self.device = _make_device("gtsw002")
        self.input = hc_types.BaseHealthCheckIn()

    # ---- FBOSS path (_run) -------------------------------------------------

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_ancient_core_not_flagged_with_start_time(
        self, mock_find, _mock_time
    ) -> None:
        """A days-old core predating start_time must NOT fail the check."""
        mock_find.return_value = {"fsdb.core.123": ANCIENT_TS}
        result = await self.check._run(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_ancient_core_not_flagged_when_start_time_none(
        self, mock_find, _mock_time
    ) -> None:
        """A jq expression that resolved to null puts start_time=None in
        check_params. The fail-safe must anchor to now, so ancient cores are
        NOT flagged (case (b) guard)."""
        mock_find.return_value = {"fsdb.core.123": ANCIENT_TS}
        result = await self.check._run(self.device, self.input, {"start_time": None})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_ancient_core_not_flagged_when_no_params(
        self, mock_find, _mock_time
    ) -> None:
        """THE ROOT-CAUSE PATH: a bare check produces empty check_params (no
        start_time key). Pre-fix, `.get("start_time", 0)` defaulted to 0 and
        `mtime > 0` flagged every ancient core. Post-fix the absent key anchors
        to now -> ancient core ignored -> PASS."""
        mock_find.return_value = {"fsdb.core.123": ANCIENT_TS}
        result = await self.check._run(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_explicit_zero_start_time_means_epoch(
        self, mock_find, _mock_time
    ) -> None:
        """An EXPLICIT start_time=0 is honored verbatim as epoch (no fail-safe),
        so an in-window core is flagged. Distinguishes deliberate epoch from the
        bare/null regression. No live construction passes literal 0, so this is
        purely a semantics guard."""
        mock_find.return_value = {"bgpd_main.core.9": IN_WINDOW_TS}
        result = await self.check._run(self.device, self.input, {"start_time": 0})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_in_window_core_flagged(self, mock_find, _mock_time) -> None:
        """A core created inside the test window IS a failure."""
        mock_find.return_value = {"bgpd_main.core.9": IN_WINDOW_TS}
        result = await self.check._run(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("bgpd_main.core.9", result.message or "")

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_future_core_not_flagged(self, mock_find, _mock_time) -> None:
        """A core with mtime beyond end_time (default now) is excluded."""
        mock_find.return_value = {"fsdb.core.777": FUTURE_TS}
        result = await self.check._run(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_explicit_end_time_bound(self, mock_find, _mock_time) -> None:
        """An explicit end_time excludes cores created after it, even if they
        are after start_time."""
        mock_find.return_value = {"fsdb.core.5": IN_WINDOW_TS}
        # end_time set before the in-window core → excluded.
        result = await self.check._run(
            self.device,
            self.input,
            {"start_time": TEST_START, "end_time": IN_WINDOW_TS - 10},
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_mixed_cores_only_in_window_flagged(
        self, mock_find, _mock_time
    ) -> None:
        mock_find.return_value = {
            "fsdb.core.old": ANCIENT_TS,
            "bgpd_main.core.new": IN_WINDOW_TS,
            "fsdb.core.future": FUTURE_TS,
        }
        result = await self.check._run(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("bgpd_main.core.new", result.message or "")
        self.assertNotIn("fsdb.core.old", result.message or "")
        self.assertNotIn("fsdb.core.future", result.message or "")

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_core_dumps_to_ignore_respected(self, mock_find, _mock_time) -> None:
        mock_find.return_value = {"bgpd_main.core.9": IN_WINDOW_TS}
        result = await self.check._run(
            self.device,
            self.input,
            {"start_time": TEST_START, "core_dumps_to_ignore": ["bgpd_main.core.9"]},
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    # ---- EOS/Arista path (_run_arista) ------------------------------------

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_arista_ancient_core_not_flagged(self, mock_find, _mock_time) -> None:
        # Filename without a parseable timestamp → falls back to the dict ts.
        mock_find.return_value = {"bgpd_main.core": ANCIENT_TS}
        result = await self.check._run_arista(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_arista_in_window_core_flagged(self, mock_find, _mock_time) -> None:
        mock_find.return_value = {"bgpd_main.core": IN_WINDOW_TS}
        result = await self.check._run_arista(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("bgpd_main.core", result.message or "")

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_arista_future_core_not_flagged(self, mock_find, _mock_time) -> None:
        mock_find.return_value = {"bgpd_main.core": FUTURE_TS}
        result = await self.check._run_arista(
            self.device, self.input, {"start_time": TEST_START}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_arista_ancient_core_not_flagged_when_no_params(
        self, mock_find, _mock_time
    ) -> None:
        """Bare/absent start_time on the EOS path anchors to now -> PASS."""
        mock_find.return_value = {"bgpd_main.core": ANCIENT_TS}
        result = await self.check._run_arista(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)


class DeviceCoreDumpsRealJqPathTest(unittest.IsolatedAsyncioTestCase):
    """End-to-end: build the check via the SAME factory the FPF playbooks use,
    resolve its check_params through the REAL ParameterEvaluator (modeling the
    runner's jq scope), then feed the resolved dict into `_run`. This exercises
    the actual construction + jq-resolution path, not just the comparison.

    Two constructions are covered:
      - `create_device_core_dumps_check()` (default, WITH `.test_case_start_time`
        jq param) — the FPF postcheck at _build_fpf_generic_checks (line 22603).
      - `create_device_core_dumps_check(use_start_time=False)` (BARE, no params)
        — the link-event postcheck at playbook_definitions.py line 23899, the
        construction that produced the observed "since 0" failure (ROOT CAUSE
        CASE (a): a no-jq-params bare check → start_time absent → 0).
    """

    def setUp(self) -> None:
        self.check = DeviceCoreDumpsHealthCheck(
            logger=MagicMock(spec=ConsoleFileLogger)
        )
        self.device = _make_device("gtsw002")
        self.input = hc_types.BaseHealthCheckIn()

    @staticmethod
    def _resolve_params(check, jq_vars):
        """Resolve a check's check_params exactly like TaacRunner does at stage
        run time: through ParameterEvaluator with the live jq_vars dict.

        `eval_jq` is stubbed to model pyjq's `.key` semantics (present key ->
        value, absent key -> None) because pyjq is unavailable on Py3.12+.
        """
        from neteng.test_infra.dne.taac.libs import parameter_evaluator as pe_mod
        from taac.libs.parameter_evaluator import (
            ParameterEvaluator,
        )

        def fake_eval_jq(jq_expr, vars_):
            # Model `.some_key` lookups against the jq_vars dict.
            key = jq_expr.lstrip(".")
            return vars_.get(key)

        evaluator = ParameterEvaluator(jq_vars=jq_vars)
        with patch.object(pe_mod, "eval_jq", side_effect=fake_eval_jq):
            return evaluator.evaluate(check.check_params)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_fpf_default_postcheck_ancient_core_passes(
        self, mock_find, _mock_time
    ) -> None:
        """FPF default postcheck: `.test_case_start_time` resolves to the real
        epoch, so a 6-day-old core is outside (start, now] -> PASS."""
        from taac.health_checks.healthcheck_definitions import (
            create_device_core_dumps_check,
        )

        check = create_device_core_dumps_check()  # default, WITH start_time
        params = self._resolve_params(check, {"test_case_start_time": TEST_START})
        self.assertEqual(params.get("start_time"), TEST_START)
        mock_find.return_value = {"fsdb.core.old": ANCIENT_TS}
        result = await self.check._run(self.device, self.input, params)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_bare_link_event_postcheck_ancient_core_passes(
        self, mock_find, _mock_time
    ) -> None:
        """ROOT CAUSE REPRODUCTION: the bare link-event postcheck has no
        check_params, so ParameterEvaluator returns {} (start_time ABSENT).
        Pre-fix this defaulted to 0 and flagged a 6-day-old core. Post-fix the
        check anchors to now -> ancient core is ignored -> PASS."""
        from taac.health_checks.healthcheck_definitions import (
            create_device_core_dumps_check,
        )

        check = create_device_core_dumps_check(use_start_time=False)  # BARE
        self.assertIsNone(check.check_params)
        params = self._resolve_params(check, {"test_case_start_time": TEST_START})
        self.assertEqual(params, {})  # start_time genuinely absent, not 0
        mock_find.return_value = {"fsdb.core.old": ANCIENT_TS}
        result = await self.check._run(self.device, self.input, params)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_fpf_default_postcheck_in_window_core_fails(
        self, mock_find, _mock_time
    ) -> None:
        """A real crash inside the window is still caught via the real path."""
        from taac.health_checks.healthcheck_definitions import (
            create_device_core_dumps_check,
        )

        check = create_device_core_dumps_check()
        params = self._resolve_params(check, {"test_case_start_time": TEST_START})
        mock_find.return_value = {"bgpd_main.core.new": IN_WINDOW_TS}
        result = await self.check._run(self.device, self.input, params)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("bgpd_main.core.new", result.message or "")

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_fpf_default_postcheck_future_core_ignored(
        self, mock_find, _mock_time
    ) -> None:
        """A core with a future mtime (> end_time default now) is ignored."""
        from taac.health_checks.healthcheck_definitions import (
            create_device_core_dumps_check,
        )

        check = create_device_core_dumps_check()
        params = self._resolve_params(check, {"test_case_start_time": TEST_START})
        mock_find.return_value = {"fsdb.core.future": FUTURE_TS}
        result = await self.check._run(self.device, self.input, params)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    @patch(f"{MODULE}.time.time", return_value=NOW)
    @patch(f"{MODULE}.async_find_critical_core_dumps", new_callable=AsyncMock)
    async def test_default_postcheck_missing_jq_var_is_failsafe(
        self, mock_find, _mock_time
    ) -> None:
        """CASE (b) guard: even if the factory emits the start_time jq param but
        `.test_case_start_time` is ABSENT from the runner's jq context, the jq
        resolves to null (None) -> the check's fail-safe anchors to now instead
        of treating null as epoch -> ancient core ignored -> PASS."""
        from taac.health_checks.healthcheck_definitions import (
            create_device_core_dumps_check,
        )

        check = create_device_core_dumps_check()
        params = self._resolve_params(check, {})  # jq var absent -> None
        self.assertIsNone(params.get("start_time"))
        mock_find.return_value = {"fsdb.core.old": ANCIENT_TS}
        result = await self.check._run(self.device, self.input, params)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)


if __name__ == "__main__":
    unittest.main()

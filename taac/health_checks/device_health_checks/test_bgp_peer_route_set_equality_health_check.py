# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for BgpPeerRouteSetEqualityHealthCheck."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.bgp_peer_route_set_equality_health_check import (
    BgpPeerRouteSetEqualityHealthCheck,
)
from taac.health_checks.healthcheck_definitions import (
    create_bgp_peer_route_set_equality_check,
)
from taac.health_check.health_check import types as hc_types


class _P:
    """Module-scope TIpPrefix mock so instances across calls compare equal."""

    def __init__(self, addr, prefix_len):
        self.prefix = addr
        self.prefix_length = prefix_len

    def __eq__(self, other):
        return (
            isinstance(other, _P)
            and self.prefix == other.prefix
            and self.prefix_length == other.prefix_length
        )

    def __hash__(self):
        return hash((self.prefix, self.prefix_length))

    def __repr__(self):
        return f"{self.prefix}/{self.prefix_length}"


def _prefix(addr, length=128):
    """Build a TIpPrefix-like mock comparable + hashable by (addr, length)."""
    return _P(addr, length)


def _prefixes(n, base="2401:db00:1::", length=128):
    """Return n prefixes addr `base{i}` length /128 (mock TBgpPath value=None)."""
    return {_prefix(f"{base}{i}", length): MagicMock() for i in range(n)}


BASELINE = "2401:db00::11"
TESTED_1 = "2401:db00::13"
TESTED_2 = "2401:db00::15"


class BgpPeerRouteSetEqualityHealthCheckTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        self.hc = BgpPeerRouteSetEqualityHealthCheck(logger=self.logger)
        self.hc.driver = AsyncMock()
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "bag012.ash6"
        self.input = hc_types.BaseHealthCheckIn()

    def _wire(self, per_peer):
        """Wire async_get_postfilter_advertised_networks to per-peer dicts."""

        async def fake(peer):
            return per_peer[peer]

        self.hc.driver.async_get_postfilter_advertised_networks = AsyncMock(
            side_effect=fake
        )

    async def test_passes_when_baseline_and_tested_match(self):
        shared = _prefixes(300)
        self._wire({BASELINE: shared, TESTED_1: shared, TESTED_2: shared})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1, TESTED_2],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_fails_when_tested_missing_prefixes(self):
        baseline = _prefixes(300)
        tested = dict(list(baseline.items())[:200])
        self._wire({BASELINE: baseline, TESTED_1: tested})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("MISSING", result.message)
        self.assertIn(TESTED_1, result.message)

    async def test_fails_when_tested_has_extra_prefixes_strict(self):
        baseline = _prefixes(300)
        extra_one = _prefix("2401:db00:1::extra", 128)
        tested = {**baseline, extra_one: MagicMock()}
        self._wire({BASELINE: baseline, TESTED_1: tested})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("EXTRA", result.message)

    async def test_extra_tolerated_when_allow_extra_in_tested(self):
        baseline = _prefixes(300)
        extra_one = _prefix("2401:db00:1::extra", 128)
        tested = {**baseline, extra_one: MagicMock()}
        self._wire({BASELINE: baseline, TESTED_1: tested})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "allow_extra_in_tested": True,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_anchor_route_count_passes_at_exact_value(self):
        shared = _prefixes(300)
        self._wire({BASELINE: shared, TESTED_1: shared})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_route_count": 300,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_anchor_route_count_fails_when_both_off(self):
        """The "all peers wrong with the same count" failure: set equality
        passes but the anchor catches the actual error (e.g. stale 500 when
        we expected 300 post-withdrawal)."""
        shared = _prefixes(500)
        self._wire({BASELINE: shared, TESTED_1: shared})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_route_count": 300,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        # Both baseline and tested should be flagged.
        self.assertIn("Baseline", result.message)
        self.assertIn("Tested", result.message)

    async def test_missing_required_params_returns_fail(self):
        result = await self.hc._run(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("baseline_peer_addr", result.message)

    async def test_thrift_error_returns_error(self):
        self.hc.driver.async_get_postfilter_advertised_networks = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.ERROR)

    async def test_arista_cli_falls_back_to_thrift_on_bgp_inactive(self):
        """ARISTA_FBOSS path: CLI raises "BGP inactive" -> delegate to thrift."""
        shared = _prefixes(300)
        self._wire({BASELINE: shared, TESTED_1: shared})
        self.hc.driver.async_execute_show_json_on_shell = AsyncMock(
            side_effect=Exception("BGP inactive")
        )
        result = await self.hc._run_arista(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_arista_cli_falls_back_to_thrift_on_invalid_input(self):
        """ARISTA_FBOSS path: CLI raises "% Invalid input" (BGP++ doesn't
        expose the EOS received-routes CLI surface) -> delegate to thrift."""
        shared = _prefixes(300)
        self._wire({BASELINE: shared, TESTED_1: shared})
        self.hc.driver.async_execute_show_json_on_shell = AsyncMock(
            side_effect=Exception(
                "Running command: show bgp ipv6 unicast neighbors ... "
                "resulted in exception. Response received was: % Invalid input"
            )
        )
        result = await self.hc._run_arista(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    # --- factory ---

    def test_factory_emits_correct_check_name(self):
        check = create_bgp_peer_route_set_equality_check(
            baseline_peer_addr=BASELINE,
            tested_peer_addrs=[TESTED_1],
            anchor_route_count=300,
        )
        self.assertEqual(
            check.name, hc_types.CheckName.BGP_PEER_ROUTE_SET_EQUALITY_CHECK
        )
        params = json.loads(check.check_params.json_params)
        self.assertEqual(params["baseline_peer_addr"], BASELINE)
        self.assertEqual(params["tested_peer_addrs"], [TESTED_1])
        self.assertEqual(params["anchor_route_count"], 300)

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for BgpReceivedRouteCommunityHealthCheck."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.bgp_received_route_community_health_check import (
    BgpReceivedRouteCommunityHealthCheck,
)
from taac.health_checks.healthcheck_definitions import (
    create_bgp_received_route_community_check,
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
    return _P(addr, length)


def _path_with_communities(communities):
    """Build a TBgpPath-like mock. The production TBgpPath thrift struct has
    field 3 ``communities`` (list[TBgpCommunity]) -- mirror that name here.
    Pin ``community_list`` to None so the HC's defensive fallback doesn't
    accidentally read a MagicMock auto-attr."""
    path = MagicMock()
    path.communities = list(communities)
    path.community_list = None
    return path


def _route_map(n, communities, base="2401:db00:1::"):
    return {
        _prefix(f"{base}{i}"): _path_with_communities(communities) for i in range(n)
    }


BASELINE = "2401:db00::11"
TESTED_1 = "2401:db00::13"
TESTED_2 = "2401:db00::15"

OLD_COMM = "65529:39744"
NEW_COMM = "0:665"


class BgpReceivedRouteCommunityHealthCheckTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        self.hc = BgpReceivedRouteCommunityHealthCheck(logger=self.logger)
        self.hc.driver = AsyncMock()
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "bag012.ash6"
        self.input = hc_types.BaseHealthCheckIn()

    def _wire(self, per_peer):
        async def fake(peer):
            return per_peer[peer]

        self.hc.driver.async_get_postfilter_advertised_networks = AsyncMock(
            side_effect=fake
        )

    async def test_passes_when_all_peers_have_anchor_community(self):
        routes = _route_map(200, [NEW_COMM])
        self._wire({BASELINE: routes, TESTED_1: routes, TESTED_2: routes})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1, TESTED_2],
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_fails_when_held_back_has_stale_community(self):
        """2.4.3 spec failure mode: held-back peer ends up with the OLD
        community despite the mutation."""
        new_routes = _route_map(200, [NEW_COMM])
        stale_routes = _route_map(200, [OLD_COMM])
        self._wire({BASELINE: new_routes, TESTED_1: stale_routes, TESTED_2: new_routes})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1, TESTED_2],
                "anchor_community": NEW_COMM,
                "forbidden_communities": [OLD_COMM],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn(TESTED_1, result.message)
        # Both the anchor-missing AND forbidden-present checks should flag it.
        self.assertIn("missing anchor community", result.message)
        self.assertIn("forbidden community", result.message)

    async def test_fails_on_per_prefix_community_drift(self):
        """Same anchor, but baseline has [NEW_COMM] and tested has
        [NEW_COMM, "extra:1"] -- per-prefix equality catches the drift even
        though anchor is present."""
        baseline_routes = _route_map(50, [NEW_COMM])
        # Tested has the anchor PLUS an extra community on every prefix.
        tested_routes = _route_map(50, [NEW_COMM, "extra:1"])
        self._wire({BASELINE: baseline_routes, TESTED_1: tested_routes})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("community mismatch", result.message)

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
        routes = _route_map(50, [NEW_COMM])
        self._wire({BASELINE: routes, TESTED_1: routes})
        self.hc.driver.async_execute_show_json_on_shell = AsyncMock(
            side_effect=Exception("BGP inactive")
        )
        result = await self.hc._run_arista(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_arista_cli_falls_back_to_thrift_on_invalid_input(self):
        """ARISTA_FBOSS path: BGP++ doesn't expose the EOS received-routes
        CLI surface, so the CLI raises "% Invalid input" -> delegate to thrift."""
        routes = _route_map(50, [NEW_COMM])
        self._wire({BASELINE: routes, TESTED_1: routes})
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
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    # --- regression: TBgpCommunity struct handling (T271301144) ---

    async def test_handles_tbgpcommunity_struct_from_live_thrift(self):
        """Regression test: post-T271301144 bgpcpp returns TBgpCommunity
        thrift structs (with .asn + .value attrs), not plain strings. The
        HC must normalize struct -> 'asn:value' string to compare against
        anchor/forbidden communities. Bug observed on bag012 2026-06-23:
        empirically captured `TBgpCommunity(asn=65529, value=39744,
        community=...)` which the old _normalize_community stringified
        as 'TBgpCommunity(...)' and never matched the test's '65529:39744'
        anchor."""
        # Mimic the real thrift struct shape (.asn + .value) -- immutable
        # NamedTuple satisfies B903 / matches the read-only nature of the
        # actual TBgpCommunity binding.
        from collections import namedtuple

        _MockTBgpCommunity = namedtuple("_MockTBgpCommunity", ["asn", "value"])
        anchor_struct = _MockTBgpCommunity(asn=65529, value=39744)
        other_struct = _MockTBgpCommunity(asn=65060, value=10012)
        path = MagicMock()
        path.communities = [anchor_struct, other_struct]
        path.community_list = None

        async def fake(peer):
            return {_prefix("2401:db00:1::0"): path}

        self.hc.driver.async_get_postfilter_advertised_networks = AsyncMock(
            side_effect=fake
        )
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_community": "65529:39744",
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    # --- adj-RIB-IN mode (sender_peer_addr) ---

    async def test_adj_rib_in_passes_when_sender_carries_anchor(self):
        """``sender_peer_addr`` set -> HC probes ``getPrefilterReceivedNetworks``
        for that single peer and evaluates against the anchor. Wrapper
        contract verification path."""
        routes = _route_map(750, [NEW_COMM])

        async def fake(peer):
            return routes

        self.hc.driver.async_get_prefilter_received_networks = AsyncMock(
            side_effect=fake
        )
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "sender_peer_addr": BASELINE,
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        self.hc.driver.async_get_prefilter_received_networks.assert_awaited_once_with(
            BASELINE
        )

    async def test_adj_rib_in_errors_when_thrift_query_fails(self):
        self.hc.driver.async_get_prefilter_received_networks = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "sender_peer_addr": BASELINE,
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.ERROR)
        self.assertIn("adj-RIB-IN", result.message)
        self.assertIn(BASELINE, result.message)

    async def test_adj_rib_in_arista_delegates_to_thrift(self):
        """EOS CLI has no adj-RIB-IN equivalent -- ``_run_arista`` must
        delegate to ``_run`` (thrift) when ``sender_peer_addr`` is set,
        skipping the CLI code path entirely."""
        routes = _route_map(50, [NEW_COMM])

        async def fake(peer):
            return routes

        self.hc.driver.async_get_prefilter_received_networks = AsyncMock(
            side_effect=fake
        )
        # If _run_arista tried its CLI path, this AsyncMock would blow up.
        self.hc.driver.async_execute_show_json_on_shell = AsyncMock(
            side_effect=AssertionError("CLI path must not be taken in adj-RIB-IN mode")
        )
        result = await self.hc._run_arista(
            self.device,
            self.input,
            {
                "sender_peer_addr": BASELINE,
                "anchor_community": NEW_COMM,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        self.hc.driver.async_execute_show_json_on_shell.assert_not_awaited()

    # --- factory ---

    def test_factory_emits_correct_check_name(self):
        check = create_bgp_received_route_community_check(
            baseline_peer_addr=BASELINE,
            tested_peer_addrs=[TESTED_1],
            anchor_community=NEW_COMM,
            forbidden_communities=[OLD_COMM],
        )
        self.assertEqual(
            check.name, hc_types.CheckName.BGP_RECEIVED_ROUTE_COMMUNITY_CHECK
        )
        params = json.loads(check.check_params.json_params)
        self.assertEqual(params["baseline_peer_addr"], BASELINE)
        self.assertEqual(params["anchor_community"], NEW_COMM)
        self.assertEqual(params["forbidden_communities"], [OLD_COMM])

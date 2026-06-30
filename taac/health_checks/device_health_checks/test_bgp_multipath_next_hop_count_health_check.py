# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for BgpMultipathNextHopCountHealthCheck.

Covers the measure-don't-assert discovery mode (modal-width selection +
optional sanity bounds), and width-relative validation mode
(use_discovered_width + peers_stopped_delta math).
"""

import socket
import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.bgp_multipath_next_hop_count_health_check import (
    BgpMultipathNextHopCountHealthCheck,
)
from taac.health_check.health_check import types as hc_types


def _packed_ipv4(addr: str) -> bytes:
    return socket.inet_pton(socket.AF_INET, addr)


def _make_prefix(addr: str, num_bits: int):
    prefix = MagicMock()
    prefix.prefix_bin = _packed_ipv4(addr)
    prefix.num_bits = num_bits
    return prefix


def _make_path(next_hop_addr: str, as_path_value=None):
    """Build a path with a next-hop and (optionally) a non-empty AS_PATH.

    A non-empty AS_PATH marks the route as eBGP; otherwise it's treated as
    iBGP/local and discovery will skip it.
    """
    path = MagicMock()
    next_hop = MagicMock()
    next_hop.prefix_bin = _packed_ipv4(next_hop_addr)
    path.next_hop = next_hop
    # MagicMock auto-creates attrs; spec= None so hasattr() returns True for
    # everything. Set AS_PATH explicitly to control eBGP detection.
    path.as_path = as_path_value
    path.asPath = None
    path.as_path_segments = None
    path.aspath = None
    path.path_attributes = None
    return path


def _make_entry(prefix_addr: str, num_bits: int, next_hops, is_ebgp: bool = True):
    """Build a RIB entry whose best_group contains one path per next_hop addr."""
    entry = MagicMock()
    entry.prefix = _make_prefix(prefix_addr, num_bits)
    as_path = [65001] if is_ebgp else None
    entry.best_group = "bg"
    entry.paths = {"bg": [_make_path(nh, as_path) for nh in next_hops]}
    return entry


def _logger():
    return ConsoleFileLogger("test_bgp_multipath_hc")


def _make_hc():
    """Fresh HC with mocked driver. Class state is reset by every test."""
    device = MagicMock(spec=TestDevice)
    device.name = "test_dut"
    hc = BgpMultipathNextHopCountHealthCheck(logger=_logger())
    hc.driver = MagicMock()
    hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=[])
    hc.driver.async_get_bgp_originated_routes = AsyncMock(return_value=[])
    return hc, device


class BgpMultipathDiscoveryModeTest(unittest.IsolatedAsyncioTestCase):
    """Discovery mode: measure modal width + optional sanity bounds."""

    def setUp(self):
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = set()
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = None

    async def test_modal_width_wins_in_mixed_distribution(self):
        """5 prefixes @ 4-way, 3 prefixes @ 8-way, 1 prefix @ 16-way → mode is 4."""
        hc, device = _make_hc()
        entries = []
        for i in range(5):
            entries.append(
                _make_entry(
                    f"10.0.{i}.0",
                    24,
                    [f"10.1.0.{j}" for j in range(4)],
                )
            )
        for i in range(3):
            entries.append(
                _make_entry(
                    f"10.2.{i}.0",
                    24,
                    [f"10.1.0.{j}" for j in range(8)],
                )
            )
        entries.append(_make_entry("10.3.0.0", 24, [f"10.1.0.{j}" for j in range(16)]))
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(device, MagicMock(), {"discover_baseline": True})

        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS, result.message)
        self.assertEqual(
            BgpMultipathNextHopCountHealthCheck._discovered_baseline_width, 4
        )
        self.assertEqual(
            len(BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes), 5
        )

    async def test_single_nh_prefixes_excluded_by_min_multipath_width(self):
        """Default min_multipath_width=2 excludes single-NH prefixes."""
        hc, device = _make_hc()
        entries = [_make_entry(f"10.0.{i}.0", 24, ["10.1.0.1"]) for i in range(10)]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(device, MagicMock(), {"discover_baseline": True})

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("No multipath eBGP prefixes", result.message)
        self.assertIsNone(
            BgpMultipathNextHopCountHealthCheck._discovered_baseline_width
        )

    async def test_empty_rib_fails(self):
        hc, device = _make_hc()

        result = await hc._run(device, MagicMock(), {"discover_baseline": True})

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("No multipath eBGP prefixes", result.message)

    async def test_sanity_bound_below_min_fails(self):
        """Mode measures 4 but expected_min_baseline_width=8 → FAIL with reason."""
        hc, device = _make_hc()
        entries = [
            _make_entry(f"10.0.{i}.0", 24, [f"10.1.0.{j}" for j in range(4)])
            for i in range(5)
        ]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {"discover_baseline": True, "expected_min_baseline_width": 8},
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("expected_min_baseline_width", result.message)
        # Discovery failed sanity-check → state must not be written.
        self.assertIsNone(
            BgpMultipathNextHopCountHealthCheck._discovered_baseline_width
        )

    async def test_sanity_bound_above_max_fails(self):
        hc, device = _make_hc()
        entries = [
            _make_entry(f"10.0.{i}.0", 24, [f"10.1.0.{j}" for j in range(16)])
            for i in range(5)
        ]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {"discover_baseline": True, "expected_max_baseline_width": 8},
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("expected_max_baseline_width", result.message)

    async def test_legacy_baseline_nexthop_count_mismatch_fails(self):
        """Legacy exact-match selector: if supplied, measured width must equal it."""
        hc, device = _make_hc()
        entries = [
            _make_entry(f"10.0.{i}.0", 24, [f"10.1.0.{j}" for j in range(4)])
            for i in range(5)
        ]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {"discover_baseline": True, "baseline_nexthop_count": 140},
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("baseline_nexthop_count", result.message)

    async def test_ibgp_routes_excluded_by_default(self):
        """ebgp_only defaults to True; iBGP entries don't enter the distribution."""
        hc, device = _make_hc()
        entries = [
            _make_entry(
                f"10.0.{i}.0",
                24,
                [f"10.1.0.{j}" for j in range(4)],
                is_ebgp=False,
            )
            for i in range(5)
        ]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(device, MagicMock(), {"discover_baseline": True})

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("No multipath eBGP prefixes", result.message)


class BgpMultipathValidationModeTest(unittest.IsolatedAsyncioTestCase):
    """Validation mode: width-relative expected count + skip-when-unprimed."""

    def setUp(self):
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = set()
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = None

    async def test_use_discovered_width_without_prior_discovery_skips(self):
        """No measurement stored → validation SKIPs (not FAILs)."""
        hc, device = _make_hc()

        result = await hc._run(
            device,
            MagicMock(),
            {"use_discovered_width": True, "peers_stopped_delta": 3},
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.SKIP)
        self.assertIn("no baseline width discovered", result.message)

    async def test_delta_exceeds_width_errors(self):
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = 4
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = {
            "10.0.0.0/24"
        }
        hc, device = _make_hc()

        result = await hc._run(
            device,
            MagicMock(),
            {
                "use_discovered_width": True,
                "use_discovered_prefixes": True,
                "peers_stopped_delta": 99,
            },
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.ERROR)
        self.assertIn("exceeds", result.message)

    async def test_reduce_assertion_uses_measured_width_minus_delta(self):
        """Width=8, delta=3 → expected_nexthop_count=5. Entries with 5 NHs PASS."""
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = 8
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = {
            "10.0.0.0/24",
            "10.0.1.0/24",
        }
        hc, device = _make_hc()
        entries = [
            _make_entry("10.0.0.0", 24, [f"10.1.0.{j}" for j in range(5)]),
            _make_entry("10.0.1.0", 24, [f"10.1.0.{j}" for j in range(5)]),
        ]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {
                "use_discovered_width": True,
                "use_discovered_prefixes": True,
                "peers_stopped_delta": 3,
            },
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS, result.message)

    async def test_reduce_assertion_fails_when_width_did_not_drop(self):
        """Width=8, delta=3 → expected 5. But RIB still has 8 → FAIL."""
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = 8
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = {
            "10.0.0.0/24"
        }
        hc, device = _make_hc()
        entries = [_make_entry("10.0.0.0", 24, [f"10.1.0.{j}" for j in range(8)])]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {
                "use_discovered_width": True,
                "use_discovered_prefixes": True,
                "peers_stopped_delta": 3,
            },
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("expected exactly 5, got 8", result.message)

    async def test_restore_assertion_delta_zero_expects_baseline(self):
        """delta=0 (restore) → expected_nexthop_count=width=8. Entries with 8 NHs PASS."""
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_width = 8
        BgpMultipathNextHopCountHealthCheck._discovered_baseline_prefixes = {
            "10.0.0.0/24"
        }
        hc, device = _make_hc()
        entries = [_make_entry("10.0.0.0", 24, [f"10.1.0.{j}" for j in range(8)])]
        hc.driver.async_get_bgp_rib_entries = AsyncMock(return_value=entries)

        result = await hc._run(
            device,
            MagicMock(),
            {
                "use_discovered_width": True,
                "use_discovered_prefixes": True,
                "peers_stopped_delta": 0,
            },
        )

        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS, result.message)

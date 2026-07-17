# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""build_sweep_peer_list threads v4_peer_start_offset to the v4 peer generators.

The perf-scaling sweep must generate v4 peers at the same host offset as the
device's v4 secondary interface IPs (IXIA_IPV4_START_OFFSET=10); otherwise the
v4 peers get local source addresses the interface does not have and the sessions
stay IDLE (P2415335739). v6 is unaffected (both interface IPs and peers use 16).
"""

import unittest

from taac.testconfigs.routing.util.bgp_ebb_constants import (
    IXIA_IPV4_START_OFFSET,
)
from taac.testconfigs.routing.util.bgp_ebb_setup_tasks import (
    build_sweep_peer_list,
)

_IBGP_V4_BASE = "10.164.28"
_EBGP_V4_BASE = "10.163.28"


def _sweep(v4_offset: int):
    return build_sweep_peer_list(
        ebgp_remote_as=65334,
        ibgp_remote_as=64981,
        ebgp_v6_base="2401:db00:e50d:11:8",
        ebgp_v4_base=_EBGP_V4_BASE,
        ibgp_v6_base="2401:db00:e50d:11:9",
        ibgp_v4_base=_IBGP_V4_BASE,
        peergroup_ebgp_v6="EB-FA-V6",
        peergroup_ebgp_v4="EB-FA-V4",
        peergroup_ibgp_v6="EB-EB-V6",
        peergroup_ibgp_v4="EB-EB-V4",
        ebgp_peer_count=1,
        ibgp_peer_count=3,
        v4_peer_start_offset=v4_offset,
    )


def _v4_locals(peers, base: str):
    return [p["local_addr"] for p in peers if p["local_addr"].startswith(base + ".")]


class SweepPeerV4OffsetTest(unittest.TestCase):
    def test_offset_10_aligns_v4_local_addrs_with_interface(self) -> None:
        peers = _sweep(IXIA_IPV4_START_OFFSET)
        self.assertEqual(_v4_locals(peers, _EBGP_V4_BASE), ["10.163.28.10"])
        self.assertEqual(
            _v4_locals(peers, _IBGP_V4_BASE),
            ["10.164.28.10", "10.164.28.12", "10.164.28.14"],
        )

    def test_offset_is_threaded_not_hardcoded(self) -> None:
        # A different offset must shift the v4 locals (proves the param is wired).
        peers = _sweep(16)
        self.assertEqual(_v4_locals(peers, _EBGP_V4_BASE), ["10.163.28.16"])
        self.assertEqual(
            _v4_locals(peers, _IBGP_V4_BASE),
            ["10.164.28.16", "10.164.28.18", "10.164.28.20"],
        )

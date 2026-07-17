# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP++ EBB characteristic ad-hoc testconfigs (egress peer-scale / perf-scaling).

Re-homed here after D111520998 consolidated ``cicd_ebb_int_tc.py`` down to the
8 conveyor-scheduled configs. The bag010 egress peer-scale (perf-scaling case1)
sweep is runnable via the Netcastle CLI (``--test-config``) but is not (yet)
wired into a ``dne_routing`` conveyor node, so it belongs in this ad-hoc
catalog rather than in ``cicd_ebb_int_tc.py`` (which is now the scheduled-only
source of truth).

External consumers import from this member module directly; see README.md §7.
"""

from taac.testconfigs.routing.factories.bgp_ebb_characteristic import (
    create_bgp_ebb_characteristic_performance_scaling_test_config,
)
from taac.testconfigs.routing.testbed import BAG010_ASH6


# ─── bag010.ash6 — SC1 Egress peer-scale (scale & characteristics case 1) ─
# Testbed-driven characteristic factory (2-port, no BGP-MON); bag010 relies on
# the device-default router-id (no pinned router_id on the testbed). Ad-hoc:
# resolvable via ``--test-config`` but not scheduled on a conveyor node. The
# TestConfig.name is ``BAG010_ASH6_SC1_EGRESS_PEER_SCALE_TEST`` (+ ``_UPDATE_GROUP``).
BAG010_ASH6_SC1_EGRESS_PEER_SCALE_TEST_CONFIG = (
    create_bgp_ebb_characteristic_performance_scaling_test_config(BAG010_ASH6)
)
BAG010_ASH6_SC1_EGRESS_PEER_SCALE_TEST_UPDATE_GROUP_CONFIG = (
    create_bgp_ebb_characteristic_performance_scaling_test_config(
        BAG010_ASH6, enable_update_group=True
    )
)


__all__ = [
    "BAG010_ASH6_SC1_EGRESS_PEER_SCALE_TEST_CONFIG",
    "BAG010_ASH6_SC1_EGRESS_PEER_SCALE_TEST_UPDATE_GROUP_CONFIG",
]

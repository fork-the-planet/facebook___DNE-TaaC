# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""EBB integration testconfigs scheduled on the CICD conveyor.

Successor to ``conveyor_node_test_configs.py`` under
``routing/ebb/ebb_bgp_plus_plus_test_config/ebb_bgp_plus_plus_conveyor/``.
Holds bag conveyor testconfigs and the aggregated
``EBB_BGP_PLUS_PLUS_CONVEYOR_NODE_TEST_CONFIGS`` list.

External consumers import via ``testconfigs.routing`` root; see README.md §7.
"""

from taac.testconfigs.routing.factories.bgp_ebb_full_scale import (
    create_ebb_cold_start_and_daemon_restart_test_config,
)
from taac.testconfigs.routing.testbed import BAG002_SNC1


# ─── Diff 5 — BAG002_SNC1 conveyor (cold_start + daemon_restart) ────────────
# TestConfig constant name grandfathered from bag002_snc1_test_config.py
# (Wave 4 renames to fit the {TESTBED}_{FACTORY}_{VARIANT}_TEST_CONFIG shape).
# The internal ``TestConfig.name`` field is preserved verbatim as
# ``BAG002_SNC1_BGP_CONVEYOR_TEST`` so the golden manifest is byte-wise
# identical to pre-migration.
BAG002_SNC1_CONVEYOR_TEST_CONFIG = create_ebb_cold_start_and_daemon_restart_test_config(
    BAG002_SNC1
)


__all__ = [
    "BAG002_SNC1_CONVEYOR_TEST_CONFIG",
]

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
    create_ebb_drain_test_config,
    create_ebb_instability_test_config,
    create_ebb_longevity_test_config,
    create_ebb_runtime_update_test_config,
    create_ebb_stage1_consolidated_test_config,
)
from taac.testconfigs.routing.testbed import (
    BAG002_SNC1,
    BAG010_ASH6,
)


# ─── Diff 5 — BAG002_SNC1 conveyor (cold_start + daemon_restart) ────────────
# TestConfig constant name grandfathered from bag002_snc1_test_config.py
# (Wave 4 renames to fit the {TESTBED}_{FACTORY}_{VARIANT}_TEST_CONFIG shape).
# The internal ``TestConfig.name`` field is preserved verbatim as
# ``BAG002_SNC1_BGP_CONVEYOR_TEST`` so the golden manifest is byte-wise
# identical to pre-migration.
BAG002_SNC1_CONVEYOR_TEST_CONFIG = create_ebb_cold_start_and_daemon_restart_test_config(
    BAG002_SNC1
)


# ─── Diff 6 — BAG010_ASH6 conveyor family (5 factories × baseline+UG) ───────
# TestConfig constant names + internal ``TestConfig.name`` field values are
# grandfathered from ``bag010_ash6_test_config.py`` (Wave 4 renames). Golden
# manifest hashes for the 6 tracked configs (DRAIN / RUNTIME_UPDATE /
# LONGEVITY, each with ``_UPDATE_GROUP`` sibling) are preserved byte-wise.
# INSTABILITY + STAGE1 variants are on the golden's nondeterministic-serialization
# allowlist so their hashes are not tracked, but the internal ``TestConfig.name``
# is preserved so the allowlist entries still match.
BAG010_ASH6_BGP_STAGE1_CONVEYOR_TEST_CONFIG = (
    create_ebb_stage1_consolidated_test_config(BAG010_ASH6)
)
BAG010_ASH6_BGP_STAGE1_CONVEYOR_TEST_UPDATE_GROUP_CONFIG = (
    create_ebb_stage1_consolidated_test_config(BAG010_ASH6, enable_update_group=True)
)
BAG010_ASH6_INSTABILITY_CONVEYOR_TEST_CONFIG = create_ebb_instability_test_config(
    BAG010_ASH6
)
BAG010_ASH6_INSTABILITY_CONVEYOR_TEST_UPDATE_GROUP_CONFIG = (
    create_ebb_instability_test_config(BAG010_ASH6, enable_update_group=True)
)
BAG010_ASH6_RUNTIME_UPDATE_CONVEYOR_TEST_CONFIG = create_ebb_runtime_update_test_config(
    BAG010_ASH6
)
BAG010_ASH6_RUNTIME_UPDATE_CONVEYOR_TEST_UPDATE_GROUP_CONFIG = (
    create_ebb_runtime_update_test_config(BAG010_ASH6, enable_update_group=True)
)
BAG010_ASH6_DRAIN_CONVEYOR_TEST_CONFIG = create_ebb_drain_test_config(BAG010_ASH6)
BAG010_ASH6_DRAIN_CONVEYOR_TEST_UPDATE_GROUP_CONFIG = create_ebb_drain_test_config(
    BAG010_ASH6, enable_update_group=True
)
BAG010_ASH6_CONVEYOR_LONGEVITY_TEST_CONFIG = create_ebb_longevity_test_config(
    BAG010_ASH6
)
BAG010_ASH6_CONVEYOR_LONGEVITY_TEST_UPDATE_GROUP_CONFIG = (
    create_ebb_longevity_test_config(BAG010_ASH6, enable_update_group=True)
)


__all__ = [
    "BAG002_SNC1_CONVEYOR_TEST_CONFIG",
    "BAG010_ASH6_BGP_STAGE1_CONVEYOR_TEST_CONFIG",
    "BAG010_ASH6_BGP_STAGE1_CONVEYOR_TEST_UPDATE_GROUP_CONFIG",
    "BAG010_ASH6_CONVEYOR_LONGEVITY_TEST_CONFIG",
    "BAG010_ASH6_CONVEYOR_LONGEVITY_TEST_UPDATE_GROUP_CONFIG",
    "BAG010_ASH6_DRAIN_CONVEYOR_TEST_CONFIG",
    "BAG010_ASH6_DRAIN_CONVEYOR_TEST_UPDATE_GROUP_CONFIG",
    "BAG010_ASH6_INSTABILITY_CONVEYOR_TEST_CONFIG",
    "BAG010_ASH6_INSTABILITY_CONVEYOR_TEST_UPDATE_GROUP_CONFIG",
    "BAG010_ASH6_RUNTIME_UPDATE_CONVEYOR_TEST_CONFIG",
    "BAG010_ASH6_RUNTIME_UPDATE_CONVEYOR_TEST_UPDATE_GROUP_CONFIG",
]

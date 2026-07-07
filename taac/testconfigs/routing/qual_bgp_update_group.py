# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification testconfigs (active qualification project).

Covers UG specs 2.1.1, 2.3.x, 2.4.x, 2.7.2.

External consumers import via ``testconfigs.routing`` root; see README.md §7.
"""

from taac.testconfigs.routing.factories.bgp_update_group import (
    create_bgp_ug_eb03_initial_dump_identical_routes_test_config,
    create_bgp_ug_initial_dump_identical_routes_test_config,
    create_bgp_ug_new_peer_join_test_config,
    create_bgp_ug_sustained_link_flap_test_config,
)
from taac.testconfigs.routing.testbed import (
    BAG012_ASH6,
    BAG013_ASH6,
    EB03_LAB_ASH6,
)


# ─── Diff 2 — BAG012 UG new-peer-join (specs 2.4.1 + 2.4.2 + 2.4.3) ────────
# TestConfig constant name grandfathered from bag012_ash6_test_config.py
# (Wave 4 renames to BAG012_ASH6_BGP_UG_NEW_PEER_JOIN_TEST_CONFIG per the
# {TESTBED}_{FACTORY}_{VARIANT}_TEST_CONFIG framework naming rule).
BGP_UG_NEW_PEER_JOIN_TEST_CONFIG = create_bgp_ug_new_peer_join_test_config(BAG012_ASH6)


# ─── Diff 3 — BAG013 conveyor (spec 2.1.1 initial-dump + 2.7.2 sustained-link-flap)
# Python module-level constants renamed to the framework
# ``{TESTBED}_{BGP_UG_}{VARIANT}_TEST_CONFIG`` shape (Wave 4-ish); the internal
# ``TestConfig.name`` field is preserved verbatim
# (``BAG013_ASH6_BGP_CONVEYOR_TEST`` / ``..._UPDATE_GROUP``) so the golden
# manifest stays byte-wise identical.
BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST_CONFIG = (
    create_bgp_ug_initial_dump_identical_routes_test_config(BAG013_ASH6)
)
BAG013_ASH6_BGP_UG_SUSTAINED_LINK_FLAP_TEST_CONFIG = (
    create_bgp_ug_sustained_link_flap_test_config(BAG013_ASH6)
)


# ─── Diff 4 — EB03 lab-box UG initial-dump (spec 2.1.1 + longevity debugging)
# TestConfig.name field grandfathered from eb03_update_group_test_config.py
# so the golden manifest stays byte-wise identical (hash 56b3fa16bf520c5f).
EB03_LAB_ASH6_BGP_TEST_UPDATE_GROUP_CONFIG = (
    create_bgp_ug_eb03_initial_dump_identical_routes_test_config(EB03_LAB_ASH6)
)


__all__ = [
    "BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST_CONFIG",
    "BAG013_ASH6_BGP_UG_SUSTAINED_LINK_FLAP_TEST_CONFIG",
    "BGP_UG_NEW_PEER_JOIN_TEST_CONFIG",
    "EB03_LAB_ASH6_BGP_TEST_UPDATE_GROUP_CONFIG",
]

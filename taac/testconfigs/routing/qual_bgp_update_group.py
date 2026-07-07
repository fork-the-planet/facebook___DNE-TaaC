# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification testconfigs (active qualification project).

Covers UG specs 2.1.1, 2.3.x, 2.4.x, 2.7.2.

External consumers import via ``testconfigs.routing`` root; see README.md §7.
"""

from taac.testconfigs.routing.factories.bgp_update_group import (
    create_bgp_ug_new_peer_join_test_config,
)
from taac.testconfigs.routing.testbed import BAG012_ASH6


# ─── Diff 2 — BAG012 UG new-peer-join (specs 2.4.1 + 2.4.2 + 2.4.3) ────────
# TestConfig constant name grandfathered from bag012_ash6_test_config.py
# (Wave 4 renames to BAG012_ASH6_BGP_UG_NEW_PEER_JOIN_TEST_CONFIG per the
# {TESTBED}_{FACTORY}_{VARIANT}_TEST_CONFIG framework naming rule).
BGP_UG_NEW_PEER_JOIN_TEST_CONFIG = create_bgp_ug_new_peer_join_test_config(BAG012_ASH6)


__all__ = [
    "BGP_UG_NEW_PEER_JOIN_TEST_CONFIG",
]

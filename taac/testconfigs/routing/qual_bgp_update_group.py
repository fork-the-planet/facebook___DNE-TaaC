# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification testconfigs — one catalog constant per spec section.

Post-Wave-6 layout: all 7 sub-sections (2.1 through 2.7) have a catalog
constant here. Sections 2.2, 2.5, 2.6 are SKELETON — empty-playbook
TestConfigs establishing the catalog surface pending implementation. See
``factories/qual_bgp_update_group/tc{N}_*.py`` for per-section factories.

Grandfathered Python constant names (referenced from cconf and elsewhere)
retained verbatim alongside the newer spec-anchored names.
"""

from taac.testconfigs.routing.factories.qual_bgp_update_group.tc1_distribution_correctness import (
    create_bgp_ug_distribution_correctness_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc2_peer_lifecycle import (
    create_bgp_ug_peer_lifecycle_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc3_backpressure import (
    create_bgp_ug_backpressure_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc4_new_peer_join import (
    create_bgp_ug_new_peer_join_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc5_multigroup_formation import (
    create_bgp_ug_multigroup_formation_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc6_bit_alloc_group_stab_under_flap import (
    create_bgp_ug_bit_alloc_group_stab_under_flap_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc7_disruption_recovery import (
    create_bgp_ug_disruption_recovery_test_config,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc9_edge_cases import (
    create_bgp_ug_edge_cases_test_config,
)
from taac.testconfigs.routing.testbed import (
    BAG011_ASH6,
    BAG012_ASH6,
    BAG013_ASH6,
    EB03_LAB_ASH6,
)


# ─── Spec 2.1 Distribution Correctness ──────────────────────────────────
BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST_CONFIG = (
    create_bgp_ug_distribution_correctness_test_config(BAG013_ASH6)
)
EB03_LAB_ASH6_BGP_TEST_UPDATE_GROUP_CONFIG = (
    create_bgp_ug_distribution_correctness_test_config(EB03_LAB_ASH6)
)

# ─── Spec 2.2 Peer Lifecycle (SKELETON) ─────────────────────────────────
BGP_UG_PEER_LIFECYCLE_TEST_CONFIG = create_bgp_ug_peer_lifecycle_test_config(
    BAG013_ASH6
)

# ─── Spec 2.3 Backpressure ──────────────────────────────────────────────
BGP_UG_BACKPRESSURE_TEST_CONFIG = create_bgp_ug_backpressure_test_config(BAG013_ASH6)
BAG013_ASH6_BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE_CONFIG = (
    create_bgp_ug_backpressure_test_config(BAG013_ASH6, smoke_only=True)
)
EB03_LAB_ASH6_BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE_CONFIG = (
    create_bgp_ug_backpressure_test_config(EB03_LAB_ASH6, smoke_only=True)
)

# ─── Spec 2.4 New Peer Join ─────────────────────────────────────────────
BGP_UG_NEW_PEER_JOIN_TEST_CONFIG = create_bgp_ug_new_peer_join_test_config(BAG012_ASH6)

# ─── Spec 2.5 Multi-Group Formation (SKELETON) ──────────────────────────
BGP_UG_MULTIGROUP_FORMATION_TEST_CONFIG = (
    create_bgp_ug_multigroup_formation_test_config(BAG013_ASH6)
)

# ─── Spec 2.6 Bit Allocation Under Flaps (SKELETON) ─────────────────────
BGP_UG_BIT_ALLOC_GROUP_STAB_UNDER_FLAP_TEST_CONFIG = (
    create_bgp_ug_bit_alloc_group_stab_under_flap_test_config(BAG013_ASH6)
)

# ─── Spec 2.7 Disruption and Recovery ───────────────────────────────────
BAG013_ASH6_BGP_UG_SUSTAINED_LINK_FLAP_TEST_CONFIG = (
    create_bgp_ug_disruption_recovery_test_config(BAG013_ASH6)
)

# ─── Spec 2.9 Edge Cases and Adversarial Scenarios ──────────────────────
# Bundles the section-2.9 edge-case playbooks (2.9.7 empty group live today;
# 2.9.1/2.9.2/2.9.3/2.9.4/2.9.6 land incrementally). Select an individual
# scenario at run time with ``--regex 'bgp_ug_<usecase>'``.
BAG011_ASH6_BGP_UG_EDGE_CASES_TEST_CONFIG = create_bgp_ug_edge_cases_test_config(
    BAG011_ASH6
)


__all__ = [
    "BAG011_ASH6_BGP_UG_EDGE_CASES_TEST_CONFIG",
    "BAG013_ASH6_BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE_CONFIG",
    "BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST_CONFIG",
    "BAG013_ASH6_BGP_UG_SUSTAINED_LINK_FLAP_TEST_CONFIG",
    "BGP_UG_BACKPRESSURE_TEST_CONFIG",
    "BGP_UG_BIT_ALLOC_GROUP_STAB_UNDER_FLAP_TEST_CONFIG",
    "BGP_UG_MULTIGROUP_FORMATION_TEST_CONFIG",
    "BGP_UG_NEW_PEER_JOIN_TEST_CONFIG",
    "BGP_UG_PEER_LIFECYCLE_TEST_CONFIG",
    "EB03_LAB_ASH6_BGP_TEST_UPDATE_GROUP_CONFIG",
    "EB03_LAB_ASH6_BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE_CONFIG",
]

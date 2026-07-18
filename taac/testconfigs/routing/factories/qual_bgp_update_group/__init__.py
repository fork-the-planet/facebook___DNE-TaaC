# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification testconfig factories — one file per spec section.

Layout: ``tc{N}_<slug>.py`` maps to UG spec section 2.N. Sections without
implementation yet expose SKELETON empty-playbook TestConfigs so the
qualification catalog can enumerate all 7 sections uniformly.

Force-import the tc modules so downstream ``import ...factories.qual_bgp_update_group``
reaches every factory (mirrors the sibling ``factories/__init__.py`` pattern).
"""

from taac.testconfigs.routing.factories.qual_bgp_update_group import (  # noqa: F401
    tc1_distribution_correctness,
    tc2_peer_lifecycle,
    tc3_backpressure,
    tc4_new_peer_join,
    tc5_multigroup_formation,
    tc6_bit_alloc_group_stab_under_flap,
    tc7_disruption_recovery,
    tc9_edge_cases,
)

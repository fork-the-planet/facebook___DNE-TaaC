# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification playbook factories — one file per spec section.

Layout: ``tc{N}_<slug>.py`` maps to UG spec section 2.N. Sub-specs without
implementation yet expose skeleton factories that ``raise NotImplementedError``;
those skeletons are not called from any testconfig factory (skeleton
TestConfigs return ``playbooks=[]``).

Force-import the tc modules so downstream force-import via
``import ...factories.qual_bgp_update_group`` reaches every playbook factory
module and their ``Playbook(...)`` construction sites get registered by
``tests/test_no_inline_playbook_construction.py``.
"""

from taac.playbooks.routing.factories.qual_bgp_update_group import (  # noqa: F401
    tc1_distribution_correctness,
    tc2_peer_lifecycle,
    tc3_backpressure,
    tc4_new_peer_join,
    tc5_multigroup_formation,
    tc6_bit_alloc_group_stab_under_flap,
    tc7_disruption_recovery,
    tc9_edge_cases,
)

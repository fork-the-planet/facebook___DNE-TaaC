# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Routing testconfig factories package.

Each ``<domain>.py`` file exposes ``create_<domain>_<workflow>_test_config``
factories consumed by catalog files in the parent package. Force-import
the domain modules so downstream ``import ...testconfigs.routing.factories``
reaches every factory (parallels the sibling ``playbooks/routing/__init__.py``
pattern).

See ../README.md §3 for the factory contract.
"""

from taac.testconfigs.routing.factories import (  # noqa: F401
    bgp_dc_chronos_node,
    bgp_ebb_characteristic,
    bgp_ebb_full_scale,
    bgp_ebb_full_scale_mimic,
    bgp_features,
    bgp_update_group,
    cte_ucmp,
)

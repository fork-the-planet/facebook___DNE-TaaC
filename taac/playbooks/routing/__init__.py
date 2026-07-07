# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Routing playbook factories package — single re-export point.

Testconfig factories under ``testconfigs/routing/factories/`` import
playbook factories from this package root, never from a domain file
directly. See README.md §6.

Force-import the domain modules so downstream force-import via
``import neteng.test_infra.dne.taac.playbooks.routing`` (used by
``tests/test_no_inline_playbook_construction.py``) reaches every playbook
factory module and their ``Playbook(...)`` construction sites get
registered by the gate test.

Skeleton — factories populated as Wave 1 migration diffs land.
"""

from taac.playbooks.routing import (  # noqa: F401
    bgp_ebb_playbooks,
    bgp_ug_playbooks,
)

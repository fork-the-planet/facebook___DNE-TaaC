# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Playbook factories package (per-qualification-project subpackages).

Each subpackage under this directory groups playbook factories by
qualification project (matching the sibling ``testconfigs/routing/factories/``
subpackage layout).

Force-import the subpackages so downstream force-import via
``import neteng.test_infra.dne.taac.playbooks.routing`` reaches every
playbook factory and their ``Playbook(...)`` construction sites get
registered by ``tests/test_no_inline_playbook_construction.py``.
"""

from taac.playbooks.routing.factories import (  # noqa: F401
    qual_bgp_update_group,
)

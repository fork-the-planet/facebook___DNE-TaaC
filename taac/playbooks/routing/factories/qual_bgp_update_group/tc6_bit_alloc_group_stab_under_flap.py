# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.6 — Bit Allocation and Group Stability Under Flaps. SKELETON playbook factories.

Sub-specs pending implementation. Skeletons raise NotImplementedError at call
time; they are not wired into the SKELETON tc6 testconfig
(``playbooks=[]``), so raising is safe.
"""

from taac.test_as_a_config.types import Playbook


def create_bgp_ug_repeated_peer_flaps_group_stable_playbook() -> Playbook:
    """Spec 2.6.1 — Repeated Peer Flaps — Group Remains Stable. SKELETON."""
    raise NotImplementedError(
        "Spec 2.6.1 (repeated_peer_flaps_group_stable) playbook not yet implemented"
    )

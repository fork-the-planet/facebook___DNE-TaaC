# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.2 — Peer Lifecycle Within Update Groups. SKELETON playbook factories.

Sub-specs pending implementation. Skeletons raise NotImplementedError at call
time; they are not wired into the SKELETON tc2 testconfig
(``playbooks=[]``), so raising is safe.
"""

from taac.test_as_a_config.types import Playbook


def create_bgp_ug_peer_down_remaining_unaffected_playbook() -> Playbook:
    """Spec 2.2.1 — Peer Down: Remaining Group Members Unaffected. SKELETON."""
    raise NotImplementedError(
        "Spec 2.2.1 (peer_down_remaining_unaffected) playbook not yet implemented"
    )


def create_bgp_ug_peer_reconnect_shadow_rib_playbook() -> Playbook:
    """Spec 2.2.2 — Peer Reconnect: Re-Sync from Shadow RIB. SKELETON."""
    raise NotImplementedError(
        "Spec 2.2.2 (peer_reconnect_shadow_rib) playbook not yet implemented"
    )


def create_bgp_ug_sustained_group_membership_churn_playbook() -> Playbook:
    """Spec 2.2.3 — Sustained Group Membership Churn: No Memory Leak. SKELETON."""
    raise NotImplementedError(
        "Spec 2.2.3 (sustained_group_membership_churn) playbook not yet implemented"
    )

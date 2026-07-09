# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.5 — Multi-Group Formation Correctness. SKELETON playbook factories.

Sub-specs pending implementation. Skeletons raise NotImplementedError at call
time; they are not wired into the SKELETON tc5 testconfig
(``playbooks=[]``), so raising is safe.
"""

from taac.test_as_a_config.types import Playbook


def create_bgp_ug_multiple_groups_outbound_policies_playbook() -> Playbook:
    """Spec 2.5.1 — Multiple Groups Formed for Different Outbound Policies. SKELETON."""
    raise NotImplementedError(
        "Spec 2.5.1 (multiple_groups_outbound_policies) playbook not yet implemented"
    )


def create_bgp_ug_scale_withdraw_10plus_peers_playbook() -> Playbook:
    """Spec 2.5.2 — Scale Withdraw: 10+ Peers in Same Group, Withdraw Routes. SKELETON."""
    raise NotImplementedError(
        "Spec 2.5.2 (scale_withdraw_10plus_peers) playbook not yet implemented"
    )

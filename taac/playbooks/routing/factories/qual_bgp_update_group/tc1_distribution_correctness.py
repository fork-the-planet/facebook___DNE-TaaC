# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.1 — Distribution Correctness. UG qualification playbook factories.

- 2.1.1 Initial Dump: All Peers in Same Group Receive Identical Routes (REAL)
- 2.1.2 Runtime Route Distribution: Routes Flow to All Group Members (SKELETON)
"""

import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_graceful_restart_check,
    create_bgp_update_group_check,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_custom_step,
    create_validation_step,
)
from taac.testconfigs.routing.util.bgp_ebb_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_PRECHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
)
from taac.test_as_a_config.types import Playbook


def create_bgp_ug_initial_dump_identical_routes_playbook(
    device_name: str,
    ixia_interface_mimic_ibgp: str,
    ixia_interface_mimic_bgp_mon: str,
    ibgp_v6_peer_group: str,
    ebgp_v6_peer_group: str,
    ibgp_v4_peer_group: str,
    bgp_mon_peer_group: str,
    ibgp_peer_regex: str = "BGP_PEER_IPV6_IBGP_PLANE_1_REMOTE_EB",
    ibgp_peer_session_indices: t.Optional[t.List[int]] = None,
    bgp_mon_peer_regex: str = "BGP_PEER_IPV6_BGP_MON",
    bgp_mon_session_index: int = 1,
    capture_duration_seconds: int = 300,
    settle_seconds: int = 10,
    expected_group_count: int = 5,
    expected_ibgp_v6_member_count: int = 496,
    expected_ebgp_v6_member_count: int = 140,
    expected_bgp_mon_member_count: int = 2,
    check_id_prefix: str = "bag013_2_1_1",
    playbook_name: str = "bag013_2_1_1_initial_dump_identical_routes",
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.1.1 playbook
    (Initial Dump -- Identical Routes to Peers in Same UG).

    Byte-wise-identical move of the inline helper
    ``_create_2_1_1_initial_dump_identical_routes_playbook`` from the legacy
    ``testconfigs/routing/ebb/bag013_ash6_test_config.py`` under the routing
    framework naming.

    The membership check verifies:
      - all iBGP IPv6 peers (peer-group EB-EB-V6) are in the SAME update group,
      - all eBGP IPv6 peers (EB-FA-V6) are in a DIFFERENT update group,
      - BGP Monitor peers are in their OWN update group (distinct from both),
      - all iBGP peers in the shared group received an IDENTICAL number of
        routes from the DUT (single distribution path).

    Steps 6-7 flap the WHOLE BGP layer via the ``test_bgp_update_group_dump_compare``
    custom step so both observed iBGP peers dump in the same UG cycle; the step
    compares NLRI/AS_PATH/LOCAL_PREF/COMMUNITY/MED (only next-hop may differ)
    and asserts BGP-MON add-path formatting on the diagnostic capture.
    """
    if ibgp_peer_session_indices is None:
        ibgp_peer_session_indices = [1, 2]
    prechecks = [
        *BGP_STANDARD_PRECHECKS,
        # Pre-condition 3: GR must NOT be enabled on the iBGP mesh (V6 + V4).
        create_bgp_graceful_restart_check(
            peer_group_name=ibgp_v6_peer_group,
            expected_graceful_restart_enabled=False,
            check_id=f"{check_id_prefix}_gr_disabled_ibgp_v6",
        ),
        create_bgp_graceful_restart_check(
            peer_group_name=ibgp_v4_peer_group,
            expected_graceful_restart_enabled=False,
            check_id=f"{check_id_prefix}_gr_disabled_ibgp_v4",
        ),
    ]
    verify_step = create_validation_step(
        point_in_time_checks=[
            create_bgp_update_group_check(
                # iBGP-V6, eBGP-V6 and BGP-MON must each have Established peers in
                # the update-group table. (A peer-group may form more than one
                # update group -- one per distinct egress policy -- which is
                # expected, not a failure.)
                peer_group_substrings=[
                    ibgp_v6_peer_group,
                    ebgp_v6_peer_group,
                    bgp_mon_peer_group,
                ],
                # Passing criterion 5: total update groups == number of distinct
                # outbound-policy configs (one per peer-group per AFI + BGP-MON):
                # EB-EB-V4, EB-EB-V6, EB-FA-V4, EB-FA-V6, BGP-MON = 5.
                expected_group_count=expected_group_count,
                # Golden values (full parity with eb03):
                #   EB-EB-V6 -> policy EB-EB-OUT, 496 members
                #     (62/plane x 4 planes x 2 (DC+MP))
                #   EB-FA-V6 -> policy EB-FA-OUT, 140 members
                #   BGP-MON  -> policy PROPAGATE_EVERYTHING_OUT, 2 members
                expected_member_counts={
                    ibgp_v6_peer_group: expected_ibgp_v6_member_count,
                    ebgp_v6_peer_group: expected_ebgp_v6_member_count,
                    bgp_mon_peer_group: expected_bgp_mon_member_count,
                },
                expected_policy_names={
                    ibgp_v6_peer_group: ["EB-EB-OUT"],
                    ebgp_v6_peer_group: ["EB-FA-OUT"],
                    bgp_mon_peer_group: ["PROPAGATE_EVERYTHING_OUT"],
                },
                check_id=f"{check_id_prefix}_update_group_membership",
            )
        ],
        description=(
            "BGP++ Update Group qualification 2.1.1 -- verify EB-EB-V6 iBGP (496 "
            "members, EB-EB-OUT), EB-FA-V6 eBGP (140, EB-FA-OUT) and BGP-MON "
            "(2, PROPAGATE_EVERYTHING_OUT) form distinct update groups, with 5 "
            "groups total (one per peer-group per AFI + BGP-MON)."
        ),
    )
    # Steps 6-7: capture the initial-dump UPDATEs to two iBGP peers in the same
    # update group and assert they are identical (NLRI/AS_PATH/LOCAL_PREF/
    # COMMUNITY/MED; only next-hop may differ). Per the 2.1.1 test plan this is a
    # COLD START: the custom step flaps the WHOLE BGP layer DOWN (no established
    # sessions -- pre-condition 1) then all UP together (step 1), so the update
    # group re-forms with all members and every peer dumps at once. It captures
    # only the observed peers' vport(s) (+ BGP-MON) and compares the two. It
    # flaps BGP sessions via regex='.*' (relies on the per-peer session_end_idx
    # fix in start_bgp_peers), NOT stop_protocols (which tears down reachability).
    # capture_duration must span full reconvergence (route sources bounce too).
    # Requires a full IXIA run (won't work under --skip-setup-tasks).
    pcap_compare_step = create_custom_step(
        params_dict={
            "custom_step_name": "test_bgp_update_group_dump_compare",
            "hostname": device_name,
            "ixia_capture_interface": ixia_interface_mimic_ibgp,
            # IXIA BGP-peer names (from the session topology), not peer-group
            # names. Two sessions of one iBGP-V6 device group -- both land in
            # update group 0 (all EB-EB-V6 peers share one group).
            "ibgp_peer_regex": ibgp_peer_regex,
            "ibgp_peer_session_indices": list(ibgp_peer_session_indices),
            # Flapping ALL sessions bounces the route sources too, so the dump
            # spans full reconvergence -- give it a long window.
            "capture_duration_seconds": capture_duration_seconds,
            "settle_seconds": settle_seconds,
            # Criterion 4: BGP-Monitor (add-path capable) UPDATEs must be
            # add-path formatted (distinct from iBGP).
            "bgp_mon_capture_interface": ixia_interface_mimic_bgp_mon,
            "bgp_mon_peer_regex": bgp_mon_peer_regex,
            "bgp_mon_session_index": bgp_mon_session_index,
        },
        description=(
            "BGP++ Update Group 2.1.1 steps 6-7 -- capture and compare the "
            "initial-dump UPDATEs to two iBGP peers in the same update group "
            "(identical NLRI/AS_PATH/LOCAL_PREF/COMMUNITY/MED; next-hop may differ)."
        ),
    )
    return Playbook(
        name=playbook_name,
        stages=[
            create_steps_stage(steps=[verify_step]),
            create_steps_stage(steps=[pcap_compare_step]),
        ],
        prechecks=prechecks,
        postchecks=list(BGP_STANDARD_POSTCHECKS),
        snapshot_checks=list(BGP_STANDARD_SNAPSHOT_CHECKS),
    )


def create_bgp_ug_runtime_route_distribution_playbook() -> Playbook:
    """Spec 2.1.2 — Runtime Route Distribution: Routes Flow to All Group Members. SKELETON."""
    raise NotImplementedError(
        "Spec 2.1.2 (runtime_route_distribution) playbook not yet implemented"
    )

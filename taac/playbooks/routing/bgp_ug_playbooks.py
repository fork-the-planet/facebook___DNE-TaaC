# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group qualification playbook factories.

Naming: ``create_bgp_ug_<usecase>_playbook``. One factory = one playbook =
one UG spec test case. Playbook ``name=`` field values are GRANDFATHERED
from the legacy ``playbooks/playbook_definitions.py`` home (Wave 4 will
rename them to the canonical framework form).

See ../README.md.
"""

import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_graceful_restart_check,
    create_bgp_peer_route_set_equality_check,
    create_bgp_received_route_community_check,
    create_bgp_route_count_verification_check,
    create_bgp_session_establish_check,
    create_bgp_stale_route_check,
    create_bgp_update_group_check,
    create_service_restart_check,
    create_system_cpu_load_average_check,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.common_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_PRECHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_custom_step,
    create_ixia_api_step,
    create_longevity_step,
    create_start_stop_bgp_peers_step,
    create_tcpdump_step,
    create_validation_step,
)
from taac.test_as_a_config.types import (
    Playbook,
    PointInTimeHealthCheck,
    SnapshotHealthCheck,
    Step,
)


__all__ = [
    "create_bgp_ug_initial_dump_identical_routes_playbook",
    "create_bgp_ug_new_peer_join_attribute_change_playbook",
    "create_bgp_ug_new_peer_join_full_sync_resilience_playbook",
    "create_bgp_ug_new_peer_join_routes_withdrawn_playbook",
    "create_bgp_ug_sustained_link_flap_playbook",
]


def create_bgp_ug_new_peer_join_full_sync_resilience_playbook(
    device_name: str,
    control_peer_addrs: t.List[str],
    held_back_peer_addr: str,
    held_back_peer_regex: str,
    disp_peer_addrs: t.List[str],
    disp_peer_regex: str,
    disp_session_start_idx: int,
    disp_session_end_idx: int,
    b_keep_peer_addr: str,
    b_keep_route_count: int,
    b_var1_peer_regex: str,
    b_var1_peer_addr: str,
    b_var1_route_count: int,
    b_var2_peer_regex: str,
    b_var2_peer_addr: str,
    b_var2_route_count: int,
    ug_peer_group_substring: str = "EB-FA-V6",
    setup_convergence_s: int = 30,
    post_test_convergence_s: int = 60,
    post_inject_convergence_s: int = 30,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.4.1 playbook
    (New Peer Joins, Receives Full Sync, Then a Peer Goes Down).

    See legacy ``playbook_definitions.create_new_peer_join_full_sync_resilience_playbook``
    for the full spec / rationale / flow docstring — this factory is the
    byte-wise-identical move under the routing framework naming.
    """
    phase_1_inject_steps = [
        create_start_stop_bgp_peers_step(
            peer_regex=b_var1_peer_regex,
            start=True,
            start_idx=1,
            end_idx=1,
            description=(
                f"Phase 1 (2.4.1): bring sender DG_B_VAR1 UP -- inject "
                f"{b_var1_route_count} routes while held-back is still down"
            ),
        ),
        create_longevity_step(
            duration=setup_convergence_s,
            description=(
                f"Phase 1 (2.4.1): settle {setup_convergence_s}s for "
                f"DG_B_VAR1 advertise to propagate via UG to side A receivers"
            ),
        ),
        create_validation_step(
            point_in_time_checks=[
                create_bgp_route_count_verification_check(
                    json_params={
                        "descriptions_to_check": list(control_peer_addrs),
                        "direction": "received",
                        "policy_type": "post_policy",
                        "expected_count": b_keep_route_count + b_var1_route_count,
                    },
                )
            ],
            description=(
                "Phase 1 verify (2.4.1): control peers received baseline + "
                "inject routes"
            ),
        ),
    ]

    trigger_steps = [
        create_start_stop_bgp_peers_step(
            peer_regex=held_back_peer_regex,
            start=True,
            start_idx=1,
            end_idx=1,
            description=("Phase 2a (2.4.1): bring held-back peer UP -- begin UG sync"),
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=disp_peer_regex,
            start=False,
            start_idx=disp_session_start_idx,
            end_idx=disp_session_end_idx,
            description=(
                f"Phase 2b (2.4.1): kill DG_A_DISP sessions "
                f"{disp_session_start_idx}-{disp_session_end_idx} mid-sync "
                "(UG member churn during held-back's initial sync)"
            ),
        ),
        create_longevity_step(
            duration=post_test_convergence_s,
            description=(
                f"Phase 2 (2.4.1): settle {post_test_convergence_s}s for "
                "held-back sync + UG re-convergence"
            ),
        ),
        create_validation_step(
            point_in_time_checks=[
                create_bgp_peer_route_set_equality_check(
                    baseline_peer_addr=control_peer_addrs[0],
                    tested_peer_addrs=[held_back_peer_addr]
                    + list(control_peer_addrs[1:]),
                    anchor_route_count=b_keep_route_count + b_var1_route_count,
                )
            ],
            description=(
                "Phase 3 spec gate (2.4.1): held-back + remaining control peers "
                f"received {b_keep_route_count + b_var1_route_count} routes "
                "after sync (full initial dump survived DISP kill mid-sync)"
            ),
        ),
    ]

    expected_after_inject_50 = (
        b_keep_route_count + b_var1_route_count + b_var2_route_count
    )
    phase_3_checks = [
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=[held_back_peer_addr],
        ),
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=disp_peer_addrs,
            expected_established_sessions=0,
        ),
        create_bgp_peer_route_set_equality_check(
            baseline_peer_addr=control_peer_addrs[0],
            tested_peer_addrs=[held_back_peer_addr] + list(control_peer_addrs[1:]),
            anchor_route_count=expected_after_inject_50,
        ),
        create_service_restart_check(
            services=["Bgp"],
            daemons=["FibBgpGrpc"],
        ),
        create_bgp_stale_route_check(),
    ]

    phase_4_steps = [
        create_start_stop_bgp_peers_step(
            peer_regex=b_var2_peer_regex,
            start=True,
            start_idx=1,
            end_idx=1,
            description=(
                f"Phase 4 (2.4.1): bring sender DG_B_VAR2 UP -- inject "
                f"{b_var2_route_count} more routes (runtime update)"
            ),
        ),
        create_longevity_step(
            duration=post_inject_convergence_s,
            description=(
                f"Phase 4 (2.4.1): settle {post_inject_convergence_s}s for "
                "DG_B_VAR2 advertise to propagate"
            ),
        ),
        create_validation_step(
            point_in_time_checks=[
                create_bgp_peer_route_set_equality_check(
                    baseline_peer_addr=control_peer_addrs[0],
                    tested_peer_addrs=[held_back_peer_addr]
                    + list(control_peer_addrs[1:]),
                    anchor_route_count=expected_after_inject_50,
                )
            ],
            description=(
                "Phase 4 verify (2.4.1): held-back + remaining control peers "
                f"received {expected_after_inject_50} routes after runtime "
                "inject (no missing prefixes)"
            ),
        ),
    ]

    cleanup_steps = [
        create_start_stop_bgp_peers_step(
            peer_regex=disp_peer_regex,
            start=True,
            start_idx=disp_session_start_idx,
            end_idx=disp_session_end_idx,
            description="Phase 5 cleanup (2.4.1): restore DG_A_DISP sessions UP",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=b_var1_peer_regex,
            start=False,
            start_idx=1,
            end_idx=1,
            description="Phase 5 cleanup (2.4.1): bring DG_B_VAR1 back DOWN",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=b_var2_peer_regex,
            start=False,
            start_idx=1,
            end_idx=1,
            description="Phase 5 cleanup (2.4.1): bring DG_B_VAR2 back DOWN",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=held_back_peer_regex,
            start=False,
            start_idx=1,
            end_idx=1,
            description="Phase 5 cleanup (2.4.1): restore HELD to admin-DOWN",
        ),
        create_longevity_step(
            duration=setup_convergence_s,
            description=(
                f"Phase 5 cleanup (2.4.1): settle {setup_convergence_s}s for "
                "baseline state to converge"
            ),
        ),
    ]

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(
                expect_enabled=True,
                peer_group_substrings=[ug_peer_group_substring],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=list(control_peer_addrs)
                + [b_keep_peer_addr],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=[
                    held_back_peer_addr,
                    b_var1_peer_addr,
                    b_var2_peer_addr,
                ],
                expected_established_sessions=0,
            ),
            create_bgp_route_count_verification_check(
                json_params={
                    "descriptions_to_check": list(control_peer_addrs),
                    "direction": "received",
                    "policy_type": "post_policy",
                    "expected_count": b_keep_route_count,
                },
            ),
        ]
    if postchecks is None:
        postchecks = list(phase_3_checks)
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs = {
        "name": "new_peer_join_full_sync_resilience",
        "stages": [
            create_steps_stage(
                steps=phase_1_inject_steps,
                description="Phase 1 (2.4.1): inject 200 while held-back DOWN",
            ),
            create_steps_stage(
                steps=trigger_steps,
                description=(
                    "Phase 2 (2.4.1): held-back UP + DISP kill (mid-sync churn)"
                ),
            ),
            create_steps_stage(
                steps=phase_4_steps,
                description="Phase 4 (2.4.1): runtime inject 50 more",
            ),
        ],
        "cleanup_steps": cleanup_steps,
        "prechecks": prechecks,
        "postchecks": postchecks,
        "snapshot_checks": snapshot_checks,
    }
    if setup_steps is not None:
        kwargs["setup_steps"] = setup_steps
    return Playbook(**kwargs)


def create_bgp_ug_sustained_link_flap_playbook(
    device_name: str,
    port_schedule: t.List[t.Dict[str, t.Any]],
    total_duration_s: int,
    prechecks: t.List[PointInTimeHealthCheck],
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
    stabilization_s: int = 30,
    checkpoint_interval_s: int = 900,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.7.2 playbook
    (Sustained Link Flapping Across Multiple Ports).

    Byte-wise-identical move of the legacy
    ``playbook_definitions.create_update_group_sustained_link_flap_playbook``
    under the routing framework naming. See the legacy docstring for the full
    spec / rationale / flow.
    """
    flap_step = create_custom_step(
        params_dict={
            "custom_step_name": "staggered_flap_with_isolation_check",
            "hostname": device_name,
            "port_schedule": port_schedule,
            "total_duration_s": total_duration_s,
            "stabilization_s": stabilization_s,
            "checkpoint_interval_s": checkpoint_interval_s,
        },
        description=(
            f"BGP++ Update Group qualification 2.7.2 -- rotate flap on "
            f"{len(port_schedule)} ports for {total_duration_s}s on "
            f"{device_name}; per-session isolation check after each cycle."
        ),
    )
    # 2.7.2 pass criteria #3 and #6:
    #   #3 "all update groups correctly formed, no stale entries"
    #      -> ``create_bgp_update_group_check`` (Thrift API per D108632994).
    #   #6 "1m, 5m and 15m load-averages never cross 12"
    #      -> ``create_system_cpu_load_average_check(baseline=12.0)``.
    # ``BGP_STANDARD_POSTCHECKS`` covers per-process CPU (400% threshold) and
    # memory but neither of the above, so extend the default postcheck list
    # here so every consumer of this factory asserts both spec bounds.
    if postchecks is None:
        postchecks = list(BGP_STANDARD_POSTCHECKS) + [
            create_system_cpu_load_average_check(baseline=12.0),
            create_bgp_update_group_check(expect_enabled=True),
        ]
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)
    return Playbook(
        # Generic name -- reusable across EBB devices. Device-specific scope
        # lives in the surrounding TestConfig (e.g.
        # ``BAG013_ASH6_BGP_CONVEYOR_TEST_UPDATE_GROUP``), not in the
        # playbook name itself.
        name="update_group_sustained_link_flap",
        stages=[create_steps_stage(steps=[flap_step])],
        prechecks=prechecks,
        postchecks=postchecks,
        snapshot_checks=snapshot_checks,
    )


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


def create_bgp_ug_new_peer_join_routes_withdrawn_playbook(
    device_name: str,
    control_peer_addrs: t.List[str],
    held_back_peer_addr: str,
    held_back_peer_regex: str,
    b_keep_peer_addr: str,
    b_keep_route_count: int,
    b_var1_peer_regex: str,
    b_var1_peer_addr: str,
    b_var1_route_count: int,
    b_var1_device_group_regex: str,
    ug_peer_group_substring: str = "EB-FA-V6",
    setup_convergence_s: int = 30,
    post_test_convergence_s: int = 180,
    capture_tcpdump_device: t.Optional[str] = None,
    capture_tcpdump_path: str = "/tmp/bgp_capture_2_4_2.txt",
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.4.2 playbook
    (New Peer Joins, Then Routes Are Withdrawn).

    See legacy ``playbook_definitions.create_new_peer_join_routes_withdrawn_playbook``
    for the full spec / rationale / flow docstring — this factory is the
    byte-wise-identical move under the routing framework naming.
    """
    trigger_steps: t.List[Step] = []

    if capture_tcpdump_device is not None:
        trigger_steps.append(
            create_tcpdump_step(
                device_name=capture_tcpdump_device,
                mode="start_capture",
                capture_file_path=capture_tcpdump_path,
                description=(
                    "Phase 2 (2.4.2): start tcpdump capture (diagnostic -- "
                    "proves the withdrawal trigger fires on the wire)"
                ),
            )
        )

    trigger_steps.extend(
        [
            create_start_stop_bgp_peers_step(
                peer_regex=held_back_peer_regex,
                start=True,
                start_idx=1,
                end_idx=1,
                description=(
                    "Phase 2a (2.4.2): bring held-back peer UP -- begin UG sync"
                ),
            ),
            create_ixia_api_step(
                api_name="toggle_device_groups",
                args_dict={
                    "enable": False,
                    "device_group_name_regex": b_var1_device_group_regex,
                    "sleep_time_before_applying_change": 5,
                },
                description=(
                    "Phase 2b (2.4.2): admin-disable DG_B_VAR1 mid-sync -- "
                    "DUT withdraws B_VAR1's routes via UG to all members"
                ),
            ),
        ]
    )

    if capture_tcpdump_device is not None:
        trigger_steps.append(
            create_tcpdump_step(
                device_name=capture_tcpdump_device,
                mode="stop_capture",
                capture_file_path=capture_tcpdump_path,
                description="Phase 2 (2.4.2): stop tcpdump capture",
            )
        )

    trigger_steps.append(
        create_longevity_step(
            duration=post_test_convergence_s,
            description=(
                f"Phase 2 (2.4.2): settle {post_test_convergence_s}s for "
                "UG to converge on withdrawn state"
            ),
        )
    )

    phase_3_checks = [
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=[held_back_peer_addr],
        ),
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=[b_var1_peer_addr],
            expected_established_sessions=0,
        ),
        create_bgp_peer_route_set_equality_check(
            baseline_peer_addr=control_peer_addrs[0],
            tested_peer_addrs=[held_back_peer_addr] + list(control_peer_addrs[1:]),
            anchor_route_count=b_keep_route_count,
        ),
        create_service_restart_check(
            services=["Bgp"],
            daemons=["FibBgpGrpc"],
        ),
        create_bgp_stale_route_check(),
    ]

    cleanup_steps = [
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": b_var1_device_group_regex,
                "sleep_time_before_applying_change": 0,
            },
            description="Phase 5 cleanup (2.4.2): re-enable DG_B_VAR1",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=held_back_peer_regex,
            start=False,
            start_idx=1,
            end_idx=1,
            description="Phase 5 cleanup (2.4.2): restore HELD to admin-DOWN",
        ),
        create_longevity_step(
            duration=setup_convergence_s,
            description=(
                f"Phase 5 cleanup (2.4.2): settle {setup_convergence_s}s for "
                "baseline state to converge"
            ),
        ),
    ]

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(
                expect_enabled=True,
                peer_group_substrings=[ug_peer_group_substring],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=list(control_peer_addrs)
                + [b_keep_peer_addr, b_var1_peer_addr],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=[held_back_peer_addr],
                expected_established_sessions=0,
            ),
            create_bgp_route_count_verification_check(
                json_params={
                    "descriptions_to_check": list(control_peer_addrs),
                    "direction": "received",
                    "policy_type": "post_policy",
                    "expected_count": b_keep_route_count + b_var1_route_count,
                },
            ),
        ]
    if postchecks is None:
        postchecks = list(phase_3_checks)
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs = {
        "name": "new_peer_join_routes_withdrawn",
        "stages": [
            create_steps_stage(
                steps=trigger_steps,
                description=(
                    "Phase 2 (2.4.2): held-back UP + sender session-DOWN "
                    "(mid-sync withdrawal trigger)"
                ),
            ),
        ],
        "cleanup_steps": cleanup_steps,
        "prechecks": prechecks,
        "postchecks": postchecks,
        "snapshot_checks": snapshot_checks,
    }
    if setup_steps is not None:
        kwargs["setup_steps"] = setup_steps
    return Playbook(**kwargs)


def create_bgp_ug_new_peer_join_attribute_change_playbook(
    device_name: str,
    control_peer_addrs: t.List[str],
    held_back_peer_addr: str,
    held_back_peer_regex: str,
    b_keep_peer_addr: str,
    b_keep_route_count: int,
    b_keep_peer_regex: str,
    b_keep_device_group_regex: str,
    b_keep_mutated_peer_addr: str,
    b_keep_mutated_device_group_regex: str,
    initial_community: str,
    mutated_community: str,
    ug_peer_group_substring: str = "EB-FA-V6",
    setup_convergence_s: int = 30,
    initial_withdraw_settle_s: int = 90,
    post_test_convergence_s: int = 60,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.4.3 playbook
    (New Peer Joins, Then Attribute Change on Existing Routes).

    See legacy ``playbook_definitions.create_new_peer_join_attribute_change_playbook``
    for the full spec / rationale / flow docstring — this factory is the
    byte-wise-identical move under the routing framework naming.
    """
    trigger_steps: t.List[Step] = [
        create_start_stop_bgp_peers_step(
            peer_regex=held_back_peer_regex,
            start=True,
            start_idx=1,
            end_idx=1,
            description=("Phase 2a (2.4.3): bring held-back peer UP -- begin UG sync"),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": b_keep_device_group_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "Phase 2b (2.4.3): DG-disable KEEP_INITIAL -- DUT withdraws "
                "the 300 routes carrying the initial community via hold-timer"
            ),
        ),
        create_longevity_step(
            duration=initial_withdraw_settle_s,
            description=(
                f"Phase 2b-settle (2.4.3): {initial_withdraw_settle_s}s for "
                "DUT hold-timer expiry + adj-RIB-out withdraw"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": b_keep_mutated_device_group_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "Phase 2c (2.4.3): DG-enable KEEP_MUTATED -- same 300 prefixes "
                "re-advertised with mutated community; DUT must re-distribute "
                "via UG to HELD+CTRL"
            ),
        ),
        create_longevity_step(
            duration=post_test_convergence_s,
            description=(
                f"Phase 2 (2.4.3): settle {post_test_convergence_s}s for "
                "KEEP_MUTATED session establish, full route re-advertise, "
                "and DUT UG re-distribute to HELD+CTRL"
            ),
        ),
    ]

    phase_3_checks = [
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=[held_back_peer_addr],
        ),
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=[b_keep_mutated_peer_addr],
        ),
        create_bgp_received_route_community_check(
            baseline_peer_addr=control_peer_addrs[0],
            tested_peer_addrs=[held_back_peer_addr] + list(control_peer_addrs[1:]),
            anchor_community=mutated_community,
            forbidden_communities=[initial_community],
        ),
        create_bgp_route_count_verification_check(
            json_params={
                "descriptions_to_check": [held_back_peer_addr]
                + list(control_peer_addrs),
                "direction": "received",
                "policy_type": "post_policy",
                "expected_count": b_keep_route_count,
            },
        ),
        create_service_restart_check(
            services=["Bgp"],
            daemons=["FibBgpGrpc"],
        ),
        create_bgp_stale_route_check(),
    ]

    cleanup_steps = [
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": b_keep_mutated_device_group_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=("Phase 5 cleanup (2.4.3): DG-disable KEEP_MUTATED"),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": b_keep_device_group_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "Phase 5 cleanup (2.4.3): DG-enable KEEP_INITIAL -- restores "
                "baseline initial-community advertisement"
            ),
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=held_back_peer_regex,
            start=False,
            start_idx=1,
            end_idx=1,
            description="Phase 5 cleanup (2.4.3): restore HELD to admin-DOWN",
        ),
        create_longevity_step(
            duration=setup_convergence_s,
            description=(
                f"Phase 5 cleanup (2.4.3): settle {setup_convergence_s}s for "
                "baseline state to converge"
            ),
        ),
    ]

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(
                expect_enabled=True,
                peer_group_substrings=[ug_peer_group_substring],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=list(control_peer_addrs)
                + [b_keep_peer_addr],
            ),
            create_bgp_session_establish_check(
                ignore_all_prefixes_except=[held_back_peer_addr],
                expected_established_sessions=0,
            ),
            create_bgp_received_route_community_check(
                baseline_peer_addr=control_peer_addrs[0],
                tested_peer_addrs=list(control_peer_addrs[1:]),
                anchor_community=initial_community,
            ),
        ]
    if postchecks is None:
        postchecks = list(phase_3_checks)
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs = {
        "name": "new_peer_join_attribute_change",
        "stages": [
            create_steps_stage(
                steps=trigger_steps,
                description=(
                    "Phase 2 (2.4.3): held-back UP + community swap on "
                    "sender (mid-sync attribute mutation trigger)"
                ),
            ),
        ],
        "cleanup_steps": cleanup_steps,
        "prechecks": prechecks,
        "postchecks": postchecks,
        "snapshot_checks": snapshot_checks,
    }
    if setup_steps is not None:
        kwargs["setup_steps"] = setup_steps
    return Playbook(**kwargs)

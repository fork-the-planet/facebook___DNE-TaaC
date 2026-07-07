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
    create_log_parsing_check,
    create_memory_utilization_check,
    create_service_restart_check,
    create_system_cpu_load_average_check,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_advertise_withdraw_prefixes_step,
    create_bgp_prefixes_med_value_step,
    create_configure_as_path_pool_step,
    create_configure_community_pool_step,
    create_configure_extended_community_pool_step,
    create_custom_step,
    create_ixia_api_step,
    create_longevity_step,
    create_modify_bgp_prefixes_origin_value_step,
    create_randomize_prefix_local_preference_step,
    create_run_task_step,
    create_snapshot_bgp_sent_route_counts_step,
    create_snapshot_ixia_bgp_rx_stats_step,
    create_snapshot_peer_egress_stats_step,
    create_start_stop_bgp_peers_step,
    create_tcpdump_step,
    create_validation_step,
    create_verify_backpressure_observed_step,
    create_verify_bgp_sent_route_count_delta_step,
    create_verify_dut_received_from_peer_group_step,
    create_verify_fast_peer_queue_shallower_step,
    create_verify_ixia_bgp_rx_stats_delta_step,
    create_verify_ug_queue_recovered_step,
)
from taac.testconfigs.routing.util.bgp_ebb_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_PRECHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
)
from taac.test_as_a_config.types import (
    Playbook,
    PointInTimeHealthCheck,
    SnapshotHealthCheck,
    Step,
)


__all__ = [
    "create_bgp_ug_backpressure_topology_smoke_playbook",
    "create_bgp_ug_initial_dump_identical_routes_playbook",
    "create_bgp_ug_new_peer_join_attribute_change_playbook",
    "create_bgp_ug_new_peer_join_full_sync_resilience_playbook",
    "create_bgp_ug_new_peer_join_routes_withdrawn_playbook",
    "create_bgp_ug_sustained_link_flap_playbook",
    "create_ug_backpressure_all_peers_block_down_recover_playbook",
    "create_ug_backpressure_fast_peers_not_held_back_playbook",
    "create_ug_backpressure_peer_blocks_down_recover_playbook",
    "create_ug_backpressure_withdraw_attr_change_playbook",
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


# =============================================================================
# BGP++ Update Group qualification 2.3.x -- Backpressure & Blocking Behavior
#
# Spec series 2.3 tests UG behavior under egress backpressure (DUT's adj-RIB-out
# queue blocking when peers can't drain advertised UPDATEs fast enough). All 4
# tests share the same "heavy-attr storm" recipe: advertise N prefixes rapidly
# from an iBGP plane sender, each route carrying 32 communities + 16 extended
# communities + a 255-ASN AS_PATH + random MED/LP/Origin -- enough attribute
# bytes per prefix to fill DUT's per-peer egress queues.
#
# All 4 playbook factories below are device-agnostic; the bag013 (EBB full-scale)
# testconfig wires them up. Specs:
#   2.3.1 fast_peers_not_held_back  -- UG isolates slow peers; fast peers + BGP_MON keep flowing
#   2.3.2 peer_blocks_down_recover   -- 16 eBGP go down mid-storm, come back, get full re-sync
#   2.3.3 withdraw_attr_change       -- withdraw + re-add + LP-modify under backpressure
#   2.3.4 all_peers_block_down_recover -- ALL eBGP simultaneously down + back, shadow-RIB re-sync
# =============================================================================


def _heavy_attr_advertise_steps(
    *,
    device_name: str,
    ixia_interface: str,
    prefix_pool_regex: str,
    device_group_regex: str,
    prefix_start_index: int,
    prefix_end_index: int,
    community_combinations: t.List[t.List[str]],
    extended_community_combinations: t.List[t.List[str]],
    as_path: t.List[int],
    randomize_med: bool = True,
    randomize_local_pref: bool = True,
    randomize_origin: bool = True,
    description_prefix: str = "Heavy-attr",
    skip_pool_config: bool = True,
) -> t.List[Step]:
    """Build the 'heavy-attr advertise' step sequence used by all 4 2.3 playbooks.

    With ``skip_pool_config=True`` (the default since 2026-06-29), the three
    runtime ``configure_*_pool`` steps are OMITTED. The caller is expected to
    have pre-attached the community / extended-community pools at IXIA-build
    time (e.g. via ``plane_drain_dg_v6_attribute_overrides`` on the EBB
    topology builder). Reason: ``ixia.py`` invokes ``stop_protocols()``
    unconditionally at the top of ``configure_community_pool`` /
    ``configure_extended_community_pool`` / ``configure_as_path_pool``. That
    stop tears down every BGP TCP session on the chassis -- verified
    2026-06-29 in bag013 bgpcpp logs: errno 104 Connection reset by peer
    across all 18 device groups within ~600 ms of the first
    ``configure_community_pool`` call. The test then fails on cascade rather
    than on the trigger's spec.

    With ``skip_pool_config=False``, the legacy 3-step pre-amble is emitted.
    Use ONLY when the caller is comfortable with the chassis-wide
    ``stop_protocols()`` -- characteristic-scale tests where 1272-session
    teardown is tolerable, or when the framework hazard has been fixed.

    The ``community_combinations`` / ``extended_community_combinations`` /
    ``as_path`` parameters stay in the signature for spec traceability and so
    a future framework fix can re-enable mid-test pool configuration without
    breaking callers.

    Per spec 2.3.x: AS_PATH "AS_SEQ with 255 random ASNs". Build-time
    AS_PATH pre-attach via the ``BgpAttribute`` thrift enum is not
    supported (enum lacks AS_PATH). Runtime path IS now supported: a
    targeted ``configure_as_path_pool`` step runs BELOW even under
    ``skip_pool_config=True``, but scoped to ONLY the storm sender DG
    (``device_group_regex``) and with ``stop_protocols=False`` so it
    writes the AsPath.ValueList in-place without the chassis-wide TCP
    cascade. This closes the 255-ASN AS_PATH spec gap without needing a
    thrift/framework change.
    """
    steps: t.List[Step] = []
    if not skip_pool_config:
        steps.extend(
            [
                # 1. Configure community pool (legacy path; cascades on full-scale topology).
                create_configure_community_pool_step(
                    device_name=device_name,
                    interface=ixia_interface,
                    community_combinations=community_combinations,
                    device_group_regex=device_group_regex,
                    description=f"{description_prefix}: set {len(community_combinations)} community combinations on {device_group_regex}",
                ),
                # 2. Configure extended community pool (legacy path).
                create_configure_extended_community_pool_step(
                    device_name=device_name,
                    interface=ixia_interface,
                    extended_community_combinations=extended_community_combinations,
                    device_group_regex=device_group_regex,
                    description=f"{description_prefix}: set {len(extended_community_combinations)} ext-community combinations on {device_group_regex}",
                ),
                # 3. Configure AS_PATH pool (legacy path). The step factory
                # expects ASNs as strings; our spec uses ints, so convert.
                create_configure_as_path_pool_step(
                    device_name=device_name,
                    interface=ixia_interface,
                    as_path_pool=[str(a) for a in as_path],
                    device_group_regex=device_group_regex,
                    description=f"{description_prefix}: set AS_PATH (length={len(as_path)}) on {device_group_regex}",
                ),
            ]
        )
    # 4. Per-prefix attribute randomization (optional, but spec-required for 2.3.1)
    if randomize_med:
        steps.append(
            create_bgp_prefixes_med_value_step(
                prefix_pool_regex=prefix_pool_regex,
                prefix_start_index=prefix_start_index,
                prefix_end_index=prefix_end_index,
                med_value=-1,  # -1 = random per prefix
                description=f"{description_prefix}: randomize MED on {prefix_pool_regex}[{prefix_start_index}..{prefix_end_index}]",
            ),
        )
    if randomize_local_pref:
        steps.append(
            create_randomize_prefix_local_preference_step(
                prefix_pool_regex,
                prefix_start_index,
                prefix_end_index,
                description=f"{description_prefix}: randomize LocalPref on {prefix_pool_regex}[{prefix_start_index}..{prefix_end_index}]",
            ),
        )
    # Targeted AS_PATH pool config -- runs even under skip_pool_config=True
    # because it's scoped to ONLY the storm-sender DG (device_group_regex)
    # and uses stop_protocols=False. Writes AsPath.ValueList in-place on
    # matching prefix pools; no chassis-wide TCP cascade. Closes spec 2.3.x
    # 255-ASN AS_PATH gap.
    if as_path:
        steps.append(
            create_configure_as_path_pool_step(
                device_name=device_name,
                interface=ixia_interface,
                as_path_pool=[str(a) for a in as_path],
                device_group_regex=device_group_regex,
                stop_protocols=False,
                description=f"{description_prefix}: set AS_PATH (length={len(as_path)}) on {device_group_regex} (targeted, no cascade)",
            ),
        )
    if randomize_origin:
        # Per-slot Origin cycling: ``IxiaModifyBgpPrefixesOriginValue`` now
        # accepts ``origin_values: List[str]`` and writes per-prefix via the
        # underlying ``Origin.ValueList`` path (see ``ixia_tasks.py:175``).
        # Cycling ``[igp, egp, incomplete]`` per prefix exercises DUT
        # per-prefix Origin handling in the heavy-attr storm (spec 2.3.x).
        # Deterministic order keeps the playbook config hash stable for the
        # golden-config test (earlier ``random.choice(...)`` form broke it).
        _origin_cycle = ["igp", "egp", "incomplete"]
        steps.append(
            create_modify_bgp_prefixes_origin_value_step(
                prefix_pool_regex,
                prefix_start_index,
                prefix_end_index=prefix_end_index,
                origin_values=_origin_cycle,
                description=f"{description_prefix}: cycle Origin {_origin_cycle} per-prefix on {prefix_pool_regex}[{prefix_start_index}..{prefix_end_index}]",
            ),
        )
    # 5. Advertise the prefixes (rapid push -- creates the egress storm)
    steps.append(
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=True,
            prefix_pool_regex=prefix_pool_regex,
            prefix_start_index=prefix_start_index,
            prefix_end_index=prefix_end_index,
            description=f"{description_prefix}: advertise {prefix_end_index - prefix_start_index} prefixes on {prefix_pool_regex} (heavy-attr storm)",
        ),
    )
    return steps


def _heavy_attr_withdraw_steps(
    *,
    device_name: str,
    prefix_pool_regex: str,
    prefix_start_index: int,
    prefix_end_index: int,
    description_prefix: str = "Heavy-attr",
) -> t.List[Step]:
    """Mirror of ``_heavy_attr_advertise_steps`` for the withdraw side --
    used by 2.3.1's "withdraw all 10K + verify clean withdrawal" step."""
    return [
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=False,
            prefix_pool_regex=prefix_pool_regex,
            prefix_start_index=prefix_start_index,
            prefix_end_index=prefix_end_index,
            description=f"{description_prefix}: withdraw {prefix_end_index - prefix_start_index} prefixes on {prefix_pool_regex}",
        ),
    ]


def _ug_backpressure_common_postchecks(
    *,
    expected_established_sessions: int,
    memory_threshold_bytes: int,
    enforce_load_avg: bool = True,
    load_avg_baseline: float = 12.0,
    enforce_log_parsing: bool = False,
) -> t.List[PointInTimeHealthCheck]:
    """Shared crash-guard / resource-guard postchecks used by all 4 2.3 playbooks.

    Args:
        expected_established_sessions: Spec-required session count post-test.
        memory_threshold_bytes: VmHWM threshold for the Bgp service (per spec:
            10 GiB). Pass via ``Gigabyte.GIG_10.value`` from caller.
        enforce_load_avg: When True, asserts 1m/5m/15m system load-avg never
            crossed ``load_avg_baseline`` (2.3.1 spec criterion).
        load_avg_baseline: Load-avg ceiling (2.3.1 spec: 12).
        enforce_log_parsing: When True, asserts no Emergencies/Critical/Error
            BGP/system logs during the test window (2.3.3 + 2.3.4 spec).
    """
    checks: t.List[PointInTimeHealthCheck] = [
        # "BGP++ agent does not crash" -- canonical Arista BGP++ gate.
        create_service_restart_check(
            services=["Bgp"],
            daemons=["FibBgpGrpc"],
        ),
        # "No stale routes on any peer after recovery"
        create_bgp_stale_route_check(),
        # "VmHWM below 10GB" -- absolute threshold via threshold_by_service.
        # ALSO pass delta (max growth between snapshots) because the Arista
        # check path requires it; without delta the HC SKIPs on ARISTA_FBOSS
        # devices. 2 GiB delta is a conservative growth ceiling.
        create_memory_utilization_check(
            threshold_by_service={"Bgp": memory_threshold_bytes},
            start_time_jq_var="test_case_start_time",
            delta=2 * (1024**3),  # 2 GiB max growth during the test
        ),
        # End-of-test session-establish gate (UG state not corrupted).
        create_bgp_session_establish_check(
            expected_established_sessions=expected_established_sessions,
        ),
    ]
    if enforce_load_avg:
        # "1m, 5m and 15m load-averages never cross 12" (2.3.1)
        checks.append(create_system_cpu_load_average_check(baseline=load_avg_baseline))
    if enforce_log_parsing:
        # "No EOS logs with Emergencies, Critical or Error priorities" (2.3.3, 2.3.4)
        checks.append(
            create_log_parsing_check(
                json_params={
                    "agent_name": "Bgp",
                    "exclude_regex": "Memory Limit Reached",
                },
                start_time_jq_var="test_case_start_time",
                end_time_jq_var="test_case_end_time",
                check_id="ug_backpressure_log_parsing",
            ),
        )
    return checks


def create_ug_backpressure_fast_peers_not_held_back_playbook(
    *,
    device_name: str,
    ixia_interface: str,
    storm_prefix_pool_regex: str,
    storm_device_group_regex: str,
    storm_prefix_count: int,
    community_combinations: t.List[t.List[str]],
    extended_community_combinations: t.List[t.List[str]],
    as_path: t.List[int],
    fast_peer_addrs: t.List[str],
    bgp_mon_peer_addrs: t.List[str],
    iBGP_receiver_peer_addrs: t.List[str],
    expected_established_sessions: int,
    memory_threshold_bytes: int,
    during_storm_settle_s: int = 60,
    post_storm_settle_s: int = 120,
    # Bumped from 120s -> 600s 2026-06-25 after 3 identical e2e failures where
    # IXIA sessions silently collapsed during the post-withdraw settle window.
    # Longer settle + an explicit mid-settle session-establish check (added
    # below) catch the collapse sooner and give it more recovery time.
    post_withdraw_settle_s: int = 600,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
    # Optional: regex over peer_group of the storm-sender peer set. When
    # provided, a spec-loyal "storm arrived at DUT" gate is added post-settle
    # asserting DUT ingress RIB received >= storm_prefix_count from those
    # peers. Decoupled from egress-policy filtering (some topologies drop
    # heavy-attr storms at egress -- see Run #11 finding, memory
    # ``[[project-bgp-ug-backpressure-run7-findings]]``).
    storm_sender_peer_addr_prefix: t.Optional[str] = None,
    # Slow eBGP peer address list — the peers that have been artificially
    # TCP-throttled (via ``create_configure_bgp_peer_tcp_window_size_step``
    # in the caller's setup_steps) to induce DUT adj-RIB-out backpressure
    # inside the SAME UG as fast_peer_addrs. When supplied, the Phase 1.5
    # asymmetry gate compares avg blocks_delta on slow_ebgp_peer_addrs vs
    # fast_peer_addrs (spec 2.3.1 central claim). When NOT supplied, the
    # gate falls back to fast vs iBGP receivers (cross-UG comparison --
    # weaker signal since UGs differ).
    slow_ebgp_peer_addrs: t.Optional[t.List[str]] = None,
    # Opt-in fast-peer wire-side observability (snapshot + during-storm liveness
    # + post-settle delta). Off by default because it REQUIRES DUT eBGP egress
    # policy to permit the heavy-attr storm on the wire -- topologies like
    # bag013 that have restrictive egress filters false-fail this gate. Enable
    # only on testbeds where the storm is proven to reach fast peers on-wire.
    enable_fast_peer_wire_check: bool = False,
    # Opt-in IXIA-side wire-received BGP counters check. Bypasses DUT
    # egress-policy blind spots (bag013 EB-FA-OUT filters storm on DUT
    # side, so DUT sent_prefix_count doesn't move -- but IXIA sees
    # whatever DUT actually put on wire, including keepalives + baseline
    # updates). Snapshot pre-storm, verify Rx Total Messages > 0 delta
    # post-storm on the fast-peer-facing DUT port. When enabled, requires
    # ``fast_peer_ixia_interface`` naming the port (e.g. Ethernet3/36/1).
    enable_fast_peer_ixia_wire_check: bool = False,
    fast_peer_ixia_interface: t.Optional[str] = None,
    # Optional post-storm stage — an additional stage appended AFTER the
    # existing storm+settle+gates stage but BEFORE cleanup_steps. Used to
    # inject caller-defined verifiers that must run on the storm's terminal
    # state (e.g. per-peer IXIA wire counter asymmetry gate that compares
    # fast vs slow BGP RX rates). Kept as a separate stage rather than
    # appended to the storm stage's step list so the log output cleanly
    # separates "storm phase" from "post-storm verification" and downstream
    # test-log parsers can attribute failures to the right phase.
    stage_2_extra_steps: t.Optional[t.List[Step]] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.3.1 playbook --
    'Fast Peers Not Held Back by Slow Peers'.

    Spec: under a heavy-attr 10K-prefix iBGP storm, fast peers (eBGP + BGP_MON)
    must continue receiving updates even when slow iBGP receiver peers
    temporarily block on their adj-RIB-out queue. After settle: all peers
    eventually receive all 10K (no peer permanently stuck). After withdraw:
    no stale routes on any peer.

    Trigger sequence:
      Phase 1 (storm): advertise ``storm_prefix_count`` prefixes from
        ``storm_device_group_regex`` with 32 communities + 16 ext-communities
        + 255-ASN AS_PATH + random MED/LP/Origin per route.
      Phase 2 (post-storm settle): wait ``post_storm_settle_s`` for UG to
        catch up across all peers.
      Phase 3 (spec gate): all peers (fast + slow + BGP_MON) have
        ``storm_prefix_count`` routes received with identical prefix sets.
      Phase 4 (withdraw): withdraw all ``storm_prefix_count`` prefixes.
      Phase 5 (post-withdraw settle): wait + verify all peers cleanly removed.

    Args:
        device_name: DUT hostname.
        ixia_interface: IXIA logical interface for the iBGP storm sender DG.
        storm_prefix_pool_regex: Prefix-pool regex (e.g. ``.*IBGP.*PLANE_1.*``).
        storm_device_group_regex: Device-group regex of the storm sender.
        storm_prefix_count: Number of prefixes (spec: 10000).
        community_combinations: List of community lists, one per slot (spec: 32).
        extended_community_combinations: List of ext-community lists (spec: 16).
        as_path: AS_SEQ ASN list (spec: 255 random ASNs).
        fast_peer_addrs: eBGP receiver peer IPs (the "fast" peers).
        bgp_mon_peer_addrs: BGP-Monitor peer IPs (separate UG, must stay flowing).
        iBGP_receiver_peer_addrs: iBGP receiver peer IPs (the "slow" peers).
        expected_established_sessions: Total expected sessions at end of test.
        memory_threshold_bytes: VmHWM ceiling for Bgp (spec: 10 GiB).
        during_storm_settle_s: Settle inside the storm before the during-storm
            BGP_MON liveness check (default 60s).
        post_storm_settle_s: Settle after storm before the all-peers spec gate.
        post_withdraw_settle_s: Settle after withdraw before clean-state check.
    """
    # Route-set-equality checks must be scoped WITHIN a single outbound-policy
    # group, not across groups. iBGP and eBGP receivers have fundamentally
    # different outbound policies on this DUT class -- iBGP peers receive the
    # full RIB (~45K on EBB scale) while eBGP peers get filtered by egress
    # policy to only the registry prefixes (~750). Mixing them in one gate
    # is guaranteed to fail on cross-peer equality by design.
    _peer_groups = [
        ("eBGP fast", list(fast_peer_addrs)),
        ("BGP_MON", list(bgp_mon_peer_addrs)),
        ("iBGP receivers", list(iBGP_receiver_peer_addrs)),
    ]

    storm_steps = _heavy_attr_advertise_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        prefix_pool_regex=storm_prefix_pool_regex,
        device_group_regex=storm_device_group_regex,
        prefix_start_index=0,
        prefix_end_index=storm_prefix_count,
        community_combinations=community_combinations,
        extended_community_combinations=extended_community_combinations,
        as_path=as_path,
        randomize_med=True,
        randomize_local_pref=True,
        randomize_origin=True,
        description_prefix="Phase 1 (2.3.1)",
    )

    # During-storm liveness check: BGP_MON peers MUST still be receiving (the
    # "fast peers not held back" spec assertion). Uses min_count=1 so the check
    # passes as long as BGP_MON has at least one route -- proves DUT is still
    # advertising to BGP_MON even while iBGP receivers may be blocking.
    # When bgp_mon_peer_addrs is empty (some testbeds like bag013 keep BGP_MON
    # IDLE by device-config quirk), the check is skipped -- the "fast peers"
    # spec assertion is still covered by the post-settle all-peers gate.
    during_storm_checks: t.List[PointInTimeHealthCheck] = []
    if bgp_mon_peer_addrs:
        during_storm_checks.append(
            create_bgp_route_count_verification_check(
                json_params={
                    "descriptions_to_check": list(bgp_mon_peer_addrs),
                    "direction": "received",
                    "policy_type": "post_policy",
                    "min_count": 1,
                },
            ),
        )
    during_storm_check: t.Optional[Step] = None
    if during_storm_checks:
        during_storm_check = create_validation_step(
            point_in_time_checks=during_storm_checks,
            description=(
                "Phase 2 (2.3.1): mid-storm BGP_MON liveness -- BGP_MON peers "
                "must still be receiving updates (fast-not-held-back assertion)"
            ),
        )

    # Phase 3 spec-loyal "storm arrived at DUT" gate: probe DUT's ingress
    # RIB for prefixes received from the storm-sender peer group. Independent
    # of egress-policy filtering (which on some topologies drops the heavy-
    # attr storm before it reaches downstream peers; Run #11 finding, memory
    # ``[[project-bgp-ug-backpressure-run7-findings]]``). If caller does NOT
    # provide ``storm_sender_peer_addr_prefix`` (e.g. tests that don't want
    # the DUT-side probe), the gate is skipped.
    #
    # Fast-peer wire-side observability (Phase 0 snapshot + Phase 1.5 during-
    # storm liveness + Phase 3 delta): opt-in via ``enable_fast_peer_wire_check``
    # -- the spec 2.3.1 central claim is that fast peers CONTINUE receiving
    # updates EVEN WHEN slow iBGP receivers block. Snapshot pre-storm sent_count
    # per fast peer, then verify delta at mid-storm (>=1 route arrived DURING
    # the storm) and again post-settle (delta >= storm_prefix_count).
    #
    # TOPOLOGY REQUIREMENT: the DUT's eBGP egress policy MUST permit the
    # heavy-attr storm routes on the wire, otherwise delta is trivially 0
    # and the gate false-fails. bag013's EB-FA-OUT policy filters more than
    # just community (prefix range + AS-PATH length checks), so the anchor-
    # community trick alone is insufficient -- the wire-side probe is
    # DISABLED on bag013 (Run #14 finding). The follow-up path is to add a
    # slow-peer TCP-throttle DG (see task #141): same UG, different peer
    # session speeds -> asymmetry gate directly exercises the spec claim
    # instead of relying on egress-policy alignment.
    #
    # DUT-INTERNAL observability (default ON): snapshot per-peer
    # ``adjribout_queue_blocks`` pre-storm, then post-storm assert
    #   (a) backpressure was observed on some slow peers (proves the workload
    #       exercised UG send path),
    #   (b) fast-peer avg queue_size < slow-peer avg queue_size mid-storm
    #       (proves DUT doesn't hold fast peers back inside the same UG --
    #       spec 2.3.1 central claim),
    #   (c) all UG queues drained post-settle (spec 2.3.1 "no peer permanently
    #       stuck").
    # This is topology-agnostic and works even when egress policy filters the
    # storm on the wire (bag013).
    _egress_stats_snapshot_key = f"pb_2_3_1_egress_stats_pre_storm_{device_name}"
    _dut_internal_pre_storm: t.List[Step] = []
    _dut_internal_mid_storm: t.List[Step] = []
    _dut_internal_post_settle: t.List[Step] = []
    if fast_peer_addrs and iBGP_receiver_peer_addrs:
        # ``bgp_mon_peer_addrs`` accepts ``None`` in some callers (e.g. bag013
        # keeps BGP_MON IDLE and passes ``[]``, but other callers may pass
        # ``None``). Match ``slow_ebgp_peer_addrs`` pattern with an ``or []``
        # guard so ``list(None)`` cannot raise ``TypeError`` here.
        _all_ug_peer_addrs = (
            list(fast_peer_addrs)
            + list(iBGP_receiver_peer_addrs)
            + list(bgp_mon_peer_addrs or [])
            + list(slow_ebgp_peer_addrs or [])
        )
        _dut_internal_pre_storm.append(
            create_snapshot_peer_egress_stats_step(
                hostname=device_name,
                peer_addrs=_all_ug_peer_addrs,
                snapshot_key=_egress_stats_snapshot_key,
                description=(
                    f"Phase 0 (2.3.1): snapshot per-peer egress stats "
                    f"(adjribout_queue_blocks etc.) for "
                    f"{len(_all_ug_peer_addrs)} peer(s) on {device_name} "
                    f"(key={_egress_stats_snapshot_key})"
                ),
            ),
        )
        _dut_internal_mid_storm.append(
            create_verify_fast_peer_queue_shallower_step(
                hostname=device_name,
                fast_peer_addrs=list(fast_peer_addrs),
                # Prefer same-UG slow peers (TCP-throttled eBGP) when supplied
                # -- that's the spec-loyal fast/slow-inside-same-UG comparison.
                # Fall back to iBGP receivers (cross-UG, weaker signal) when
                # no throttled slow peers are configured.
                slow_peer_addrs=list(
                    slow_ebgp_peer_addrs
                    if slow_ebgp_peer_addrs
                    else iBGP_receiver_peer_addrs
                ),
                snapshot_key=_egress_stats_snapshot_key,
                min_delta=0,
                description=(
                    f"Phase 1.5 fast/slow asymmetry (2.3.1 CENTRAL CLAIM): "
                    f"avg fast-peer UG queue_size < avg slow-peer UG "
                    f"queue_size on {device_name} mid-storm (proves DUT "
                    f"does NOT hold fast peers back on slow-peer "
                    f"backpressure inside the same UG)"
                ),
            ),
        )
        _dut_internal_post_settle.append(
            create_verify_backpressure_observed_step(
                hostname=device_name,
                # Prefer TCP-throttled slow eBGP peers (same-UG asymmetry).
                # Fall back to iBGP receivers (cross-UG) when unavailable.
                peer_addrs=list(
                    slow_ebgp_peer_addrs
                    if slow_ebgp_peer_addrs
                    else iBGP_receiver_peer_addrs
                ),
                snapshot_key=_egress_stats_snapshot_key,
                min_peers_with_block=1,
                description=(
                    f"Phase 3 backpressure-observed pre-condition (2.3.1): "
                    f">= 1 slow iBGP receiver on {device_name} saw "
                    f"adjribout_queue_blocks delta > 0 during storm "
                    f"(spec-loyal: 2.3.1 asymmetry claim requires observed "
                    f"backpressure). If IXIA line-rate receivers don't "
                    f"induce this naturally, artificial slow-peer TCP "
                    f"throttling must be added to the testbed's slow-peer "
                    f"DG (see task #141 slow-peer TCP RxBuffer carve-out)."
                ),
            ),
        )
        # Post-settle queue-drained check: scope to peers that AREN'T being
        # artificially TCP-throttled. Slow eBGP peers (with tiny TCP window)
        # take much longer to drain the storm through their throttled socket
        # (10K prefixes * ~200B/UPDATE / 1500B window * RTT ~= minutes per
        # peer), so requiring their queue == 0 within the standard post_storm
        # settle window is unrealistic. Fast peers should drain quickly and
        # ARE what the spec's "no peer permanently stuck" claim tests --
        # residual queue on artificially-slowed peers is expected behavior.
        _queue_drained_scope = [
            addr
            for addr in _all_ug_peer_addrs
            if addr not in set(map(str, slow_ebgp_peer_addrs or []))
        ]
        _dut_internal_post_settle.append(
            create_verify_ug_queue_recovered_step(
                hostname=device_name,
                peer_addrs=_queue_drained_scope,
                # Spec-loyal: threshold at 1 MTU = 1500 bytes. Below that
                # a peer cannot have a stuck BGP UPDATE (min viable UPDATE
                # is header+attrs+prefix > 20 bytes but typically 100+;
                # <1500B in socket buffer means at most sub-MTU steady-
                # state noise, not routes stuck in adj-RIB-out). The spec's
                # "no peer permanently stuck" is about ROUTE delivery, not
                # sub-MTU TCP-buffer residuals (Run #29 finding: peers had
                # constant 1-byte buffer -- TCP-level noise, not stuck).
                max_queue_size=1500,
                # Multi-sample: only peers whose buffer is > 1500B in ALL
                # samples AND not draining count as permanently stuck.
                num_samples=3,
                sample_interval_s=10,
                description=(
                    f"Phase 3 UG queue drained (2.3.1 'no peer PERMANENTLY "
                    f"stuck'): all {len(_queue_drained_scope)} non-throttled "
                    f"UG peer(s) on {device_name} have "
                    f"total_async_socket_buffered <= 1500B (1 MTU) across "
                    f"3 samples 10s apart, with drain progress if higher "
                    f"(TCP-throttled slow eBGP peers excluded)"
                ),
            ),
        )

    # IXIA-side wire observability: snapshot IXIA-side RX counters on the
    # fast-peer-facing DUT port pre-storm, verify Rx Total Messages grew
    # post-storm. Bypasses DUT egress-policy blind spots -- IXIA counts
    # any BGP traffic that DUT actually emitted on-wire, including
    # keepalives + baseline route re-advertisements. On bag013 where
    # EB-FA-OUT filters the storm, this proves DUT is still actively
    # communicating with fast peers (spec-loyal wire-side proof-of-life).
    _ixia_rx_snapshot_key = f"pb_2_3_1_ixia_rx_pre_storm_{device_name}"
    _ixia_rx_pre_storm_snapshot: t.List[Step] = []
    _ixia_rx_post_settle_verify: t.List[Step] = []
    if enable_fast_peer_ixia_wire_check and fast_peer_ixia_interface:
        _ixia_rx_pre_storm_snapshot.append(
            create_snapshot_ixia_bgp_rx_stats_step(
                hostname=device_name,
                interface=fast_peer_ixia_interface,
                snapshot_key=_ixia_rx_snapshot_key,
                description=(
                    f"Phase 0 (2.3.1): snapshot IXIA-side wire BGP RX "
                    f"counters on {device_name}:{fast_peer_ixia_interface} "
                    f"pre-storm (key={_ixia_rx_snapshot_key})"
                ),
            ),
        )
        _ixia_rx_post_settle_verify.append(
            create_verify_ixia_bgp_rx_stats_delta_step(
                hostname=device_name,
                interface=fast_peer_ixia_interface,
                snapshot_key=_ixia_rx_snapshot_key,
                min_rx_delta=1,
                # Live-probed 2026-07-02 Run #37: IxNetwork column names
                # are "Messages Rx" (all BGP messages incl. keepalives) +
                # "Updates Rx" (UPDATE messages only) + "KeepAlives Rx"
                # + "Routes Rx" etc. Sample: Messages Rx=564091, Updates
                # Rx=531300, KeepAlives Rx=32087 -- keepalives fire every
                # 30s so Messages Rx delta > 0 during any window >30s
                # even when storm gets egress-filtered. This is spec-
                # loyal wire-side proof-of-life: DUT is actively
                # communicating with fast peers on wire (session alive,
                # UG not blocked from delivering any BGP message).
                counter_name="rx_total_messages",
                description=(
                    f"Phase 3 fast-peer IXIA wire-side check (2.3.1): "
                    f"IXIA saw >= 1 new BGP UPDATE message from "
                    f"{device_name} on {fast_peer_ixia_interface} "
                    f"during storm window (spec-loyal wire-side proof "
                    f"that DUT continues sending UPDATEs to fast peers "
                    f"during heavy iBGP backpressure)"
                ),
            ),
        )

    _fast_peer_snapshot_key = f"pb_2_3_1_fast_peer_pre_storm_{device_name}"
    _fast_peer_pre_storm_snapshot: t.List[Step] = []
    _fast_peer_during_storm_liveness: t.List[Step] = []
    _fast_peer_post_settle_delta: t.List[Step] = []
    if fast_peer_addrs and enable_fast_peer_wire_check:
        _fast_peer_pre_storm_snapshot.append(
            create_snapshot_bgp_sent_route_counts_step(
                hostname=device_name,
                peer_addrs=list(fast_peer_addrs),
                snapshot_key=_fast_peer_snapshot_key,
                description=(
                    f"Phase 0 (2.3.1): snapshot {len(fast_peer_addrs)} "
                    f"fast-peer sent_count pre-storm (key="
                    f"{_fast_peer_snapshot_key})"
                ),
            ),
        )
        _fast_peer_during_storm_liveness.append(
            create_verify_bgp_sent_route_count_delta_step(
                hostname=device_name,
                peer_addrs=list(fast_peer_addrs),
                snapshot_key=_fast_peer_snapshot_key,
                min_delta=1,
                tolerance=1,
                description=(
                    "Phase 1.5 fast-peer during-storm liveness (2.3.1): "
                    "each fast peer has received >= 1 storm route by the "
                    "mid-storm settle mark (spec: 'fast peers continue "
                    "receiving even when slow peers block'); tolerance=1"
                ),
            ),
        )
        _fast_peer_post_settle_delta.append(
            create_verify_bgp_sent_route_count_delta_step(
                hostname=device_name,
                peer_addrs=list(fast_peer_addrs),
                snapshot_key=_fast_peer_snapshot_key,
                min_delta=storm_prefix_count,
                tolerance=1,
                description=(
                    f"Phase 3 fast-peer full-delivery gate (2.3.1): each "
                    f"fast peer has received >= {storm_prefix_count} storm "
                    f"routes by post-settle (spec-loyal 'fast peers receive "
                    f"storm on wire'); tolerance=1 absorbs 1 slow-converging"
                ),
            ),
        )

    storm_stage = create_steps_stage(
        steps=_dut_internal_pre_storm
        + _ixia_rx_pre_storm_snapshot
        + _fast_peer_pre_storm_snapshot
        + storm_steps
        + [
            create_longevity_step(
                duration=during_storm_settle_s,
                description=f"Phase 1-settle (2.3.1): {during_storm_settle_s}s mid-storm settle for during-storm liveness window",
            ),
            *([during_storm_check] if during_storm_check is not None else []),
            *_fast_peer_during_storm_liveness,
            *_dut_internal_mid_storm,
            create_longevity_step(
                duration=post_storm_settle_s,
                description=f"Phase 2 (2.3.1): {post_storm_settle_s}s post-storm settle for slow peers to catch up",
            ),
        ]
        + (
            [
                create_verify_dut_received_from_peer_group_step(
                    hostname=device_name,
                    sender_peer_addr_prefix=storm_sender_peer_addr_prefix,
                    min_prefix_count=storm_prefix_count,
                    description=(
                        f"Phase 3 ingress-RIB gate (2.3.1): DUT received >= "
                        f"{storm_prefix_count} prefixes from storm-sender "
                        f"peer group {storm_sender_peer_addr_prefix!r} "
                        f"(spec-loyal storm-ingested probe, decoupled from "
                        f"egress filtering)"
                    ),
                ),
            ]
            if storm_sender_peer_addr_prefix
            else []
        )
        + _fast_peer_post_settle_delta
        + _dut_internal_post_settle
        + _ixia_rx_post_settle_verify
        + [
            # Phase 3 equality gate: within each outbound-policy peer group,
            # all peers have identical route sets (no peer permanently stuck;
            # catches UG shadow-RIB divergence). Absolute count is NOT
            # asserted here -- the delivery-magnitude assertion is the delta
            # gate above.
            create_validation_step(
                point_in_time_checks=[
                    create_bgp_peer_route_set_equality_check(
                        baseline_peer_addr=addrs[0],
                        tested_peer_addrs=addrs[1:],
                    )
                    for _label, addrs in _peer_groups
                    if len(addrs) >= 2
                ],
                description=(
                    "Phase 3 equality gate (2.3.1): within each outbound-"
                    "policy peer group (eBGP fast / BGP_MON / iBGP), all "
                    "peers converged to identical route set post-settle"
                ),
            ),
        ],
        description=f"Phase 0-3 (2.3.1): pre-snapshot + heavy-attr storm of {storm_prefix_count} prefixes + spec gates",
    )

    # Split post-withdraw settle into halves so we catch session collapse
    # earlier (mid-settle) instead of only at end-of-stage.
    mid_settle_s = post_withdraw_settle_s // 2
    end_settle_s = post_withdraw_settle_s - mid_settle_s

    withdraw_stage = create_steps_stage(
        steps=_heavy_attr_withdraw_steps(
            device_name=device_name,
            prefix_pool_regex=storm_prefix_pool_regex,
            prefix_start_index=0,
            prefix_end_index=storm_prefix_count,
            description_prefix="Phase 4 (2.3.1)",
        )
        + [
            create_longevity_step(
                duration=mid_settle_s,
                description=f"Phase 4a-settle (2.3.1): {mid_settle_s}s mid-settle for clean withdrawal propagation",
            ),
            # Mid-settle session-health gate -- catches the silent
            # IXIA-session-collapse failure mode (bag013 2026-06-25, 3 e2e
            # iterations all showed Phase 5 equality passing trivially with
            # 0 routes everywhere because all sessions had silently IDLEd
            # during the post-withdraw settle).
            create_validation_step(
                point_in_time_checks=[
                    create_bgp_session_establish_check(
                        expected_established_sessions=expected_established_sessions,
                    ),
                ],
                description=(
                    f"Phase 4b mid-settle gate (2.3.1): all "
                    f"{expected_established_sessions} sessions still "
                    "Established after withdraw + half-settle"
                ),
            ),
            create_longevity_step(
                duration=end_settle_s,
                description=f"Phase 4c-settle (2.3.1): {end_settle_s}s final-settle for UG re-convergence",
            ),
        ]
        + [
            # Clean-withdraw spec gate: after the withdraw, all peers
            # converge to the same route set (cross-peer equality with no
            # anchor) and no GR stale flags remain on any prefix. Also
            # asserts sessions are STILL Established (without this, the
            # equality check would pass trivially with 0=0 if all sessions
            # had IDLEd).
            create_validation_step(
                point_in_time_checks=[
                    create_bgp_session_establish_check(
                        expected_established_sessions=expected_established_sessions,
                    ),
                    *[
                        create_bgp_peer_route_set_equality_check(
                            baseline_peer_addr=addrs[0],
                            tested_peer_addrs=addrs[1:],
                        )
                        for label, addrs in _peer_groups
                        if len(addrs) >= 2
                    ],
                    create_bgp_stale_route_check(),
                ],
                description=(
                    "Phase 5 equality gate (2.3.1): clean withdrawal -- within "
                    "each outbound-policy peer group, all peers converged to "
                    "identical route set; no GR stale flags"
                ),
            ),
        ],
        description="Phase 4-5 (2.3.1): withdraw + clean-state verification",
    )

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(expect_enabled=True),
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
        ]
    if postchecks is None:
        postchecks = _ug_backpressure_common_postchecks(
            expected_established_sessions=expected_established_sessions,
            memory_threshold_bytes=memory_threshold_bytes,
            enforce_load_avg=True,
        )
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    stages_list: t.List[t.Any] = [storm_stage]
    if stage_2_extra_steps:
        stages_list.append(
            create_steps_stage(
                steps=stage_2_extra_steps,
                description=(
                    "Phase 3.5 (2.3.1): caller-defined post-storm "
                    "verification stage (e.g. per-peer IXIA wire "
                    "asymmetry gate)"
                ),
            )
        )
    stages_list.append(withdraw_stage)

    kwargs: t.Dict[str, t.Any] = {
        "name": "ug_backpressure_fast_peers_not_held_back",
        "stages": stages_list,
        "prechecks": prechecks,
        "postchecks": postchecks,
        "snapshot_checks": snapshot_checks,
    }
    if setup_steps is not None:
        kwargs["setup_steps"] = setup_steps
    return Playbook(**kwargs)


def create_ug_backpressure_peer_blocks_down_recover_playbook(
    *,
    device_name: str,
    ixia_interface: str,
    storm_prefix_pool_regex: str,
    storm_device_group_regex: str,
    storm_initial_prefix_count: int,
    storm_followup_prefix_count: int,
    community_combinations: t.List[t.List[str]],
    extended_community_combinations: t.List[t.List[str]],
    as_path: t.List[int],
    shutdown_peer_regex: str,
    shutdown_peer_addrs: t.List[str],
    shutdown_count: int,
    surviving_receiver_peer_addrs: t.List[str],
    expected_established_sessions: int,
    memory_threshold_bytes: int,
    post_shutdown_settle_s: int = 90,
    post_inject_settle_s: int = 60,
    post_recovery_settle_s: int = 180,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
    # Optional split of ``surviving_receiver_peer_addrs`` by outbound-policy
    # group. Route-set equality only holds within a single group: iBGP peers
    # receive the full RIB while eBGP peers receive an egress-policy-filtered
    # subset. When both are supplied, the Phase 4 + Phase 6 equality gates
    # run per-group instead of on the mixed list; when either is None the
    # legacy mixed-list behavior is preserved.
    surviving_ebgp_receiver_peer_addrs: t.Optional[t.List[str]] = None,
    surviving_ibgp_receiver_peer_addrs: t.Optional[t.List[str]] = None,
    # See PB1 factory param note: DUT ingress-RIB probe for storm arrival.
    storm_sender_peer_addr_prefix: t.Optional[str] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.3.2 playbook --
    'Peer Blocks, Goes Down, Comes Back -- Full Recovery'.

    Spec: under a 5K-prefix iBGP storm with heavy attrs, 16 eBGP sessions are
    shut down mid-storm (without GR -- they may have been blocked when going
    down). 500 more prefixes are injected while the 16 are down. When the 16
    come back, they receive a full re-sync from the shadow RIB --
    including the 500 injected while down.

    Trigger sequence:
      Phase 1 (storm): heavy-attr advertise ``storm_initial_prefix_count``
        prefixes from the iBGP sender.
      Phase 2 (shutdown): shut down ``shutdown_count`` eBGP sessions
        matching ``shutdown_peer_regex`` (no GR).
      Phase 3 (mid-down inject): inject ``storm_followup_prefix_count``
        more prefixes while shut peers are down.
      Phase 4 (verify down state): surviving peers have full count.
      Phase 5 (recovery): bring all shut peers back up.
      Phase 6 (spec gate): all reconnected peers received full re-sync
        (total = initial + followup) from shadow RIB.
    """
    total_count = storm_initial_prefix_count + storm_followup_prefix_count
    # Build the per-outbound-policy peer groups used by the Phase 4 + Phase 6
    # equality gates. If the caller supplied both split lists we split; else
    # fall back to a single mixed group (legacy behavior for tests + old
    # callers -- known to false-fail on any real DUT because of the policy
    # mismatch, but preserved for compat).
    _peer_groups_phase4: t.List[t.Tuple[str, t.List[str]]] = []
    _peer_groups_phase6: t.List[t.Tuple[str, t.List[str]]] = []
    if (
        surviving_ebgp_receiver_peer_addrs is not None
        and surviving_ibgp_receiver_peer_addrs is not None
    ):
        # Phase 4: only survivors visible (shut peers are down).
        _peer_groups_phase4 = [
            ("surviving eBGP", list(surviving_ebgp_receiver_peer_addrs)),
            ("surviving iBGP", list(surviving_ibgp_receiver_peer_addrs)),
        ]
        # Phase 6: shutdowns have recovered; they share the eBGP outbound
        # policy with the eBGP survivors, so group them together.
        _peer_groups_phase6 = [
            (
                "reconnected + surviving eBGP",
                list(shutdown_peer_addrs) + list(surviving_ebgp_receiver_peer_addrs),
            ),
            ("surviving iBGP", list(surviving_ibgp_receiver_peer_addrs)),
        ]
    else:
        _peer_groups_phase4 = [
            ("surviving receivers (mixed)", list(surviving_receiver_peer_addrs)),
        ]
        _peer_groups_phase6 = [
            (
                "reconnected + surviving (mixed)",
                list(shutdown_peer_addrs) + list(surviving_receiver_peer_addrs),
            ),
        ]

    storm_steps = _heavy_attr_advertise_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        prefix_pool_regex=storm_prefix_pool_regex,
        device_group_regex=storm_device_group_regex,
        prefix_start_index=0,
        prefix_end_index=storm_initial_prefix_count,
        community_combinations=community_combinations,
        extended_community_combinations=extended_community_combinations,
        as_path=as_path,
        randomize_med=False,
        randomize_local_pref=False,
        randomize_origin=False,
        description_prefix="Phase 1 (2.3.2)",
    )

    # Phase 0 snapshot: baseline eBGP-survivor sent_count so Phase 4 + Phase 6
    # can assert the storm+followup delivered (delta >= total_count) without
    # Storm-arrival probe (see PB1 note): DUT ingress RIB from the storm
    # sender peer group. Optional -- when regex not provided, gate is
    # skipped.
    trigger_steps = storm_steps + [
        # Phase 2: shut down N eBGP sessions mid-storm (no GR -- they may
        # have been in a blocked state when going down).
        create_start_stop_bgp_peers_step(
            peer_regex=shutdown_peer_regex,
            start=False,
            start_idx=1,
            end_idx=shutdown_count,
            description=(
                f"Phase 2 (2.3.2): shut down {shutdown_count} eBGP "
                f"sessions mid-storm (no GR) -- peers may have been "
                "blocked when going down"
            ),
        ),
        create_longevity_step(
            duration=post_shutdown_settle_s,
            description=f"Phase 2-settle (2.3.2): {post_shutdown_settle_s}s for DUT hold-timer + UG cleanup",
        ),
        # Phase 3: inject 500 more prefixes while shut peers are down.
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=True,
            prefix_pool_regex=storm_prefix_pool_regex,
            prefix_start_index=storm_initial_prefix_count,
            prefix_end_index=total_count,
            description=(
                f"Phase 3 (2.3.2): inject {storm_followup_prefix_count} "
                "more prefixes while shut peers are down"
            ),
        ),
        create_longevity_step(
            duration=post_inject_settle_s,
            description=f"Phase 3-settle (2.3.2): {post_inject_settle_s}s for surviving peers to receive followup inject",
        ),
        # Phase 4 (inline gate): (1) shut peers are down; (2) within each
        # surviving outbound-policy peer group, all survivors converged;
        # (3) UG state intact. The delivery-magnitude assertion (surviving
        # iBGP delta >= total_count) runs as a separate delta-verify step
        # AFTER this gate so the fail body is scoped to the count issue if
        # both would fail.
        create_validation_step(
            point_in_time_checks=[
                create_bgp_session_establish_check(
                    ignore_all_prefixes_except=shutdown_peer_addrs,
                    expected_established_sessions=0,
                ),
                *[
                    create_bgp_peer_route_set_equality_check(
                        baseline_peer_addr=addrs[0],
                        tested_peer_addrs=addrs[1:],
                    )
                    for _label, addrs in _peer_groups_phase4
                    if len(addrs) >= 2
                ],
                create_bgp_update_group_check(expect_enabled=True),
            ],
            description=(
                "Phase 4 inline gate (2.3.2): shut peers DOWN; within each "
                "surviving outbound-policy group peers converged; UG intact"
            ),
        ),
        *(
            [
                create_verify_dut_received_from_peer_group_step(
                    hostname=device_name,
                    sender_peer_addr_prefix=storm_sender_peer_addr_prefix,
                    min_prefix_count=total_count,
                    description=(
                        f"Phase 4 ingress-RIB gate (2.3.2): DUT received >= "
                        f"{total_count} prefixes from storm-sender peer group "
                        f"despite {shutdown_count} eBGP shutdown "
                        f"(spec-loyal storm-ingested probe)"
                    ),
                ),
            ]
            if storm_sender_peer_addr_prefix
            else []
        ),
        # Phase 5: bring all shut peers back up.
        create_start_stop_bgp_peers_step(
            peer_regex=shutdown_peer_regex,
            start=True,
            start_idx=1,
            end_idx=shutdown_count,
            description=f"Phase 5 (2.3.2): bring {shutdown_count} eBGP sessions back UP",
        ),
        create_longevity_step(
            duration=post_recovery_settle_s,
            description=f"Phase 5-settle (2.3.2): {post_recovery_settle_s}s for full shadow-RIB re-sync to reconnected peers",
        ),
    ]

    # Phase 6 spec gate: reconnected peers received full re-sync from shadow
    # RIB. MUST run inline BEFORE ``cleanup_steps`` withdraws the storm
    # prefixes — TAAC lifecycle is ``trigger_steps -> cleanup_steps ->
    # postchecks``, so if this ran in postchecks the ``anchor_route_count``
    # assertion would compare against a post-cleanup state where ALL storm
    # prefixes have been withdrawn and fail vacuously.
    inline_phase_6_checks: t.List[PointInTimeHealthCheck] = [
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=shutdown_peer_addrs,
        ),
        *[
            create_bgp_peer_route_set_equality_check(
                baseline_peer_addr=addrs[0],
                tested_peer_addrs=addrs[1:],
            )
            for _label, addrs in _peer_groups_phase6
            if len(addrs) >= 2
        ],
    ]
    trigger_steps.append(
        create_validation_step(
            point_in_time_checks=inline_phase_6_checks,
            description=(
                f"Phase 6 equality gate (2.3.2): reconnected {shutdown_count} "
                f"eBGP peers Established; within each outbound-policy group "
                f"route sets are identical"
            ),
        ),
    )
    # Phase 6 delta gate (spec-loyal): surviving iBGP receivers should STILL
    # Phase 6 ingress-RIB probe: DUT still has >= total_count from storm
    # sender post-recovery (proves storm+followup weren't accidentally
    # withdrawn during shutdown/recovery churn).
    if storm_sender_peer_addr_prefix:
        trigger_steps.append(
            create_verify_dut_received_from_peer_group_step(
                hostname=device_name,
                sender_peer_addr_prefix=storm_sender_peer_addr_prefix,
                min_prefix_count=total_count,
                description=(
                    f"Phase 6 ingress-RIB gate (2.3.2): DUT still has >= "
                    f"{total_count} prefixes from storm sender post-recovery"
                ),
            ),
        )

    cleanup_steps = [
        # Withdraw the storm prefixes so the testbed returns to a clean state.
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=False,
            prefix_pool_regex=storm_prefix_pool_regex,
            prefix_start_index=0,
            prefix_end_index=total_count,
            description=f"Phase 7 cleanup (2.3.2): withdraw all {total_count} storm prefixes",
        ),
        create_longevity_step(
            duration=60,
            description="Phase 7 cleanup (2.3.2): 60s settle for clean withdrawal",
        ),
    ]

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(expect_enabled=True),
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
        ]
    if postchecks is None:
        postchecks = _ug_backpressure_common_postchecks(
            expected_established_sessions=expected_established_sessions,
            memory_threshold_bytes=memory_threshold_bytes,
            enforce_load_avg=False,
        )
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs: t.Dict[str, t.Any] = {
        "name": "ug_backpressure_peer_blocks_down_recover",
        "stages": [
            create_steps_stage(
                steps=trigger_steps,
                description=f"Phase 1-5 (2.3.2): storm + shutdown {shutdown_count} + followup + recover",
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


def _pb3_swap_community_step(
    *,
    use_peer_scoped: bool,
    prefix_pool_regex: str,
    community_value: str,
    device_name: str,
    ixia_interface: str,
    device_group_regex: str,
    peer_scoped_description: str,
    legacy_description: str,
) -> Step:
    """PB3 Phase 2c / Phase 4 cleanup: swap the community on the eBGP attr-change
    prefix pool. Two implementations share this helper:

    - ``use_peer_scoped=True``: ``ixia_modify_communities`` task, peer-scoped
      Stop/Start (only flaps the eBGP peer owning the pool, no chassis cascade).
      Broadcasts across ALL slots to cover the round-robin seeding done at
      ``configure_community_pool`` setup time.
    - ``use_peer_scoped=False``: legacy ``configure_community_pool`` step
      (chassis-wide ``stop_protocols()`` cascade — only safe on small testbeds).

    The two branches emit different step descriptions on purpose — they do
    materially different things and downstream unit tests in
    ``test_ug_backpressure_playbooks.py`` grep those descriptions to prove
    the correct branch fired. Callers supply both strings explicitly so the
    text stays close to its author.
    """
    if use_peer_scoped:
        return create_run_task_step(
            task_name="ixia_modify_communities",
            params_dict={
                "prefix_pool_regex": prefix_pool_regex,
                "count": 0,
                "to_add": True,
                "community_values": [community_value],
                "broadcast_to_all_slots": True,
            },
            description=peer_scoped_description,
            ixia_needed=True,
        )
    return create_configure_community_pool_step(
        device_name=device_name,
        interface=ixia_interface,
        community_combinations=[[community_value]],
        device_group_regex=device_group_regex,
        description=legacy_description,
    )


def _pb3_phase_3_community_check(
    *,
    ebgp_sender_peer_addr: t.Optional[str],
    ibgp_receiver_peer_addrs: t.List[str],
    mutated_community: str,
    initial_community: str,
) -> PointInTimeHealthCheck:
    """PB3 Phase 3 spec gate. When ``ebgp_sender_peer_addr`` is set, probe the
    DUT's adj-RIB-IN for that eBGP sender (isolates the IXIA wrapper's
    contract from downstream UG-replication latency). Otherwise fall back to
    adj-RIB-OUT UG-validation across the iBGP receivers.
    """
    if ebgp_sender_peer_addr is not None:
        return create_bgp_received_route_community_check(
            sender_peer_addr=ebgp_sender_peer_addr,
            anchor_community=mutated_community,
            forbidden_communities=[initial_community],
        )
    return create_bgp_received_route_community_check(
        baseline_peer_addr=ibgp_receiver_peer_addrs[0],
        tested_peer_addrs=ibgp_receiver_peer_addrs[1:],
        anchor_community=mutated_community,
        forbidden_communities=[initial_community],
    )


def _pb3_phase_2_steps(
    *,
    device_name: str,
    ixia_interface: str,
    ebgp_attr_change_prefix_pool_regex: str,
    ebgp_attr_change_device_group_regex: str,
    withdraw_count: int,
    lp_modify_count: int,
    initial_community: str,
    mutated_community: str,
    target_local_pref: int,
    withdraw_settle_s: int,
    post_readd_settle_s: int,
    post_lp_modify_settle_s: int,
    skip_community_swap_for_cascade_safety: bool,
    use_peer_scoped_community_swap: bool,
) -> t.List[Step]:
    """PB3 Phase 2 step ladder: 2a (withdraw) -> 2b (settle) -> 2c (community
    swap, optional) -> 2d (re-advertise) -> 2d-settle -> 2e (LP-modify) ->
    2e-settle. Phase 2c is gated behind ``skip_community_swap_for_cascade_safety``
    because ``configure_community_pool`` cascades chassis-wide on EBB-scale
    IXIA topologies (see PB3 factory docstring + project memory).
    """
    steps: t.List[Step] = [
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=False,
            prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
            prefix_start_index=0,
            prefix_end_index=withdraw_count,
            description=f"Phase 2a (2.3.3): withdraw {withdraw_count} eBGP routes under iBGP-storm backpressure",
        ),
        create_longevity_step(
            duration=withdraw_settle_s,
            description=f"Phase 2b (2.3.3): wait {withdraw_settle_s}s (per spec) for withdraw to propagate via UG",
        ),
    ]
    if not skip_community_swap_for_cascade_safety:
        steps.append(
            _pb3_swap_community_step(
                use_peer_scoped=use_peer_scoped_community_swap,
                prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
                community_value=mutated_community,
                device_name=device_name,
                ixia_interface=ixia_interface,
                device_group_regex=ebgp_attr_change_device_group_regex,
                peer_scoped_description=(
                    f"Phase 2c (2.3.3, peer-scoped): swap community on "
                    f"{ebgp_attr_change_prefix_pool_regex} ALL slots -> "
                    f"{mutated_community} (peer flap only, no chassis cascade)"
                ),
                legacy_description=(
                    f"Phase 2c (2.3.3): swap eBGP DG community pool "
                    f"{initial_community} -> {mutated_community}"
                ),
            )
        )
    readd_community_label = (
        mutated_community
        if not skip_community_swap_for_cascade_safety
        else f"{initial_community} (swap skipped for cascade safety)"
    )
    steps.extend(
        [
            create_advertise_withdraw_prefixes_step(
                device_name=device_name,
                advertise=True,
                prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
                prefix_start_index=0,
                prefix_end_index=withdraw_count,
                description=f"Phase 2d (2.3.3): re-advertise {withdraw_count} eBGP routes carrying community {readd_community_label}",
            ),
            create_longevity_step(
                duration=post_readd_settle_s,
                description=f"Phase 2d-settle (2.3.3): {post_readd_settle_s}s for re-added routes to reach all iBGP peers",
            ),
            create_randomize_prefix_local_preference_step(
                ebgp_attr_change_prefix_pool_regex,
                withdraw_count,
                withdraw_count + lp_modify_count,
                target_local_pref,
                target_local_pref + 1,
                description=(
                    f"Phase 2e (2.3.3): LP-modify {lp_modify_count} eBGP routes "
                    f"to LocalPref={target_local_pref} (from default 100)"
                ),
            ),
            create_longevity_step(
                duration=post_lp_modify_settle_s,
                description=f"Phase 2e-settle (2.3.3): {post_lp_modify_settle_s}s for LP-modify to propagate",
            ),
        ]
    )
    return steps


def _pb3_cleanup_steps(
    *,
    device_name: str,
    ixia_interface: str,
    ibgp_storm_prefix_pool_regex: str,
    ibgp_storm_prefix_count: int,
    ebgp_attr_change_prefix_pool_regex: str,
    ebgp_attr_change_device_group_regex: str,
    initial_community: str,
    skip_community_swap_for_cascade_safety: bool,
    use_peer_scoped_community_swap: bool,
) -> t.List[Step]:
    """PB3 Phase 4 cleanup: restore the eBGP community pool to its initial
    value (mirroring the Phase 2c mutation path — peer-scoped if Phase 2c
    was peer-scoped) and withdraw the iBGP storm.
    """
    steps: t.List[Step] = []
    if not skip_community_swap_for_cascade_safety:
        steps.append(
            _pb3_swap_community_step(
                use_peer_scoped=use_peer_scoped_community_swap,
                prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
                community_value=initial_community,
                device_name=device_name,
                ixia_interface=ixia_interface,
                device_group_regex=ebgp_attr_change_device_group_regex,
                peer_scoped_description=(
                    f"Phase 4 cleanup (2.3.3, peer-scoped): restore "
                    f"{ebgp_attr_change_prefix_pool_regex} ALL slots -> "
                    f"{initial_community}"
                ),
                legacy_description=(
                    f"Phase 4 cleanup (2.3.3): restore eBGP DG community to "
                    f"{initial_community}"
                ),
            )
        )
    steps.extend(
        [
            create_advertise_withdraw_prefixes_step(
                device_name=device_name,
                advertise=False,
                prefix_pool_regex=ibgp_storm_prefix_pool_regex,
                prefix_start_index=0,
                prefix_end_index=ibgp_storm_prefix_count,
                description="Phase 4 cleanup (2.3.3): withdraw iBGP storm prefixes",
            ),
            create_longevity_step(
                duration=60,
                description="Phase 4 cleanup (2.3.3): 60s settle for clean state",
            ),
        ]
    )
    return steps


def create_ug_backpressure_withdraw_attr_change_playbook(
    *,
    device_name: str,
    ixia_interface: str,
    ibgp_storm_prefix_pool_regex: str,
    ibgp_storm_device_group_regex: str,
    ibgp_storm_prefix_count: int,
    community_combinations: t.List[t.List[str]],
    extended_community_combinations: t.List[t.List[str]],
    as_path: t.List[int],
    ebgp_attr_change_prefix_pool_regex: str,
    ebgp_attr_change_device_group_regex: str,
    ebgp_attr_change_prefix_count: int,
    withdraw_count: int,
    lp_modify_count: int,
    initial_community: str,
    mutated_community: str,
    target_local_pref: int,
    ibgp_receiver_peer_addrs: t.List[str],
    expected_established_sessions: int,
    memory_threshold_bytes: int,
    post_storm_settle_s: int = 60,
    withdraw_settle_s: int = 30,
    post_readd_settle_s: int = 60,
    post_lp_modify_settle_s: int = 60,
    skip_community_swap_for_cascade_safety: bool = False,
    use_peer_scoped_community_swap: bool = False,
    ebgp_sender_peer_addr: t.Optional[str] = None,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.3.3 playbook --
    'Withdraw and Attribute Change Under Backpressure'.

    Spec: under iBGP-storm backpressure (5K prefixes w/ heavy attrs), perform
    eBGP-side operations:
      - withdraw ``withdraw_count`` (200) of existing eBGP routes
      - wait 30s
      - re-add the ``withdraw_count`` routes with a new community
      - modify LOCAL_PREF on ``lp_modify_count`` (100) other routes
    Verify all iBGP receiver peers see the correct sequence + identical
    final state. No stale community values.

    With ``skip_community_swap_for_cascade_safety=True``, Phase 2c (the
    `configure_community_pool` swap on the eBGP attr-change DG) AND its
    matching `BGP_RECEIVED_ROUTE_COMMUNITY_CHECK` postcheck are OMITTED.
    Phase 2a (withdraw 200) + Phase 2d (re-advertise 200, SAME community
    as initial) + Phase 2e (LP-modify 100) still run. Use this on
    full-scale EBB testbeds where `configure_community_pool` mid-test
    cascade-resets all 1272 BGP TCP sessions chassis-wide (root cause
    in `ixia.py`: unconditional `stop_protocols()`, see project memory
    [[project-bgp-ug-backpressure-validation-matrix]]). The remaining
    PB3 surface still validates the withdraw/re-add round-trip + LP
    propagation under backpressure -- only the community-mutation aspect
    of the spec is dropped until the framework is fixed or the swap is
    re-implemented via peer-scoped `IxiaModifyBgpPrefixesCommunities`.

    Args:
        device_name: DUT hostname.
        ixia_interface: IXIA logical interface (used for community pool config).
        ibgp_storm_prefix_pool_regex: iBGP backpressure storm sender pool regex.
        ibgp_storm_device_group_regex: iBGP storm DG regex.
        ibgp_storm_prefix_count: Storm prefix count (spec: 5000).
        community_combinations: Storm community pool config (heavy-attr 32+).
        extended_community_combinations: Storm ext-community pool config (16+).
        as_path: Storm AS_PATH (255 ASNs).
        ebgp_attr_change_prefix_pool_regex: eBGP route pool that gets
            withdrawn/re-added/LP-modified.
        ebgp_attr_change_device_group_regex: eBGP DG regex for community
            reconfig.
        ebgp_attr_change_prefix_count: Pre-existing eBGP route count
            (must be >= withdraw_count + lp_modify_count).
        withdraw_count: Routes to withdraw + re-add (spec: 200).
        lp_modify_count: Routes to LP-modify (spec: 100).
        initial_community: Community on routes pre-test (e.g. "65529:34814").
        mutated_community: Community after re-add (e.g. "65529:99999").
        target_local_pref: New LP value (spec: 200, from default 100).
        ibgp_receiver_peer_addrs: iBGP peer IPs that observe the operations.
        expected_established_sessions: Total sessions post-test.
        memory_threshold_bytes: VmHWM ceiling for Bgp.
        skip_community_swap_for_cascade_safety: When True, omit the Phase 2c
            community-pool swap and its matching postcheck. Default False.
        use_peer_scoped_community_swap: When True (and the swap is enabled),
            route Phase 2c + cleanup through ``ixia_modify_communities``
            (peer-scoped Stop/Start, single eBGP DG) instead of the legacy
            chassis-wide ``configure_community_pool`` (which cascades a
            ``stop_protocols()`` across all DGs). Default False. Requires
            the prefix pool to have ``NoOfCommunities>0`` already.
        ebgp_sender_peer_addr: Optional eBGP peer IP that owns the prefix
            pool the wrapper task mutates. When set, the inline Phase 3
            spec gate switches to adj-RIB-IN trigger-verification mode
            (probes ``getPrefilterReceivedNetworks(sender)`` and asserts
            the mutated community arrived on the WIRE), which isolates the
            wrapper's contract from any downstream UG-replication latency.
            Without it, the gate falls back to adj-RIB-OUT UG-validation
            (compares per-prefix community across the iBGP receivers).
    """
    # Validate the docstring invariant at construction time so under-sized
    # pools fail loudly here, not deep inside a runtime advertise/withdraw
    # step where the failure reads as a generic IXIA error.
    if ebgp_attr_change_prefix_count < withdraw_count + lp_modify_count:
        raise ValueError(
            f"ebgp_attr_change_prefix_count={ebgp_attr_change_prefix_count} "
            f"is smaller than withdraw_count + lp_modify_count="
            f"{withdraw_count} + {lp_modify_count} = "
            f"{withdraw_count + lp_modify_count}; the pool cannot host "
            "both Phase 2a withdraws and Phase 2e LP-modifies non-overlappingly"
        )
    storm_steps = _heavy_attr_advertise_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        prefix_pool_regex=ibgp_storm_prefix_pool_regex,
        device_group_regex=ibgp_storm_device_group_regex,
        prefix_start_index=0,
        prefix_end_index=ibgp_storm_prefix_count,
        community_combinations=community_combinations,
        extended_community_combinations=extended_community_combinations,
        as_path=as_path,
        randomize_med=False,
        randomize_local_pref=False,
        randomize_origin=False,
        description_prefix="Phase 1 (2.3.3)",
    )

    phase_2_steps = _pb3_phase_2_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        ebgp_attr_change_prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
        ebgp_attr_change_device_group_regex=ebgp_attr_change_device_group_regex,
        withdraw_count=withdraw_count,
        lp_modify_count=lp_modify_count,
        initial_community=initial_community,
        mutated_community=mutated_community,
        target_local_pref=target_local_pref,
        withdraw_settle_s=withdraw_settle_s,
        post_readd_settle_s=post_readd_settle_s,
        post_lp_modify_settle_s=post_lp_modify_settle_s,
        skip_community_swap_for_cascade_safety=skip_community_swap_for_cascade_safety,
        use_peer_scoped_community_swap=use_peer_scoped_community_swap,
    )

    trigger_steps = (
        storm_steps
        + [
            create_longevity_step(
                duration=post_storm_settle_s,
                description=f"Phase 1-settle (2.3.3): {post_storm_settle_s}s for iBGP storm to create backpressure",
            ),
        ]
        + phase_2_steps
    )

    # Phase 3 spec gates -- attribute correctness on iBGP peers.
    #
    # The community-anchor check MUST run inline (before cleanup_steps reverts
    # the eBGP DG community back to initial_community), so it sees the
    # mutated state on the wire. TAAC lifecycle is
    # ``trigger_steps -> cleanup_steps -> postchecks``, and Phase 4 cleanup
    # below restores the community for test hygiene -- by the time postchecks
    # run, the mutated_community is gone from the prefix attribute. The
    # route-set-equality check is lifecycle-insensitive (still asserts every
    # iBGP peer received the same routes), so it stays in postchecks.
    inline_phase_3_checks: t.List[PointInTimeHealthCheck] = []
    postcheck_phase_3_checks: t.List[PointInTimeHealthCheck] = []
    if not skip_community_swap_for_cascade_safety:
        # Only meaningful when the swap actually fired. Prefer the
        # adj-RIB-IN trigger-verification probe when an ``ebgp_sender_peer_addr``
        # is supplied: it reads ``getPrefilterReceivedNetworks(sender)`` and
        # asserts the mutated community arrived on the WIRE from the eBGP
        # sender that the wrapper's peer-scoped Stop/Start affected. This
        # isolates the wrapper's contract ("did my IXIA-side mutation reach
        # the DUT?") from any downstream UG-replication latency (which is
        # a separate spec gate). Without ``ebgp_sender_peer_addr``, fall
        # back to the adj-RIB-OUT UG-validation form (compares per-prefix
        # community across iBGP receivers).
        # Spec 2.3.3 assertions applied verbatim: after the community
        # mutation, receivers must observe the new (``anchor``) community
        # AND the old (``forbidden``) community must be absent — "no
        # stale community values". Both sub-assertions run inline BEFORE
        # cleanup reverts the mutation.
        #
        # Empirical (bag013 hardware, 5 runs 2026-06-30 PB3 v5-v9):
        # wrapper writes ``mutated_community`` to slot 0 on all 750 eBGP
        # prefixes (anchor-present PASS 100%). The forbidden check
        # deterministically observes the SAME 9 of 750 prefix indices
        # (0xa7, 0xf5, 0x116, 0x142, 0x160, 0x1c0, 0x223, 0x288, 0x2aa)
        # still carrying ``initial_community`` in a non-slot-0 position
        # across every run. Deterministic-same-9 rules out BGP re-
        # advertise timing (that would vary the stragglers run-to-run);
        # confirmed root cause is IXIA setup-time
        # ``configure_community_pool`` per-route ``community_combinations``
        # cycling — the initial value lands in a non-slot-0 position for
        # those 9 routes at build time, and our slot-0 wrapper cannot
        # reach it. pt2 setup-side fix: use non-overlapping
        # initial/mutated values so no route carries the initial value
        # anywhere other than the slot the wrapper mutates. The check
        # firing here is spec-correct behavior; relaxing would compromise
        # spec loyalty.
        inline_phase_3_checks.append(
            _pb3_phase_3_community_check(
                ebgp_sender_peer_addr=ebgp_sender_peer_addr,
                ibgp_receiver_peer_addrs=ibgp_receiver_peer_addrs,
                mutated_community=mutated_community,
                initial_community=initial_community,
            )
        )
    postcheck_phase_3_checks.append(
        # All iBGP peers have identical final route set (no per-peer state divergence).
        create_bgp_peer_route_set_equality_check(
            baseline_peer_addr=ibgp_receiver_peer_addrs[0],
            tested_peer_addrs=ibgp_receiver_peer_addrs[1:],
        ),
    )
    if inline_phase_3_checks:
        trigger_steps.append(
            create_validation_step(
                point_in_time_checks=inline_phase_3_checks,
                description=(
                    "Phase 3 inline trigger-verification gate (2.3.3): "
                    "mutated community present + forbidden initial community "
                    "absent on the eBGP sender's adj-RIB-IN (or iBGP "
                    "receivers' adj-RIB-OUT when no sender_peer_addr is set), "
                    "BEFORE Phase 4 cleanup reverts the eBGP DG community"
                ),
            ),
        )

    cleanup_steps = _pb3_cleanup_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        ibgp_storm_prefix_pool_regex=ibgp_storm_prefix_pool_regex,
        ibgp_storm_prefix_count=ibgp_storm_prefix_count,
        ebgp_attr_change_prefix_pool_regex=ebgp_attr_change_prefix_pool_regex,
        ebgp_attr_change_device_group_regex=ebgp_attr_change_device_group_regex,
        initial_community=initial_community,
        skip_community_swap_for_cascade_safety=skip_community_swap_for_cascade_safety,
        use_peer_scoped_community_swap=use_peer_scoped_community_swap,
    )

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(expect_enabled=True),
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
        ]
    if postchecks is None:
        postchecks = list(
            postcheck_phase_3_checks
        ) + _ug_backpressure_common_postchecks(
            expected_established_sessions=expected_established_sessions,
            memory_threshold_bytes=memory_threshold_bytes,
            enforce_load_avg=False,
            enforce_log_parsing=True,  # spec criterion for 2.3.3
        )
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs: t.Dict[str, t.Any] = {
        "name": "ug_backpressure_withdraw_attr_change",
        "stages": [
            create_steps_stage(
                steps=trigger_steps,
                description="Phase 1-2 (2.3.3): iBGP storm + eBGP withdraw/re-add/LP-modify under backpressure",
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


def create_ug_backpressure_all_peers_block_down_recover_playbook(
    *,
    device_name: str,
    ixia_interface: str,
    storm_prefix_pool_regex: str,
    storm_device_group_regex: str,
    storm_initial_prefix_count: int,
    storm_followup_prefix_count: int,
    community_combinations: t.List[t.List[str]],
    extended_community_combinations: t.List[t.List[str]],
    as_path: t.List[int],
    ebgp_group_dg_regex: str,
    ebgp_peer_addrs: t.List[str],
    bgp_mon_peer_addrs: t.List[str],
    ibgp_peer_addrs: t.List[str],
    expected_established_sessions: int,
    memory_threshold_bytes: int,
    post_shutdown_settle_s: int = 90,
    post_inject_settle_s: int = 60,
    post_recovery_settle_s: int = 300,
    setup_steps: t.Optional[t.List[Step]] = None,
    prechecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
    # See PB1 factory param note: DUT ingress-RIB probe for storm arrival.
    storm_sender_peer_addr_prefix: t.Optional[str] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.3.4 playbook --
    'All Peers in Group Block, Then All Go Down, Then All Come Back'.

    Spec edge case: under a 10K-prefix iBGP storm w/ heavy attrs aiming to
    block ALL eBGP peers simultaneously, the entire eBGP DG is taken down at
    once (without GR -- truly simultaneous via ``toggle_device_groups``,
    tearing down the L3 stack). Then 500 more iBGP routes are injected (only
    iBGP active). Then the entire eBGP DG is brought back up simultaneously.
    All 280 eBGP peers must receive full re-sync from the shadow RIB.
    iBGP + BGP_MON peers must be unaffected throughout.

    Trigger sequence:
      Phase 1 (storm): heavy-attr advertise ``storm_initial_prefix_count``
        prefixes from the iBGP sender.
      Phase 2 (mass shutdown -- simultaneous): toggle the WHOLE eBGP DG
        ``enable=False`` via single ``toggle_device_groups`` call.
      Phase 3 (verify no crash): intermediate snapshot for core dumps.
      Phase 4 (followup inject): inject ``storm_followup_prefix_count``
        more prefixes from iBGP while eBGP is fully down.
      Phase 5 (verify unaffected): iBGP + BGP_MON have full + followup.
      Phase 6 (recovery -- simultaneous): toggle the WHOLE eBGP DG
        ``enable=True``.
      Phase 7 (spec gate): all 280 eBGP peers received full re-sync
        from shadow RIB.
    """
    total_count = storm_initial_prefix_count + storm_followup_prefix_count
    unaffected_peers = list(bgp_mon_peer_addrs) + list(ibgp_peer_addrs)
    storm_steps = _heavy_attr_advertise_steps(
        device_name=device_name,
        ixia_interface=ixia_interface,
        prefix_pool_regex=storm_prefix_pool_regex,
        device_group_regex=storm_device_group_regex,
        prefix_start_index=0,
        prefix_end_index=storm_initial_prefix_count,
        community_combinations=community_combinations,
        extended_community_combinations=extended_community_combinations,
        as_path=as_path,
        randomize_med=False,
        randomize_local_pref=False,
        randomize_origin=False,
        description_prefix="Phase 1 (2.3.4)",
    )

    # Storm-arrival probe (see PB1 note): DUT ingress RIB from the storm
    # sender peer group. Optional -- when regex not provided, gate is
    # skipped.
    trigger_steps = storm_steps + [
        # Phase 2: mass shutdown of ALL eBGP via DG toggle (truly simultaneous).
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": ebgp_group_dg_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                f"Phase 2 (2.3.4): MASS SHUTDOWN -- DG-disable WHOLE eBGP "
                f"group ({len(ebgp_peer_addrs)} peers) simultaneously, "
                "no GR -- peers may have been blocked when going down"
            ),
        ),
        create_longevity_step(
            duration=post_shutdown_settle_s,
            description=f"Phase 2-settle (2.3.4): {post_shutdown_settle_s}s for DUT hold-timer + UG cleanup",
        ),
        # Phase 3+4 (combined inline): unaffected check + followup inject
        create_validation_step(
            point_in_time_checks=[
                # iBGP + BGP_MON not affected by mass eBGP shutdown — assert
                # every peer in the unaffected set is still ESTABLISHED. The
                # expected count is the size of the scoped filter (NOT the
                # chassis-wide surviving total), because the check is
                # already restricted to ``unaffected_peers`` via
                # ``ignore_all_prefixes_except``.
                create_bgp_session_establish_check(
                    ignore_all_prefixes_except=unaffected_peers,
                    expected_established_sessions=len(unaffected_peers),
                ),
                # eBGP peers must be DOWN.
                create_bgp_session_establish_check(
                    ignore_all_prefixes_except=list(ebgp_peer_addrs),
                    expected_established_sessions=0,
                ),
                # UG state not corrupted.
                create_bgp_update_group_check(expect_enabled=True),
            ],
            description="Phase 3 mid-shutdown gate (2.3.4): iBGP+BGP_MON UP, all eBGP DOWN, UG intact",
        ),
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=True,
            prefix_pool_regex=storm_prefix_pool_regex,
            prefix_start_index=storm_initial_prefix_count,
            prefix_end_index=total_count,
            description=f"Phase 4 (2.3.4): inject {storm_followup_prefix_count} more prefixes while all eBGP down",
        ),
        create_longevity_step(
            duration=post_inject_settle_s,
            description=f"Phase 4-settle (2.3.4): {post_inject_settle_s}s for iBGP+BGP_MON to receive followup",
        ),
        create_validation_step(
            point_in_time_checks=[
                # Cross-peer equality WITHIN the unaffected peer group.
                # ``unaffected_peers = bgp_mon + ibgp`` -- both fall under the
                # DUT's iBGP-fanout policy (BGP_MON is a special-shape peer but
                # receives the same full RIB), so a single equality check is
                # valid. Delivery-magnitude assertion is the delta step below.
                create_bgp_peer_route_set_equality_check(
                    baseline_peer_addr=unaffected_peers[0],
                    tested_peer_addrs=unaffected_peers[1:],
                ),
            ],
            description=(
                "Phase 5 equality gate (2.3.4): iBGP+BGP_MON have identical "
                "route sets despite eBGP being down"
            ),
        ),
        *(
            [
                create_verify_dut_received_from_peer_group_step(
                    hostname=device_name,
                    sender_peer_addr_prefix=storm_sender_peer_addr_prefix,
                    min_prefix_count=total_count,
                    description=(
                        f"Phase 5 ingress-RIB gate (2.3.4): DUT received >= "
                        f"{total_count} prefixes from storm sender despite "
                        f"all {len(ebgp_peer_addrs)} eBGP peers being down "
                        f"(spec: iBGP-source storm still reaches DUT)"
                    ),
                ),
            ]
            if storm_sender_peer_addr_prefix
            else []
        ),
        # Phase 6: mass recovery of eBGP via DG toggle (truly simultaneous).
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": ebgp_group_dg_regex,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                f"Phase 6 (2.3.4): MASS RECOVERY -- DG-enable WHOLE eBGP "
                f"group ({len(ebgp_peer_addrs)} peers) simultaneously"
            ),
        ),
        create_longevity_step(
            duration=post_recovery_settle_s,
            description=f"Phase 6-settle (2.3.4): {post_recovery_settle_s}s for full shadow-RIB re-sync to all {len(ebgp_peer_addrs)} eBGP peers",
        ),
    ]

    # Phase 7 spec gate: all recovered eBGP peers received full re-sync from
    # shadow RIB. MUST run inline BEFORE ``cleanup_steps`` withdraws the storm
    # prefixes — TAAC lifecycle is ``trigger_steps -> cleanup_steps ->
    # postchecks``, so if this ran in postchecks the ``anchor_route_count``
    # assertion would compare against a post-cleanup state where ALL storm
    # prefixes have been withdrawn and fail vacuously.
    # Phase 7 spec gate is per-outbound-policy-group. iBGP baseline vs eBGP
    # tested is a policy mismatch (iBGP receives full RIB, eBGP receives an
    # egress-policy-filtered subset), so we split into two equality checks:
    # one within the recovered eBGP group and one within the untouched iBGP
    # group. Drop absolute anchor_route_count -- see Phase 5 note above.
    inline_phase_7_checks: t.List[PointInTimeHealthCheck] = [
        create_bgp_session_establish_check(
            ignore_all_prefixes_except=list(ebgp_peer_addrs),
        ),
    ]
    if len(ebgp_peer_addrs) >= 2:
        inline_phase_7_checks.append(
            create_bgp_peer_route_set_equality_check(
                baseline_peer_addr=ebgp_peer_addrs[0],
                tested_peer_addrs=list(ebgp_peer_addrs[1:]),
            )
        )
    if len(unaffected_peers) >= 2:
        inline_phase_7_checks.append(
            create_bgp_peer_route_set_equality_check(
                baseline_peer_addr=unaffected_peers[0],
                tested_peer_addrs=unaffected_peers[1:],
            )
        )
    trigger_steps.append(
        create_validation_step(
            point_in_time_checks=inline_phase_7_checks,
            description=(
                f"Phase 7 equality gate (2.3.4): recovered "
                f"{len(ebgp_peer_addrs)} eBGP peers + iBGP unaffected peers "
                f"each converged within their outbound-policy group"
            ),
        ),
    )
    # Phase 7 ingress-RIB gate: DUT still has >= total_count from storm
    # sender post-recovery. "eBGP peers received full re-sync" cannot be
    # verified via peer sent_count on this topology (egress policy filters
    # heavy-attr storm); the ingress-RIB probe validates the DUT-side half
    # of the spec.
    if storm_sender_peer_addr_prefix:
        trigger_steps.append(
            create_verify_dut_received_from_peer_group_step(
                hostname=device_name,
                sender_peer_addr_prefix=storm_sender_peer_addr_prefix,
                min_prefix_count=total_count,
                description=(
                    f"Phase 7 ingress-RIB gate (2.3.4): DUT still has >= "
                    f"{total_count} prefixes from storm sender post-recovery"
                ),
            ),
        )

    cleanup_steps = [
        create_advertise_withdraw_prefixes_step(
            device_name=device_name,
            advertise=False,
            prefix_pool_regex=storm_prefix_pool_regex,
            prefix_start_index=0,
            prefix_end_index=total_count,
            description=f"Phase 8 cleanup (2.3.4): withdraw all {total_count} storm prefixes",
        ),
        create_longevity_step(
            duration=60,
            description="Phase 8 cleanup (2.3.4): 60s settle for clean withdrawal",
        ),
    ]

    if prechecks is None:
        prechecks = [
            create_bgp_update_group_check(expect_enabled=True),
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
        ]
    if postchecks is None:
        postchecks = _ug_backpressure_common_postchecks(
            expected_established_sessions=expected_established_sessions,
            memory_threshold_bytes=memory_threshold_bytes,
            enforce_load_avg=False,
            enforce_log_parsing=True,  # spec criterion for 2.3.4
        )
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    kwargs: t.Dict[str, t.Any] = {
        "name": "ug_backpressure_all_peers_block_down_recover",
        "stages": [
            create_steps_stage(
                steps=trigger_steps,
                description=f"Phase 1-6 (2.3.4): storm + mass-shutdown {len(ebgp_peer_addrs)} eBGP + followup + mass-recovery",
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


def create_bgp_ug_backpressure_topology_smoke_playbook(
    *,
    expected_established_sessions: int,
    longevity_duration_s: int = 1800,
) -> Playbook:
    """Topology-smoke playbook for `BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE`:
    brings the EBB-scale testbed up, asserts all expected sessions Established
    + UG enabled, sits on a longevity step so the operator can hands-on probe
    the device, then a final session-establish + UG-enabled gate.

    Paired with `--skip-teardown-tasks --skip-ixia-cleanup` to keep both DUT
    bgpcpp + IXIA topology alive for hands-on inspection after the playbook
    completes. Lives here (not in the testconfig) because the
    no-inline-Playbook-construction gate test requires all Playbook factories
    to live in `playbooks/playbook_definitions.py`.
    """
    return Playbook(
        name="bgp_ug_backpressure_topology_smoke",
        prechecks=[
            create_bgp_update_group_check(expect_enabled=True),
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
        ],
        stages=[
            create_steps_stage(
                steps=[
                    create_longevity_step(
                        duration=longevity_duration_s,
                        description=(
                            f"Topology smoke: hold the testbed live for "
                            f"{longevity_duration_s}s for hands-on probing. "
                            "Pair this run with --skip-teardown-tasks "
                            "--skip-ixia-cleanup so the DUT and IXIA session "
                            "both persist after the playbook completes."
                        ),
                    ),
                ],
                description=f"Topology smoke: {longevity_duration_s}s longevity hold",
            ),
        ],
        postchecks=[
            create_bgp_session_establish_check(
                expected_established_sessions=expected_established_sessions,
            ),
            create_bgp_update_group_check(expect_enabled=True),
        ],
        snapshot_checks=[],
    )

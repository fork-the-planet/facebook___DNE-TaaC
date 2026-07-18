# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.9 — Edge Cases and Adversarial Scenarios. UG qualification playbook factories.

Implemented:
- 2.9.7 Empty Group, Last Peer Goes Down Without Detached Peers

The remaining section-2.9 scenarios (2.9.1 best-path-change, 2.9.2 simultaneous
disruptions, 2.9.3 NOTIFICATION isolation, 2.9.4 dual-stack isolation, 2.9.6
staggered startup) land as their own factory functions here when implemented.
Spec 2.9.5 is struck-through / excluded in the qualification plan.
"""

import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_session_establish_check,
    create_bgp_update_group_check,
    create_device_core_dumps_check,
    create_memory_utilization_check,
    create_service_restart_check,
    create_system_cpu_load_average_check,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_advertise_withdraw_prefixes_step,
    create_custom_step,
    create_ixia_api_step,
    create_longevity_step,
    create_validation_step,
)
from taac.testconfigs.routing.util.bgp_ebb_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
)
from taac.test_as_a_config.types import (
    Playbook,
    PointInTimeHealthCheck,
    SnapshotHealthCheck,
)


# Crash gate for every UG edge-case stage: if an empty-group transition kills
# any of these, ``create_service_restart_check`` (no ``expected_restarted_services``
# -> asserts none restarted) fails the test. Same service/daemon set as
# ``create_standard_postchecks`` so empty-group churn is held to the same
# no-restart bar as the rest of the EBB suite.
_CRASH_GATE_SERVICES: t.List[str] = ["Bgp", "FibAgent", "FibAgentBgp"]
_CRASH_GATE_DAEMONS: t.List[str] = ["FibBgpGrpc"]


def _no_crash_checks() -> t.List[PointInTimeHealthCheck]:
    """No-crash gate: BGP/FIB daemons did not restart and no new core dumps."""
    return [
        create_service_restart_check(
            services=_CRASH_GATE_SERVICES,
            daemons=_CRASH_GATE_DAEMONS,
        ),
        create_device_core_dumps_check(),
    ]


def _flap_bgp_peers(*, peer_regex: str, start: bool, description: str):
    """Start/stop ALL sessions of every IXIA BGP peer matching ``peer_regex``.

    Empties / recovers update groups by bringing the IXIA-emulated peers' BGP
    SESSIONS down/up -- NOT by toggling their DeviceGroups. This is deliberate:

    - ``toggle_device_groups(enable=False)`` removes the whole emulated router
      and de-materializes its IXIA-imported route range (the eBGP prefixes come
      from a one-shot ``ImportBgpRoutes`` at setup). Nothing ever re-imports, so
      after recovery the peers advertise NOTHING and the DUT has no eBGP routes
      to redistribute to iBGP -- the recovery never actually re-syncs routes,
      and any distribution check (spec step 10) sees an empty dump.
    - ``start_bgp_peers`` only stops/starts the BGP protocol; the emulated
      routers and their imported route ranges stay materialized, so on ``start``
      the peers re-advertise their routes -- exactly what a real peer does when
      it flaps. This makes the recovery genuinely restore the route state (spec
      pass-criterion "full route re-sync") and lets step 10 verify distribution.
      It also matches the spec wording ("shut down ALL eBGP sessions").

    Omits the session indices so ``start_bgp_peers`` flaps each matched peer's
    FULL session range (the API defaults ``session_end_idx`` to each peer's own
    ``Count``); ``create_start_stop_bgp_peers_step`` can't express "all sessions"
    across peers with differing session counts, hence the direct API step.
    """
    return create_ixia_api_step(
        api_name="start_bgp_peers",
        args_dict={"start": start, "regex": peer_regex},
        description=description,
    )


def create_bgp_ug_empty_group_playbook(
    *,
    device_name: str,
    ebgp_peer_regex: str,
    ibgp_peer_regex: str,
    ibgp_v6_peer_group: str,
    ebgp_v6_peer_group: str,
    prechecks: t.List[PointInTimeHealthCheck],
    postchecks: t.Optional[t.List[PointInTimeHealthCheck]] = None,
    snapshot_checks: t.Optional[t.List[SnapshotHealthCheck]] = None,
    bgp_mon_ignore_prefixes: t.Optional[t.List[str]] = None,
    non_ebgp_parent_prefixes: t.Optional[t.List[str]] = None,
    # Spec step 3 (iBGP keeps functioning while eBGP is empty): inject
    # ``inject_route_count`` iBGP routes (withdraw then re-advertise) from this
    # prefix pool. None -> skip the injection.
    ibgp_inject_pool_regex: t.Optional[str] = None,
    inject_route_count: int = 100,
    # Spec step 10 (full initial dump + distribution on recovery): the UG-immune
    # tcpdump dump-compare. Needed because adj-RIB-out is vacuous under UG on
    # bag011 (postpolicy_sent_prefix_count reads 0, T271301144), so per-peer
    # distribution can only be verified on the wire. All three required to run.
    ibgp_dump_capture_interface: t.Optional[str] = None,
    ibgp_dump_peer_regex: t.Optional[str] = None,
    ibgp_dump_session_indices: t.Optional[t.List[int]] = None,
    dump_capture_duration_s: int = 300,
    dump_settle_s: int = 10,
    settle_after_flap_s: int = 90,
    ebgp_empty_soak_s: int = 300,
    all_empty_soak_s: int = 120,
    recovery_convergence_s: int = 240,
    recovery_session_retry_count: int = 10,
    recovery_session_retry_delay_s: float = 30.0,
    # Spec step 8 fidelity ("bring peers back up") + pass-criterion "full route
    # re-sync": IXIA does NOT re-advertise the one-shot ``ImportBgpRoutes``-imported
    # eBGP prefixes when a session comes back up, so after recovery the DUT would
    # relearn 0 eBGP routes (recovery re-establishes sessions but never re-syncs
    # routes -- and spec step 10's distribution check then sees an empty dump).
    # When set, withdraw then re-advertise this eBGP prefix pool at recovery to
    # force IXIA to re-send the imported routes -- emulating what a real eBGP peer
    # does on flap. None -> skip (topologies where session-up re-advertises).
    ebgp_prefix_pool_regex: t.Optional[str] = None,
    recovery_readvertise_settle_s: int = 30,
    # Spec pass-criterion "groups re-created correctly" + "no stale group
    # entries": when set, assert the TOTAL update-group count on recovery equals
    # the pre-test baseline (records the baseline count per spec pre-condition 3
    # and proves no orphaned/leftover empty group survived the empty-group
    # period -- a count above baseline would mean a stale group). None -> skip.
    expected_recovered_group_count: t.Optional[int] = None,
    # Spec pass-criterion "VmHWM below 10 GB": when set, append a postcheck
    # asserting the BGP++ (bgpcpp) process VmHWM stays below this many bytes.
    # Reads /proc/<pid>/status on Arista (the standard memory check only samples
    # RSS deltas there and cannot assert an absolute peak). None -> skip.
    vmhwm_threshold_bytes: t.Optional[int] = None,
) -> Playbook:
    """Build the BGP++ Update Group qualification 2.9.7 playbook
    (Empty Group — Last Peer Goes Down Without Detached Peers).

    Intent (spec 2.9.7): shutting every peer in a group (empty group), and
    then every peer in every group, must not crash the BGP daemon; the
    update groups must re-form cleanly on recovery with no stale routes.

    Flow — the groups are emptied / recovered by STOPPING and STARTING the
    IXIA-emulated peers' BGP SESSIONS (``start_bgp_peers``), NOT by toggling
    their DeviceGroups. See ``_flap_bgp_peers`` for the full rationale: session
    stop/start leaves the imported eBGP route ranges materialized, so recovery
    genuinely re-syncs routes (DeviceGroup toggling de-materializes them and the
    recovery would advertise nothing, defeating spec step 10). It also matches
    the spec wording ("shut down ALL eBGP sessions"). ``settle_after_flap_s``
    gives the DUT time to tear the sessions down and empty the groups after each
    stop (90s default, ample for the EBB hold-times):

      1. Empty the eBGP update group: stop ALL eBGP BGP sessions
         (``ebgp_peer_regex``). Settle, then verify
         no crash; the eBGP sessions actually went down (0 eBGP Established --
         a non-vacuous guard against a mis-matched regex, when
         ``non_ebgp_parent_prefixes`` is supplied); the eBGP UPDATE GROUP
         itself emptied on the device (``expect_empty_peer_groups`` -- spec
         "group with zero members"); AND the iBGP update group is still
         enabled/formed (isolation -- emptying one group must not disturb the
         others).
      2. Soak with the eBGP group empty (spec step 4: default 5 minutes).
      3. Empty ALL groups: stop ALL iBGP BGP sessions too
         (``ibgp_peer_regex``). Every update group is now empty (the "last
         peer goes down" condition). Verify no crash; 0 sessions Established
         (excluding BGP-MON); AND both update groups empty on the device
         (``expect_empty_peer_groups`` for eBGP + iBGP).
      4. Soak with all groups empty (spec step 7: default 2 minutes).
      5. Recover: start ALL eBGP then ALL iBGP BGP sessions, then (if
         ``ebgp_prefix_pool_regex`` is set) withdraw + re-advertise the eBGP
         prefix pool so IXIA actually re-sends the imported eBGP routes -- a bare
         session-up does NOT re-advertise them, so without this the DUT relearns
         0 eBGP routes and recovery re-syncs nothing. Then wait
         ``recovery_convergence_s`` for the ~640-session topology to begin
         re-establishing, then verify no crash, the update groups re-formed
         (eBGP + iBGP), and sessions re-established. When
         ``expected_recovered_group_count`` is supplied, ALSO assert the total
         update-group count returned to the pre-test baseline (spec: groups
         re-created correctly, no stale/orphaned groups left from the empty
         period). The session-establish check retries
         (``recovery_session_retry_*``) to absorb full-scale re-convergence
         timing. "No stale routes" is asserted by the postchecks
         (``BGP_STANDARD_POSTCHECKS``), which run after the full 600s
         convergence budget rather than at this mid-test point.

    Spec step 3 (``ibgp_inject_pool_regex``): between stages 1 and 2, inject
    ``inject_route_count`` iBGP routes (withdraw then re-advertise) and re-check
    the iBGP update group -- verifies iBGP keeps functioning while the eBGP group
    is empty. Spec step 10 (``ibgp_dump_*``): a final tcpdump dump-compare that
    asserts two iBGP peers in one update group receive identical UPDATEs -- the
    only UG-immune per-peer distribution check (adj-RIB-out is vacuous under UG
    per T271301144; the sent-prefix gauge read 0 on bag011). It cold-starts ONLY
    the iBGP sink peers (``flap_peer_regex`` = the dump peer set) so the eBGP
    route sources stay up and the DUT still holds the routes to dump; it flaps
    those peers, so it runs LAST. Both are skipped if their params are omitted.

    ``bgp_mon_ignore_prefixes`` (if the testbed has BGP-MON peers configured
    on the device that IXIA does not emulate) is threaded into the session
    checks so those intentionally-down peers do not fail them.

    ``non_ebgp_parent_prefixes`` (the iBGP + BGP-MON parent networks) scopes
    the Stage-1 "eBGP actually emptied" assertion to eBGP-only. If omitted,
    that assertion is skipped (the Stage-3 all-empty assertion still proves
    the toggles took effect). See spec 2.9.7 in the qualification plan.
    """
    # Stage-1 checks: no crash + iBGP update group still formed (isolation).
    # When the caller supplies ``non_ebgp_parent_prefixes`` we ALSO assert the
    # eBGP group actually emptied (0 eBGP sessions Established, scoped to eBGP by
    # ignoring every non-eBGP parent). Without this, a mis-matched DeviceGroup
    # regex would make the whole test pass vacuously.
    ebgp_emptied_checks: t.List[PointInTimeHealthCheck] = [
        *_no_crash_checks(),
        # One UG check asserts BOTH: the iBGP update group is still formed
        # (isolation) AND the eBGP update group itself emptied -- 0 Established
        # members / cleaned up (spec 2.9.7 "group with zero members" +
        # pass-criterion "no stale group entries or orphaned state").
        create_bgp_update_group_check(
            expect_enabled=True,
            peer_group_substrings=[ibgp_v6_peer_group],
            expect_empty_peer_groups=[ebgp_v6_peer_group],
            check_id="empty_group_ebgp_ug_empty_ibgp_ug_intact",
        ),
    ]
    if non_ebgp_parent_prefixes is not None:
        ebgp_emptied_checks.append(
            create_bgp_session_establish_check(
                expected_established_sessions=0,
                parent_prefixes_to_ignore=non_ebgp_parent_prefixes,
                check_id="empty_group_ebgp_sessions_down",
            )
        )

    # Stage-3 checks: no crash + assert EVERY group is empty (the "last peer
    # goes down" condition): 0 Established sessions, ignoring only BGP-MON
    # (never emulated by IXIA under UG). This is the primary non-vacuous guard --
    # it fails if either the eBGP or the iBGP toggle did not take effect.
    all_empty_checks: t.List[PointInTimeHealthCheck] = [
        *_no_crash_checks(),
        create_bgp_session_establish_check(
            expected_established_sessions=0,
            parent_prefixes_to_ignore=bgp_mon_ignore_prefixes,
            check_id="empty_group_all_sessions_down",
        ),
        # Both update groups empty on the UG object too (spec 2.9.7 "ALL groups
        # are empty"): neither peer-group maps to an update group with an
        # Established member.
        create_bgp_update_group_check(
            expect_enabled=True,
            expect_empty_peer_groups=[ebgp_v6_peer_group, ibgp_v6_peer_group],
            check_id="empty_group_all_ugs_empty",
        ),
    ]

    # --- Spec step 3: verify the iBGP update group keeps functioning while the
    # eBGP group is empty. Inject (withdraw then re-advertise) iBGP routes, then
    # re-check the iBGP UG + no crash. Per-peer distribution is NOT asserted here
    # -- under UG on bag011 the adj-RIB-out gauge reads 0 (T271301144), so
    # distribution is verified on the wire by step 10 (which cold-starts BGP and
    # therefore cannot run during the eBGP-empty window). ---
    step3_stage = None
    if ibgp_inject_pool_regex is not None:
        step3_stage = create_steps_stage(
            steps=[
                create_advertise_withdraw_prefixes_step(
                    device_name=device_name,
                    advertise=False,
                    prefix_pool_regex=ibgp_inject_pool_regex,
                    prefix_start_index=0,
                    prefix_end_index=inject_route_count,
                    description=(
                        f"2.9.7 step 3 -- withdraw {inject_route_count} iBGP "
                        "routes while the eBGP group is empty"
                    ),
                ),
                create_longevity_step(
                    duration=settle_after_flap_s,
                    description="2.9.7 step 3 -- settle after withdraw",
                ),
                create_advertise_withdraw_prefixes_step(
                    device_name=device_name,
                    advertise=True,
                    prefix_pool_regex=ibgp_inject_pool_regex,
                    prefix_start_index=0,
                    prefix_end_index=inject_route_count,
                    description=(
                        f"2.9.7 step 3 -- inject (re-advertise) "
                        f"{inject_route_count} iBGP routes"
                    ),
                ),
                create_longevity_step(
                    duration=settle_after_flap_s,
                    description="2.9.7 step 3 -- settle after inject",
                ),
                create_validation_step(
                    point_in_time_checks=[
                        *_no_crash_checks(),
                        create_bgp_update_group_check(
                            expect_enabled=True,
                            peer_group_substrings=[ibgp_v6_peer_group],
                            check_id="empty_group_step3_ibgp_functions",
                        ),
                    ],
                    description=(
                        "2.9.7 step 3 -- iBGP update group continues to function "
                        "under eBGP-empty (route churn accepted, group formed, "
                        "no crash)"
                    ),
                ),
            ],
        )

    # --- Spec step 10: verify all peers received the full initial dump + route
    # distribution on recovery. The tcpdump dump-compare cold-starts BGP and
    # asserts two iBGP peers in the same update group receive IDENTICAL UPDATEs
    # (NLRI + attributes) -- the only UG-immune per-peer distribution check. It
    # cold-starts, so it runs LAST (after the empty-group recovery). ---
    step10_stage = None
    if (
        ibgp_dump_peer_regex is not None
        and ibgp_dump_capture_interface is not None
        and ibgp_dump_session_indices is not None
    ):
        step10_stage = create_steps_stage(
            steps=[
                create_custom_step(
                    params_dict={
                        "custom_step_name": "test_bgp_update_group_dump_compare",
                        "hostname": device_name,
                        "ixia_capture_interface": ibgp_dump_capture_interface,
                        "ibgp_peer_regex": ibgp_dump_peer_regex,
                        "ibgp_peer_session_indices": list(ibgp_dump_session_indices),
                        "capture_duration_seconds": dump_capture_duration_s,
                        "settle_seconds": dump_settle_s,
                        # Flap ONLY the iBGP sink peers, NOT the whole layer:
                        # bouncing eBGP would strip the DUT's imported eBGP RIB
                        # (never re-advertised on session-up) and yield an empty
                        # dump. Keeping eBGP up means the re-establishing iBGP
                        # peers get a real, non-empty initial dump to compare.
                        "flap_peer_regex": ibgp_dump_peer_regex,
                    },
                    description=(
                        "2.9.7 step 10 -- verify full initial dump: two iBGP peers "
                        "in the same update group receive identical UPDATEs "
                        "(distribution correct after recovery)"
                    ),
                ),
            ],
        )

    # Spec step 8 + "full route re-sync": force IXIA to re-advertise the imported
    # eBGP routes at recovery (session-up alone does not re-send them). Withdraw
    # then re-advertise creates the per-prefix Active False->True transition that
    # makes IXIA re-flood the persisted imported eBGP pool, so the DUT relearns
    # its eBGP RIB and can redistribute to iBGP (spec step 10). Empty if the
    # caller does not configure a pool (e.g. session-up re-advertises natively).
    recovery_readvertise_steps = []
    if ebgp_prefix_pool_regex is not None:
        recovery_readvertise_steps = [
            create_advertise_withdraw_prefixes_step(
                device_name=device_name,
                advertise=False,
                prefix_pool_regex=ebgp_prefix_pool_regex,
                prefix_start_index=0,
                description=(
                    "2.9.7 recovery -- withdraw eBGP prefixes (forces the Active "
                    "transition so the following re-advertise actually re-sends)"
                ),
            ),
            create_longevity_step(
                duration=recovery_readvertise_settle_s,
                description="2.9.7 recovery -- settle before re-advertising eBGP",
            ),
            create_advertise_withdraw_prefixes_step(
                device_name=device_name,
                advertise=True,
                prefix_pool_regex=ebgp_prefix_pool_regex,
                prefix_start_index=0,
                description=(
                    "2.9.7 recovery -- re-advertise ALL eBGP prefixes so the DUT "
                    "relearns its eBGP RIB (IXIA does not re-advertise imported "
                    "routes on session-up); enables full re-sync + step 10 dump"
                ),
            ),
        ]

    stages = [
        # 1. Empty the eBGP update group.
        create_steps_stage(
            steps=[
                _flap_bgp_peers(
                    peer_regex=ebgp_peer_regex,
                    start=False,
                    description=(
                        "2.9.7 -- stop ALL eBGP BGP sessions (empty the eBGP "
                        "update group; routes stay materialized for recovery)"
                    ),
                ),
                create_longevity_step(
                    duration=settle_after_flap_s,
                    description="2.9.7 -- settle after stopping eBGP sessions",
                ),
                create_validation_step(
                    point_in_time_checks=ebgp_emptied_checks,
                    description=(
                        "2.9.7 -- eBGP group emptied: no crash; eBGP sessions "
                        "down; iBGP update group still enabled/formed (isolation)"
                    ),
                ),
            ],
        ),
        # 2. Soak with the eBGP group empty.
        create_steps_stage(
            steps=[
                create_longevity_step(
                    duration=ebgp_empty_soak_s,
                    description=(
                        "2.9.7 step 4 -- soak (default 5 min) with the eBGP "
                        "update group empty, iBGP groups active"
                    ),
                ),
            ],
        ),
        # 3. Empty ALL groups (last peer down across every group).
        create_steps_stage(
            steps=[
                _flap_bgp_peers(
                    peer_regex=ibgp_peer_regex,
                    start=False,
                    description=(
                        "2.9.7 -- stop ALL iBGP BGP sessions (all update "
                        "groups now empty -- last peer goes down)"
                    ),
                ),
                create_longevity_step(
                    duration=settle_after_flap_s,
                    description="2.9.7 -- settle after stopping iBGP sessions",
                ),
                create_validation_step(
                    point_in_time_checks=all_empty_checks,
                    description=(
                        "2.9.7 -- all update groups empty (last peer down): no "
                        "crash; 0 sessions Established (excl BGP-MON)"
                    ),
                ),
            ],
        ),
        # 4. Soak fully empty.
        create_steps_stage(
            steps=[
                create_longevity_step(
                    duration=all_empty_soak_s,
                    description=(
                        "2.9.7 step 7 -- soak (default 2 min) with all update "
                        "groups empty"
                    ),
                ),
            ],
        ),
        # 5. Recover eBGP then iBGP and verify re-formation.
        create_steps_stage(
            steps=[
                _flap_bgp_peers(
                    peer_regex=ebgp_peer_regex,
                    start=True,
                    description=(
                        "2.9.7 -- start ALL eBGP BGP sessions (re-advertise the "
                        "still-materialized eBGP routes for redistribution)"
                    ),
                ),
                _flap_bgp_peers(
                    peer_regex=ibgp_peer_regex,
                    start=True,
                    description="2.9.7 -- start ALL iBGP BGP sessions",
                ),
                # Force IXIA to re-advertise the imported eBGP routes now that the
                # eBGP sessions are back up (session-up alone does not re-send
                # them) -- otherwise the DUT relearns nothing and recovery is a
                # no-op for routes. No-op when ebgp_prefix_pool_regex is unset.
                *recovery_readvertise_steps,
                create_longevity_step(
                    duration=recovery_convergence_s,
                    description=(
                        "2.9.7 -- allow sessions to re-establish and update "
                        "groups to re-form"
                    ),
                ),
                create_validation_step(
                    point_in_time_checks=[
                        *_no_crash_checks(),
                        create_bgp_update_group_check(
                            expect_enabled=True,
                            peer_group_substrings=[
                                ibgp_v6_peer_group,
                                ebgp_v6_peer_group,
                            ],
                            # Assert the total update-group count returned to the
                            # pre-test baseline (spec: groups re-created correctly,
                            # no stale/orphaned groups). No-op when the caller does
                            # not supply a baseline count.
                            expected_group_count=expected_recovered_group_count,
                            check_id="empty_group_recovery_ug_reformed",
                        ),
                        # Retries absorb full-scale (~640-session) re-convergence
                        # timing. "No stale routes" is left to the postchecks,
                        # which run after the full convergence budget rather than
                        # at this mid-test point.
                        create_bgp_session_establish_check(
                            parent_prefixes_to_ignore=bgp_mon_ignore_prefixes,
                            retry_count=recovery_session_retry_count,
                            retry_delay_seconds=recovery_session_retry_delay_s,
                            check_id="empty_group_recovery_sessions_reestablished",
                        ),
                    ],
                    description=(
                        "2.9.7 -- recovery: no crash, update groups re-formed "
                        "(eBGP + iBGP), sessions re-established"
                    ),
                ),
            ],
        ),
    ]
    # Step 3 runs during the eBGP-empty window (after Stage 1, before the 5-min
    # soak); step 10 runs last (after recovery, since it cold-starts BGP).
    if step3_stage is not None:
        stages.insert(1, step3_stage)
    if step10_stage is not None:
        stages.append(step10_stage)

    # The two UG-specific bounds the spec calls out (load-average never crosses
    # 12; update group enabled) are ALWAYS appended -- whether the caller takes
    # the default ``BGP_STANDARD_POSTCHECKS`` bundle or supplies its own list --
    # so a caller-provided ``postchecks`` can never silently drop them.
    base_postchecks = (
        list(postchecks) if postchecks is not None else list(BGP_STANDARD_POSTCHECKS)
    )
    postchecks = base_postchecks + [
        create_system_cpu_load_average_check(baseline=12.0),
        create_bgp_update_group_check(expect_enabled=True),
    ]
    # Spec pass-criterion "VmHWM below 10 GB" -- the standard postcheck memory
    # check SKIPs on Arista (RSS-delta only), so add an explicit absolute-VmHWM
    # postcheck when the caller supplies a ceiling.
    if vmhwm_threshold_bytes is not None:
        postchecks.append(
            create_memory_utilization_check(vmhwm_threshold=vmhwm_threshold_bytes)
        )
    if snapshot_checks is None:
        snapshot_checks = list(BGP_STANDARD_SNAPSHOT_CHECKS)

    return Playbook(
        # Generic, DUT-agnostic name -- device scope lives in the surrounding
        # TestConfig (e.g. ``BAG011_ASH6_BGP_UG_EDGE_CASES_TEST``).
        name="bgp_ug_empty_group",
        stages=stages,
        prechecks=prechecks,
        postchecks=postchecks,
        snapshot_checks=snapshot_checks,
    )

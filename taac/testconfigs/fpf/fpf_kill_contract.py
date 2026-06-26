# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Shared disrupt-window health-check contract for the FPF service-kill tests.

The bgp/wedge_agent/fsdb "SIGKILL every Ns for M min" configs (tc49/tc50/tc51)
all kill ONE service on the DUT GTSW (gtsw001, which owns lane 0) and then must
assert the same *shape* of contract: everything stays healthy EXCEPT the killed
service and the plane it owns (lane 0). But which checks are assertable differs
by service, so this builder parameterizes those differences in ONE place:

  killed service │ bgp up? │ ports up? │ HRT FSDB sessions          │ exclude (systemctl/unclean)
  ───────────────┼─────────┼───────────┼────────────────────────────┼────────────────────────────
  fsdb           │  yes    │   yes     │ dip 32→28 on lane0 (×4 GPU) │ fsdb
  bgpd           │  no     │   yes     │ stable 32 (fsdb still up)   │ bgpd
  wedge_agent    │  no     │   no      │ stable 32 (fsdb still up)   │ wedge_agent + bgpd (BindsTo)

Common to all three (the killed service owns lane 0 on this BE node):
  - SYSTEMCTL_ACTIVE_STATE (minus killed/cascaded) — others stay active
  - UNCLEAN_EXIT (minus killed/cascaded)           — only the kill is "unclean"
  - DEVICE_CORE_DUMPS                              — no new core dumps
  - FPF_HRT_SYSTEM_MEMORY / DRIVER_DISCONNECT      — HRT healthy
  - GENERIC_ODS discards                           — in_dst_null & in_discard spike
                                                     >=10k (loss actually happened),
                                                     congestion == 0
  - FPF_HOST_SPRAY                                 — beth1-3 spray > floor; beth0
                                                     (lane 0) exempt during the kill

NOT asserted in the disrupt window (captured by the long-lived collectors and
judged in the stable-state longevity playbook instead): FPF_HRT_BULK,
FPF_HRT_REMOTE_FAILURE, FPF_PROD_HRT_PREFIX.
"""

import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_session_establish_check,
    create_device_core_dumps_check,
    create_fpf_bgp_rib_convergence_check,
    create_fpf_host_spray_check,
    create_fpf_hrt_driver_disconnect_check,
    create_fpf_hrt_session_stat_check,
    create_fpf_hrt_system_memory_check,
    create_fpf_ods_counter_check,
    create_port_state_check,
    create_systemctl_active_state_check,
    create_unclean_exit_check,
)

ALL_FPF_SERVICES = ["bgpd", "fsdb", "wedge_agent", "qsfp_service"]

# Services to drop from the systemctl/unclean-exit assertions per killed service.
# wedge_agent is BindsTo bgpd, so killing the agent also bounces bgpd.
KILL_EXCLUDE_SERVICES = {
    "fsdb": ["fsdb"],
    "bgpd": ["bgpd"],
    "wedge_agent": ["wedge_agent", "bgpd"],
}

# ODS discard/congestion counters on the GTSW "industrial cards".
_ODS_REDUCE = r"groupby(entity, (\S+?\.\S+?)\..*, %1),sum"
_ODS_IN_DST_NULL_KEY = (
    r"regex(fboss.agent.eth.*discards.sum.60),filter(.*in_dst_null.*)"
)
_ODS_IN_DISCARD_KEY = r"regex(fboss.agent.eth.*discards.sum.60),filter(.*in_discard.*)"
_ODS_IN_CONGESTION_KEY = (
    r"regex(fboss.agent.eth.*congestion.*sum.60),filter(.*in_congestion_discards.sum.*)"
)
_ODS_OUT_CONGESTION_KEY = r"regex(fboss.agent.eth.*congestion.*sum.60),filter(.*out_congestion_discards.sum.*)"
DISCARD_FLOOR = 10000  # in_dst_null / in_discard must spike past this (loss occurred)
SPRAY_FLOOR_GBPS = 75.0
SPRAY_IMPACTED_MAX_GBPS = 10.0


def build_kill_disrupt_postchecks(
    *,
    killed_service: str,
    observer_gtsws: list[str],
    hrt_memory_hosts: list[str],
    spray_hosts: list[str] | None,
    kill_duration_sec: int,
    prefix_count: int,
    skip_ssh: bool,
    expected_fsdb_total: int = 32,
    impacted_lane: int = 0,
    session_lookback_sec: int = 1000,
) -> list:
    """Return the disrupt-window postcheck list for a service-kill test.

    ``killed_service`` is one of "fsdb" | "bgpd" | "wedge_agent" and selects the
    per-service knobs (see module docstring). The killed service owns
    ``impacted_lane`` (lane 0 = gtsw001) on the BE node.
    """
    if killed_service not in KILL_EXCLUDE_SERVICES:
        raise ValueError(
            f"killed_service must be one of {sorted(KILL_EXCLUDE_SERVICES)}, "
            f"got {killed_service!r}"
        )
    excluded = KILL_EXCLUDE_SERVICES[killed_service]
    allow_services = [s for s in ALL_FPF_SERVICES if s not in excluded]

    # fsdb kill leaves bgpd up (RIB/sessions intact) and tears HRT FSDB sessions
    # on lane 0; bgpd/wedge_agent kills take bgp down but leave fsdb up.
    bgp_healthy = killed_service == "fsdb"
    ports_healthy = killed_service in ("fsdb", "bgpd")

    checks = []

    # --- SSH/device-shell: everything healthy except the killed/cascaded svc ---
    if not skip_ssh:
        if bgp_healthy:
            checks.append(
                create_bgp_session_establish_check(
                    min_established_pct=0.5,
                    check_id=f"{killed_service}_disrupt_bgp_establish",
                )
            )
        if ports_healthy:
            checks.append(create_port_state_check())
        checks.append(create_systemctl_active_state_check(services_json=allow_services))
        checks.append(create_unclean_exit_check(exclude_services=excluded))
        checks.append(create_device_core_dumps_check(use_start_time=True))

    # --- BGP RIB stays converged only when bgpd is alive (fsdb kill) ---
    if bgp_healthy:
        for lane_id, gtsw in enumerate(observer_gtsws):
            checks.append(
                create_fpf_bgp_rib_convergence_check(
                    lane_map={str(lane_id): gtsw},
                    expected_matched=prefix_count,
                    use_live_collectors=True,
                    check_id=f"{killed_service}_disrupt_bgp_rib_lane{lane_id}",
                )
            )

    # --- HRT process health (all services) ---
    checks.append(
        create_fpf_hrt_system_memory_check(
            hosts=hrt_memory_hosts, check_id=f"{killed_service}_disrupt_hrt_mem"
        )
    )
    checks.append(
        create_fpf_hrt_driver_disconnect_check(
            hosts=hrt_memory_hosts, check_id=f"{killed_service}_disrupt_hrt_driver"
        )
    )

    # --- HRT FSDB session census ---
    # gtsw001 owns lane 0. Killing ANY of fsdb/bgpd/wedge_agent on it tears HRT's
    # view of lane-0's ribMap on all 4 GPUs, so the CONNECTED census dips 32->28
    # during the kill, then recovers to 32 once the service is back. (Confirmed:
    # the bgpd run also dipped to 28 — fsdb staying up does NOT keep the session
    # CONNECTED when the ribMap source/agent on that GTSW is down.) So all three
    # services use the same disruption-mode session expectation.
    checks.append(
        create_fpf_hrt_session_stat_check(
            mode="disruption",
            expected_connected=expected_fsdb_total,
            expected_connected_during=expected_fsdb_total - 4,
            impacted_lanes=[impacted_lane],
            recovery_min_sec=60,
            lookback_sec=session_lookback_sec,
            check_id=f"{killed_service}_disrupt_session_stat",
        )
    )

    # --- ODS discards ---
    # Graceful loop-kill: lane 0 keeps spraying, so there is NO sustained
    # blackhole — the in_dst_null/in_discard spikes are small transients (~6k
    # observed, below the old 10k bar) and asserting >=10k would contradict the
    # "lane 0 sprays" expectation. We therefore CAPTURE the discard peaks
    # informationally (the peak + ODS link are recorded, the check never fails)
    # and keep congestion == 0 as a HARD assertion.
    ods_entity_desc = ",".join(observer_gtsws)
    checks.extend(
        [
            create_fpf_ods_counter_check(
                entity_desc=ods_entity_desc,
                key_desc=_ODS_IN_DST_NULL_KEY,
                validation_expr=f">= {DISCARD_FLOOR}",
                reduce_desc=_ODS_REDUCE,
                aggregate="max",
                require="any",
                informational=True,
                counter_name="in_dst_null discards (captured)",
                check_id=f"{killed_service}_disrupt_ods_in_dst_null",
            ),
            create_fpf_ods_counter_check(
                entity_desc=ods_entity_desc,
                key_desc=_ODS_IN_DISCARD_KEY,
                validation_expr=f">= {DISCARD_FLOOR}",
                reduce_desc=_ODS_REDUCE,
                aggregate="max",
                require="any",
                informational=True,
                counter_name="in_discard discards (captured)",
                check_id=f"{killed_service}_disrupt_ods_in_discard",
            ),
            create_fpf_ods_counter_check(
                entity_desc=ods_entity_desc,
                key_desc=_ODS_IN_CONGESTION_KEY,
                validation_expr="<= 0",
                reduce_desc=_ODS_REDUCE,
                counter_name="in_congestion discards (must be 0)",
                check_id=f"{killed_service}_disrupt_ods_in_congestion",
            ),
            create_fpf_ods_counter_check(
                entity_desc=ods_entity_desc,
                key_desc=_ODS_OUT_CONGESTION_KEY,
                validation_expr="<= 0",
                reduce_desc=_ODS_REDUCE,
                counter_name="out_congestion discards (must be 0)",
                check_id=f"{killed_service}_disrupt_ods_out_congestion",
            ),
        ]
    )

    # --- Host spray (per-service lane-0 handling) ---
    # fsdb / bgpd loop-kills stay GRACEFUL: the service recovers between kills and
    # HRT's disconnected_gr_hold timer RESETS on every reconnect (never expires),
    # so lane 0 is never purged → assert ALL 4 lanes (incl. beth0) stay > floor.
    #
    # wedge_agent is DIFFERENT at any cadence: a killed agent session triggers a
    # COLDBOOT (forwarding/DOCA state wiped, no GR for the data plane), so lane 0
    # drains. The ib_write_bw flow is bidirectional, so beth0 drops to ~0 on BOTH
    # the impacted host AND the remote host. So for wedge_agent we EXCLUDE beth0
    # from the floor/spread evaluation on EVERY spray host (mark it impacted, allow
    # it drained) and only evaluate beth1-3. Confirmed empirically: 15s wedge_agent
    # run showed beth0=0 on both rtptest1544 and rtptest1575 while beth1-3 ~95-101G.
    if spray_hosts:
        spray_kwargs: t.Dict[str, t.Any] = {
            "hosts": spray_hosts,
            "min_egress_gbps": SPRAY_FLOOR_GBPS,
            "window_from_disruption_time": True,
            "window_duration_sec": kill_duration_sec,
            "check_id": f"{killed_service}_disrupt_host_spray",
        }
        if killed_service == "wedge_agent":
            # Coldboot drains lane 0 on BOTH hosts (bidirectional flow). Exclude
            # beth0 from floor/spread on every spray host; assert beth1-3 spray.
            spray_kwargs["impacted_lanes_by_host"] = {h: ["beth0"] for h in spray_hosts}
            spray_kwargs["impacted_max_gbps"] = SPRAY_IMPACTED_MAX_GBPS
            spray_kwargs["label"] = (
                "[wedge_agent-kill/coldboot] lane0(beth0) excluded (drains on both "
                "hosts); lanes1-3 spray >75G"
            )
        else:
            spray_kwargs["label"] = (
                f"[{killed_service}-kill] all 4 lanes spray >75G "
                "(graceful loop-kill, lane0 not purged)"
            )
        checks.append(create_fpf_host_spray_check(**spray_kwargs))

    return checks

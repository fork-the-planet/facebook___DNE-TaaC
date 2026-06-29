# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""IcePack/TH6 DLB & ECMP hardening test configurations.

Builds two TestConfig instances from the same parameterized factory:

* ``NPI_DVT_ICEPACK_GTSW__DLB_HARDENING`` — 18 short-runtime test cases
  (TC#210, TC#211–TC#224, TC#230–TC#232). Each playbook mutates the
  IxNetwork advertisement to a target shape and validates via
  ``DLB_RESOURCE_STICKINESS_CHECK`` postcheck.
* ``NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY`` — 5 hours-to-days runtime
  test cases (TC#225–TC#229). Each playbook layers a background
  disruption (warmboot/GR/flap) on top of a fixed advertisement
  geometry held for the runtime.

Both testconfigs share the same DUT setup tasks (peer-group push,
spine-disable, NDP-supporting DG) and the same ASIC profile
(:data:`ICEPACK_TH6_PROFILE`). Per-test scale derives from
:mod:`dlb_hardening_test_params` so swapping the ASIC = swapping the
profile constant + Pool definitions, no per-test edit needed.

Live coordinates (gtsw001.l1001.c085.ash6):
    Rogue port `eth1/1/3` parent /64 = 2401:db00:206a:c002::/64
    Gold NHs        = c002::a001..a080   (within DLB unique-NH pool)
    Silver NHs      = c002::b001..b???   (outside DLB pool → non-DLB ECMP)
    Gold prefixes   = 5000:dd::/64..
    Silver prefixes = 5000:ee::/64..
    IXIA chassis    = ixia19.netcastle.ash6 (2401:db00:2066:31fb::3019)

Empirical verification 2026-06-25 via ``dlb_resource_stickiness_runner``:
511 Gold prefixes × 64 NHs each → 381 ARS (Default DLB) + 130
PER_PACKET_RANDOM spillover + ECMP Width=64. Matches the post-test
expectations derived in :mod:`dlb_hardening_test_params`.
"""

import json
import os
import typing as t

from ixia.ixia import types as ixia_types
from taac.health_checks.healthcheck_definitions import (
    create_core_dumps_snapshot_check,
    create_dlb_resource_stickiness_check,
    create_systemctl_active_state_check,
)
from taac.packet_headers import DSF_RDMA_IB_PACKET_HEADERS
from taac.steps.step_definitions import (
    create_ixia_api_step,
    create_longevity_step,
    create_start_traffic_step,
    create_stop_traffic_step,
)
from taac.task_definitions import (
    create_coop_apply_patchers_task,
    create_coop_register_patcher_task,
    create_coop_unregister_patchers_task,
)
from taac.testconfigs.npi.dlb_asic_profiles import (
    DlbEcmpAsicProfile,
    ICEPACK_GOLD_POOL,
    ICEPACK_SILVER_POOL,
    ICEPACK_TH6_PROFILE,
    NhPool,
)
from taac.testconfigs.npi.dlb_csvs import gen_dlb_csv
from taac.testconfigs.npi.dlb_hardening_test_params import (
    derive_test_params,
    TESTS_HARDENING,
    TESTS_LONGEVITY,
)
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import Playbook, Stage, TestConfig


# =============================================================================
# Constants — peer group name, IXIA chassis, default per-test scale knobs.
# =============================================================================
PEERGROUP_GTSW_IXIA_V6: str = "PEERGROUP_GTSW_IXIA_V6"
IXIA19_CHASSIS_IP: str = "2401:db00:2066:31fb::3019"

# Per-DUT GTSW→STSW spine modules — the modules carrying UP BGP peering
# to STSW spines. Disabling these at testconfig setup leaves the silicon
# DLB unique-NH pool (128 entries on TH6) entirely free for our test
# advertisements; otherwise spine NHs occupy ~92 of those 128 slots and
# every test case past 36 NHs/prefix fails to install.
#
# IMPORTANT: this list was empirically determined 2026-06-26 on
# gtsw001.l1001.c085.ash6 (`fboss2 show port | grep " Enabled +Up "
# | awk '{print $2}' | awk -F'/' '{print $2}' | sort -un`). The prior
# hardcoded value of `{3, 4, 7, 8, 11, 12, 15, 16}` was WRONG for this
# cabling (silent no-op — spine peers stayed UP). All 31 modules below
# are the actual non-IxIA UP modules on this DUT. If we add new DUTs to
# this testconfig, each needs its own per-DUT spine-modules list.
GTSW001_ASH6_SPINE_MODULES: t.Tuple[int, ...] = (
    5,
    9,
    13,
    17,
    19,
    20,
    21,
    23,
    24,
    25,
    27,
    28,
    29,
    31,
    32,
    35,
    36,
    39,
    40,
    43,
    44,
    47,
    48,
    51,
    52,
    55,
    56,
    59,
    60,
    63,
    64,
)
# Per-module port indices that need disabling (matches the original
# patcher's per-module port set; one set per 400G module).
SPINE_PORT_INDICES: t.Tuple[int, ...] = (1, 3, 5, 7)

# Per-playbook traffic runtime for the SHORT (hardening) tests. Long enough
# for stickiness HC to converge but short enough that 18 playbooks finish
# in a single CI window. Bump on a per-playbook basis if a case needs more
# settle time (e.g. overcommit cases that wait for reject to register).
DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC: int = 120

# Longevity runtime defaults. Spec: cases 18–20 want 6h–12h; cases 16+17 are
# "background warmboot/GR while running prior cases" — we encode them as
# 1-hour wrappers around case_02 for now and let the playbook layer
# orchestrate the actual repeated inner-case sequence in a future iteration.
LONGEVITY_RUNTIMES_SEC: t.Dict[str, int] = {
    "case_16_background_warmboot": 3600,
    "case_17_background_bgp_gr": 3600,
    "case_18_dlb_ecmp_flap_longevity": 6 * 3600,
    "case_19_switch_dlb_ecmp": 12 * 3600,
    "case_20_flap_warmboot_longevity": 3600,
}


# =============================================================================
# CSV generation at module load — one CSV per (test_id, pool). Cached at a
# deterministic path so the testconfig's serialized step args are stable
# across runs (required for golden manifest hash). Regenerated each load
# (idempotent — same inputs → same output bytes).
# =============================================================================
_DLB_CSV_DIR: str = f"/tmp/dlb_csvs/{ICEPACK_TH6_PROFILE.name}"
os.makedirs(_DLB_CSV_DIR, exist_ok=True)


def _csv_path(test_id: str, pool: NhPool) -> str:
    return os.path.join(_DLB_CSV_DIR, pool.name, f"{test_id}.csv")


def _ensure_csvs(profile: DlbEcmpAsicProfile) -> t.Dict[str, t.Dict[NhPool, str]]:
    """Generate the per-(test_id, pool) CSV files once at module load.

    Heavy Silver cases (case_05/08/15/18/19/20) emit hundreds-of-MB CSVs
    when generated full-scale; they take minutes total. Run once here
    instead of per-playbook execution. Returns a nested dict keyed by
    test_id then pool, ready for step args_dict construction.
    """
    params = derive_test_params(profile, ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL)
    paths: t.Dict[str, t.Dict[NhPool, str]] = {}
    for tid, pool_params in params.items():
        paths[tid] = {}
        for pool, (groups, width) in pool_params.items():
            csv_path = _csv_path(tid, pool)
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            rows = gen_dlb_csv.gen_fill_for_pool(pool, groups, width)
            gen_dlb_csv.write_csv(csv_path, rows)
            paths[tid][pool] = csv_path
    return paths


# Generate up front. Mapping is consumed by each playbook factory.
_TEST_CSV_PATHS: t.Dict[str, t.Dict[NhPool, str]] = _ensure_csvs(ICEPACK_TH6_PROFILE)


# =============================================================================
# Per-case derivation of stickiness-HC expected_counts. Pure function of
# (profile, derived params) — ASIC swap recomputes automatically.
# =============================================================================
def _stickiness_expectations(
    profile: DlbEcmpAsicProfile,
    test_id: str,
    pool_params: t.Dict[NhPool, t.Tuple[int, int]],
) -> t.Dict[str, t.Any]:
    """Compute the stickiness-HC ``json_params`` for one playbook.

    Maps the per-pool (groups, width) shape to category-keyed
    expectations: ``"5000:dd prefixes"`` for Gold-advertised routes,
    ``"5000:ee prefixes"`` for Silver. Spillover rows expect
    ``dlb=usable_cap``, ``per_packet_random=overflow``. Width-cap rows
    expect ``ecmp_width=cap``. Background-only rows (cases 16/17)
    inherit case_02's expectations as their baseline.

    Returns a dict suitable for ``create_dlb_resource_stickiness_check
    (json_params=...)``.
    """
    if not pool_params:
        # Background-task wrappers: inherit case_02's baseline.
        baseline = derive_test_params(profile, ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL)[
            "case_02_dlb_fill_50pct"
        ]
        return _stickiness_expectations(profile, "case_02_dlb_fill_50pct", baseline)

    prefix_patterns: t.List[str] = []
    expected_counts: t.Dict[str, t.Dict[str, t.Any]] = {}
    totals_dlb = 0
    totals_ppr = 0

    for pool, (groups, width) in pool_params.items():
        pattern = pool.prefix_base.rstrip(":")
        prefix_patterns.append(pool.prefix_base)
        cat_key = f"{pattern} prefixes"

        if pool is ICEPACK_GOLD_POOL:
            # Gold advertises into the DLB-eligible NH pool. Up to
            # `dlb_max_groups_usable` will land as ARS; rest spill to
            # PER_PACKET_RANDOM (FBOSS Agent flips the override mode
            # when ARS budget is exhausted).
            dlb_count = min(groups, profile.dlb_max_groups_usable)
            ppr_count = max(0, groups - profile.dlb_max_groups_usable)
            expected_counts[cat_key] = {
                "total": groups,
                "ecmp_width": min(width, profile.dlb_max_width),
                "dlb": dlb_count,
                "per_packet_random": ppr_count,
            }
            totals_dlb += dlb_count
            totals_ppr += ppr_count
        else:
            # Silver advertises into the non-DLB NH range. Everything
            # classifies as PER_PACKET_RANDOM (or whatever the non-DLB
            # default mode resolves to); zero DLB.
            expected_counts[cat_key] = {
                "total": groups,
                "ecmp_width": min(width, profile.ecmp_max_width),
                "dlb": 0,
                "per_packet_random": groups,
            }
            totals_ppr += groups

    return {
        "prefix_patterns": prefix_patterns,
        "expected_counts": expected_counts,
        "expected_totals": {
            "dlb": totals_dlb,
            "per_packet_random": totals_ppr,
            "other_modes": 0,
        },
    }


# =============================================================================
# Step factories for the DLB-specific TaacIxia helpers we added.
# `mutate_dlb_pool_from_csv` + `toggle_dlb_pool_enabled` live in
# `ixia/taac_ixia.py`. We invoke them via the existing
# `INVOKE_IXIA_API_STEP` plumbing.
# =============================================================================
def _mutate_pool_step(csv_path: str, pool_name: str) -> taac_types.Step:
    """Step that calls ``TaacIxia.mutate_dlb_pool_from_csv``."""
    return create_ixia_api_step(
        api_name="mutate_dlb_pool_from_csv",
        args_dict={"csv_path": csv_path, "pool_name": pool_name},
        description=f"Mutate {pool_name} from {os.path.basename(csv_path)}",
    )


def _toggle_pool_step(pool_name: str, enabled: bool) -> taac_types.Step:
    """Step that calls ``TaacIxia.toggle_dlb_pool_enabled``."""
    return create_ixia_api_step(
        api_name="toggle_dlb_pool_enabled",
        args_dict={"pool_name": pool_name, "enabled": enabled},
        description=f"{'Enable' if enabled else 'Disable'} {pool_name}",
    )


def _pool_name_for(pool: NhPool) -> str:
    """Map an NhPool to its IxNetwork NetworkGroup name in this testbed."""
    if pool is ICEPACK_GOLD_POOL:
        return "DLB_GOLD_PREFIX_POOL"
    if pool is ICEPACK_SILVER_POOL:
        return "DLB_SILVER_PREFIX_POOL"
    raise ValueError(f"Unknown NhPool: {pool.name}")


# =============================================================================
# Playbook builders. One Playbook per test_id. Order of steps:
#   1. For each pool in pool_params: mutate_dlb_pool_from_csv(csv_path, pool_name)
#   2. For each pool NOT in pool_params but defined in testbed: toggle off
#   3. start_traffic
#   4. longevity (case-specific duration)
#   5. stop_traffic
# Postcheck: stickiness HC with derived expectations.
# Test-config-level prechecks (systemctl active, no core dumps) attach in
# the factory wrapper `_add_tc_checks_to_playbooks`.
# =============================================================================
def _build_playbook(
    profile: DlbEcmpAsicProfile,
    test_id: str,
    pool_params: t.Dict[NhPool, t.Tuple[int, int]],
    csv_paths: t.Dict[NhPool, str],
    runtime_sec: int,
) -> Playbook:
    """Construct one Playbook for the given test_id + pool_params."""
    setup_steps: t.List[taac_types.Step] = []

    # 1. Mutate each active pool.
    for pool, csv_path in csv_paths.items():
        setup_steps.append(_mutate_pool_step(csv_path, _pool_name_for(pool)))

    # 2. Explicitly disable Silver if not used in this case (default
    # state could be enabled from a prior playbook). Skip for cases
    # that don't even have Gold to keep the inherited state.
    all_pools = {ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL}
    inactive_pools = all_pools - set(pool_params.keys()) if pool_params else set()
    for pool in inactive_pools:
        # Only toggle Silver — Gold should always stay up for the
        # session-level BGP peer to remain ESTABLISHED.
        if pool is ICEPACK_SILVER_POOL:
            setup_steps.append(_toggle_pool_step(_pool_name_for(pool), False))

    # 3 + 4 + 5: traffic on / longevity / off.
    traffic_steps: t.List[taac_types.Step] = [
        create_start_traffic_step(),
        create_longevity_step(
            duration=runtime_sec, description=f"{test_id} run window"
        ),
        create_stop_traffic_step(),
    ]

    stages: t.List[Stage] = []
    if setup_steps:
        stages.append(Stage(steps=setup_steps))
    stages.append(Stage(steps=traffic_steps))

    # Postcheck: stickiness HC with per-case expected_counts.
    postchecks = [
        create_dlb_resource_stickiness_check(
            json_params=_stickiness_expectations(profile, test_id, pool_params),
        ),
    ]

    return Playbook(
        name=test_id.upper(),
        stages=stages,
        postchecks=postchecks,
    )


def _build_playbooks_for_ids(
    profile: DlbEcmpAsicProfile,
    test_ids: t.List[str],
    runtime_sec_overrides: t.Optional[t.Dict[str, int]] = None,
    default_runtime_sec: int = DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
) -> t.List[Playbook]:
    """Walk a list of test_ids → list of Playbooks."""
    params = derive_test_params(profile, ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL)
    overrides = runtime_sec_overrides or {}
    playbooks: t.List[Playbook] = []
    for tid in test_ids:
        pool_params = params[tid]
        csv_paths = _TEST_CSV_PATHS[tid]
        runtime = overrides.get(tid, default_runtime_sec)
        playbooks.append(_build_playbook(profile, tid, pool_params, csv_paths, runtime))
    return playbooks


# =============================================================================
# Peer-group helper (shared between Gold + Silver peers — same on-device
# policy chain, just different BGP peer addresses).
# =============================================================================
def _get_gtsw_ixia_peer_group_tasks(device_name: str) -> t.List[t.Any]:
    return [
        create_coop_register_patcher_task(
            hostname=device_name,
            config_name="bgpcpp",
            patcher_name="add_peer_group_patcher_PEERGROUP_GTSW_IXIA_V6",
            task_name="add_peer_group_patcher",
            patcher_args={
                "name": PEERGROUP_GTSW_IXIA_V6,
                "description": "eBGP peering from GTSW to IXIA, IPv6",
                "disable_ipv4_afi": "True",
                "disable_ipv6_afi": "False",
                "ingress_policy_name": "PROPAGATE_GTSW_STSW_IN",
                "egress_policy_name": "PROPAGATE_GTSW_STSW_OUT",
                "bgp_peer_timers_hold_time_seconds": "30",
                "bgp_peer_timers_keep_alive_seconds": "10",
                "bgp_peer_timers_out_delay_seconds": "0",
                "bgp_peer_timers_withdraw_unprog_delay_seconds": "0",
                "peer_tag": "IXIA",
                "max_routes": "900000",
                "warning_only": "True",
                "warning_limit": "0",
                "next_hop_self": "False",
                "add_path": "BOTH",
                "is_confed_peer": "False",
                "is_passive": "False",
                "v4_over_v6_nexthop": "False",
                "link_bandwidth_bps": "auto",
            },
            py_func_name="add_peer_group_patcher",
        ),
    ]


# =============================================================================
# Factory: build a TestConfig with the named playbooks.
# =============================================================================
def build_dlb_hardening_testconfig(
    test_config_name: str,
    profile: DlbEcmpAsicProfile,
    device_name: str,
    local_mac_address: str,
    ixia_downlink_interface: str,
    ixia_rogue_interface: str,
    ixia_remote_interface: str,
    ixia_downlink_parent_v6: str,
    ixia_rogue_parent_v6: str,
    ixia_remote_parent_v6: str,
    gold_pool: NhPool,
    silver_pool: NhPool,
    remote_uplink_as_4byte: int,
    is_uplink_peer_confed: str,
    prefix_limit: str,
    test_ids: t.List[str],
    spine_modules: t.Sequence[int],
    runtime_sec_overrides: t.Optional[t.Dict[str, int]] = None,
    default_runtime_sec: int = DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
    direct_ixia_connections: t.Optional[t.List[t.Any]] = None,
    basset_pool: t.Optional[str] = None,
) -> TestConfig:
    """Build the IcePack/TH6 DLB hardening or longevity TestConfig.

    Shared factory for both ``NPI_DVT_ICEPACK_GTSW__DLB_HARDENING``
    (18 short tests) and ``NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY`` (5
    long tests). Differs only in ``test_ids`` (which playbooks to wire)
    and ``runtime_sec_overrides`` (per-playbook longevity durations).
    """
    # ---- L1 config (PFC priority groups for RDMA-IB DLB-eligible traffic) ----
    # NOTE: an IMIX FrameSize was originally defined here for DLB traffic
    # profile but the basic_traffic_item_configs below uses a FIXED-1024
    # frame size directly (matches the icepack_ecmp_resource_testing_config
    # reference). When we want IMIX, re-add the FrameSize struct here
    # and wire it into the traffic-item's frame_size_settings.
    dsf_l1_config = ixia_types.L1Config(
        enable_fcoe=True,
        flow_control_config=ixia_types.FlowControlConfig(
            pfc_prority_groups_config=ixia_types.PfcPriorityGroupsConfig(
                priority0_pfc_queue=ixia_types.PfcQueue.TWO,
                priority1_pfc_queue=ixia_types.PfcQueue.ONE,
                priority2_pfc_queue=ixia_types.PfcQueue.ZERO,
                priority3_pfc_queue=ixia_types.PfcQueue.THREE,
            ),
            enable_pfc_pause_delay=False,
        ),
    )

    # ---- TC-level pre/postchecks ----
    tc_prechecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
            ],
        ),
    ]
    tc_postchecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
            ],
        ),
    ]
    tc_snapshot_checks = [create_core_dumps_snapshot_check()]

    def _add_tc_checks(pb: Playbook) -> Playbook:
        new_prechecks = tc_prechecks + list(pb.prechecks or [])
        new_postchecks = list(pb.postchecks or []) + tc_postchecks
        if pb.skip_test_config_snapshot_checks:
            new_snapshot_checks = list(pb.snapshot_checks or [])
        else:
            new_snapshot_checks = list(pb.snapshot_checks or []) + tc_snapshot_checks
        return pb(
            prechecks=new_prechecks,
            postchecks=new_postchecks,
            snapshot_checks=new_snapshot_checks,
            skip_test_config_snapshot_checks=False,
        )

    # ---- BGP peer configs (Gold + Silver — two distinct peers on the
    # same rogue port, different local addrs so silicon classifies one
    # via DLB pool and the other via non-DLB ECMP) ----
    peer_configs_json = json.dumps(
        [
            {
                "local_addr": f"{ixia_rogue_parent_v6}::a",
                "peer_addr": f"{ixia_rogue_parent_v6}::b",
                "peer_group_name": PEERGROUP_GTSW_IXIA_V6,
                "remote_as_4_byte": str(remote_uplink_as_4byte),
                "description": "ixia_session_gold",
            },
            {
                "local_addr": f"{ixia_rogue_parent_v6}::c",
                "peer_addr": f"{ixia_rogue_parent_v6}::d",
                "peer_group_name": PEERGROUP_GTSW_IXIA_V6,
                "remote_as_4_byte": str(remote_uplink_as_4byte),
                "description": "ixia_session_silver",
            },
        ]
    )

    # ---- Endpoint ----
    endpoints = [
        taac_types.Endpoint(
            name=device_name,
            ixia_ports=[
                ixia_downlink_interface,
                ixia_rogue_interface,
                ixia_remote_interface,
            ],
            dut=True,
            mac_address=local_mac_address,
            direct_ixia_connections=direct_ixia_connections or [],
        ),
    ]

    # ---- Device groups on rogue port: Gold DG + Silver DG + NDP DG ----
    rogue_dgs = [
        # DG 0: Gold (DLB-eligible) BGP peer
        taac_types.DeviceGroupConfig(
            device_group_index=0,
            tag_name="DLB_resource(Gold)",
            enable=True,
            multiplier=1,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{ixia_rogue_parent_v6}::b",
                increment_ip="::",
                gateway_starting_ip=f"{ixia_rogue_parent_v6}::a",
                gateway_increment_ip="::",
                mask=64,
            ),
            v6_bgp_config=taac_types.BgpConfig(
                local_as_4_bytes=remote_uplink_as_4byte,
                local_as_increment=0,
                enable_4_byte_local_as=True,
                bgp_peer_type=ixia_types.BgpPeerType.EBGP,
                is_confed=is_uplink_peer_confed == "True",
                bgp_capabilities=[
                    ixia_types.BgpCapability.IpV6Unicast,
                    ixia_types.BgpCapability.Ipv6UnicastAddPath,
                ],
                custom_network_group_configs=[
                    ixia_types.CustomNetworkGroupConfig(
                        device_group_name="DLB_resource(Gold)",
                        network_group_name="DLB_GOLD_PREFIX_POOL",
                        # Starting shape — overwritten per-test by
                        # mutate_dlb_pool_from_csv. Pick a baseline
                        # that boots cleanly (1 prefix, 1 NH).
                        network_group_multiplier=1,
                        prefix_start_value="5000:dd::",
                        prefix_length=64,
                        nexthop_start_value=f"{gold_pool.nh_network}::a001",
                        nexthop_increments="::1",
                        ecmp_width=1,
                        community_list=[
                            "65446:30",
                            "65441:323",
                            "65456:323",
                        ],
                        network_group_index=0,
                    ),
                ],
            ),
        ),
        # DG 1: Silver (non-DLB ECMP) BGP peer
        taac_types.DeviceGroupConfig(
            device_group_index=1,
            tag_name="ECMP_resource(Silver)",
            enable=True,
            multiplier=1,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{ixia_rogue_parent_v6}::d",
                increment_ip="::",
                gateway_starting_ip=f"{ixia_rogue_parent_v6}::c",
                gateway_increment_ip="::",
                mask=64,
            ),
            v6_bgp_config=taac_types.BgpConfig(
                local_as_4_bytes=remote_uplink_as_4byte,
                local_as_increment=0,
                enable_4_byte_local_as=True,
                bgp_peer_type=ixia_types.BgpPeerType.EBGP,
                is_confed=is_uplink_peer_confed == "True",
                bgp_capabilities=[
                    ixia_types.BgpCapability.IpV6Unicast,
                    ixia_types.BgpCapability.Ipv6UnicastAddPath,
                ],
                custom_network_group_configs=[
                    ixia_types.CustomNetworkGroupConfig(
                        device_group_name="ECMP_resource(Silver)",
                        network_group_name="DLB_SILVER_PREFIX_POOL",
                        network_group_multiplier=1,
                        prefix_start_value="5000:ee::",
                        prefix_length=64,
                        nexthop_start_value=f"{silver_pool.nh_network}::b001",
                        nexthop_increments="::1",
                        ecmp_width=1,
                        community_list=[
                            "65446:30",
                            "65441:323",
                            "65456:323",
                        ],
                        network_group_index=0,
                    ),
                ],
            ),
        ),
        # DG 2: NDP-supporting nexthops (no BGP). Covers BOTH Gold NHs
        # (::a001..a080 = 128) and Silver NHs (::b001..b???) so silicon
        # NDP-resolves all advertised next-hops. Sized to cover Gold
        # 128 + Silver up to 3072 = 3200, but we cap at a reasonable
        # number for the smoke setup; the real silver tests will need
        # to grow this DG's multiplier — TODO.
        taac_types.DeviceGroupConfig(
            device_group_index=2,
            tag_name="NDP_SUPPORTING_NEXTHOP",
            multiplier=130,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{gold_pool.nh_network}::a001",
                increment_ip="::1",
                gateway_starting_ip=f"{gold_pool.nh_network}::a",
                mask=64,
            ),
        ),
    ]

    # ---- Playbooks ----
    playbooks = [
        _add_tc_checks(p)
        for p in _build_playbooks_for_ids(
            profile,
            test_ids,
            runtime_sec_overrides=runtime_sec_overrides,
            default_runtime_sec=default_runtime_sec,
        )
    ]

    return TestConfig(
        name=test_config_name,
        ixia_protocol_verification_timeout=10,
        skip_ixia_protocol_verification=True,
        ixia_config_cache=taac_types.IxiaConfigCache(enabled=False),
        basset_pool=basset_pool,
        endpoints=endpoints,
        setup_tasks=[
            create_coop_unregister_patchers_task(device_name),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="agent",
                patcher_name="disable_gtsw_spine_interfaces",
                task_name="change_port_admin_state",
                patcher_args={
                    f"eth1/{module}/{port}": "disable"
                    for module in spine_modules
                    for port in SPINE_PORT_INDICES
                },
                py_func_name="change_port_admin_state",
            ),
        ]
        + _get_gtsw_ixia_peer_group_tasks(device_name)
        + [
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name="add_bgp_peers_dut",
                task_name="add_bgp_peers",
                patcher_args={"peer_configs": peer_configs_json},
                py_func_name="add_bgp_peers",
            ),
            create_coop_apply_patchers_task(
                hostnames=[device_name],
                do_warmboot=True,
            ),
        ],
        teardown_tasks=[
            create_coop_unregister_patchers_task(device_name),
        ],
        basic_traffic_item_configs=[
            taac_types.BasicTrafficItemConfig(
                name=f"{ixia_downlink_interface.upper().replace('/', '_')}_TO_DLB_GOLDEN_TRAFFIC",
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_rogue_interface}",
                        device_group_index=0,
                        network_group_index=0,
                    ),
                ],
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.FIXED,
                    fixed_size=1024,
                ),
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                traffic_type=ixia_types.TrafficType.IPV6,
                tracking_types=[ixia_types.TrafficStatsTrackingType.TRAFFIC_ITEM],
                packet_headers=DSF_RDMA_IB_PACKET_HEADERS,
            ),
        ],
        basic_port_configs=[
            taac_types.BasicPortConfig(
                l1_config=dsf_l1_config,
                endpoint=f"{device_name}:{ixia_downlink_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="DOWNLINK_L3_TRAFFIC",
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_downlink_parent_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_downlink_parent_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                    ),
                ],
            ),
            taac_types.BasicPortConfig(
                l1_config=dsf_l1_config,
                endpoint=f"{device_name}:{ixia_rogue_interface}",
                device_group_configs=rogue_dgs,
            ),
            taac_types.BasicPortConfig(
                l1_config=dsf_l1_config,
                endpoint=f"{device_name}:{ixia_remote_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="REMOTE_L3_TRAFFIC",
                        enable=True,
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_remote_parent_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_remote_parent_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                    ),
                ],
            ),
        ],
        playbooks=playbooks,
    )


# =============================================================================
# Instances — gtsw001.l1001.c085.ash6 (IcePack TH6 / ICECUBE800BC).
# =============================================================================
_COMMON_DUT_KWARGS = {
    "profile": ICEPACK_TH6_PROFILE,
    "device_name": "gtsw001.l1001.c085.ash6",
    "local_mac_address": "02:00:00:00:0f:0c",
    "ixia_downlink_interface": "eth1/1/1",
    "ixia_rogue_interface": "eth1/1/3",
    "ixia_remote_interface": "eth1/1/5",
    "ixia_downlink_parent_v6": "2401:db00:206a:c000",
    "ixia_rogue_parent_v6": "2401:db00:206a:c002",
    "ixia_remote_parent_v6": "2401:db00:206a:c004",
    "gold_pool": ICEPACK_GOLD_POOL,
    "silver_pool": ICEPACK_SILVER_POOL,
    "spine_modules": GTSW001_ASH6_SPINE_MODULES,
    "remote_uplink_as_4byte": 4200601902,
    "is_uplink_peer_confed": "False",
    "prefix_limit": "75000",
    "basset_pool": "taac_netcastle_ash6",
    "direct_ixia_connections": [
        taac_types.DirectIxiaConnection(
            interface="eth1/1/1",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/25",
        ),
        taac_types.DirectIxiaConnection(
            interface="eth1/1/3",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/27",
        ),
        taac_types.DirectIxiaConnection(
            interface="eth1/1/5",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/29",
        ),
    ],
}


NPI_DVT_ICEPACK_GTSW__DLB_HARDENING: TestConfig = build_dlb_hardening_testconfig(
    test_config_name="NPI_DVT_ICEPACK_GTSW__DLB_HARDENING",
    test_ids=TESTS_HARDENING,
    default_runtime_sec=DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
    **_COMMON_DUT_KWARGS,
)


NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY: TestConfig = build_dlb_hardening_testconfig(
    test_config_name="NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY",
    test_ids=TESTS_LONGEVITY,
    runtime_sec_overrides=LONGEVITY_RUNTIMES_SEC,
    # 1hr default for any longevity case missing an explicit override.
    default_runtime_sec=3600,
    **_COMMON_DUT_KWARGS,
)

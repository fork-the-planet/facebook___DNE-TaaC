# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP Update Group (UG) qualification testconfig factories.

Naming: ``create_bgp_ug_<usecase>_test_config(testbed: Testbed, ...) -> TestConfig``.

See ../README.md §3.

Wave 1 status: real factory bodies moved from
``testconfigs/routing/ebb/bag012_ash6_test_config.py`` and
``testconfigs/routing/ebb/bag013_ash6_backpressure_test_config.py``.
``testbed`` is asserted against the expected DUT for now; Wave 2
refactors the factory to derive every DUT value from ``testbed.*``
so bag010/011/013 can host the UG new-peer-join qualification via a
one-line catalog change.
"""

import json
import os
import typing as t

from ixia.ixia import types as ixia_types
from taac.constants import (
    BgpPlusPlusProfile,
    DEFAULT_LOCAL_LINK,
    DEFAULT_OPENR_START_IPV4S,
    DEFAULT_OPENR_START_IPV6S,
    DEFAULT_OTHER_LINK,
    Gigabyte,
    OpenRRouteAction,
)
from taac.health_checks.healthcheck_definitions import (
    create_bgp_graceful_restart_check,
    create_bgp_session_establish_check,
    create_bgp_update_group_check,
    create_cpu_utilization_check,
    create_drain_state_check,
    create_memory_utilization_check,
)
from taac.playbooks.playbook_definitions import (
    build_arista_ebb_scale_playbook,
)
from taac.playbooks.routing.bgp_ug_playbooks import (
    create_bgp_ug_backpressure_topology_smoke_playbook,
    create_bgp_ug_initial_dump_identical_routes_playbook,
    create_bgp_ug_new_peer_join_attribute_change_playbook,
    create_bgp_ug_new_peer_join_full_sync_resilience_playbook,
    create_bgp_ug_new_peer_join_routes_withdrawn_playbook,
    create_bgp_ug_sustained_link_flap_playbook,
    create_ug_backpressure_all_peers_block_down_recover_playbook,
    create_ug_backpressure_fast_peers_not_held_back_playbook,
    create_ug_backpressure_peer_blocks_down_recover_playbook,
    create_ug_backpressure_withdraw_attr_change_playbook,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.common_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_PRECHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_common_tasks import (
    get_common_setup_tasks,
    get_teardown_tasks,
    get_update_packing_setup_tasks,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_constants import (
    BGP_MON_PEER_COUNT,
    BGP_MON_REMOTE_AS,
    DEFAULT_PROFILE,
    EBGP_PEER_COUNT_V4,
    EBGP_PEER_COUNT_V6,
    EBGP_PEER_TO_DRAIN,
    EBGP_REMOTE_AS,
    IBGP_PEER_SCALE_PER_PLANE,
    IBGP_PEER_TO_DRAIN_PER_PLANE,
    IBGP_REMOTE_AS,
    IXIA_BGP_MON_IC_PARENT_NETWORK,
    IXIA_EBGP_IC_PARENT_NETWORK_V4,
    IXIA_EBGP_IC_PARENT_NETWORK_V6,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE2,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE3,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE4,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE2,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE3,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE4,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4,
    PEERGROUP_BGP_MON,
    PEERGROUP_EBGP_V6,
    PEERGROUP_IBGP_V4,
    PEERGROUP_IBGP_V6,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ixia_config_for_ebb_scale import (
    create_ebb_scale_basic_port_configs,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_configure_bgp_peer_tcp_window_size_step,
    create_custom_step,
    create_ixia_api_step,
    create_longevity_step,
    create_snapshot_per_peer_bgp_rx_stats_step,
    create_start_stop_bgp_peers_step,
    create_validation_step,
    create_verify_per_peer_bgp_rx_asymmetry_step,
)
from taac.task_definitions import create_openr_route_action_task
from taac.testconfigs.routing.testbed import Testbed
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection, Endpoint, TestConfig


# =============================================================================
# BGP UG new-peer-join (spec 2.4.1 + 2.4.2 + 2.4.3) — bag012 topology
# =============================================================================
#
# 21-eBGP + 4-iBGP topology on bag012.ash6 (moved from
# testconfigs/routing/ebb/bag012_ash6_test_config.py).
#
# Side A receivers on eBGP port (EB-FA-V6 UG under test):
#   CTRL × 4    — always UP
#   HELD × 1    — admin-DOWN at baseline; brought UP mid-test = the SUT
#   DISP × 16   — always UP; killed mid-sync in 2.4.1
#
# Side B senders on iBGP port (EB-EB-V6):
#   KEEP_INITIAL   — 300 routes with initial community; UP at baseline
#   KEEP_MUTATED   — 300 routes with mutated community; DG-disabled baseline
#                    (2.4.3 trigger flips the pair to swap community on wire)
#   VAR1           — 200 routes; DG-enabled at baseline but sessions DOWN
#   VAR2           — 50 routes; DG-enabled at baseline but sessions DOWN

_UG_PEER_GROUP_SUBSTRING = "EB-FA-V6"

# Community values required to pass DUT's policy chain.
_UG_IBGP_SENDER_COMMUNITIES = [
    "65060:10012",
    "65140:65529",
    "65520:503",
    "65529:11610",
    "65529:39744",
    "65530:50300",
    "65530:50320",
    "65530:50800",
]
_UG_INITIAL_COMMUNITY = "65529:39744"  # 2.4.3 starting "marker" community
_UG_MUTATED_COMMUNITY = "65531:50200"
_UG_BASE_SENDER_COMMUNITIES = _UG_IBGP_SENDER_COMMUNITIES

# Per-DG counts (multiplier).
_UG_CTRL_MULTIPLIER = 4
_UG_DISP_MULTIPLIER = 16
_UG_DISP_KILL_COUNT = 16  # kill all 16 in 2.4.1
_UG_TOTAL_EBGP_PEERS = _UG_CTRL_MULTIPLIER + 1 + _UG_DISP_MULTIPLIER  # 21
_UG_TOTAL_IBGP_PEERS = 1 + 1 + 1 + 1  # KEEP_INITIAL + KEEP_MUTATED + VAR1 + VAR2

# Pool sizes.
_UG_KEEP_ROUTE_COUNT = 300
_UG_VAR1_ROUTE_COUNT = 200
_UG_VAR2_ROUTE_COUNT = 50

# Tag names = IXIA peer-object regex handles used by step_definitions.
_UG_DG_A_CTRL_TAG = "BGP_PEER_IPV6_EBGP_UG_CTRL"
_UG_DG_A_HELD_TAG = "BGP_PEER_IPV6_EBGP_UG_HELD"
_UG_DG_A_DISP_TAG = "BGP_PEER_IPV6_EBGP_UG_DISP"
_UG_DG_B_KEEP_TAG = "BGP_PEER_IPV6_IBGP_UG_B_KEEP"  # = INITIAL (legacy name)
_UG_DG_B_KEEP_MUTATED_TAG = "BGP_PEER_IPV6_IBGP_UG_B_KEEP_MUTATED"
_UG_DG_B_VAR1_TAG = "BGP_PEER_IPV6_IBGP_UG_B_VAR1"
_UG_DG_B_VAR2_TAG = "BGP_PEER_IPV6_IBGP_UG_B_VAR2"


# IXIA-side peer addresses derived from `_generate_ixia_v6_peer_entries_for_bgpcpp`
# (start_offset=0x10, stride=2). For each AF: DUT-local at offset i*2+0x10
# (::10, ::12, ...); IXIA-side peer at i*2+0x11 (::11, ::13, ...).
def _ug_ibgp_peer_addr(idx: int) -> str:
    """IXIA-side peer address for the idx-th iBGP peer (0-based)."""
    return f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1}::{0x11 + 2 * idx:x}"


def _ug_ibgp_gateway_addr(idx: int) -> str:
    """DUT-side iBGP local address (= IXIA-side gateway) for the idx-th peer."""
    return f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1}::{0x10 + 2 * idx:x}"


def _ug_ebgp_peer_addr(idx: int) -> str:
    """IXIA-side peer address for the idx-th eBGP peer (sender)."""
    return f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::{0x11 + 2 * idx:x}"


def _ug_ebgp_gateway_addr(idx: int) -> str:
    """DUT-side eBGP local address (= IXIA-side gateway) for the idx-th peer."""
    return f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::{0x10 + 2 * idx:x}"


# Allocate peer index ranges to roles within their respective AF/protocol.
_UG_EBGP_CTRL_START_IDX = 0  # 0..3
_UG_EBGP_HELD_IDX = 4
_UG_EBGP_DISP_START_IDX = 5  # 5..20
_UG_IBGP_B_KEEP_IDX = 0
_UG_IBGP_B_KEEP_MUTATED_IDX = 1
_UG_IBGP_B_VAR1_IDX = 2
_UG_IBGP_B_VAR2_IDX = 3

# Mutated 8-community list: base list with the marker position swapped.
_UG_MUTATED_SENDER_COMMUNITIES = [
    _UG_MUTATED_COMMUNITY if c == _UG_INITIAL_COMMUNITY else c
    for c in _UG_BASE_SENDER_COMMUNITIES
]

# Resolved peer-IP lists used by playbook factories.
_UG_CTRL_PEER_ADDRS = [
    _ug_ebgp_peer_addr(_UG_EBGP_CTRL_START_IDX + i) for i in range(_UG_CTRL_MULTIPLIER)
]
_UG_HELD_PEER_ADDR = _ug_ebgp_peer_addr(_UG_EBGP_HELD_IDX)
_UG_DISP_PEER_ADDRS = [
    _ug_ebgp_peer_addr(_UG_EBGP_DISP_START_IDX + i) for i in range(_UG_DISP_MULTIPLIER)
]
_UG_B_KEEP_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_IDX)
_UG_B_KEEP_MUTATED_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_MUTATED_IDX)
_UG_B_VAR1_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_VAR1_IDX)
_UG_B_VAR2_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_VAR2_IDX)


def _ug_bgp_dg(
    *,
    device_group_index: int,
    tag_name: str,
    multiplier: int,
    starting_peer_ip: str,
    gateway_ip: str,
    remote_as: int,
    is_ebgp: bool,
    advertised_route_count: int = 0,
    starting_prefix: str = "",
    communities: t.Optional[t.List[str]] = None,
) -> taac_types.DeviceGroupConfig:
    """Build one BGP DG (eBGP or iBGP) for the UG hardening topology."""
    route_scales = []
    if advertised_route_count > 0:
        route_scales = [
            taac_types.RouteScaleSpec(
                network_group_index=0,
                v6_route_scale=taac_types.RouteScale(
                    multiplier=1,
                    prefix_count=advertised_route_count,
                    prefix_length=128,
                    starting_prefixes=starting_prefix,
                    prefix_step="0:0:0:0::1",
                    bgp_communities=list(communities or []),
                    ip_address_family=ixia_types.IpAddressFamily.IPV6,
                ),
            ),
        ]

    peer_type = ixia_types.BgpPeerType.EBGP if is_ebgp else ixia_types.BgpPeerType.IBGP

    return taac_types.DeviceGroupConfig(
        device_group_index=device_group_index,
        tag_name=tag_name,
        multiplier=multiplier,
        v6_addresses_config=taac_types.IpAddressesConfig(
            starting_ip=starting_peer_ip,
            increment_ip="0:0:0:0::2",
            gateway_starting_ip=gateway_ip,
            gateway_increment_ip="0:0:0:0::2",
            mask=127,
            start_index=0,
        ),
        v6_bgp_config=taac_types.BgpConfig(
            bgp_peer_name=tag_name,
            local_as_4_bytes=remote_as,
            enable_4_byte_local_as=True,
            bgp_peer_type=peer_type,
            bgp_capabilities=[ixia_types.BgpCapability.IpV6Unicast],
            hold_timer=30,
            keepalive_timer=10,
            route_scales=route_scales,
        ),
    )


def _ebgp_dgs() -> list:
    """Return the 3 eBGP receiver DGs on Et3/36/1 (CTRL, HELD, DISP)."""
    return [
        _ug_bgp_dg(
            device_group_index=0,
            tag_name=_UG_DG_A_CTRL_TAG,
            multiplier=_UG_CTRL_MULTIPLIER,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_CTRL_START_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_CTRL_START_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
        _ug_bgp_dg(
            device_group_index=1,
            tag_name=_UG_DG_A_HELD_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_HELD_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_HELD_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
        _ug_bgp_dg(
            device_group_index=2,
            tag_name=_UG_DG_A_DISP_TAG,
            multiplier=_UG_DISP_MULTIPLIER,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_DISP_START_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_DISP_START_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
    ]


def _ibgp_dgs() -> list:
    """Return the 4 iBGP sender DGs on Et3/36/2."""
    return [
        _ug_bgp_dg(
            device_group_index=0,
            tag_name=_UG_DG_B_KEEP_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_KEEP_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_KEEP_ROUTE_COUNT,
            starting_prefix="2401:db00:1000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=1,
            tag_name=_UG_DG_B_KEEP_MUTATED_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_MUTATED_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_KEEP_MUTATED_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_KEEP_ROUTE_COUNT,
            starting_prefix="2401:db00:1000::",
            communities=_UG_MUTATED_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=2,
            tag_name=_UG_DG_B_VAR1_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_VAR1_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_VAR1_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_VAR1_ROUTE_COUNT,
            starting_prefix="2401:db00:2000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=3,
            tag_name=_UG_DG_B_VAR2_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_VAR2_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_VAR2_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_VAR2_ROUTE_COUNT,
            starting_prefix="2401:db00:3000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
    ]


def _baseline_steps(*, bring_var1_up: bool = False) -> list:
    """Return setup_steps that bring HELD/VAR1/VAR2 to a clean baseline state.

    SCRUB-THEN-REARM pattern — see legacy `bag012_ash6_test_config._baseline_steps`
    for the full commentary on why DG-disable + hold-timer settle is required.
    """
    return [
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_VAR1_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_VAR1 -- forces DUT to "
                "drop stale VAR1 routes from adj-RIB-out via hold-timer"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_VAR2_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_VAR2 -- forces DUT to "
                "drop stale VAR2 routes from adj-RIB-out via hold-timer"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_KEEP_MUTATED_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_KEEP_MUTATED -- ensures "
                "only KEEP_INITIAL advertises the 300-prefix range at baseline "
                "(2.4.3 trigger toggles this pair to swap community)"
            ),
        ),
        create_longevity_step(
            duration=90,
            description=(
                "UG baseline SCRUB: settle 90s for DUT hold-timer expiry "
                "+ adj-RIB-out withdraw to propagate (iBGP peer-group "
                "hold-time is >60s on bag012, per 2.4.2 v17 finding)"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": _UG_DG_B_VAR1_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description="UG baseline REARM: re-enable DG_B_VAR1",
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": _UG_DG_B_VAR2_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description="UG baseline REARM: re-enable DG_B_VAR2",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_A_HELD_TAG,
            start=False,
            start_idx=1,
            end_idx=1,
            description="UG baseline: bring HELD admin-DOWN",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_B_VAR1_TAG,
            start=bring_var1_up,
            start_idx=1,
            end_idx=1,
            description=(
                "UG baseline: bring DG_B_VAR1 admin-"
                + ("UP" if bring_var1_up else "DOWN")
            ),
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_B_VAR2_TAG,
            start=False,
            start_idx=1,
            end_idx=1,
            description="UG baseline: bring DG_B_VAR2 admin-DOWN",
        ),
    ]


def _pb_2_4_1(device_name: str) -> taac_types.Playbook:
    return create_bgp_ug_new_peer_join_full_sync_resilience_playbook(
        device_name=device_name,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        disp_peer_addrs=_UG_DISP_PEER_ADDRS,
        disp_peer_regex=_UG_DG_A_DISP_TAG,
        disp_session_start_idx=1,
        disp_session_end_idx=_UG_DISP_KILL_COUNT,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_var1_peer_regex=_UG_DG_B_VAR1_TAG,
        b_var1_peer_addr=_UG_B_VAR1_PEER_ADDR,
        b_var1_route_count=_UG_VAR1_ROUTE_COUNT,
        b_var2_peer_regex=_UG_DG_B_VAR2_TAG,
        b_var2_peer_addr=_UG_B_VAR2_PEER_ADDR,
        b_var2_route_count=_UG_VAR2_ROUTE_COUNT,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        setup_steps=_baseline_steps(bring_var1_up=False),
    )


def _pb_2_4_2(device_name: str) -> taac_types.Playbook:
    return create_bgp_ug_new_peer_join_routes_withdrawn_playbook(
        device_name=device_name,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_var1_peer_regex=_UG_DG_B_VAR1_TAG,
        b_var1_peer_addr=_UG_B_VAR1_PEER_ADDR,
        b_var1_route_count=_UG_VAR1_ROUTE_COUNT,
        b_var1_device_group_regex=_UG_DG_B_VAR1_TAG,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        capture_tcpdump_device=device_name,
        setup_steps=_baseline_steps(bring_var1_up=True),
    )


def _pb_2_4_3(device_name: str) -> taac_types.Playbook:
    return create_bgp_ug_new_peer_join_attribute_change_playbook(
        device_name=device_name,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_keep_peer_regex=_UG_DG_B_KEEP_TAG,
        b_keep_device_group_regex=_UG_DG_B_KEEP_TAG,
        b_keep_mutated_peer_addr=_UG_B_KEEP_MUTATED_PEER_ADDR,
        b_keep_mutated_device_group_regex=_UG_DG_B_KEEP_MUTATED_TAG,
        initial_community=_UG_INITIAL_COMMUNITY,
        mutated_community=_UG_MUTATED_COMMUNITY,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        setup_steps=_baseline_steps(bring_var1_up=False),
    )


def create_bgp_ug_new_peer_join_test_config(testbed: Testbed) -> taac_types.TestConfig:
    """BGP++ Update Group qualification specs 2.4.1 + 2.4.2 + 2.4.3 TestConfig.

    Three qualification playbooks sharing one 21-eBGP + 4-iBGP testbed.
    ``enable_update_group=True`` is baked in (UG MUST be on for these specs).

    Wave 1 constraint: hardcoded to bag012's topology + IXIA wiring
    (helpers use ``IXIA_EBGP_IC_PARENT_NETWORK_V6`` etc. from the shared
    EBB conveyor constants module). ``testbed`` MUST be BAG012_ASH6. Wave 2
    parameterizes the underlying helpers on ``testbed.ixia_ports`` +
    ``testbed.dut_bgp_as`` so bag010/011/013 can host this qualification via
    a one-line catalog change.
    """
    assert testbed.device_name == "bag012.ash6", (
        f"create_bgp_ug_new_peer_join_test_config Wave 1 is hardcoded to "
        f"bag012.ash6; got testbed.device_name={testbed.device_name!r}. "
        f"Wave 2 will parameterize on testbed."
    )
    assert testbed.dut_bgp_as is not None, "Testbed must have dut_bgp_as set"
    assert testbed.router_id is not None, (
        "Testbed must have router_id set (used as BGP router-id)"
    )
    assert testbed.bgpcpp_configerator_path is not None, (
        "Testbed must have bgpcpp_configerator_path set for BGP++ deployment"
    )
    assert len(testbed.ixia_ports) >= 2, (
        "Testbed must have >= 2 IXIA ports (eBGP + iBGP)"
    )

    ebgp_dut_iface, ebgp_chassis_port = testbed.ixia_ports[0]
    ibgp_dut_iface, ibgp_chassis_port = testbed.ixia_ports[1]

    setup_tasks = get_update_packing_setup_tasks(
        device_name=testbed.device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ebgp_dut_iface,
        ixia_interface_mimic_ibgp=ibgp_dut_iface,
        ebgp_peer_count=_UG_TOTAL_EBGP_PEERS,
        ibgp_peer_count=_UG_TOTAL_IBGP_PEERS,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=True,
    )

    return taac_types.TestConfig(
        name="BGP_UG_NEW_PEER_JOIN_TEST",
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        endpoints=[
            taac_types.Endpoint(
                name=testbed.device_name,
                dut=True,
                ixia_ports=[
                    f"{testbed.ixia_chassis_ip}:{ebgp_chassis_port}",
                    f"{testbed.ixia_chassis_ip}:{ibgp_chassis_port}",
                ],
                direct_ixia_connections=[
                    taac_types.DirectIxiaConnection(
                        interface=ebgp_dut_iface,
                        ixia_chassis_ip=testbed.ixia_chassis_ip,
                        ixia_port=ebgp_chassis_port,
                    ),
                    taac_types.DirectIxiaConnection(
                        interface=ibgp_dut_iface,
                        ixia_chassis_ip=testbed.ixia_chassis_ip,
                        ixia_port=ibgp_chassis_port,
                    ),
                ],
            ),
        ],
        host_os_type_map={testbed.device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=[],
        basic_port_configs=[
            taac_types.BasicPortConfig(
                endpoint=f"{testbed.device_name}:{ebgp_dut_iface}",
                device_group_configs=_ebgp_dgs(),
            ),
            taac_types.BasicPortConfig(
                endpoint=f"{testbed.device_name}:{ibgp_dut_iface}",
                device_group_configs=_ibgp_dgs(),
            ),
        ],
        playbooks=[
            _pb_2_4_1(testbed.device_name),
            _pb_2_4_2(testbed.device_name),
            _pb_2_4_3(testbed.device_name),
        ],
    )


__all__ = [
    "create_bgp_ug_backpressure_test_config",
    "create_bgp_ug_backpressure_topology_smoke_test_config",
    "create_bgp_ug_eb03_initial_dump_identical_routes_test_config",
    "create_bgp_ug_initial_dump_identical_routes_test_config",
    "create_bgp_ug_new_peer_join_test_config",
    "create_bgp_ug_sustained_link_flap_test_config",
]


# =============================================================================
# BGP UG initial-dump-identical-routes (spec 2.1.1) + sustained-link-flap
# (spec 2.7.2) — bag013 conveyor topology.
#
# Moved from testconfigs/routing/ebb/bag013_ash6_test_config.py. Wave 1
# constraint: hardcoded to bag013.ash6's topology / IXIA wiring / OpenR link
# addresses. ``testbed`` MUST be BAG013_ASH6. Wave 2 will parameterize the
# helpers here on ``testbed.*`` so other EBB devices can host the qualification
# via a one-line catalog change.
# =============================================================================

# BGP++ Update Group qualification 2.7.2 -- Sustained Link Flap timing.
# Test values are intentional first-run defaults: 15-min total run with short
# cadences (30/45/75 s) and a brief 5 s down to exercise the orchestration in
# a few minutes per iteration. Production values per the BGP++ Update Group
# qualification 2.7.2 doc are 1 h total with 2/3/5 min cadences and 15 s down --
# swap by flipping ``_BAG013_2_7_2_USE_PRODUCTION_VALUES``.
_BAG013_2_7_2_USE_PRODUCTION_VALUES = True

# Per-interface peer subnets in CIDR form. Used by the step's isolation check
# to attribute each Established BGP peer to its IXIA-facing interface so the
# check knows which peers should NOT flap during a given cycle. CIDR is
# required because the step uses ``ipaddress.ip_address() in ipaddress.ip_network()``
# matching (an earlier iteration used bare string prefixes and mis-attributed
# peers that spilled beyond the literal ``IXIA_*_PARENT_NETWORK_*`` constant,
# producing hundreds of false-positive cross-group violations -- e.g. eBGP V4
# extends from 10.163.28.X into 10.163.29.X to fit 140 /31 pairs).
#
# Subnet sizes chosen empirically from the V6 run's peer-address ranges:
#   * eBGP V4 covers 10.163.28-29  -> /16 (10.163.0.0/16) is generously safe
#   * eBGP V6 sits inside :8::/80  -> /80 matches the IXIA generator
#   * iBGP V4 planes 1-8 are on 10.164-10.171, one /16 per plane
#   * iBGP V6 planes 1-8 are on :9::/80 through :16::/80 (one /80 per plane)
#   * BGP MON V6 sits inside :22:a::/80
_BAG013_EBGP_PEER_SUBNETS = [
    "10.163.0.0/16",
    f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::/80",
]
_BAG013_IBGP_PEER_SUBNETS = [
    # iBGP V4 -- 8 planes (DC 1-4: 10.164-10.167.X; MP 1-4: 10.168-10.171.X)
    "10.164.0.0/16",
    "10.165.0.0/16",
    "10.166.0.0/16",
    "10.167.0.0/16",
    "10.168.0.0/16",
    "10.169.0.0/16",
    "10.170.0.0/16",
    "10.171.0.0/16",
    # iBGP V6 -- 8 planes, each on a distinct /80 inside 2401:db00:e50d:11::
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3}::/80",
    f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4}::/80",
]
_BAG013_BGP_MON_PEER_SUBNETS = [f"{IXIA_BGP_MON_IC_PARENT_NETWORK}::/80"]

if _BAG013_2_7_2_USE_PRODUCTION_VALUES:
    _BAG013_2_7_2_TOTAL_DURATION_S = 3600
    _BAG013_2_7_2_PORT_SCHEDULE = [
        {
            "interface": "Ethernet3/36/1",
            "label": "eBGP",
            "period_s": 120,
            "down_s": 15,
            "peer_subnets": _BAG013_EBGP_PEER_SUBNETS,
        },
        {
            "interface": "Ethernet3/36/2",
            "label": "iBGP",
            "period_s": 180,
            "down_s": 15,
            "peer_subnets": _BAG013_IBGP_PEER_SUBNETS,
        },
        {
            "interface": "Ethernet3/36/3",
            "label": "BGP-MON",
            "period_s": 300,
            "down_s": 15,
            "peer_subnets": _BAG013_BGP_MON_PEER_SUBNETS,
        },
    ]
else:
    _BAG013_2_7_2_TOTAL_DURATION_S = 900
    _BAG013_2_7_2_PORT_SCHEDULE = [
        {
            "interface": "Ethernet3/36/1",
            "label": "eBGP",
            "period_s": 30,
            "down_s": 5,
            "peer_subnets": _BAG013_EBGP_PEER_SUBNETS,
        },
        {
            "interface": "Ethernet3/36/2",
            "label": "iBGP",
            "period_s": 45,
            "down_s": 5,
            "peer_subnets": _BAG013_IBGP_PEER_SUBNETS,
        },
        {
            "interface": "Ethernet3/36/3",
            "label": "BGP-MON",
            "period_s": 75,
            "down_s": 5,
            "peer_subnets": _BAG013_BGP_MON_PEER_SUBNETS,
        },
    ]


def _bag013_2_7_2_prechecks():
    """Build the bag013.ash6-specific precheck list for the 2.7.2 playbook.

    Hand-rolled (rather than via ``create_standard_prechecks``) for two
    bag013-specific reasons:
      1. bag013.ash6 BGP MON peers stay IDLE (known device-level bgpcpp
         config quirk; see project notes / MEMORY). We pass
         ``parent_prefixes_to_ignore=[IXIA_BGP_MON_IC_PARENT_NETWORK::/80]``
         to drop them from the session count.
      2. ``create_standard_prechecks`` enforces an EXACT
         ``expected_established_sessions`` count (defaults to 0 and is
         strictly compared, so omitting the count fails with "expected 0
         found N"). bag013's actual count drifts from the bag010 formula
         (1272 vs 1290) for reasons we haven't traced -- safer to use the
         "no non-established peers among non-MON set" semantics (omit
         ``expected_established_sessions``) than to hard-code a
         device-specific number that will rot.

    Other devices (bag010 / bag011) that pick up the
    ``create_bgp_ug_sustained_link_flap_playbook`` factory should
    pass their own precheck list -- typically
    ``create_standard_prechecks(peergroup_ibgp_v6=..., peergroup_ibgp_v4=...,
    expected_established_sessions=N, exclude_bgp_mon=True)`` -- since
    they don't share bag013's IDLE-MON quirk.
    """
    return [
        create_bgp_session_establish_check(
            # ``IXIA_BGP_MON_IC_PARENT_NETWORK`` is a bare string prefix
            # (e.g. ``"2401:db00:e50d:22:a"``), but the precheck pipes
            # ``parent_prefixes_to_ignore`` through ``ipaddress.ip_network()``
            # which rejects that form. Append ``::/80`` to make it a valid
            # CIDR -- mirrors how ``common_health_checks.create_standard_prechecks``
            # builds the same exclusion list.
            parent_prefixes_to_ignore=[f"{IXIA_BGP_MON_IC_PARENT_NETWORK}::/80"],
        ),
        create_drain_state_check(),
        create_memory_utilization_check(
            threshold=Gigabyte.GIG_5.value,
            start_time_jq_var="test_case_start_time",
        ),
        create_cpu_utilization_check(
            threshold=400.0, start_time_jq_var="test_case_start_time"
        ),
        # Confirm BGP++ ``update_group`` is actually active on the running
        # daemon before the flap loop starts. Mirrors the setup-task-level
        # ``Cli -p15 -c 'show bgpcpp update-group'`` guard in
        # ``conveyor_common_tasks._get_control_plane_tasks`` (D108374944), but
        # goes through the ``getUpdateGroupInfo`` thrift API (D108632994)
        # instead of CLI parsing. Provides a second, structured early-fail if
        # the patch silently regressed between setup completion and prechecks.
        create_bgp_update_group_check(expect_enabled=True),
    ]


def _create_bag013_ash6_conveyor_test_config_impl(
    testbed: Testbed,
    profile: BgpPlusPlusProfile,
    enable_update_group: bool,
) -> taac_types.TestConfig:
    """Byte-wise-identical extraction of the legacy
    ``bag013_ash6_test_config.create_bag013_ash6_conveyor_test_config``.

    The default (``enable_update_group=False``) variant has NO playbooks --
    bag013 is reserved for ad-hoc testing.

    When ``enable_update_group=True``, the BGP++ ``enable_update_group`` setting
    is dynamically toggled on the device during BGP++ deployment (in-shell patch
    of ``/mnt/flash/bgpcpp_config`` per D100093369), the TestConfig ``name``
    field is suffixed with ``_UPDATE_GROUP``, and the qualification 2.1.1 +
    2.7.2 playbooks are attached.
    """
    assert testbed.device_name == "bag013.ash6", (
        f"bag013 conveyor factories are Wave 1 hardcoded to bag013.ash6; "
        f"got testbed.device_name={testbed.device_name!r}. Wave 2 will "
        f"parameterize on testbed."
    )
    assert testbed.dut_bgp_as is not None, "Testbed must have dut_bgp_as set"
    assert testbed.bgpcpp_configerator_path is not None, (
        "Testbed must have bgpcpp_configerator_path set for BGP++ deployment"
    )
    assert testbed.openr_configerator_path is not None, (
        "Testbed must have openr_configerator_path set for OpenR deployment"
    )
    assert len(testbed.ixia_ports) >= 3, (
        "Testbed must have >= 3 IXIA ports (eBGP + iBGP + BGP-MON)"
    )

    device_name = testbed.device_name
    ixia_chassis_ip = testbed.ixia_chassis_ip
    ixia_interface_mimic_ebgp, ixia_port_ebgp = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, ixia_port_ibgp = testbed.ixia_ports[1]
    ixia_interface_mimic_bgp_mon, ixia_port_bgp_mon = testbed.ixia_ports[2]

    setup_tasks = get_common_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=profile,
        openr_configerator_path=testbed.openr_configerator_path,
        openr_port_channel_member="Ethernet3/9/1",
        openr_port_channel_ipv4="10.131.97.232/31",
        openr_port_channel_link_local="fe80::eba:a7f:fcfc/64",
        openr_local_link={
            "ipv4": "10.131.97.232",
            "ipv6": "fe80::eba:a7f:fcfc",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
        openr_other_link={
            "ipv4": "10.131.97.233",
            "ipv6": "fe80::eba:a7f:fcfd",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
        enable_update_group=enable_update_group,
    )

    teardown_tasks = get_teardown_tasks(
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
    )

    test_config_name = "BAG013_ASH6_BGP_CONVEYOR_TEST"
    if enable_update_group:
        test_config_name += "_UPDATE_GROUP"

    playbooks = (
        [
            # 2.1.1 Initial Dump: all peers in the same group receive identical
            # routes (membership + dump-compare). Full parity with eb03.
            create_bgp_ug_initial_dump_identical_routes_playbook(
                device_name=device_name,
                ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
                ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
                ibgp_v6_peer_group=PEERGROUP_IBGP_V6,
                ebgp_v6_peer_group=PEERGROUP_EBGP_V6,
                ibgp_v4_peer_group=PEERGROUP_IBGP_V4,
                bgp_mon_peer_group=PEERGROUP_BGP_MON,
            ),
            create_bgp_ug_sustained_link_flap_playbook(
                device_name=device_name,
                port_schedule=_BAG013_2_7_2_PORT_SCHEDULE,
                total_duration_s=_BAG013_2_7_2_TOTAL_DURATION_S,
                prechecks=_bag013_2_7_2_prechecks(),
                # postchecks/snapshot_checks left None -- factory defaults
                # cover the spec (BGP_STANDARD_POSTCHECKS + load-avg<12 +
                # BGP_STANDARD_SNAPSHOT_CHECKS).
            ),
        ]
        if enable_update_group
        else []
    )

    return taac_types.TestConfig(
        name=test_config_name,
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        endpoints=[
            taac_types.Endpoint(
                name=device_name,
                dut=True,
                ixia_ports=[
                    ixia_interface_mimic_ebgp,
                    ixia_interface_mimic_ibgp,
                    ixia_interface_mimic_bgp_mon,
                ],
                direct_ixia_connections=[
                    taac_types.DirectIxiaConnection(
                        interface=ixia_interface_mimic_ebgp,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_ebgp,
                    ),
                    taac_types.DirectIxiaConnection(
                        interface=ixia_interface_mimic_ibgp,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_ibgp,
                    ),
                    taac_types.DirectIxiaConnection(
                        interface=ixia_interface_mimic_bgp_mon,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_bgp_mon,
                    ),
                ],
            ),
        ],
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=teardown_tasks,
        basic_port_configs=create_ebb_scale_basic_port_configs(
            device_name=device_name,
            ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
            ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
            ebgp_peer_count_v6=EBGP_PEER_COUNT_V6,
            ebgp_peer_count_v4=EBGP_PEER_COUNT_V4,
            ebgp_peer_to_drain=EBGP_PEER_TO_DRAIN,
            ibgp_peer_scale_per_plane=IBGP_PEER_SCALE_PER_PLANE,
            ibgp_peer_to_drain_per_plane=IBGP_PEER_TO_DRAIN_PER_PLANE,
            bgp_mon_peer_count=BGP_MON_PEER_COUNT,
            ebgp_remote_as=EBGP_REMOTE_AS,
            ibgp_remote_as=IBGP_REMOTE_AS,
            bgp_mon_remote_as=BGP_MON_REMOTE_AS,
            ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
            ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
            ixia_ibgp_ic_parent_network_v6_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v6_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v6_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v6_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v6_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v6_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v6_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v6_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4,
            ixia_ibgp_ic_parent_network_v4_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v4_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v4_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v4_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v4_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v4_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v4_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v4_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE4,
            ixia_bgp_mon_ic_parent_network=IXIA_BGP_MON_IC_PARENT_NETWORK,
            profile=profile,
        ),
        playbooks=playbooks,
    )


def create_bgp_ug_initial_dump_identical_routes_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.1.1 (Initial Dump -- Identical Routes)
    TestConfig for the bag013 conveyor topology.

    NAME/BEHAVIOR MISMATCH (grandfathered, tracked for Wave 4 rename):
    despite its name this factory does NOT wire up the 2.1.1 playbook -- it
    returns a TestConfig with ``name="BAG013_ASH6_BGP_CONVEYOR_TEST"`` and an
    empty playbook list, byte-wise identical to the legacy
    ``bag013_ash6_test_config.create_bag013_ash6_conveyor_test_config()``
    default variant. The 2.1.1 playbook only ships in the ``_UPDATE_GROUP``
    sibling (``create_bgp_ug_sustained_link_flap_test_config``); bag013's
    default has always been ad-hoc.

    Wave 4 followup: rename this to something like
    ``create_bag013_ash6_adhoc_test_config`` (or restructure to actually
    attach the 2.1.1 playbook here, matching name-to-behavior). Left as-is
    for now because renaming a public factory would ripple across the
    catalog + conveyor node aggregator without providing byte-identity
    savings.
    """
    return _create_bag013_ash6_conveyor_test_config_impl(
        testbed=testbed,
        profile=profile,
        enable_update_group=False,
    )


def create_bgp_ug_sustained_link_flap_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.7.2 (Sustained Link Flap) TestConfig
    for the bag013 conveyor topology.

    Byte-wise identical to the legacy
    ``bag013_ash6_test_config.create_bag013_ash6_conveyor_test_config(
    enable_update_group=True)`` -- returns a TestConfig with
    ``name="BAG013_ASH6_BGP_CONVEYOR_TEST_UPDATE_GROUP"`` and two playbooks
    attached: the 2.1.1 initial-dump-identical-routes playbook (full parity
    with eb03.lab.ash6) followed by the 2.7.2 sustained-link-flap playbook
    (rotates flapping the 3 IXIA-facing ports on independent cadences,
    asserts no cross-group BGP session disruption after each cycle).
    """
    return _create_bag013_ash6_conveyor_test_config_impl(
        testbed=testbed,
        profile=profile,
        enable_update_group=True,
    )


# =============================================================================
# EB03 UG initial-dump — Arista lab-box variant (BGP++ UG spec 2.1.1 on eb03.lab.ash6)
# =============================================================================
#
# eb03.lab.ash6 is structurally distinct from the bag conveyor UG topology:
#   - Lab device (admin/password auth via TAAC_EBB_LAB_DEVICE_PASSWORD env)
#   - netwhoami returns #INVALID# → need oss_mock_device_data override
#   - Setup path always uses WITHOUT_OPEN_R + conditional openr_route_action_task
#     (eb03 is route-injection only, not the bag-style Port-Channel)
#   - Playbooks pin eb03-specific expected_member_counts / policy_names
#     (EB-EB-V6 → 496 members, EB-FA-V6 → 140, BGP-MON → 2) and use the
#     build_arista_ebb_scale_playbook trampoline (Wave 2 kill target)
#
# Because of these differences, eb03 has its own factory rather than reusing
# create_bgp_ug_initial_dump_identical_routes_test_config from the bag013 path.


def _create_eb03_2_1_1_initial_dump_identical_routes_playbook(testbed: Testbed):
    """eb03-specific BGP++ Update Group qualification 2.1.1 playbook.

    Byte-wise identical to the legacy
    ``eb03_update_group_test_config._create_2_1_1_initial_dump_identical_routes_playbook``.
    Pinned expected_member_counts (EB-EB-V6=496, EB-FA-V6=140, BGP-MON=2) and
    policy_names are eb03-specific golden values from the live device.
    """
    ibgp_dut_iface, _ = testbed.ixia_ports[1]  # IXIA_INTERFACE_MIMIC_IBGP
    bgp_mon_dut_iface, _ = testbed.ixia_ports[2]  # IXIA_INTERFACE_MIMIC_BGP_MON

    prechecks = [
        *BGP_STANDARD_PRECHECKS,
        create_bgp_graceful_restart_check(
            peer_group_name=PEERGROUP_IBGP_V6,
            expected_graceful_restart_enabled=False,
            check_id="eb03_2_1_1_gr_disabled_ibgp_v6",
        ),
        create_bgp_graceful_restart_check(
            peer_group_name=PEERGROUP_IBGP_V4,
            expected_graceful_restart_enabled=False,
            check_id="eb03_2_1_1_gr_disabled_ibgp_v4",
        ),
    ]
    verify_step = create_validation_step(
        point_in_time_checks=[
            create_bgp_update_group_check(
                peer_group_substrings=[
                    PEERGROUP_IBGP_V6,
                    PEERGROUP_EBGP_V6,
                    PEERGROUP_BGP_MON,
                ],
                expected_group_count=5,
                expected_member_counts={
                    PEERGROUP_IBGP_V6: 496,
                    PEERGROUP_EBGP_V6: 140,
                    PEERGROUP_BGP_MON: 2,
                },
                expected_policy_names={
                    PEERGROUP_IBGP_V6: ["EB-EB-OUT"],
                    PEERGROUP_EBGP_V6: ["EB-FA-OUT"],
                    PEERGROUP_BGP_MON: ["PROPAGATE_EVERYTHING_OUT"],
                },
                check_id="eb03_2_1_1_update_group_membership",
            )
        ],
        description=(
            "BGP++ Update Group qualification 2.1.1 -- verify EB-EB-V6 iBGP (496 "
            "members, EB-EB-OUT), EB-FA-V6 eBGP (140, EB-FA-OUT) and BGP-MON "
            "(2, PROPAGATE_EVERYTHING_OUT) form distinct update groups, with 5 "
            "groups total (one per peer-group per AFI + BGP-MON)."
        ),
    )
    pcap_compare_step = create_custom_step(
        params_dict={
            "custom_step_name": "test_bgp_update_group_dump_compare",
            "hostname": testbed.device_name,
            "ixia_capture_interface": ibgp_dut_iface,
            "ibgp_peer_regex": "BGP_PEER_IPV6_IBGP_PLANE_1_REMOTE_EB",
            "ibgp_peer_session_indices": [1, 2],
            "capture_duration_seconds": 300,
            "settle_seconds": 10,
            "bgp_mon_capture_interface": bgp_mon_dut_iface,
            "bgp_mon_peer_regex": "BGP_PEER_IPV6_BGP_MON",
            "bgp_mon_session_index": 1,
        },
        description=(
            "BGP++ Update Group 2.1.1 steps 6-7 -- capture and compare the "
            "initial-dump UPDATEs to two iBGP peers in the same update group "
            "(identical NLRI/AS_PATH/LOCAL_PREF/COMMUNITY/MED; next-hop may differ)."
        ),
    )
    return build_arista_ebb_scale_playbook(
        name="eb03_2_1_1_initial_dump_identical_routes",
        stages=[
            create_steps_stage(steps=[verify_step]),
            create_steps_stage(steps=[pcap_compare_step]),
        ],
        prechecks=prechecks,
        postchecks=BGP_STANDARD_POSTCHECKS,
        snapshot_checks=BGP_STANDARD_SNAPSHOT_CHECKS,
    )


def _create_eb03_longevity_debugging_playbook():
    """eb03-specific longevity soak playbook — byte-wise identical to legacy inline.

    From ``eb03_update_group_test_config.create_eb03_update_group_test_config()``,
    the inline second-playbook. 20s longevity + one BgpUpdateGroupHealthCheck
    precheck (probe mode, no pinned counts).
    """
    return build_arista_ebb_scale_playbook(
        name="eb03_longevity_debugging",
        prechecks=[
            create_bgp_update_group_check(
                peer_group_substrings=[
                    PEERGROUP_IBGP_V6,
                    PEERGROUP_EBGP_V6,
                    PEERGROUP_BGP_MON,
                ],
                check_id="eb03_longevity_update_group_probe",
            ),
        ],
        stages=[
            create_steps_stage(
                steps=[create_longevity_step(duration=20)],
            ),
        ],
    )


def create_bgp_ug_eb03_initial_dump_identical_routes_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.1.1 TestConfig for eb03.lab.ash6.

    Byte-wise identical to the legacy
    ``eb03_update_group_test_config.create_eb03_update_group_test_config()``.

    Differs from ``create_bgp_ug_initial_dump_identical_routes_test_config``
    (which handles bag013's topology) in these eb03-specific ways:
      - ``host_driver_args`` for admin/password auth (svc-netcastle_bot not
        authorized on the lab device)
      - ``oss_mock_device_data`` MockDeviceInfo (netwhoami returns #INVALID#)
      - Setup path uses WITHOUT_OPEN_R + conditional openr_route_action_task
        (eb03 is route-injection only, no bag-style Port-Channel)
      - Playbooks pin eb03-specific expected_member_counts / policy_names

    Wave 2 candidate: fold host_driver_args / oss_mock_device_data into the
    Testbed dataclass so this factory can share more infrastructure with the
    bag013 factory. Wave 4 candidate: rename the pinned playbook names.
    """
    assert testbed.device_name == "eb03.lab.ash6", (
        f"create_bgp_ug_eb03_initial_dump_identical_routes_test_config is "
        f"hardcoded to eb03.lab.ash6 (pinned expected_member_counts + "
        f"policy_names). Got testbed.device_name={testbed.device_name!r}."
    )
    assert len(testbed.ixia_ports) >= 3, (
        "eb03 UG initial-dump requires >= 3 IXIA ports (eBGP + iBGP + BGP-MON)."
    )
    assert testbed.dut_bgp_as is not None, "Testbed must have dut_bgp_as set"
    assert testbed.bgpcpp_configerator_path is not None, (
        "Testbed must have bgpcpp_configerator_path set"
    )

    ebgp_dut_iface, ebgp_chassis_port = testbed.ixia_ports[0]
    ibgp_dut_iface, ibgp_chassis_port = testbed.ixia_ports[1]
    bgp_mon_dut_iface, bgp_mon_chassis_port = testbed.ixia_ports[2]

    # Lab device credentials — env-var override with fallback to the shared
    # eb03 lab password default (documented in testbed.py::EB03_LAB_ASH6.extras).
    lab_password_env = (
        testbed.lab_device_password_env_var or "TAAC_EBB_LAB_DEVICE_PASSWORD"
    )
    lab_admin_username = testbed.extras.get("lab_admin_username", "admin")
    lab_admin_password_default = testbed.extras.get(
        "lab_admin_password_default",
        "dnepit",  # pragma: allowlist secret
    )
    lab_password = os.environ.get(lab_password_env, lab_admin_password_default)

    setup_tasks = get_common_setup_tasks(
        device_name=testbed.device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ebgp_dut_iface,
        ixia_interface_mimic_ibgp=ibgp_dut_iface,
        ixia_interface_mimic_bgp_mon=bgp_mon_dut_iface,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=True,
    )

    if profile == BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R:
        setup_tasks.append(
            create_openr_route_action_task(
                device_name=testbed.device_name,
                action=OpenRRouteAction.INJECT.value,
                start_ipv4s=DEFAULT_OPENR_START_IPV4S,
                start_ipv6s=DEFAULT_OPENR_START_IPV6S,
                local_link=DEFAULT_LOCAL_LINK,
                other_link=DEFAULT_OTHER_LINK,
                count=63,
                step=2,
                ixia_needed=True,
                set_outer_hostname=True,
                description="Inject Open/R routes during test setup",
            )
        )

    teardown_tasks = get_teardown_tasks(
        ixia_interface_mimic_ebgp=ebgp_dut_iface,
        ixia_interface_mimic_ibgp=ibgp_dut_iface,
        ixia_interface_mimic_bgp_mon=bgp_mon_dut_iface,
    )

    return TestConfig(
        name="EB03_LAB_ASH6_BGP_TEST_UPDATE_GROUP_CONFIG",
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        host_driver_args={
            testbed.device_name: json.dumps(
                {"username": lab_admin_username, "password": lab_password}
            ),
        },
        endpoints=[
            Endpoint(
                name=testbed.device_name,
                dut=True,
                ixia_ports=[
                    ebgp_dut_iface,
                    ibgp_dut_iface,
                    bgp_mon_dut_iface,
                ],
                direct_ixia_connections=[
                    DirectIxiaConnection(
                        interface=ebgp_dut_iface,
                        ixia_chassis_ip=testbed.ixia_chassis_ip,
                        ixia_port=ebgp_chassis_port,
                    ),
                    DirectIxiaConnection(
                        interface=ibgp_dut_iface,
                        ixia_chassis_ip=testbed.ixia_chassis_ip,
                        ixia_port=ibgp_chassis_port,
                    ),
                    DirectIxiaConnection(
                        interface=bgp_mon_dut_iface,
                        ixia_chassis_ip=testbed.ixia_chassis_ip,
                        ixia_port=bgp_mon_chassis_port,
                    ),
                ],
            ),
        ],
        host_os_type_map={testbed.device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        oss_mock_device_data={
            testbed.device_name: taac_types.MockDeviceInfo(
                name=testbed.device_name,
                hardware=testbed.extras.get("mock_device_hardware", "ARISTA_7516"),
                role=testbed.extras.get("mock_device_role", "EB"),
                operating_system="EOS",
                dc=testbed.extras.get("mock_device_dc", "ash6"),
                region=testbed.extras.get("mock_device_region", "ash"),
                asset_id=testbed.extras.get("mock_device_asset_id", 12345),
                asic=testbed.extras.get("mock_device_asic", "JERICHO"),
                routing_protocol="BGP",
                dc_type="ONE",
                network_area=testbed.extras.get("mock_device_network_area", "BACKBONE"),
                network_area_type="BACKBONE",
                network_type=testbed.extras.get("mock_device_network_type", "EBB"),
            ),
        },
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=teardown_tasks,
        basic_port_configs=create_ebb_scale_basic_port_configs(
            device_name=testbed.device_name,
            ixia_interface_mimic_ebgp=ebgp_dut_iface,
            ixia_interface_mimic_ibgp=ibgp_dut_iface,
            ixia_interface_mimic_bgp_mon=bgp_mon_dut_iface,
            ebgp_peer_count_v6=EBGP_PEER_COUNT_V6,
            ebgp_peer_count_v4=EBGP_PEER_COUNT_V4,
            ebgp_peer_to_drain=EBGP_PEER_TO_DRAIN,
            ibgp_peer_scale_per_plane=IBGP_PEER_SCALE_PER_PLANE,
            ibgp_peer_to_drain_per_plane=IBGP_PEER_TO_DRAIN_PER_PLANE,
            bgp_mon_peer_count=BGP_MON_PEER_COUNT,
            ebgp_remote_as=EBGP_REMOTE_AS,
            ibgp_remote_as=IBGP_REMOTE_AS,
            bgp_mon_remote_as=BGP_MON_REMOTE_AS,
            ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
            ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
            ixia_ibgp_ic_parent_network_v6_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v6_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v6_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v6_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v6_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v6_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v6_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v6_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4,
            ixia_ibgp_ic_parent_network_v4_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v4_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v4_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v4_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v4_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v4_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v4_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v4_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE4,
            ixia_bgp_mon_ic_parent_network=IXIA_BGP_MON_IC_PARENT_NETWORK,
            profile=profile,
        ),
        playbooks=[
            _create_eb03_2_1_1_initial_dump_identical_routes_playbook(testbed),
            _create_eb03_longevity_debugging_playbook(),
        ],
    )


# =============================================================================
# BGP UG Backpressure & Blocking Behavior (spec 2.3.1 / 2.3.2 / 2.3.3 / 2.3.4)
# -- bag013 conveyor topology.
#
# Moved from ``testconfigs/routing/ebb/bag013_ash6_backpressure_test_config.py``
# (Wave 2B). Wave 1 hardcoded constants that would generalize to other EBB
# devices in Wave 4 stay pinned to bag013 semantics here (peer address ranges
# hand-derived from bag013 topology; DUT-identity fields threaded from
# ``testbed.*``).
# =============================================================================


# ─── Topology constants (bag013-shape) ──────────────────────────────────────
_BAG013_BACKPRESSURE_PROFILE = BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R
_BAG013_BACKPRESSURE_STORM_PREFIX_POOL_REGEX = (
    "PREFIX_POOL_IBGP_IPV6_PLANE_1_REMOTE_EB_DRAIN"
)
_BAG013_BACKPRESSURE_STORM_DEVICE_GROUP_REGEX = (
    "DEVICE_GROUP_IPV6_IBGP_PLANE_1_REMOTE_EB_DRAIN"
)
_BAG013_BACKPRESSURE_EBGP_V6_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV6_EBGP"
_BAG013_BACKPRESSURE_EBGP_V6_PEER_REGEX = "BGP_PEER_IPV6_EBGP"
_BAG013_BACKPRESSURE_EBGP_ALL_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV[46]_EBGP$"
_BAG013_BACKPRESSURE_BGP_MON_PEER_REGEX = "BGP_PEER_IPV6_BGPMON"

# Total expected ESTABLISHED sessions on bag013 EBB full-scale.
# bgpcpp configures 1274 peers total = 280 eBGP (140 V4 + 140 V6) + 992 iBGP
# (62/plane * 8 planes * 2 AFIs) + 2 BGP_MON -- confirmed via thrift probe.
# BGP_MON peers stay IDLE on bag013 (known device quirk), so the count of
# peers that actually reach Established is 1274 - 2 = 1272.
_BAG013_BACKPRESSURE_TOTAL_CONFIGURED_PEERS = (
    EBGP_PEER_COUNT_V6
    + EBGP_PEER_COUNT_V4
    + IBGP_PEER_SCALE_PER_PLANE * 8 * 2
    + BGP_MON_PEER_COUNT
)
_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS = (
    _BAG013_BACKPRESSURE_TOTAL_CONFIGURED_PEERS - BGP_MON_PEER_COUNT
)

_BAG013_BACKPRESSURE_MEMORY_THRESHOLD_BYTES = Gigabyte.GIG_10.value
_BAG013_BACKPRESSURE_LOAD_AVG_BASELINE = 12.0

_BAG013_BACKPRESSURE_EB_FA_OUT_PERMIT_COMMUNITY = "65531:50300"


def _bag013_backpressure_heavy_communities_32() -> list:
    """32 community combinations, each with the EB-FA-OUT permit-anchor
    community + a heavy variation so DUT eBGP egress policy accepts the storm
    routes on the wire."""
    return [
        [_BAG013_BACKPRESSURE_EB_FA_OUT_PERMIT_COMMUNITY, f"65529:{30000 + i}"]
        for i in range(32)
    ]


def _bag013_backpressure_heavy_extended_communities_16() -> list:
    """16 extended-community combinations (RT format)."""
    return [[f"rt:65529:{40000 + i}"] for i in range(16)]


def _bag013_backpressure_heavy_as_path_255() -> list:
    """255-ASN AS_SEQ (deterministic private-range ASNs for reproducibility)."""
    return [64512 + (i % 1023) for i in range(255)]


def _bag013_backpressure_storm_dg_v6_attribute_overrides() -> list:
    """Inline BgpAttributeConfig overrides for the iBGP plane-1 V6 drain DG --
    pre-attaches 32 community + 16 ext-community combos at IXIA-build time so
    trigger sequences do not need runtime ``configure_*_pool`` (which cascades
    chassis-wide via unconditional ``stop_protocols()``).
    """
    return [
        ixia_types.BgpAttributeConfig(
            attribute=ixia_types.BgpAttribute.COMMUNITIES,
            value_lists=_bag013_backpressure_heavy_communities_32(),
            distribution_type=ixia_types.DistribitionType.ROUND_ROBIN,
        ),
        ixia_types.BgpAttributeConfig(
            attribute=ixia_types.BgpAttribute.EXT_COMMUNITIES,
            value_lists=_bag013_backpressure_heavy_extended_communities_16(),
            distribution_type=ixia_types.DistribitionType.ROUND_ROBIN,
        ),
    ]


def _bag013_backpressure_peer_addr(parent: str, idx: int) -> str:
    """Derive IXIA-side peer address (idx-th, 0-based) for a given parent
    network. Matches ``_generate_ixia_v6_peer_entries_for_bgpcpp`` arithmetic
    (start_offset=0x10, stride=2): IXIA peer at parent::{0x11+2*idx:x}.
    """
    return f"{parent}::{0x11 + 2 * idx:x}"


# ─── Peer address lists (hand-derived for bag013 topology) ──────────────────
_BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS = [
    _bag013_backpressure_peer_addr(IXIA_EBGP_IC_PARENT_NETWORK_V6, i)
    for i in range(EBGP_PEER_COUNT_V6)
]
# BGP_MON peers stay IDLE on bag013 -- skip liveness checks that would false-fail.
_BAG013_BACKPRESSURE_BGP_MON_PEER_ADDRS: list = []
_BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS = [
    _bag013_backpressure_peer_addr(IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2, i)
    for i in range(IBGP_PEER_SCALE_PER_PLANE)
]
_BAG013_BACKPRESSURE_IBGP_PEER_ADDRS = list(
    _BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS
)

# 2.3.1 fast vs slow (same UG, TCP-throttled subset)
_BAG013_BACKPRESSURE_EBGP_SLOW_PEER_COUNT_V6 = 20
_BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS = list(
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS[
        : EBGP_PEER_COUNT_V6 - _BAG013_BACKPRESSURE_EBGP_SLOW_PEER_COUNT_V6
    ]
)
_BAG013_BACKPRESSURE_SLOW_EBGP_V6_PEER_ADDRS = list(
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS[
        EBGP_PEER_COUNT_V6 - _BAG013_BACKPRESSURE_EBGP_SLOW_PEER_COUNT_V6 :
    ]
)
_BAG013_BACKPRESSURE_SLOW_EBGP_V6_DG_NAME = "DEVICE_GROUP_IPV6_EBGP_SLOW"
_BAG013_BACKPRESSURE_SLOW_EBGP_V6_TCP_WINDOW_BYTES = 1500

_BAG013_BACKPRESSURE_FAST_PEER_ADDRS = _BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS
_BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS_NO_SLOW = (
    _BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS
)
_BAG013_BACKPRESSURE_SHUTDOWN_PEER_ADDRS = list(
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS_NO_SLOW[:16]
)
_BAG013_BACKPRESSURE_SURVIVING_RECEIVER_ADDRS = (
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS_NO_SLOW[16:]
    + _BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS
)
_BAG013_BACKPRESSURE_SURVIVING_EBGP_RECEIVER_ADDRS = list(
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS_NO_SLOW[16:]
)
_BAG013_BACKPRESSURE_SURVIVING_IBGP_RECEIVER_ADDRS = list(
    _BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS
)
_BAG013_BACKPRESSURE_EBGP_PEER_ADDRS = list(
    _BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS_NO_SLOW
)

# ─── Per-playbook spec parameters ───────────────────────────────────────────
_BAG013_BACKPRESSURE_2_3_1_PREFIX_COUNT = 10000

_BAG013_BACKPRESSURE_2_3_2_INITIAL_PREFIX_COUNT = 5000
_BAG013_BACKPRESSURE_2_3_2_FOLLOWUP_PREFIX_COUNT = 500
_BAG013_BACKPRESSURE_2_3_2_SHUTDOWN_COUNT = 16

_BAG013_BACKPRESSURE_2_3_3_IBGP_STORM_PREFIX_COUNT = 5000
_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_CHANGE_PREFIX_COUNT = 400
_BAG013_BACKPRESSURE_2_3_3_WITHDRAW_COUNT = 200
_BAG013_BACKPRESSURE_2_3_3_LP_MODIFY_COUNT = 100
_BAG013_BACKPRESSURE_2_3_3_INITIAL_COMMUNITY = "65529:34814"
# NOTE: 16-bit constraint — BGP RFC 1997 community low field is 16 bits.
# IXIA silently truncates writes above 65535; keep both parts within range.
_BAG013_BACKPRESSURE_2_3_3_MUTATED_COMMUNITY = "65529:1234"
_BAG013_BACKPRESSURE_2_3_3_TARGET_LOCAL_PREF = 200
_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_PREFIX_POOL_REGEX = "PREFIX_POOL_IPV6_EBGP"
_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV6_EBGP"

_BAG013_BACKPRESSURE_2_3_4_INITIAL_PREFIX_COUNT = 10000
_BAG013_BACKPRESSURE_2_3_4_FOLLOWUP_PREFIX_COUNT = 500


def _bag013_backpressure_split_ebgp_v6_for_slow_peers(
    port_configs: list,
    slow_peer_count: int,
    slow_dg_name: str,
) -> list:
    """Post-process the port_configs returned by
    ``create_ebb_scale_basic_port_configs`` to carve the LAST
    ``slow_peer_count`` peers of ``DEVICE_GROUP_IPV6_EBGP`` into a new
    ``DEVICE_GROUP_IPV6_EBGP_SLOW`` DG. Both DGs point at the SAME DUT
    peer-group so they land in the same UG on DUT. A post-IXIA-setup step
    (see the 2.3.1 playbook setup_steps) reduces the slow DG's TCP WindowSize
    to induce natural DUT adj-RIB-out backpressure on ONLY those peers.
    """
    if slow_peer_count <= 0:
        return port_configs

    # thrift-python structs are immutable -- use ``__replace__`` (frozen
    # dataclasses-style) to rebuild each affected object.
    out_ports = []
    for port_cfg in port_configs:
        dgs = list(getattr(port_cfg, "device_group_configs", None) or [])
        new_dgs = []
        matched = False
        for dg in dgs:
            if (
                matched
                or getattr(dg, "device_group_name", None) != "DEVICE_GROUP_IPV6_EBGP"
            ):
                new_dgs.append(dg)
                continue
            total = int(dg.multiplier)
            if slow_peer_count >= total:
                new_dgs.append(dg)
                continue
            fast_count = total - slow_peer_count
            # Rebuild fast DG (shrunk).
            fast_bgp = dg.v6_bgp_config
            if fast_bgp and fast_bgp.import_bgp_routes_params_list:
                fast_params = fast_bgp.import_bgp_routes_params_list[0].__replace__(
                    end_index=fast_count,
                )
                fast_bgp = fast_bgp.__replace__(
                    import_bgp_routes_params_list=[fast_params],
                )
            new_dgs.append(
                dg.__replace__(multiplier=fast_count, v6_bgp_config=fast_bgp),
            )
            # Build slow DG variant.
            slow_addrs = (
                dg.v6_addresses_config.__replace__(start_index=fast_count)
                if dg.v6_addresses_config
                else None
            )
            slow_bgp = None
            if dg.v6_bgp_config:
                slow_params_list = []
                if dg.v6_bgp_config.import_bgp_routes_params_list:
                    slow_params_list = [
                        dg.v6_bgp_config.import_bgp_routes_params_list[0].__replace__(
                            prefix_pool_name="PREFIX_POOL_IPV6_EBGP_SLOW",
                            start_index=fast_count,
                            end_index=total,
                        ),
                    ]
                _parent = IXIA_EBGP_IC_PARENT_NETWORK_V6
                if 0x11 + 2 * (fast_count + slow_peer_count) > 0xFFFF:
                    raise ValueError(
                        f"eBGP fast+slow peer count "
                        f"({fast_count + slow_peer_count}) would emit an "
                        f"address outside the {_parent}::/112 range this "
                        f"config assumes; extend the addressing scheme first."
                    )
                _local_start = f"{_parent}::{0x11 + 2 * fast_count:x}"
                _remote_start = f"{_parent}::{0x10 + 2 * fast_count:x}"
                slow_bgp = dg.v6_bgp_config.__replace__(
                    bgp_peer_name="BGP_PEER_IPV6_EBGP_SLOW",
                    import_bgp_routes_params_list=slow_params_list,
                    local_peer_starting_ip=_local_start,
                    remote_peer_starting_ip=_remote_start,
                )
            new_dgs.append(
                dg.__replace__(
                    device_group_name=slow_dg_name,
                    device_group_index=max(
                        (int(getattr(d, "device_group_index", 0)) for d in dgs),
                        default=0,
                    )
                    + 1,
                    multiplier=slow_peer_count,
                    v6_addresses_config=slow_addrs,
                    v6_bgp_config=slow_bgp,
                ),
            )
            matched = True
        out_ports.append(port_cfg.__replace__(device_group_configs=new_dgs))
    return out_ports


def _bag013_backpressure_pb_2_3_1(
    *,
    device_name: str,
    ixia_interface_mimic_ebgp: str,
    ixia_interface_mimic_ibgp: str,
) -> taac_types.Playbook:
    slow_peer_throttle_setup = create_configure_bgp_peer_tcp_window_size_step(
        hostname=device_name,
        interface=ixia_interface_mimic_ebgp,
        device_group_regex=f"^{_BAG013_BACKPRESSURE_SLOW_EBGP_V6_DG_NAME}$",
        tcp_window_size_bytes=_BAG013_BACKPRESSURE_SLOW_EBGP_V6_TCP_WINDOW_BYTES,
        description=(
            f"Setup (2.3.1): throttle TCP WindowSize="
            f"{_BAG013_BACKPRESSURE_SLOW_EBGP_V6_TCP_WINDOW_BYTES} on "
            f"{_BAG013_BACKPRESSURE_SLOW_EBGP_V6_DG_NAME} "
            f"({_BAG013_BACKPRESSURE_EBGP_SLOW_PEER_COUNT_V6} slow eBGP peers) "
            f"to induce DUT adj-RIB-out backpressure -- required for spec 2.3.1 "
            f"fast/slow asymmetry to be exercised on IXIA testbeds where "
            f"peers otherwise drain at line rate."
        ),
    )
    _per_peer_wire_snapshot_key = f"pb_2_3_1_per_peer_rx_pre_storm_{device_name}"
    _per_peer_wire_snapshot = create_snapshot_per_peer_bgp_rx_stats_step(
        hostname=device_name,
        interface=ixia_interface_mimic_ebgp,
        snapshot_key=_per_peer_wire_snapshot_key,
        peer_addrs=list(_BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS)
        + list(_BAG013_BACKPRESSURE_SLOW_EBGP_V6_PEER_ADDRS),
        description=(
            f"Phase 0 wire-per-peer snapshot (2.3.1): capture per-peer "
            f"IXIA Messages Rx baseline on "
            f"{device_name}:{ixia_interface_mimic_ebgp} across "
            f"{len(_BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS)} fast + "
            f"{len(_BAG013_BACKPRESSURE_SLOW_EBGP_V6_PEER_ADDRS)} slow peer(s), "
            f"for post-storm wire-side asymmetry verification"
        ),
    )
    _per_peer_wire_verify = create_verify_per_peer_bgp_rx_asymmetry_step(
        hostname=device_name,
        interface=ixia_interface_mimic_ebgp,
        snapshot_key=_per_peer_wire_snapshot_key,
        fast_peer_addrs=list(_BAG013_BACKPRESSURE_FAST_EBGP_V6_PEER_ADDRS),
        slow_peer_addrs=list(_BAG013_BACKPRESSURE_SLOW_EBGP_V6_PEER_ADDRS),
        min_ratio=1.0,
        description=(
            f"Phase 3.5 wire-per-peer asymmetry gate (2.3.1 CENTRAL CLAIM): "
            f"median IXIA Messages Rx on fast peers must exceed slow peers "
            f"since Phase 0 snapshot on "
            f"{device_name}:{ixia_interface_mimic_ebgp} -- proves DUT drains "
            f"fast independently of slow on the WIRE inside the same UG"
        ),
    )
    return create_ug_backpressure_fast_peers_not_held_back_playbook(
        device_name=device_name,
        ixia_interface=ixia_interface_mimic_ibgp,
        storm_prefix_pool_regex=_BAG013_BACKPRESSURE_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_BAG013_BACKPRESSURE_STORM_DEVICE_GROUP_REGEX,
        storm_prefix_count=_BAG013_BACKPRESSURE_2_3_1_PREFIX_COUNT,
        community_combinations=_bag013_backpressure_heavy_communities_32(),
        extended_community_combinations=_bag013_backpressure_heavy_extended_communities_16(),
        as_path=_bag013_backpressure_heavy_as_path_255(),
        fast_peer_addrs=_BAG013_BACKPRESSURE_FAST_PEER_ADDRS,
        bgp_mon_peer_addrs=_BAG013_BACKPRESSURE_BGP_MON_PEER_ADDRS,
        iBGP_receiver_peer_addrs=_BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS,
        slow_ebgp_peer_addrs=_BAG013_BACKPRESSURE_SLOW_EBGP_V6_PEER_ADDRS,
        expected_established_sessions=_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_BAG013_BACKPRESSURE_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        setup_steps=[slow_peer_throttle_setup, _per_peer_wire_snapshot],
        stage_2_extra_steps=[_per_peer_wire_verify],
        enable_fast_peer_ixia_wire_check=True,
        fast_peer_ixia_interface=ixia_interface_mimic_ebgp,
    )


def _bag013_backpressure_pb_2_3_2(
    *,
    device_name: str,
    ixia_interface_mimic_ibgp: str,
) -> taac_types.Playbook:
    return create_ug_backpressure_peer_blocks_down_recover_playbook(
        device_name=device_name,
        ixia_interface=ixia_interface_mimic_ibgp,
        storm_prefix_pool_regex=_BAG013_BACKPRESSURE_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_BAG013_BACKPRESSURE_STORM_DEVICE_GROUP_REGEX,
        storm_initial_prefix_count=_BAG013_BACKPRESSURE_2_3_2_INITIAL_PREFIX_COUNT,
        storm_followup_prefix_count=_BAG013_BACKPRESSURE_2_3_2_FOLLOWUP_PREFIX_COUNT,
        community_combinations=_bag013_backpressure_heavy_communities_32(),
        extended_community_combinations=_bag013_backpressure_heavy_extended_communities_16(),
        as_path=_bag013_backpressure_heavy_as_path_255(),
        shutdown_peer_regex=_BAG013_BACKPRESSURE_EBGP_V6_PEER_REGEX,
        shutdown_peer_addrs=_BAG013_BACKPRESSURE_SHUTDOWN_PEER_ADDRS,
        shutdown_count=_BAG013_BACKPRESSURE_2_3_2_SHUTDOWN_COUNT,
        surviving_receiver_peer_addrs=_BAG013_BACKPRESSURE_SURVIVING_RECEIVER_ADDRS,
        surviving_ebgp_receiver_peer_addrs=_BAG013_BACKPRESSURE_SURVIVING_EBGP_RECEIVER_ADDRS,
        surviving_ibgp_receiver_peer_addrs=_BAG013_BACKPRESSURE_SURVIVING_IBGP_RECEIVER_ADDRS,
        expected_established_sessions=_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_BAG013_BACKPRESSURE_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    )


def _bag013_backpressure_pb_2_3_3(
    *,
    device_name: str,
    ixia_interface_mimic_ibgp: str,
) -> taac_types.Playbook:
    return create_ug_backpressure_withdraw_attr_change_playbook(
        device_name=device_name,
        ixia_interface=ixia_interface_mimic_ibgp,
        ibgp_storm_prefix_pool_regex=_BAG013_BACKPRESSURE_STORM_PREFIX_POOL_REGEX,
        ibgp_storm_device_group_regex=_BAG013_BACKPRESSURE_STORM_DEVICE_GROUP_REGEX,
        ibgp_storm_prefix_count=_BAG013_BACKPRESSURE_2_3_3_IBGP_STORM_PREFIX_COUNT,
        community_combinations=_bag013_backpressure_heavy_communities_32(),
        extended_community_combinations=_bag013_backpressure_heavy_extended_communities_16(),
        as_path=_bag013_backpressure_heavy_as_path_255(),
        ebgp_attr_change_prefix_pool_regex=_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_PREFIX_POOL_REGEX,
        ebgp_attr_change_device_group_regex=_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_DEVICE_GROUP_REGEX,
        ebgp_attr_change_prefix_count=_BAG013_BACKPRESSURE_2_3_3_EBGP_ATTR_CHANGE_PREFIX_COUNT,
        withdraw_count=_BAG013_BACKPRESSURE_2_3_3_WITHDRAW_COUNT,
        lp_modify_count=_BAG013_BACKPRESSURE_2_3_3_LP_MODIFY_COUNT,
        initial_community=_BAG013_BACKPRESSURE_2_3_3_INITIAL_COMMUNITY,
        mutated_community=_BAG013_BACKPRESSURE_2_3_3_MUTATED_COMMUNITY,
        target_local_pref=_BAG013_BACKPRESSURE_2_3_3_TARGET_LOCAL_PREF,
        ibgp_receiver_peer_addrs=_BAG013_BACKPRESSURE_IBGP_RECEIVER_PEER_ADDRS,
        expected_established_sessions=_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_BAG013_BACKPRESSURE_MEMORY_THRESHOLD_BYTES,
        skip_community_swap_for_cascade_safety=False,
        use_peer_scoped_community_swap=True,
        ebgp_sender_peer_addr=_BAG013_BACKPRESSURE_EBGP_V6_PEER_ADDRS[0],
    )


def _bag013_backpressure_pb_2_3_4(
    *,
    device_name: str,
    ixia_interface_mimic_ibgp: str,
) -> taac_types.Playbook:
    return create_ug_backpressure_all_peers_block_down_recover_playbook(
        device_name=device_name,
        ixia_interface=ixia_interface_mimic_ibgp,
        storm_prefix_pool_regex=_BAG013_BACKPRESSURE_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_BAG013_BACKPRESSURE_STORM_DEVICE_GROUP_REGEX,
        storm_initial_prefix_count=_BAG013_BACKPRESSURE_2_3_4_INITIAL_PREFIX_COUNT,
        storm_followup_prefix_count=_BAG013_BACKPRESSURE_2_3_4_FOLLOWUP_PREFIX_COUNT,
        community_combinations=_bag013_backpressure_heavy_communities_32(),
        extended_community_combinations=_bag013_backpressure_heavy_extended_communities_16(),
        as_path=_bag013_backpressure_heavy_as_path_255(),
        ebgp_group_dg_regex=_BAG013_BACKPRESSURE_EBGP_ALL_DEVICE_GROUP_REGEX,
        ebgp_peer_addrs=_BAG013_BACKPRESSURE_EBGP_PEER_ADDRS,
        bgp_mon_peer_addrs=_BAG013_BACKPRESSURE_BGP_MON_PEER_ADDRS,
        ibgp_peer_addrs=_BAG013_BACKPRESSURE_IBGP_PEER_ADDRS,
        expected_established_sessions=_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_BAG013_BACKPRESSURE_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    )


def _bag013_backpressure_pb_topology_smoke() -> taac_types.Playbook:
    return create_bgp_ug_backpressure_topology_smoke_playbook(
        expected_established_sessions=_BAG013_BACKPRESSURE_EXPECTED_ESTABLISHED_SESSIONS,
    )


def _bag013_backpressure_build_test_config(
    testbed: Testbed,
    *,
    name: str,
    playbooks: t.List[taac_types.Playbook],
) -> taac_types.TestConfig:
    """Shared topology builder for the two bag013 backpressure factories.

    Encapsulates the setup_tasks / teardown_tasks / basic_port_configs /
    endpoints construction so the two catalog TestConfigs land on the SAME
    topology definition (only the playbook list differs).
    """
    assert testbed.device_name == "bag013.ash6", (
        f"bag013 backpressure factories are Wave 2 hardcoded to bag013.ash6; "
        f"got testbed.device_name={testbed.device_name!r}. Wave 4 will "
        f"parameterize on testbed."
    )
    assert testbed.dut_bgp_as is not None, "Testbed must have dut_bgp_as set"
    assert testbed.bgpcpp_configerator_path is not None, (
        "Testbed must have bgpcpp_configerator_path set for BGP++ deployment"
    )
    assert testbed.openr_configerator_path is not None, (
        "Testbed must have openr_configerator_path set for OpenR deployment"
    )
    assert len(testbed.ixia_ports) >= 3, (
        "Testbed must have >= 3 IXIA ports (eBGP + iBGP + BGP-MON)"
    )

    device_name = testbed.device_name
    ixia_chassis_ip = testbed.ixia_chassis_ip
    ixia_interface_mimic_ebgp, ixia_port_ebgp = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, ixia_port_ibgp = testbed.ixia_ports[1]
    ixia_interface_mimic_bgp_mon, ixia_port_bgp_mon = testbed.ixia_ports[2]

    setup_tasks = get_common_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=_BAG013_BACKPRESSURE_PROFILE,
        openr_configerator_path=testbed.openr_configerator_path,
        openr_port_channel_member=testbed.extras["openr_port_channel_member"],
        openr_port_channel_ipv4=testbed.extras["openr_port_channel_ipv4"],
        openr_port_channel_link_local=testbed.extras["openr_port_channel_link_local"],
        openr_local_link=testbed.extras["openr_local_link"],
        openr_other_link=testbed.extras["openr_other_link"],
        enable_update_group=True,
    )
    teardown_tasks = get_teardown_tasks(
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
    )
    basic_port_configs = _bag013_backpressure_split_ebgp_v6_for_slow_peers(
        create_ebb_scale_basic_port_configs(
            device_name=device_name,
            ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
            ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
            ebgp_peer_count_v6=EBGP_PEER_COUNT_V6,
            ebgp_peer_count_v4=EBGP_PEER_COUNT_V4,
            ebgp_peer_to_drain=EBGP_PEER_TO_DRAIN,
            ibgp_peer_scale_per_plane=IBGP_PEER_SCALE_PER_PLANE,
            ibgp_peer_to_drain_per_plane=IBGP_PEER_TO_DRAIN_PER_PLANE,
            bgp_mon_peer_count=BGP_MON_PEER_COUNT,
            ebgp_remote_as=EBGP_REMOTE_AS,
            ibgp_remote_as=IBGP_REMOTE_AS,
            bgp_mon_remote_as=BGP_MON_REMOTE_AS,
            ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
            ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
            ixia_ibgp_ic_parent_network_v6_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v6_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v6_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v6_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v6_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v6_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v6_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v6_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4,
            ixia_ibgp_ic_parent_network_v4_dc_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
            ixia_ibgp_ic_parent_network_v4_dc_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE2,
            ixia_ibgp_ic_parent_network_v4_dc_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE3,
            ixia_ibgp_ic_parent_network_v4_dc_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE4,
            ixia_ibgp_ic_parent_network_v4_mp_plane1=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE1,
            ixia_ibgp_ic_parent_network_v4_mp_plane2=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE2,
            ixia_ibgp_ic_parent_network_v4_mp_plane3=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE3,
            ixia_ibgp_ic_parent_network_v4_mp_plane4=IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE4,
            ixia_bgp_mon_ic_parent_network=IXIA_BGP_MON_IC_PARENT_NETWORK,
            profile=_BAG013_BACKPRESSURE_PROFILE,
            plane_drain_dg_v6_attribute_overrides={
                1: _bag013_backpressure_storm_dg_v6_attribute_overrides(),
            },
        ),
        slow_peer_count=_BAG013_BACKPRESSURE_EBGP_SLOW_PEER_COUNT_V6,
        slow_dg_name=_BAG013_BACKPRESSURE_SLOW_EBGP_V6_DG_NAME,
    )

    return TestConfig(
        name=name,
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        ixia_config_cache=taac_types.IxiaConfigCache(enabled=False),
        endpoints=[
            Endpoint(
                name=device_name,
                dut=True,
                ixia_ports=[
                    ixia_interface_mimic_ebgp,
                    ixia_interface_mimic_ibgp,
                    ixia_interface_mimic_bgp_mon,
                ],
                direct_ixia_connections=[
                    DirectIxiaConnection(
                        interface=ixia_interface_mimic_ebgp,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_ebgp,
                    ),
                    DirectIxiaConnection(
                        interface=ixia_interface_mimic_ibgp,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_ibgp,
                    ),
                    DirectIxiaConnection(
                        interface=ixia_interface_mimic_bgp_mon,
                        ixia_chassis_ip=ixia_chassis_ip,
                        ixia_port=ixia_port_bgp_mon,
                    ),
                ],
            ),
        ],
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=teardown_tasks,
        basic_port_configs=basic_port_configs,
        playbooks=playbooks,
    )


def create_bgp_ug_backpressure_test_config(
    testbed: Testbed,
    *,
    name: str,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.3.x (Backpressure & Blocking) --
    bag013 conveyor topology. Four playbooks (2.3.1 / 2.3.2 / 2.3.3 / 2.3.4)
    sharing the EBB full-scale topology; ``enable_update_group=True`` hard-
    coded (UG MUST be on for these specs).

    Byte-wise identical to the legacy
    ``bag013_ash6_backpressure_test_config.create_bgp_ug_backpressure_test_config``.
    """
    device_name = testbed.device_name
    ixia_interface_mimic_ebgp, _ = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, _ = testbed.ixia_ports[1]
    playbooks = [
        _bag013_backpressure_pb_2_3_1(
            device_name=device_name,
            ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ),
        _bag013_backpressure_pb_2_3_2(
            device_name=device_name,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ),
        _bag013_backpressure_pb_2_3_3(
            device_name=device_name,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ),
        _bag013_backpressure_pb_2_3_4(
            device_name=device_name,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ),
    ]
    return _bag013_backpressure_build_test_config(
        testbed,
        name=name,
        playbooks=playbooks,
    )


def create_bgp_ug_backpressure_topology_smoke_test_config(
    testbed: Testbed,
    *,
    name: str,
) -> taac_types.TestConfig:
    """Topology-smoke sibling of ``create_bgp_ug_backpressure_test_config``.

    Brings up the full EBB-scale bag013 topology + runs a longevity playbook
    (precheck + 30-min longevity + postcheck) so the operator can hands-on
    probe the device. Designed to be paired with
    ``--skip-teardown-tasks --skip-ixia-cleanup``.

    Byte-wise identical to the legacy
    ``bag013_ash6_backpressure_test_config.create_bgp_ug_backpressure_topology_smoke_test_config``.
    """
    return _bag013_backpressure_build_test_config(
        testbed,
        name=name,
        playbooks=[_bag013_backpressure_pb_topology_smoke()],
    )

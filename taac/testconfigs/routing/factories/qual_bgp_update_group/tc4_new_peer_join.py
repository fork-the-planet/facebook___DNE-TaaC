# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.4 — New Peer Joining a Busy Group. UG qualification testconfig factory.

Byte-wise-identical move from ``testconfigs/routing/factories/bgp_update_group.py``
(pre-Wave-6). See ``playbooks/routing/factories/qual_bgp_update_group/tc4_new_peer_join.py``
for the 3 sub-spec playbook factories (2.4.1 / 2.4.2 / 2.4.3).
"""

import typing as t

from ixia.ixia import types as ixia_types
from taac.constants import BgpPlusPlusProfile
from taac.playbooks.routing.factories.qual_bgp_update_group.tc4_new_peer_join import (
    create_bgp_ug_new_peer_join_attribute_change_playbook,
    create_bgp_ug_new_peer_join_full_sync_resilience_playbook,
    create_bgp_ug_new_peer_join_routes_withdrawn_playbook,
)
from taac.steps.step_definitions import (
    create_ixia_api_step,
    create_longevity_step,
    create_start_stop_bgp_peers_step,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.testconfigs.routing.util.bgp_ebb_constants import (
    EBGP_REMOTE_AS,
    IBGP_REMOTE_AS,
    IXIA_EBGP_IC_PARENT_NETWORK_V6,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
)
from taac.testconfigs.routing.util.bgp_ebb_setup_tasks import (
    get_update_packing_setup_tasks,
)
from taac.test_as_a_config import types as taac_types


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
    "create_bgp_ug_new_peer_join_test_config",
]

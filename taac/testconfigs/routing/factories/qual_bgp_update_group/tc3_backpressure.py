# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.3 — Backpressure and Blocking Behavior. UG qualification testconfig factory.

Byte-wise-identical move from ``testconfigs/routing/factories/bgp_update_group.py``
(pre-Wave-6). Combines the former ``create_bgp_ug_backpressure_test_config``
and ``create_bgp_ug_backpressure_topology_smoke_test_config`` into one
factory switched by ``smoke_only=False`` (default) / ``True``.
"""

import typing as t

from ixia.ixia import types as ixia_types
from neteng.test_infra.dne.taac.constants import BgpPlusPlusProfile, Gigabyte
from taac.playbooks.routing.factories.qual_bgp_update_group.tc3_backpressure import (
    create_bgp_ug_backpressure_all_peers_block_down_recover_playbook,
    create_bgp_ug_backpressure_fast_peers_not_held_back_playbook,
    create_bgp_ug_backpressure_peer_blocks_down_recover_playbook,
    create_bgp_ug_backpressure_topology_smoke_playbook,
    create_bgp_ug_backpressure_withdraw_attr_change_playbook,
)
from taac.steps.step_definitions import (
    create_configure_bgp_peer_tcp_window_size_step,
    create_snapshot_per_peer_bgp_rx_stats_step,
    create_verify_per_peer_bgp_rx_asymmetry_step,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.testconfigs.routing.util.bgp_ebb_constants import (
    BGP_MON_PEER_COUNT,
    BGP_MON_REMOTE_AS,
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
)
from taac.testconfigs.routing.util.bgp_ebb_ixia_config import (
    create_ebb_scale_basic_port_configs,
)
from taac.testconfigs.routing.util.bgp_ebb_setup_tasks import (
    get_common_setup_tasks,
    get_teardown_tasks,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection, Endpoint, TestConfig


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
    return create_bgp_ug_backpressure_fast_peers_not_held_back_playbook(
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
    return create_bgp_ug_backpressure_peer_blocks_down_recover_playbook(
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
    return create_bgp_ug_backpressure_withdraw_attr_change_playbook(
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
    return create_bgp_ug_backpressure_all_peers_block_down_recover_playbook(
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
    smoke_only: bool = False,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.3.x (Backpressure & Blocking) --
    bag013 conveyor topology.

    Default (``smoke_only=False``): four playbooks (2.3.1 / 2.3.2 / 2.3.3 /
    2.3.4) sharing the EBB full-scale topology; ``enable_update_group=True``
    hard-coded (UG MUST be on for these specs). TestConfig ``name`` field
    grandfathered as ``BGP_UG_BACKPRESSURE_TEST``.

    ``smoke_only=True``: brings up the full EBB-scale bag013 topology + runs
    a longevity playbook (precheck + 30-min longevity + postcheck) so the
    operator can hands-on probe the device. Designed to be paired with
    ``--skip-teardown-tasks --skip-ixia-cleanup``. TestConfig ``name`` field
    grandfathered as ``BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE``.

    Byte-wise identical to the legacy
    ``bag013_ash6_backpressure_test_config.create_bgp_ug_backpressure_test_config``
    (and its topology-smoke sibling).
    """
    device_name = testbed.device_name
    ixia_interface_mimic_ebgp, _ = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, _ = testbed.ixia_ports[1]
    if smoke_only:
        return _bag013_backpressure_build_test_config(
            testbed,
            name="BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE",
            playbooks=[_bag013_backpressure_pb_topology_smoke()],
        )
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
        name="BGP_UG_BACKPRESSURE_TEST",
        playbooks=playbooks,
    )

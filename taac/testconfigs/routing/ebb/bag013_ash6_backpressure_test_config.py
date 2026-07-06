# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""BGP++ Update Group "Backpressure & Blocking Behavior" qualification test
config on bag013.ash6 (EBB full-scale: 280 eBGP + 124 iBGP + 2 BGP-MON).

Combines all 4 specs in the 2.3.x series into a single TestConfig
(``BGP_UG_BACKPRESSURE_TEST``) sharing one EBB full-scale testbed:

  2.3.1 ug_backpressure_fast_peers_not_held_back
        -- Fast peers (eBGP + BGP-MON) not held back by slow iBGP receiver
           peers during a heavy-attr 10K-prefix storm.
  2.3.2 ug_backpressure_peer_blocks_down_recover
        -- 16 eBGP go down mid-storm, come back, get full re-sync from
           shadow RIB.
  2.3.3 ug_backpressure_withdraw_attr_change
        -- Withdraw 200 + re-add with new community + LP-modify 100 routes
           under iBGP-storm backpressure.
  2.3.4 ug_backpressure_all_peers_block_down_recover
        -- ALL 280 eBGP simultaneously down (via toggle_device_group_configs on
           the whole DG) + come back, shadow-RIB re-sync.

Topology is the canonical EBB scale provided by ``get_common_setup_tasks()``
+ ``create_ebb_scale_basic_port_configs()``:
  Et3/36/1 -> eBGP receivers (140 V4 + 140 V6 = 280) -- DEVICE_GROUP_IPV6_EBGP
  Et3/36/2 -> iBGP senders (62 per plane x 4 DC + 4 MP planes x V4+V6)
              -- DEVICE_GROUP_IPV6_IBGP_PLANE_N_REMOTE_EB[_DRAIN]
  Et3/36/3 -> BGP-MON (2)

The 2.3 playbook factories (in ``playbook_definitions.py``) are
device-agnostic; this file wires them up with bag013-specific DG regexes,
peer-address lists, expected session counts, and per-playbook prefix
ranges from the shared iBGP-plane-1-drain pool.

Device: bag013.ash6
IXIA Chassis: ares1-my24520014
IXIA Ports:
- Et3/36/1 -> 8/2 (eBGP)
- Et3/36/2 -> 8/3 (iBGP)
- Et3/36/3 -> 8/4 (BGP MON)
"""

from ixia.ixia import types as ixia_types
from neteng.test_infra.dne.taac.constants import BgpPlusPlusProfile, Gigabyte
from taac.playbooks.playbook_definitions import (
    create_bgp_ug_backpressure_topology_smoke_playbook,
    create_ug_backpressure_all_peers_block_down_recover_playbook,
    create_ug_backpressure_fast_peers_not_held_back_playbook,
    create_ug_backpressure_peer_blocks_down_recover_playbook,
    create_ug_backpressure_withdraw_attr_change_playbook,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_common_tasks import (
    get_common_setup_tasks,
    get_teardown_tasks,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_constants import (
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
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ixia_config_for_ebb_scale import (
    create_ebb_scale_basic_port_configs,
)
from taac.steps.step_definitions import (
    create_configure_bgp_peer_tcp_window_size_step,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection, Endpoint, TestConfig


# =============================================================================
# Device-specific configuration for bag013.ash6
# =============================================================================
DEVICE_NAME = "bag013.ash6"
IXIA_CHASSIS_IP = "2401:db00:2066:303b::3001"
BAG013_EOS_BGP_AS = 65013
BGPCPP_CONFIGERATOR_PATH = "taac/ebb_ci_cd_configs/ebb_full_scale_bgpcpp_config"
OPENR_CONFIGERATOR_PATH = "taac/ebb_ci_cd_configs/bag013_ash6_openr_config"

IXIA_INTERFACE_MIMIC_EBGP = "Ethernet3/36/1"
IXIA_INTERFACE_MIMIC_IBGP = "Ethernet3/36/2"
IXIA_INTERFACE_MIMIC_BGP_MON = "Ethernet3/36/3"

IXIA_PORT_EBGP = "8/2"
IXIA_PORT_IBGP = "8/3"
IXIA_PORT_BGP_MON = "8/4"

# Must match bag013's BGP_PLUS_PLUS_WITH_OPEN_R DEFAULT_PROFILE -- the EBB-scale
# IXIA topology setup expects OpenR-related configerator paths on bag013.
# Using WITHOUT_OPEN_R caused a deterministic ConfigeratorMissingConfigException
# on Et3/36/1 (eBGP port) during topology setup (3 retries all hit the same
# failure point in 37 min each). bag013_ash6_test_config.py uses
# DEFAULT_PROFILE = BGP_PLUS_PLUS_WITH_OPEN_R -- same here.
PROFILE = BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R


# =============================================================================
# Topology constants (EBB scale -- reuses the iBGP-plane-1-drain pool as the
# heavy-attr storm source, same pool that bag010 attribute_churn uses).
# =============================================================================
# iBGP storm sender (the "fast" pool that drives the heavy-attr 10K storm).
# IBGP plane 1 V6 drain pool is the canonical EBB-scale "rogue route source"
# (per `create_bag010_ash6_bgp_instability_attribute_churn_playbook`).
_STORM_PREFIX_POOL_REGEX = "PREFIX_POOL_IBGP_IPV6_PLANE_1_REMOTE_EB_DRAIN"
_STORM_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV6_IBGP_PLANE_1_REMOTE_EB_DRAIN"

# eBGP fan-out receivers (the 280 "fast" peers in 2.3.1 / shut targets in
# 2.3.2 + 2.3.4). EBB scale builds these as a single DG per AFI on Et3/36/1.
_EBGP_V6_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV6_EBGP"
_EBGP_V6_PEER_REGEX = "BGP_PEER_IPV6_EBGP"
# 2.3.4's "ALL 280" trigger -- one DG name regex matches BOTH V4 + V6 eBGP DGs.
_EBGP_ALL_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV[46]_EBGP$"

# BGP-MON peer regex (the "smaller separate group" called out in 2.3.1 + 2.3.4).
# Note: bag013 BGP_MON peers may stay IDLE per `_bag013_2_7_2_prechecks`
# project notes -- verified at smoke time. If IDLE on this device, 2.3.1's
# BGP_MON-liveness check needs to be skipped (or the device swapped).
_BGP_MON_PEER_REGEX = "BGP_PEER_IPV6_BGPMON"

# Total expected ESTABLISHED sessions on bag013 EBB full-scale.
# bgpcpp configures 1274 peers total = 280 eBGP (140 V4 + 140 V6) + 992 iBGP
# (62/plane * 8 planes * 2 AFIs) + 2 BGP_MON -- confirmed via thrift probe
# of bag013 2026-06-25. BGP_MON peers stay IDLE on bag013 (known device
# quirk per 2.7.2 notes), so the count of peers that actually reach
# Established is 1274 - 2 = 1272.
_TOTAL_CONFIGURED_PEERS = (
    EBGP_PEER_COUNT_V6
    + EBGP_PEER_COUNT_V4
    + IBGP_PEER_SCALE_PER_PLANE * 8 * 2
    + BGP_MON_PEER_COUNT
)
_EXPECTED_ESTABLISHED_SESSIONS = _TOTAL_CONFIGURED_PEERS - BGP_MON_PEER_COUNT

# Spec values
_MEMORY_THRESHOLD_BYTES = Gigabyte.GIG_10.value  # spec: VmHWM below 10GB
_LOAD_AVG_BASELINE = 12.0  # spec: 1m/5m/15m < 12 (2.3.1)


# =============================================================================
# Heavy-attribute pool definitions (32 communities + 16 ext-communities +
# 255-ASN AS_PATH per spec 2.3.x). Every slot pairs the ``EB-FA-OUT`` permit-
# anchor community with a heavy variation so DUT eBGP egress policy accepts
# the storm routes and re-advertises them to fast peers -- otherwise the
# spec's central "fast peers receive N storm prefixes / not held back by
# slow peers" mechanic is unobservable on this testbed (bag013's EB-FA-OUT
# policy drops routes whose communities don't match the permit list; see
# `tcp_socket_experiment/constants.py:296` for the enumerated permit
# communities and [[feedback-bag013-ebb-topology-facts]] for the observed
# storm-blocked pattern from Runs #11-#13).
# =============================================================================
_EB_FA_OUT_PERMIT_COMMUNITY = "65531:50300"  # AS32934_AGGREGATE_GLOBAL


def _heavy_communities_32() -> list:
    """Return 32 community combinations -- each slot carries the EB-FA-OUT
    permit-anchor community plus one heavy variation, satisfying both the
    spec's "32 random BGP Communities (vary per route)" and bag013's
    outbound-policy constraint that storm routes must include a permitted
    community to reach eBGP fast peers on the wire."""
    return [[_EB_FA_OUT_PERMIT_COMMUNITY, f"65529:{30000 + i}"] for i in range(32)]


def _heavy_extended_communities_16() -> list:
    """Return 16 extended-community combinations.

    IXIA ext-community format: ``"<type>:<as>:<value>"``. Using rt:65529:<i>
    (Route Target) is the most universal extended-community shape.
    """
    return [[f"rt:65529:{40000 + i}"] for i in range(16)]


def _heavy_as_path_255() -> list:
    """255-ASN AS_SEQ -- spec '255 random ASNs'. Using deterministic ASNs
    in the private range (64512-65534) for reproducibility; the
    'random' part of the spec is about scale not entropy.

    NOTE (2026-06-29): currently unused at runtime. The trigger-time
    `configure_as_path_pool` step is omitted because IXIA's pool-config
    APIs call `stop_protocols()` unconditionally and cascade-reset every
    BGP TCP session on the chassis (root cause traced in bgpcpp logs on
    2026-06-29; see [[project-bgp-ug-backpressure-validation-matrix]]).
    The `BgpAttribute` thrift enum doesn't expose AS_PATH for build-time
    pre-config (only COMMUNITIES + EXT_COMMUNITIES), so the 255-ASN
    AS_PATH spec aspect is dropped until that hazard is fixed at the
    framework level. Kept here for spec-traceability and for a future
    re-enable path.
    """
    return [64512 + (i % 1023) for i in range(255)]


def _storm_dg_v6_attribute_overrides() -> list:
    """Inline BgpAttributeConfig overrides for the iBGP plane-1 V6 drain DG
    (the canonical "heavy-attr storm sender" in 2.3.x). Replaces the default
    CSV-driven community config with 32 community combinations + 16
    extended-community combinations baked into the IXIA topology at build
    time -- so the 2.3.x trigger sequences DO NOT need to call
    `configure_community_pool` / `configure_extended_community_pool` at
    runtime (those calls invoke `stop_protocols()` unconditionally inside
    ixia.py and tear down every BGP TCP session on the chassis -- root cause
    diagnosed 2026-06-29 from bgpcpp logs).
    """
    return [
        ixia_types.BgpAttributeConfig(
            attribute=ixia_types.BgpAttribute.COMMUNITIES,
            value_lists=_heavy_communities_32(),
            distribution_type=ixia_types.DistribitionType.ROUND_ROBIN,
        ),
        ixia_types.BgpAttributeConfig(
            attribute=ixia_types.BgpAttribute.EXT_COMMUNITIES,
            value_lists=_heavy_extended_communities_16(),
            distribution_type=ixia_types.DistribitionType.ROUND_ROBIN,
        ),
    ]


# =============================================================================
# Peer-address helpers
# =============================================================================
# For the 4 playbook factories we need peer-address lists. The EBB scale
# topology assigns addresses programmatically via
# `_generate_ixia_v6_peer_entries_for_bgpcpp`. We don't need EXACT addresses
# for the spec gates (the route-set-equality HC pulls them dynamically via
# getBgpSessions); we just need a representative list of "fast" / "slow" /
# "BGP-MON" sets.
#
# Strategy: for v1 we pass empty lists for the per-peer-addr params and
# require the playbook factories to use peer-regex-based equivalents.
# (The HCs default to "all Established sessions on the device" when no
# explicit address list is given.) v2 may switch to explicit address lists
# once we've smoked the topology and know the resolved IXIA peer IPs.
def _peer_addr(parent: str, idx: int) -> str:
    """Derive IXIA-side peer address (idx-th, 0-based) for a given parent network.

    Matches `_generate_ixia_v6_peer_entries_for_bgpcpp` arithmetic
    (start_offset=0x10, stride=2): IXIA peer at parent::{0x11+2*idx:x}.
    """
    return f"{parent}::{0x11 + 2 * idx:x}"


# eBGP V6 receivers (140 peers; for 2.3.1 "fast" + 2.3.2 shut target).
_EBGP_V6_PEER_ADDRS = [
    _peer_addr(IXIA_EBGP_IC_PARENT_NETWORK_V6, i) for i in range(EBGP_PEER_COUNT_V6)
]
# BGP-MON V6 peers -- TODO(2.3-v2): bag013's BGP_MON peers stay IDLE per a
# device-specific config quirk (see ``_bag013_2_7_2_prechecks`` notes), so the
# 2.3.1 BGP_MON liveness check + 2.3.4 BGP_MON-unaffected check can't run on
# bag013 today. The playbook factories accept empty lists and skip the
# BGP_MON checks gracefully. Re-enable when BGP_MON is fixed on bag013 OR
# when the test config is ported to bag010/bag011 (where BGP_MON works).
_BGP_MON_PEER_ADDRS: list = []
# iBGP receivers (plane 2 V6 = 62 peers; plane 1 is the storm sender so excluded).
_IBGP_RECEIVER_PEER_ADDRS = [
    _peer_addr(IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2, i)
    for i in range(IBGP_PEER_SCALE_PER_PLANE)
]
# iBGP peers used for 2.3.4 "iBGP unaffected" gate. Uses plane-2 V6 only (62
# peers) -- plane-1 is the storm SENDER and doesn't necessarily receive routes
# back, so checking route-set-equality on plane-1 would false-positive.
# TODO(2.3-v2): expand to all 7 non-sender planes (434 peers) once we confirm
# all iBGP plane-NOT-1 peers reliably receive the full UG-redistributed set.
_IBGP_PEER_ADDRS = list(_IBGP_RECEIVER_PEER_ADDRS)

# 2.3.1: "fast peers" vs "slow peers" split within the eBGP UG.
# IXIA peers otherwise drain at line rate -> DUT never backpressures ->
# spec 2.3.1 asymmetry claim untestable. We carve the last EBGP_SLOW_PEER_COUNT_V6
# eBGP addresses into a separate DEVICE_GROUP_IPV6_EBGP_SLOW DG whose TCP
# WindowSize is reduced (see _pb_2_3_1() setup step + _split_ebgp_v6_for_slow_peers
# helper), which induces natural adj-RIB-out backpressure on those peers only.
# All 140 addresses remain in the same DUT eBGP peer-group / same UG on DUT
# (per-address enumerated in bgpcpp config).
EBGP_SLOW_PEER_COUNT_V6 = 20
_FAST_EBGP_V6_PEER_ADDRS = list(
    _EBGP_V6_PEER_ADDRS[: EBGP_PEER_COUNT_V6 - EBGP_SLOW_PEER_COUNT_V6]
)
_SLOW_EBGP_V6_PEER_ADDRS = list(
    _EBGP_V6_PEER_ADDRS[EBGP_PEER_COUNT_V6 - EBGP_SLOW_PEER_COUNT_V6 :]
)
_SLOW_EBGP_V6_DG_NAME = "DEVICE_GROUP_IPV6_EBGP_SLOW"
_SLOW_EBGP_V6_TCP_WINDOW_BYTES = (
    1500  # ~ 1 MTU: forces DUT flow-control on every UPDATE
)

# 2.3.1 fast/slow gates use these two lists (asymmetry proven inside same UG).
_FAST_PEER_ADDRS = _FAST_EBGP_V6_PEER_ADDRS
# 2.3.2: shut first 16 eBGP V6; survivors = rest of eBGP + iBGP receivers.
# BGP_MON excluded (bag013 BGP_MON IDLE quirk, see _BGP_MON_PEER_ADDRS TODO).
# PB2/3/4 use FAST eBGP peers only (excluding the TCP-throttled SLOW subset,
# which is a PB1-specific spec-loyalty mechanism). Including slow peers in
# equality gates for other playbooks breaks them because slow peers can't
# keep up with the same route set within bounded time (Run #31 finding).
_EBGP_V6_PEER_ADDRS_NO_SLOW = _FAST_EBGP_V6_PEER_ADDRS  # 120 peers, indices 0..119
_SHUTDOWN_PEER_ADDRS = list(_EBGP_V6_PEER_ADDRS_NO_SLOW[:16])
# Mixed list retained for the legacy playbook arg; the new split params below
# are what the Phase 4 + Phase 6 equality gates actually use.
_SURVIVING_RECEIVER_ADDRS = _EBGP_V6_PEER_ADDRS_NO_SLOW[16:] + _IBGP_RECEIVER_PEER_ADDRS
_SURVIVING_EBGP_RECEIVER_ADDRS = list(_EBGP_V6_PEER_ADDRS_NO_SLOW[16:])
_SURVIVING_IBGP_RECEIVER_ADDRS = list(_IBGP_RECEIVER_PEER_ADDRS)
# 2.3.4: all 280 eBGP (V6 only for v1; V4 added in v2 if needed)
_EBGP_PEER_ADDRS = list(_EBGP_V6_PEER_ADDRS_NO_SLOW)


# =============================================================================
# Per-playbook spec parameters
# =============================================================================
# Per-PB spec scales -- restored from dial-down on 2026-06-26.
# PB1 / PB4 spec = 10K, PB2 / PB3 spec = 5K. Earlier 10K runs collapsed
# IXIA-side BGP emulator on bag013 (1272 sessions went IDLE under heavy-attr
# storm + withdraw). Validation runs at scale=1000 were also blocked by an
# IXIA-side topology issue on bag013 (BGP peers never reached Established
# after IXIA session creation). Recommend re-attempting these at spec scale
# only after bag013's IXIA-side BGP topology is stable -- see project notes.

# 2.3.1 (spec: 10K)
_2_3_1_PREFIX_COUNT = 10000

# 2.3.2 (spec: 5K + 500)
_2_3_2_INITIAL_PREFIX_COUNT = 5000
_2_3_2_FOLLOWUP_PREFIX_COUNT = 500
_2_3_2_SHUTDOWN_COUNT = 16

# 2.3.3 (spec: 5K storm + 200 withdraw/re-add + 100 LP-modify)
_2_3_3_IBGP_STORM_PREFIX_COUNT = 5000
_2_3_3_EBGP_ATTR_CHANGE_PREFIX_COUNT = 400  # 200 withdraw + 100 LP-modify + 100 spare
_2_3_3_WITHDRAW_COUNT = 200
_2_3_3_LP_MODIFY_COUNT = 100
_2_3_3_INITIAL_COMMUNITY = "65529:34814"
# NOTE: 16-bit constraint — BGP RFC 1997 community low field is 16 bits
# (0..65535). IXIA silently truncates writes above 65535 (e.g. 99999 →
# 99999 mod 65536 = 34463), which then lands on the wire as an unexpected
# value that breaks the community-anchor HC. Keep both parts within 16-bit
# range. Proven via community_swap_probe live-session diagnostics 2026-06-30.
_2_3_3_MUTATED_COMMUNITY = "65529:1234"
_2_3_3_TARGET_LOCAL_PREF = 200  # spec: from default 100 to 200
_2_3_3_EBGP_ATTR_PREFIX_POOL_REGEX = "PREFIX_POOL_IPV6_EBGP"
_2_3_3_EBGP_ATTR_DEVICE_GROUP_REGEX = "DEVICE_GROUP_IPV6_EBGP"

# 2.3.4 (spec: 10K + 500)
_2_3_4_INITIAL_PREFIX_COUNT = 10000
_2_3_4_FOLLOWUP_PREFIX_COUNT = 500


# =============================================================================
# Per-playbook builders
# =============================================================================
def _split_ebgp_v6_for_slow_peers(
    port_configs: list,
    slow_peer_count: int,
    slow_dg_name: str,
) -> list:
    """Post-process the port_configs returned by
    ``create_ebb_scale_basic_port_configs`` to carve the LAST
    ``slow_peer_count`` peers of ``DEVICE_GROUP_IPV6_EBGP`` into a new
    ``DEVICE_GROUP_IPV6_EBGP_SLOW`` DG. Both DGs point at the SAME DUT
    peer-group (per-address enumerated on bag013 bgpcpp; no COOP change
    needed to accept the split), so they land in the same UG on DUT.
    A post-IXIA-setup step (see ``_pb_2_3_1`` setup_steps) reduces the
    slow DG's TCP WindowSize to induce natural DUT adj-RIB-out backpressure
    on ONLY those peers -- letting the 2.3.1 fast/slow asymmetry claim be
    tested rigorously inside the same UG.
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
                # traffic_generator._build_bgp_peer_config defaults
                # remote_peer_starting_ip to v6_addresses_config.gateway_starting_ip
                # WITHOUT applying start_index offset (see
                # traffic_generator.py:688). Without overriding here, the
                # slow DG's BGP peers try to peer with DUT gateway ::10..::12
                # (fast DG's DUTs) instead of ::100..::112. Overriding
                # remote_peer_starting_ip + local_peer_starting_ip to the
                # correct shifted values makes the slow peers actually reach
                # DUT peer entries at the right addresses.
                _parent = IXIA_EBGP_IC_PARENT_NETWORK_V6
                # Shift-into-hextet safety: the slow peers occupy addresses
                # ``_parent::(0x10 + 2*fast_count) .. (0x0f + 2*(fast_count +
                # slow_peer_count))``. On bag013 that's fast_count=120,
                # slow_peer_count=20 -> range 0x100..0x127 (single hextet,
                # same /64 as fast DG's 0x10..0xf1). The bag013 DUT has
                # peer entries provisioned across that range (validated by
                # Run #39 4/4 PASS). The single-hextet capacity is 0xFFFF,
                # so this scheme supports up to ~32760 total eBGP peers on
                # this parent before an address would spill into the next
                # hextet and desync with the DUT's flat /64 peer plan.
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


def _pb_2_3_1() -> taac_types.Playbook:
    # Setup: throttle the SLOW eBGP DG's TCP WindowSize to induce natural
    # DUT adj-RIB-out backpressure on those 20 peers only. Runs once after
    # IXIA setup completes; the wrapper writes to Ethernet.Tcp directly
    # (no stop_protocols cascade). Effect persists across all subsequent
    # storm/withdraw cycles in this playbook.
    slow_peer_throttle_setup = create_configure_bgp_peer_tcp_window_size_step(
        hostname=DEVICE_NAME,
        interface=IXIA_INTERFACE_MIMIC_EBGP,
        device_group_regex=f"^{_SLOW_EBGP_V6_DG_NAME}$",
        tcp_window_size_bytes=_SLOW_EBGP_V6_TCP_WINDOW_BYTES,
        description=(
            f"Setup (2.3.1): throttle TCP WindowSize="
            f"{_SLOW_EBGP_V6_TCP_WINDOW_BYTES} on {_SLOW_EBGP_V6_DG_NAME} "
            f"({EBGP_SLOW_PEER_COUNT_V6} slow eBGP peers) to induce DUT "
            f"adj-RIB-out backpressure -- required for spec 2.3.1 "
            f"fast/slow asymmetry to be exercised on IXIA testbeds where "
            f"peers otherwise drain at line rate."
        ),
    )
    return create_ug_backpressure_fast_peers_not_held_back_playbook(
        device_name=DEVICE_NAME,
        ixia_interface=IXIA_INTERFACE_MIMIC_IBGP,
        storm_prefix_pool_regex=_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_STORM_DEVICE_GROUP_REGEX,
        storm_prefix_count=_2_3_1_PREFIX_COUNT,
        community_combinations=_heavy_communities_32(),
        extended_community_combinations=_heavy_extended_communities_16(),
        as_path=_heavy_as_path_255(),
        fast_peer_addrs=_FAST_PEER_ADDRS,
        bgp_mon_peer_addrs=_BGP_MON_PEER_ADDRS,
        iBGP_receiver_peer_addrs=_IBGP_RECEIVER_PEER_ADDRS,
        slow_ebgp_peer_addrs=_SLOW_EBGP_V6_PEER_ADDRS,
        expected_established_sessions=_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        setup_steps=[slow_peer_throttle_setup],
        # Re-enable IXIA wire check in COLUMN-DISCOVERY mode. Wrapper
        # now logs all IxNetwork view columns on snapshot so we can find
        # a counter that includes keepalives (Rx Updates alone was 0
        # delta on bag013 due to EB-FA-OUT filtering). Once we identify
        # a working counter, the check becomes spec-loyal wire-side
        # observability on bag013 too.
        enable_fast_peer_ixia_wire_check=True,
        fast_peer_ixia_interface=IXIA_INTERFACE_MIMIC_EBGP,
    )


def _pb_2_3_2() -> taac_types.Playbook:
    return create_ug_backpressure_peer_blocks_down_recover_playbook(
        device_name=DEVICE_NAME,
        ixia_interface=IXIA_INTERFACE_MIMIC_IBGP,
        storm_prefix_pool_regex=_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_STORM_DEVICE_GROUP_REGEX,
        storm_initial_prefix_count=_2_3_2_INITIAL_PREFIX_COUNT,
        storm_followup_prefix_count=_2_3_2_FOLLOWUP_PREFIX_COUNT,
        community_combinations=_heavy_communities_32(),
        extended_community_combinations=_heavy_extended_communities_16(),
        as_path=_heavy_as_path_255(),
        shutdown_peer_regex=_EBGP_V6_PEER_REGEX,
        shutdown_peer_addrs=_SHUTDOWN_PEER_ADDRS,
        shutdown_count=_2_3_2_SHUTDOWN_COUNT,
        surviving_receiver_peer_addrs=_SURVIVING_RECEIVER_ADDRS,
        surviving_ebgp_receiver_peer_addrs=_SURVIVING_EBGP_RECEIVER_ADDRS,
        surviving_ibgp_receiver_peer_addrs=_SURVIVING_IBGP_RECEIVER_ADDRS,
        expected_established_sessions=_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    )


def _pb_2_3_3() -> taac_types.Playbook:
    return create_ug_backpressure_withdraw_attr_change_playbook(
        device_name=DEVICE_NAME,
        ixia_interface=IXIA_INTERFACE_MIMIC_IBGP,
        ibgp_storm_prefix_pool_regex=_STORM_PREFIX_POOL_REGEX,
        ibgp_storm_device_group_regex=_STORM_DEVICE_GROUP_REGEX,
        ibgp_storm_prefix_count=_2_3_3_IBGP_STORM_PREFIX_COUNT,
        community_combinations=_heavy_communities_32(),
        extended_community_combinations=_heavy_extended_communities_16(),
        as_path=_heavy_as_path_255(),
        ebgp_attr_change_prefix_pool_regex=_2_3_3_EBGP_ATTR_PREFIX_POOL_REGEX,
        ebgp_attr_change_device_group_regex=_2_3_3_EBGP_ATTR_DEVICE_GROUP_REGEX,
        ebgp_attr_change_prefix_count=_2_3_3_EBGP_ATTR_CHANGE_PREFIX_COUNT,
        withdraw_count=_2_3_3_WITHDRAW_COUNT,
        lp_modify_count=_2_3_3_LP_MODIFY_COUNT,
        initial_community=_2_3_3_INITIAL_COMMUNITY,
        mutated_community=_2_3_3_MUTATED_COMMUNITY,
        target_local_pref=_2_3_3_TARGET_LOCAL_PREF,
        ibgp_receiver_peer_addrs=_IBGP_RECEIVER_PEER_ADDRS,
        expected_established_sessions=_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_MEMORY_THRESHOLD_BYTES,
        # Re-enable Phase 2c community swap via the cascade-safe peer-scoped
        # path (D110214929: IxiaModifyBgpPrefixesCommunities + community_values).
        # Only flaps the eBGP peer owning the attr-change prefix pool — does
        # NOT cascade chassis-wide. Restores the community-mutation aspect of
        # spec 2.3.3 + re-enables the BGP_RECEIVED_ROUTE_COMMUNITY_CHECK
        # postcheck.
        skip_community_swap_for_cascade_safety=False,
        use_peer_scoped_community_swap=True,
        # Trigger-verification probe: the inline Phase 3 gate queries DUT's
        # adj-RIB-IN for THIS sender peer (the eBGP peer that owns the
        # attr-change pool the wrapper mutates) and asserts the mutated
        # community arrived on the wire. Isolates wrapper correctness from
        # downstream UG-replication latency.
        ebgp_sender_peer_addr=_EBGP_V6_PEER_ADDRS[0],
    )


def _pb_2_3_4() -> taac_types.Playbook:
    return create_ug_backpressure_all_peers_block_down_recover_playbook(
        device_name=DEVICE_NAME,
        ixia_interface=IXIA_INTERFACE_MIMIC_IBGP,
        storm_prefix_pool_regex=_STORM_PREFIX_POOL_REGEX,
        storm_device_group_regex=_STORM_DEVICE_GROUP_REGEX,
        storm_initial_prefix_count=_2_3_4_INITIAL_PREFIX_COUNT,
        storm_followup_prefix_count=_2_3_4_FOLLOWUP_PREFIX_COUNT,
        community_combinations=_heavy_communities_32(),
        extended_community_combinations=_heavy_extended_communities_16(),
        as_path=_heavy_as_path_255(),
        ebgp_group_dg_regex=_EBGP_ALL_DEVICE_GROUP_REGEX,
        ebgp_peer_addrs=_EBGP_PEER_ADDRS,
        bgp_mon_peer_addrs=_BGP_MON_PEER_ADDRS,
        ibgp_peer_addrs=_IBGP_PEER_ADDRS,
        expected_established_sessions=_EXPECTED_ESTABLISHED_SESSIONS,
        memory_threshold_bytes=_MEMORY_THRESHOLD_BYTES,
        storm_sender_peer_addr_prefix=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    )


# =============================================================================
# TestConfig factory
# =============================================================================
def create_bgp_ug_backpressure_test_config() -> taac_types.TestConfig:
    """Return the BGP++ UG Backpressure TestConfig on bag013.ash6 -- 4 playbooks
    (2.3.1 / 2.3.2 / 2.3.3 / 2.3.4) sharing the EBB full-scale topology.
    ``enable_update_group=True`` hard-coded (UG MUST be on for these specs).
    """
    setup_tasks = get_common_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG013_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ixia_interface_mimic_bgp_mon=IXIA_INTERFACE_MIMIC_BGP_MON,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=PROFILE,
        openr_configerator_path=OPENR_CONFIGERATOR_PATH,
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
        enable_update_group=True,
    )
    teardown_tasks = get_teardown_tasks(
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ixia_interface_mimic_bgp_mon=IXIA_INTERFACE_MIMIC_BGP_MON,
    )

    return TestConfig(
        name="BGP_UG_BACKPRESSURE_TEST",
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        # Opt out of IXIA topology cache (both Tier 1 chassis-local and Tier 2
        # Manifold). For 1274-peer EBB scale on bag013 a cache-restored session
        # can leave protocols in a partially-Established state after
        # verify_protocols() succeeds against a stale snapshot. Forcing cold
        # setup gives a deterministic baseline at the cost of ~10-15 min on
        # first run; subsequent runs in the same session still benefit from
        # --skip-ixia-setup if needed.
        ixia_config_cache=taac_types.IxiaConfigCache(enabled=False),
        endpoints=[
            Endpoint(
                name=DEVICE_NAME,
                dut=True,
                ixia_ports=[
                    IXIA_INTERFACE_MIMIC_EBGP,
                    IXIA_INTERFACE_MIMIC_IBGP,
                    IXIA_INTERFACE_MIMIC_BGP_MON,
                ],
                direct_ixia_connections=[
                    DirectIxiaConnection(
                        interface=IXIA_INTERFACE_MIMIC_EBGP,
                        ixia_chassis_ip=IXIA_CHASSIS_IP,
                        ixia_port=IXIA_PORT_EBGP,
                    ),
                    DirectIxiaConnection(
                        interface=IXIA_INTERFACE_MIMIC_IBGP,
                        ixia_chassis_ip=IXIA_CHASSIS_IP,
                        ixia_port=IXIA_PORT_IBGP,
                    ),
                    DirectIxiaConnection(
                        interface=IXIA_INTERFACE_MIMIC_BGP_MON,
                        ixia_chassis_ip=IXIA_CHASSIS_IP,
                        ixia_port=IXIA_PORT_BGP_MON,
                    ),
                ],
            ),
        ],
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=teardown_tasks,
        basic_port_configs=_split_ebgp_v6_for_slow_peers(
            create_ebb_scale_basic_port_configs(
                device_name=DEVICE_NAME,
                ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_interface_mimic_bgp_mon=IXIA_INTERFACE_MIMIC_BGP_MON,
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
                profile=PROFILE,
                # Pre-attach 32 community + 16 ext-community combos to the iBGP
                # plane-1 V6 drain DG (the storm sender). PB triggers then advertise
                # without ever calling configure_*_pool, avoiding the chassis-wide
                # TCP cascade.
                plane_drain_dg_v6_attribute_overrides={
                    1: _storm_dg_v6_attribute_overrides(),
                },
            ),
            slow_peer_count=EBGP_SLOW_PEER_COUNT_V6,
            slow_dg_name=_SLOW_EBGP_V6_DG_NAME,
        ),
        playbooks=[_pb_2_3_1(), _pb_2_3_2(), _pb_2_3_3(), _pb_2_3_4()],
    )


BGP_UG_BACKPRESSURE_TEST_CONFIG = create_bgp_ug_backpressure_test_config()


# =============================================================================
# Topology-smoke sibling TestConfig -- brings up the full EBB-scale topology +
# sits on a longevity step so the IXIA session + DUT bgpcpp stay live for
# hands-on inspection. Used to verify peer establishment, baseline route
# counts in FIB/RIB, and BGP-MON liveness (or surface the bag013 IDLE-MON
# quirk) BEFORE running the heavier 4-playbook BGP_UG_BACKPRESSURE_TEST.
#
# Recommended launch:
#   buck2 run fbcode//neteng/netcastle:netcastle_taac -- \
#       --team taac --test-config BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE \
#       --skip-teardown --skip-ixia-cleanup
#
# After the run, both DUT bgpcpp + IXIA topology stay live -- ssh into
# bag013.ash6 to inspect FIB/RIB / `show bgp ipv6 unicast summary | json` /
# `show bgpcpp update-group` / etc.
# =============================================================================


def _pb_topology_smoke() -> taac_types.Playbook:
    """Thin wrapper around the topology-smoke factory in playbook_definitions.py
    (which is where every Playbook factory lives per the no-inline-construction
    gate test)."""
    return create_bgp_ug_backpressure_topology_smoke_playbook(
        expected_established_sessions=_EXPECTED_ESTABLISHED_SESSIONS,
    )


def create_bgp_ug_backpressure_topology_smoke_test_config() -> taac_types.TestConfig:
    """Topology-smoke sibling TestConfig -- reuses the full EBB-scale
    topology + setup_tasks of ``BGP_UG_BACKPRESSURE_TEST`` but runs only the
    smoke (precheck + 30-min longevity + postcheck) playbook. Designed to be
    paired with ``--skip-teardown --skip-ixia-cleanup`` so the testbed stays
    live after the playbook for hands-on probing.
    """
    # Reuse the module-level built config instead of re-invoking the factory
    # at import time (which would build the same TestConfig twice per import).
    base = BGP_UG_BACKPRESSURE_TEST_CONFIG
    # Build a new TestConfig with the same testbed but ONLY the smoke playbook.
    return TestConfig(
        name="BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE",
        skip_ixia_protocol_verification=base.skip_ixia_protocol_verification,
        log_collection_timeout=base.log_collection_timeout,
        basset_pool=base.basset_pool,
        endpoints=base.endpoints,
        host_os_type_map=base.host_os_type_map,
        startup_checks=base.startup_checks,
        setup_tasks=base.setup_tasks,
        teardown_tasks=base.teardown_tasks,
        basic_port_configs=base.basic_port_configs,
        ixia_config_cache=base.ixia_config_cache,
        playbooks=[_pb_topology_smoke()],
    )


BGP_UG_BACKPRESSURE_TOPOLOGY_SMOKE_CONFIG = (
    create_bgp_ug_backpressure_topology_smoke_test_config()
)

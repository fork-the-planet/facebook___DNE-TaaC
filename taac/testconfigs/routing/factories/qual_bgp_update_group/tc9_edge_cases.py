# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.9 — Edge Cases and Adversarial Scenarios. UG qualification testconfig factory.

Bundles the section-2.9 edge-case playbooks onto one shared EBB-scale
conveyor topology (one IXIA setup, one catalog constant), selected at run
time via ``--regex 'bgp_ug_<usecase>'``. Only 2.9.7 (empty group) is REAL
today; the other sub-specs (2.9.1 / 2.9.2 / 2.9.3 / 2.9.4 / 2.9.6) land
incrementally as their playbook factories in
``playbooks/routing/factories/qual_bgp_update_group/tc9_edge_cases.py`` are
implemented, each added to the ``playbooks=[...]`` list below. Spec 2.9.5 is
excluded (struck through in the plan).

Target testbed: BAG011_ASH6 (EBB conveyor node). Reuses the shared
``build_bag_conveyor_test_config`` builder from tc1 for the full-scale
topology (140 eBGP + ~500 iBGP, ``WITHOUT_OPEN_R``, ``include_bgp_mon=False``
— UG qualification never exercises BGP-MON or OpenR).
"""

from neteng.test_infra.dne.taac.constants import BgpPlusPlusProfile, Gigabyte
from taac.health_checks.healthcheck_definitions import (
    create_bgp_session_establish_check,
    create_bgp_update_group_check,
    create_cpu_utilization_check,
    create_drain_state_check,
    create_memory_utilization_check,
)
from taac.playbooks.routing.factories.qual_bgp_update_group.tc9_edge_cases import (
    create_bgp_ug_empty_group_playbook,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc1_distribution_correctness import (
    build_bag_conveyor_test_config,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.testconfigs.routing.util.bgp_ebb_constants import (
    IXIA_BGP_MON_IC_PARENT_NETWORK,
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
    PEERGROUP_EBGP_V6,
    PEERGROUP_IBGP_V6,
)
from taac.test_as_a_config import types as taac_types


# =============================================================================
# BGP UG edge cases (spec 2.9) — bag011 conveyor topology.
# =============================================================================

# BGP-peer-name regexes that select every eBGP / iBGP peer built by
# ``create_ebb_scale_basic_port_configs`` (see bgp_ebb_ixia_config.py). The
# playbook empties / recovers the update groups by STOPPING and STARTING these
# peers' BGP sessions (``start_bgp_peers``), NOT by toggling their DeviceGroups
# -- toggling de-materializes the IXIA-imported eBGP route ranges so recovery
# would advertise nothing (see the playbook's ``_flap_bgp_peers`` docstring).
# Matched with ``re.search`` against the BGP-peer name; the trailing ``$``
# anchors precisely. eBGP names carry ``EBGP``; iBGP names carry ``IBGP`` --
# cleanly disjoint, and neither matches the BGP-MON peer.
_EBGP_PEER_REGEX = r"BGP_PEER_IPV[46]_EBGP$"
_IBGP_PEER_REGEX = r"BGP_PEER_IPV[46]_IBGP_PLANE_\d+_REMOTE_(?:EB|MP)$"

# Parent prefixes of every NON-eBGP peer (all 8 iBGP planes, v6 + v4, plus
# BGP-MON). The 2.9.7 playbook ignores these when asserting the eBGP group
# actually emptied, so the session-establish check sees ONLY eBGP peers and can
# assert 0 Established. Mirrors tc7's ``_BAG013_IBGP_PEER_SUBNETS`` CIDR choices:
# iBGP v6 is a /80 per plane; iBGP v4 uses a /16 per plane because the /31 peer
# scale spills past the /24 boundary (e.g. 10.164.28.x into 10.164.29.x).
_IBGP_V6_PARENT_PREFIXES = [
    f"{net}::/80"
    for net in (
        IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE2,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE3,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE4,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE1,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE2,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE3,
        IXIA_IBGP_IC_PARENT_NETWORK_V6_MP_PLANE4,
    )
]
_IBGP_V4_PARENT_PREFIXES = [
    # "10.164.28" -> "10.164.0.0/16"
    f"{'.'.join(net.split('.')[:2])}.0.0/16"
    for net in (
        IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE2,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE3,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE4,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE1,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE2,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE3,
        IXIA_IBGP_IC_PARENT_NETWORK_V4_MP_PLANE4,
    )
]


# Spec step 3: inject from the plane-1 iBGP v6 route pool (withdraw +
# re-advertise the prefixes while the eBGP group is empty).
_IBGP_INJECT_POOL_REGEX = "PREFIX_POOL_IBGP_IPV6_PLANE_1_REMOTE_EB"
# Spec step 10 (dump-compare on recovery): compare two plane-1 iBGP peers in the
# same update group. Mirrors tc1's 2.1.1 dump-compare on this same topology.
_IBGP_DUMP_PEER_REGEX = "BGP_PEER_IPV6_IBGP_PLANE_1_REMOTE_EB"
_IBGP_DUMP_SESSION_INDICES = [1, 2]

# Spec step 8 + "full route re-sync" (recovery re-advertise): the imported eBGP
# prefix pools. IXIA does NOT re-advertise these one-shot ``ImportBgpRoutes``
# prefixes when the eBGP sessions come back up, so the playbook withdraws +
# re-advertises this pool at recovery to force IXIA to re-send them, restoring the
# DUT's eBGP RIB for redistribution (see the playbook recovery notes). ``$``
# excludes the unused ``_DRAIN`` pools (topology is built drain=False).
_EBGP_PREFIX_POOL_REGEX = r"PREFIX_POOL_IPV[46]_EBGP$"

# Spec pre-condition 3 ("record update group count") + pass-criteria "groups
# re-created correctly" / "no stale group entries". The EBB-scale UG topology
# on bag011 forms exactly 4 update groups at steady state (v6/v4 x eBGP/iBGP);
# observed on hardware (baseline 4 -> 2 when eBGP empties -> 0 all-empty -> 4 on
# recovery). Asserted at the baseline precheck (records the baseline) and again
# on recovery (must return to baseline -- a higher count would mean a stale
# group survived the empty period).
_EXPECTED_UPDATE_GROUP_COUNT = 4


def _edge_cases_prechecks(bgp_mon_ignore_prefixes):
    """Prechecks for the 2.9 edge-cases TestConfig.

    Hand-rolled (rather than the exact-count ``create_standard_prechecks``)
    for the same reasons tc7 hand-rolls bag013's: the bag conveyor DUTs run
    BGP-MON peers that IXIA does not emulate under UG qualification, so we
    drop the BGP-MON parent prefix from the session count and assert
    "no non-established peers among the non-MON set" rather than an exact
    session total (which drifts per bag node).
    """
    return [
        create_bgp_session_establish_check(
            parent_prefixes_to_ignore=bgp_mon_ignore_prefixes,
        ),
        create_drain_state_check(),
        create_memory_utilization_check(
            threshold=Gigabyte.GIG_5.value,
            start_time_jq_var="test_case_start_time",
        ),
        create_cpu_utilization_check(
            threshold=400.0, start_time_jq_var="test_case_start_time"
        ),
        # Confirm BGP++ ``update_group`` is active on the running daemon before
        # the edge-case scenarios start, and record the baseline update-group
        # count (spec pre-condition 3) so the recovery check can assert the
        # count returns to it.
        create_bgp_update_group_check(
            expect_enabled=True,
            expected_group_count=_EXPECTED_UPDATE_GROUP_COUNT,
        ),
    ]


def create_bgp_ug_edge_cases_test_config(
    testbed: Testbed,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification spec 2.9 (Edge Cases) TestConfig.

    Bundles the section-2.9 edge-case playbooks on the shared EBB-scale bag
    conveyor topology. ``enable_update_group=True`` is baked in (UG MUST be
    on for these specs). Currently wires the 2.9.7 empty-group playbook; the
    remaining sub-specs are added to ``playbooks`` as they are implemented.
    """
    bgp_mon_ignore_prefixes = [f"{IXIA_BGP_MON_IC_PARENT_NETWORK}::/80"]
    # Everything that is NOT an eBGP peer: all iBGP planes (v6 + v4) plus
    # BGP-MON. Lets the playbook scope its "eBGP actually emptied" assertion to
    # eBGP-only peers.
    non_ebgp_parent_prefixes = (
        _IBGP_V6_PARENT_PREFIXES + _IBGP_V4_PARENT_PREFIXES + bgp_mon_ignore_prefixes
    )

    empty_group_playbook = create_bgp_ug_empty_group_playbook(
        device_name=testbed.device_name,
        ebgp_peer_regex=_EBGP_PEER_REGEX,
        ibgp_peer_regex=_IBGP_PEER_REGEX,
        ibgp_v6_peer_group=PEERGROUP_IBGP_V6,
        ebgp_v6_peer_group=PEERGROUP_EBGP_V6,
        prechecks=_edge_cases_prechecks(bgp_mon_ignore_prefixes),
        bgp_mon_ignore_prefixes=bgp_mon_ignore_prefixes,
        non_ebgp_parent_prefixes=non_ebgp_parent_prefixes,
        # Spec step 3 (inject iBGP routes while eBGP empty) + step 10 (recovery
        # dump-compare on two plane-1 iBGP peers; iBGP DUT iface = ixia_ports[1]).
        ibgp_inject_pool_regex=_IBGP_INJECT_POOL_REGEX,
        ibgp_dump_capture_interface=testbed.ixia_ports[1][0],
        ibgp_dump_peer_regex=_IBGP_DUMP_PEER_REGEX,
        ibgp_dump_session_indices=_IBGP_DUMP_SESSION_INDICES,
        # Assert the update-group count returns to baseline on recovery (spec:
        # groups re-created correctly, no stale/orphaned groups).
        expected_recovered_group_count=_EXPECTED_UPDATE_GROUP_COUNT,
        # Force IXIA to re-advertise the imported eBGP routes at recovery (session
        # -up alone does not re-send them), so the DUT relearns its eBGP RIB and
        # can redistribute to iBGP for the step-10 dump + full route re-sync.
        ebgp_prefix_pool_regex=_EBGP_PREFIX_POOL_REGEX,
        # Spec pass-criterion "VmHWM below 10 GB" -- bag011 is Arista, where the
        # standard memory postcheck can only sample RSS deltas; this reads
        # bgpcpp /proc VmHWM directly and asserts the 10 GiB ceiling.
        vmhwm_threshold_bytes=Gigabyte.GIG_10.value,
    )

    return build_bag_conveyor_test_config(
        testbed,
        name="BAG011_ASH6_BGP_UG_EDGE_CASES_TEST",
        playbooks=[empty_group_playbook],
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=True,
    )


__all__ = [
    "create_bgp_ug_edge_cases_test_config",
]

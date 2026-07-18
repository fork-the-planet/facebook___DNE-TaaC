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

from taac.constants import (
    BgpPlusPlusProfile,
    DEFAULT_OPENR_START_IPV4S,
    DEFAULT_OPENR_START_IPV6S,
    Gigabyte,
)
from taac.health_checks.healthcheck_definitions import (
    create_bgp_session_establish_check,
    create_bgp_update_group_check,
    create_cpu_utilization_check,
    create_drain_state_check,
    create_memory_utilization_check,
)
from taac.playbooks.routing.factories.qual_bgp_update_group.tc9_edge_cases import (
    create_bgp_ug_empty_group_playbook,
    create_bgp_ug_simultaneous_disruptions_playbook,
)
from taac.testconfigs.routing.factories.qual_bgp_update_group.tc1_distribution_correctness import (
    build_bag_conveyor_test_config,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.testconfigs.routing.util.bgp_ebb_constants import (
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


# --- 2.9.2 Simultaneous Disruptions ---
# Route churn targets the v6 eBGP prefix pool; attribute churn targets the plane-1
# v6 iBGP prefix pool; random flaps span both eBGP AFI peers. ``$`` excludes the
# unused ``_DRAIN`` pools/peers (the bag conveyor topology is built drain=False).
_SIMUL_EBGP_ROUTE_POOL_REGEX = r"PREFIX_POOL_IPV6_EBGP$"
_SIMUL_IBGP_ATTR_POOL_REGEX = "PREFIX_POOL_IBGP_IPV6_PLANE_1_REMOTE_EB"
_SIMUL_EBGP_FLAP_PEER_REGEX = r"BGP_PEER_IPV[46]_EBGP$"
# Spec 2.9.2 pass-criterion 4: VmHWM growth (M_after - M_before) < 500 MB.
_SIMUL_VMHWM_GROWTH_THRESHOLD_BYTES = 500 * 1024 * 1024


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


def create_bgp_ug_simultaneous_disruptions_test_config(
    testbed: Testbed,
    *,
    smoke: bool = False,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification spec 2.9.2 (Simultaneous Disruptions
    Across All Groups) TestConfig on the bag conveyor topology.

    Runs the four concurrent disruption tracks (eBGP route churn with varying
    communities, random eBGP session flaps without graceful restart, IGP-metric
    oscillation via Open/R, iBGP LOCAL_PREF churn) + a monitor track + a VmHWM
    growth gate, then a convergence-verify stage. See
    ``create_bgp_ug_simultaneous_disruptions_playbook``.

    Unlike the WITHOUT_OPEN_R edge-cases bundle, 2.9.2 is its OWN TestConfig on
    the ``WITH_OPEN_R`` profile: the IGP-instability track oscillates Open/R
    adjacency metrics, which needs a running Open/R daemon + the baseline Open/R
    route injection that ``get_common_setup_tasks`` only wires under that profile.
    The eBGP peers are built graceful-restart-off so their flaps are real "without
    graceful restart" events (spec). WITH_OPEN_R does not change the 4-update-group
    or the eBGP+iBGP session baseline -- it only adds the Open/R daemon,
    Port-Channel, injected routes, and the OpenR-variant IXIA route CSVs.

    ``smoke=True`` builds a short (3-min disruption) variant with the same shape
    for validating the machinery on hardware before the full 30-min run.
    """
    bgp_mon_ignore_prefixes = [f"{IXIA_BGP_MON_IC_PARENT_NETWORK}::/80"]
    # Everything that is NOT an iBGP peer (both eBGP AFIs + BGP-MON): lets the
    # monitor scope its "iBGP stays Established" check to iBGP only, since eBGP is
    # intentionally being flapped. eBGP v6 uses a /80; eBGP v4 uses a /16 because
    # the 140 /31 peers spill past the /24 (same reasoning as the iBGP v4 parents).
    non_ibgp_parent_prefixes = [
        f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::/80",
        f"{'.'.join(IXIA_EBGP_IC_PARENT_NETWORK_V4.split('.')[:2])}.0.0/16",
    ] + bgp_mon_ignore_prefixes

    if smoke:
        name = "BAG011_ASH6_BGP_UG_SIMULTANEOUS_DISRUPTIONS_SMOKE"
        disruption_duration_s = 180
        convergence_quiesce_s = 60
        route_churn_interval_s = 30
        session_flap_interval_s = 60
        attr_churn_interval_s = 30
        monitor_interval_s = 60
        igp_frequency_s = 30
    else:
        name = "BAG011_ASH6_BGP_UG_SIMULTANEOUS_DISRUPTIONS_TEST"
        disruption_duration_s = 1800
        convergence_quiesce_s = 300
        route_churn_interval_s = 60
        session_flap_interval_s = 120
        attr_churn_interval_s = 60
        monitor_interval_s = 120
        igp_frequency_s = 60

    playbook = create_bgp_ug_simultaneous_disruptions_playbook(
        device_name=testbed.device_name,
        ebgp_route_pool_regex=_SIMUL_EBGP_ROUTE_POOL_REGEX,
        ibgp_attr_pool_regex=_SIMUL_IBGP_ATTR_POOL_REGEX,
        ebgp_flap_peer_regex=_SIMUL_EBGP_FLAP_PEER_REGEX,
        # METRIC_OSCILLATION must act on the SAME routes the WITH_OPEN_R setup
        # injects, which uses the DEFAULT start-IP lists + count=63/step=2 (the
        # playbook's igp defaults), so pass the DEFAULT lists here too.
        openr_start_ipv4s=DEFAULT_OPENR_START_IPV4S,
        openr_start_ipv6s=DEFAULT_OPENR_START_IPV6S,
        openr_local_link=testbed.extras["openr_local_link"],
        openr_other_link=testbed.extras["openr_other_link"],
        non_ibgp_parent_prefixes=non_ibgp_parent_prefixes,
        vmhwm_growth_threshold_bytes=_SIMUL_VMHWM_GROWTH_THRESHOLD_BYTES,
        prechecks=_edge_cases_prechecks(bgp_mon_ignore_prefixes),
        bgp_mon_ignore_prefixes=bgp_mon_ignore_prefixes,
        # Extra-safety absolute ceiling (consistent with 2.9.7); the growth gate
        # is the actual 2.9.2 pass-criterion.
        vmhwm_absolute_threshold_bytes=Gigabyte.GIG_10.value,
        disruption_duration_s=disruption_duration_s,
        convergence_quiesce_s=convergence_quiesce_s,
        route_churn_interval_s=route_churn_interval_s,
        session_flap_interval_s=session_flap_interval_s,
        attr_churn_interval_s=attr_churn_interval_s,
        monitor_interval_s=monitor_interval_s,
        igp_frequency_s=igp_frequency_s,
    )

    return build_bag_conveyor_test_config(
        testbed,
        name=name,
        playbooks=[playbook],
        # WITH_OPEN_R so the IGP-instability track has a running Open/R daemon +
        # injected baseline routes to oscillate.
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R,
        enable_update_group=True,
        # Spec: flap eBGP sessions "without graceful restart".
        ebgp_graceful_restart=False,
    )


__all__ = [
    "create_bgp_ug_edge_cases_test_config",
    "create_bgp_ug_simultaneous_disruptions_test_config",
]

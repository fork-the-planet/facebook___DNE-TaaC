# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Spec 2.1 — Distribution Correctness. UG qualification testconfig factory.

Merges the former bag013 initial-dump path (previously grandfathered as an
empty-playbook TestConfig inside the sustained-link-flap TC) and the eb03
initial-dump lab-box variant into a single spec-anchored factory that
dispatches internally on ``testbed.device_name``.

Golden regen for ``BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST_CONFIG``
is EXPECTED and legitimate: the former empty-playbook TestConfig is
replaced by a TestConfig that actually wires the 2.1.1 playbook. The
eb03 catalog constant remains byte-wise identical.

The bag013 conveyor topology builder is re-used by tc7 (sustained link
flap), so ``build_bag013_conveyor_test_config`` is a public helper.
"""

import json
import os
import typing as t

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
from taac.playbooks.routing.factories.qual_bgp_update_group.tc1_distribution_correctness import (
    create_bgp_ug_initial_dump_identical_routes_playbook,
)
from taac.stages.stage_definitions import create_steps_stage
from taac.steps.step_definitions import (
    create_custom_step,
    create_longevity_step,
    create_validation_step,
)
from taac.task_definitions import create_openr_route_action_task
from taac.testconfigs.routing.testbed import Testbed
from taac.testconfigs.routing.util.bgp_ebb_constants import (
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
from taac.testconfigs.routing.util.bgp_ebb_health_checks import (
    BGP_STANDARD_POSTCHECKS,
    BGP_STANDARD_PRECHECKS,
    BGP_STANDARD_SNAPSHOT_CHECKS,
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
# BAG013 conveyor topology — shared bag013 builder re-used by tc7 as well.
# =============================================================================
#
# Wave 6 factoring: the previous ``_create_bag013_ash6_conveyor_test_config_impl``
# built one TestConfig with EITHER [] playbooks (default) or [2.1.1, 2.7.2]
# (``enable_update_group=True``). Wave 6 splits that mono-TC into per-spec-section
# TestConfigs (tc1 = 2.1.1 only, tc7 = 2.7.2 only); this helper accepts the
# playbook list + TestConfig ``name`` field as parameters so each spec-section
# factory can build its own TestConfig on the same underlying bag013 topology.


def build_bag013_conveyor_test_config(
    testbed: Testbed,
    *,
    name: str,
    playbooks: t.List[taac_types.Playbook],
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
    enable_update_group: bool = True,
) -> taac_types.TestConfig:
    """Shared bag013 conveyor topology TestConfig builder.

    Wave 6 factoring of the legacy
    ``bag013_ash6_test_config.create_bag013_ash6_conveyor_test_config()``
    body. Callers pass the exact TestConfig ``name`` + playbook list they
    need; underlying setup / teardown / port config are byte-wise-identical
    to the legacy default.
    """
    assert testbed.device_name == "bag013.ash6", (
        f"bag013 conveyor topology builder is hardcoded to bag013.ash6; "
        f"got testbed.device_name={testbed.device_name!r}."
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

    return taac_types.TestConfig(
        name=name,
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


# =============================================================================
# EB03 lab-box variant helpers (BGP++ UG spec 2.1.1 on eb03.lab.ash6)
# =============================================================================


def _create_eb03_2_1_1_initial_dump_identical_routes_playbook(testbed: Testbed):
    """eb03-specific BGP++ Update Group qualification 2.1.1 playbook.

    Byte-wise identical to the legacy
    ``eb03_update_group_test_config._create_2_1_1_initial_dump_identical_routes_playbook``.
    Pinned expected_member_counts (EB-EB-V6=496, EB-FA-V6=140, BGP-MON=2) and
    policy_names are eb03-specific golden values from the live device.
    """
    ibgp_dut_iface, _ = testbed.ixia_ports[1]
    bgp_mon_dut_iface, _ = testbed.ixia_ports[2]

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
    """eb03-specific longevity soak playbook — byte-wise identical to legacy inline."""
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


def _create_eb03_distribution_correctness_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile,
) -> taac_types.TestConfig:
    """eb03.lab.ash6 branch of tc1. Byte-wise identical to the legacy
    ``eb03_update_group_test_config.create_eb03_update_group_test_config()``.

    Differs from the bag013 branch:
      - ``host_driver_args`` for admin/password auth (svc-netcastle_bot not
        authorized on the lab device)
      - ``oss_mock_device_data`` MockDeviceInfo (netwhoami returns #INVALID#)
      - Setup path uses WITHOUT_OPEN_R + conditional openr_route_action_task
        (eb03 is route-injection only, no bag-style Port-Channel)
      - Playbooks pin eb03-specific expected_member_counts / policy_names
    """
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


def _create_bag013_distribution_correctness_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile,
) -> taac_types.TestConfig:
    """bag013 branch of tc1 — wires ONLY the 2.1.1 playbook (golden regen
    expected relative to the pre-Wave-6 empty-playbook TestConfig)."""
    device_name = testbed.device_name
    _, _ = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, _ = testbed.ixia_ports[1]
    ixia_interface_mimic_bgp_mon, _ = testbed.ixia_ports[2]

    playbook = create_bgp_ug_initial_dump_identical_routes_playbook(
        device_name=device_name,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ixia_interface_mimic_bgp_mon=ixia_interface_mimic_bgp_mon,
        ibgp_v6_peer_group=PEERGROUP_IBGP_V6,
        ebgp_v6_peer_group=PEERGROUP_EBGP_V6,
        ibgp_v4_peer_group=PEERGROUP_IBGP_V4,
        bgp_mon_peer_group=PEERGROUP_BGP_MON,
    )
    return build_bag013_conveyor_test_config(
        testbed,
        name="BAG013_ASH6_BGP_UG_INITIAL_DUMP_IDENTICAL_ROUTES_TEST",
        playbooks=[playbook],
        profile=profile,
        enable_update_group=True,
    )


def create_bgp_ug_distribution_correctness_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
) -> taac_types.TestConfig:
    """BGP++ Update Group qualification 2.1.1 (Distribution Correctness /
    Initial Dump -- Identical Routes) TestConfig, dispatched on ``testbed``.

    Wave 6 merges the previous eb03 lab-box factory
    (``create_bgp_ug_eb03_initial_dump_identical_routes_test_config``) and
    the bag013 conveyor factory (``create_bgp_ug_initial_dump_identical_routes_test_config``)
    into one spec-anchored factory. Internal dispatch on ``testbed.device_name``
    because the two topologies diverge structurally (eb03 is a lab box with
    admin/password auth + mock device info; bag013 is a production EBB with
    OpenR route injection + Port-Channel).

    Golden regen for the bag013 catalog constant is EXPECTED: pre-Wave-6
    the bag013 constant returned an empty-playbook TestConfig; Wave 6
    wires the 2.1.1 playbook so the catalog name matches the actual
    behavior. eb03 golden hash is byte-wise identical.
    """
    if testbed.device_name == "eb03.lab.ash6":
        return _create_eb03_distribution_correctness_test_config(testbed, profile)
    if testbed.device_name == "bag013.ash6":
        return _create_bag013_distribution_correctness_test_config(testbed, profile)
    raise NotImplementedError(
        f"create_bgp_ug_distribution_correctness_test_config does not yet "
        f"handle testbed.device_name={testbed.device_name!r}; add a branch "
        f"or generalize the topology builder."
    )

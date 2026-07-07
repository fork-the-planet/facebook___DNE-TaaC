# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGPCPP-on-EBB full-scale workflow factories.

Bag conveyor workflows on the 1274-peer EBB topology. Naming:
``create_ebb_<workflow>_test_config(testbed: Testbed, ...) -> TestConfig``.

See ../README.md §3.
"""

from taac.constants import (
    BgpPlusPlusProfile,
    DEFAULT_LOCAL_LINK,
    DEFAULT_OPENR_START_IPV4S,
    DEFAULT_OPENR_START_IPV6S,
    DEFAULT_OTHER_LINK,
    OpenRRouteAction,
)
from taac.playbooks.routing.bgp_ebb_playbooks import (
    create_bgp_ebb_cold_start_playbook,
    create_bgp_ebb_daemon_restart_playbook,
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
    PEERGROUP_IBGP_V4,
    PEERGROUP_IBGP_V6,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ixia_config_for_ebb_scale import (
    create_ebb_scale_basic_port_configs,
)
from taac.task_definitions import (
    create_arista_create_file_from_config_task,
    create_arista_daemon_control_task,
    create_interface_ip_cleanup_task,
    create_interface_ip_configuration_task,
    create_openr_route_action_task,
    create_run_commands_on_shell_task,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection, Endpoint, TestConfig


def create_ebb_cold_start_and_daemon_restart_test_config(
    testbed: Testbed,
    profile: BgpPlusPlusProfile = DEFAULT_PROFILE,
) -> TestConfig:
    """Create the BGP++ conveyor test configuration (daemon-restart + cold-start).

    Extracted verbatim from the legacy
    ``testconfigs/routing/ebb/bag002_snc1_test_config.create_bag002_snc1_conveyor_test_config``
    factory as part of the Wave 1 hierarchical migration. Only the DUT
    identity + IXIA port map are parameterized on the ``testbed`` argument;
    everything else (setup / teardown tasks, IXIA topology, playbook list)
    is byte-wise identical to the pre-migration factory so the golden
    manifest hash for ``BAG002_SNC1_BGP_CONVEYOR_TEST`` is preserved.

    Playbooks:
    - ``bgp_daemon_restart_test_playbook``
    - ``bgp_cold_start_test_playbook``

    Args:
        testbed: Testbed instance for the DUT (currently BAG002_SNC1).
        profile: BGP++ profile — determines whether OpenR route injection
            is added to setup tasks.

    Returns:
        TestConfig configured for the BGP++ conveyor CI/CD pipeline.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )

    device_name = testbed.device_name
    ixia_chassis_ip = testbed.ixia_chassis_ip

    ixia_interface_mimic_ebgp, ixia_port_ebgp = testbed.ixia_ports[0]
    ixia_interface_mimic_ibgp, ixia_port_ibgp = testbed.ixia_ports[1]
    ixia_interface_mimic_bgp_mon, ixia_port_bgp_mon = testbed.ixia_ports[2]

    # Build setup tasks based on profile
    # EXECUTION FLOW:
    # 1. async_setUp() runs first (includes EOS image deployment if eos_image_id passed to TaacRunner)
    # 2. IXIA setup happens during async_setUp()
    # 3. PRE-IXIA setup tasks run (ixia_needed=False)
    # 4. POST-IXIA setup tasks run (ixia_needed=True) <- config tasks run here
    #
    # Config tasks have ixia_needed=True so they run AFTER IXIA is configured
    setup_tasks = []

    # All config tasks below have ixia_needed=True so they run AFTER IXIA setup
    setup_tasks.extend(
        [
            # Shutdown EOS native BGP (router bgp <ASN>)
            # This must be done before enabling BGP++ daemons
            create_run_commands_on_shell_task(
                hostname=device_name,
                cmds=["configure\nrouter bgp 65060\nshutdown\nend"],
                ixia_needed=True,
            ),
            # Add IPv6 ACL rule to permit BGP++ control plane traffic (ports 5911-5919)
            create_run_commands_on_shell_task(
                hostname=device_name,
                cmds=[
                    "configure\n"
                    "ipv6 access-list aiv6-control-plane-acl\n"
                    "permit tcp any any range 5911 5919\n"
                    "end",
                ],
                ixia_needed=True,
            ),
            # Create required directories for config files
            create_run_commands_on_shell_task(
                hostname=device_name,
                cmds=[
                    "bash mkdir -p /usr/facebook/thrift_acls",
                    "bash mkdir -p /mnt/fb/agent_configs",
                ],
                ixia_needed=True,
            ),
            # Copy BGP++ config files from configerator to device
            create_arista_create_file_from_config_task(
                hostname=device_name,
                configerator_path=testbed.bgpcpp_configerator_path,
                file_path="/mnt/flash/bgpcpp_config",
            ),
            create_arista_create_file_from_config_task(
                hostname=device_name,
                configerator_path="taac/ebb_ci_cd_configs/FibAgent.json",
                file_path="/usr/facebook/thrift_acls/FibAgent.json",
            ),
            create_arista_create_file_from_config_task(
                hostname=device_name,
                configerator_path="taac/ebb_ci_cd_configs/fib_agent_bgp.conf",
                file_path="/mnt/fb/agent_configs/fib_agent_bgp.conf",
            ),
            # Enable BGP++ daemons (ixia_needed=True so they run after IXIA setup)
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="Bgp", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="FibAgent", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="FibAgentBgp", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="FibBgpGrpc", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="FibGrpc", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="Openr", ixia_needed=True
            ),
            create_arista_daemon_control_task(
                hostname=device_name, daemon_name="RouteGrpc", ixia_needed=True
            ),
            # Configure IXIA interfaces before IP address configuration
            create_run_commands_on_shell_task(
                hostname=device_name,
                cmds=[
                    "configure\n"
                    f"interface {ixia_interface_mimic_ebgp}\n"
                    "description IXIA_EBGP\n"
                    "mtu 9000\n"
                    "speed 400g-4\n"
                    "no switchport\n"
                    "!\n"
                    f"interface {ixia_interface_mimic_ibgp}\n"
                    "description IXIA_IBGP\n"
                    "mtu 9000\n"
                    "speed 400g-4\n"
                    "no switchport\n"
                    "!\n"
                    f"interface {ixia_interface_mimic_bgp_mon}\n"
                    "description IXIA_BGP_MON\n"
                    "mtu 9000\n"
                    "speed 400g-4\n"
                    "no switchport\n"
                    "end",
                ],
                ixia_needed=True,
            ),
            # Configure eBGP interface IPs (Ethernet3/25/1)
            # 140 IPv6 + 140 IPv4 secondary IPs for IXIA peers
            create_interface_ip_configuration_task(
                interface=ixia_interface_mimic_ebgp,
                peer_count=EBGP_PEER_COUNT_V6,
                ipv4_base_network=IXIA_EBGP_IC_PARENT_NETWORK_V4,
                ipv6_base_network=IXIA_EBGP_IC_PARENT_NETWORK_V6,
                address_families=["ipv4", "ipv6"],
                ixia_needed=True,
            ),
            # Configure iBGP interface IPs (Ethernet3/26/1)
            # 504 IPv6 + 504 IPv4 secondary IPs (8 planes × 63 peers/plane)
            create_interface_ip_configuration_task(
                interface=ixia_interface_mimic_ibgp,
                peer_count=IBGP_PEER_SCALE_PER_PLANE * 8,
                ipv4_base_network=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
                ipv6_base_network=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
                address_families=["ipv4", "ipv6"],
                ixia_needed=True,
            ),
            # Configure BGP MON interface IPs (Ethernet3/27/1)
            # 1 IPv6 secondary IP for IXIA peer
            create_interface_ip_configuration_task(
                interface=ixia_interface_mimic_bgp_mon,
                peer_count=BGP_MON_PEER_COUNT,
                ipv6_base_network=IXIA_BGP_MON_IC_PARENT_NETWORK,
                address_families=["ipv6"],
                ixia_needed=True,
            ),
        ]
    )

    # Add OpenR route injection task if profile requires it
    if profile == BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R:
        setup_tasks.append(
            create_openr_route_action_task(
                device_name=device_name,
                start_ipv4s=DEFAULT_OPENR_START_IPV4S,
                start_ipv6s=DEFAULT_OPENR_START_IPV6S,
                local_link=DEFAULT_LOCAL_LINK,
                other_link=DEFAULT_OTHER_LINK,
                action=OpenRRouteAction.INJECT.value,
                count=63,
                step=2,
            ),
        )

    # Build teardown tasks - restore interface configs from backup
    teardown_tasks = [
        create_interface_ip_cleanup_task(
            interfaces=[ixia_interface_mimic_ebgp],
            restore_from_backup=True,
            hostname=device_name,
        ),
        create_interface_ip_cleanup_task(
            interfaces=[ixia_interface_mimic_ibgp],
            restore_from_backup=True,
            hostname=device_name,
        ),
        create_interface_ip_cleanup_task(
            interfaces=[ixia_interface_mimic_bgp_mon],
            restore_from_backup=True,
            hostname=device_name,
        ),
    ]

    return TestConfig(
        name="BAG002_SNC1_BGP_CONVEYOR_TEST",
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
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
        playbooks=[
            # BGP Daemon Restart Test Playbook - using factory function
            create_bgp_ebb_daemon_restart_playbook(
                device_name=device_name,
                peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
                peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
                profile=profile,
            ),
            # BGP Cold Start Test Playbook - using factory function
            create_bgp_ebb_cold_start_playbook(
                device_name=device_name,
                peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
                peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
                profile=profile,
            ),
        ],
    )

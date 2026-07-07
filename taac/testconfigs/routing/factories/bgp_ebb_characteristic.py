# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGPCPP-on-EBB characteristic/measurement workflow factories.

EBB-topology measurement tests (update-packing, constant-attribute storage,
queue/memory monitoring, performance scaling, bounded ECMP). Naming:
``create_ebb_<workflow>_test_config(testbed: Testbed, ...) -> TestConfig``.

See ../README.md §3.
"""

from taac.constants import BgpPlusPlusProfile
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_common_tasks import (
    build_per_iteration_factory_v4_capable,
    get_update_packing_setup_tasks,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_constants import (
    EBGP_PEER_COUNT_V6,
    EBGP_REMOTE_AS,
    IBGP_PEER_SCALE_PER_PLANE,
    IBGP_REMOTE_AS,
    IXIA_EBGP_IC_PARENT_NETWORK_V4,
    IXIA_EBGP_IC_PARENT_NETWORK_V6,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    IXIA_IPV4_START_OFFSET,
    PEERGROUP_EBGP_V4,
    PEERGROUP_EBGP_V6,
    PEERGROUP_IBGP_V4,
    PEERGROUP_IBGP_V6,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case1 import (
    test_config_for_bgp_plus_plus_on_ebb_arista_performance_scaling,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case2 import (
    test_config_constant_attribute_storage_varying_combinations_on_eos,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case9 import (
    test_config_for_bgp_plus_plus_on_ebb_arista_bounded_ecmp_sets,
)
from taac.testconfigs.routing.ebb.test_config_queue_memory_monitor import (
    test_config_bgp_queue_memory_monitoring_with_route_scale,
)
from taac.testconfigs.routing.ebb.test_config_update_packing import (
    test_config_bgp_update_packing_validation,
)
from taac.testconfigs.routing.testbed import Testbed
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection


# =============================================================================
# BAG012_ASH6 conveyor family — Update Packing / Constant Attribute Storage /
# Queue Memory Monitor / Performance Scaling / Bounded ECMP.
# =============================================================================
# Defaults for the performance-scaling egress IBGP peer sweep match the
# simplified rewrite of D104072489: per stage n peers per AF, total = 2n + 2
# EBGP. Each Stage rewrites /mnt/flash/bgpcpp_config to the matching number of
# peer entries so BGP++ EOR completes from 100% of configured peers.
_BAG012_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS: list = [100, 200, 300, 400, 500]
_BAG012_PERFORMANCE_SCALING_PREFIX_COUNT: int = 50000

# bag012.ash6 nexthop group threshold parameters for bounded ECMP.
_BAG012_BOUNDED_ECMP_PEER_COUNT: int = 128
_BAG012_BOUNDED_ECMP_PREFIX_COUNT: int = 5000


def _bag012_direct_ixia_connections(testbed: Testbed) -> list[DirectIxiaConnection]:
    """Two DirectIxiaConnection entries (eBGP + iBGP), no BGP-MON.

    bag012.ash6 wires only two IXIA ports (unlike bag010/bag011/bag013 which
    also have a BGP-MON port).
    """
    ebgp_iface, ebgp_port = testbed.ixia_ports[0]
    ibgp_iface, ibgp_port = testbed.ixia_ports[1]
    return [
        DirectIxiaConnection(
            interface=ebgp_iface,
            ixia_chassis_ip=testbed.ixia_chassis_ip,
            ixia_port=ebgp_port,
        ),
        DirectIxiaConnection(
            interface=ibgp_iface,
            ixia_chassis_ip=testbed.ixia_chassis_ip,
            ixia_port=ibgp_port,
        ),
    ]


def create_ebb_bag012_conveyor_test_config(
    testbed: Testbed,
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """BGP Update Packing conveyor test config for bag012.ash6.

    Extracted verbatim from the legacy
    ``bag012_ash6_test_config.create_bag012_ash6_conveyor_test_config``
    factory. Reuses ``test_config_bgp_update_packing_validation()`` with
    bag012-specific setup_tasks + direct_ixia_connections.

    Test direction matches EB02_ARISTA_BGP_UPDATE_PACKING_VALIDATION:
    - EBGP → IBGP: 10 EBGP peers inject routes, 1 IBGP peer captures UPDATEs.
    - ``ebgp_route_acceptance_communities=["65529:39744"]``.

    The internal ``TestConfig.name`` field is preserved verbatim as
    ``BAG012_ASH6_BGP_CONVEYOR_TEST`` (+ ``_UPDATE_GROUP``) so the golden
    manifest hash is byte-wise identical.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )
    assert testbed.dut_bgp_as is not None, "factory requires dut_bgp_as on testbed"
    assert testbed.router_id, "factory requires router_id on testbed"

    device_name = testbed.device_name
    ixia_interface_mimic_ebgp = testbed.ixia_ports[0][0]
    ixia_interface_mimic_ibgp = testbed.ixia_ports[1][0]

    name = "BAG012_ASH6_BGP_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"

    setup_tasks = get_update_packing_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count=10,
        ibgp_peer_count=1,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    return test_config_bgp_update_packing_validation(
        test_config_name=name,
        device_name=device_name,
        # EBGP configuration (ingress - routes sent here from Fabric Aggregators)
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4="",
        # IBGP configuration (egress - capture UPDATEs here)
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4="",
        # Test parameters (matching EB02)
        ebgp_peer_count=10,
        prefixes_per_peer=10000,
        ibgp_peer_count=1,
        test_address_families=["ipv6"],
        as_path_pool_size=10,
        community_pool_size=20,
        as_path_length=3,
        communities_per_route=2,
        ebgp_route_acceptance_communities=["65529:39744"],
        capture_duration_seconds=300,
        min_packed_size=4000,
        restart_bgp_for_complete_view=True,
        # Conveyor-specific configuration
        setup_tasks=setup_tasks,
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=_bag012_direct_ixia_connections(testbed),
        log_collection_timeout=600,
    )


def create_ebb_bag012_constant_attribute_storage_test_config(
    testbed: Testbed,
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """Constant Attribute Storage varying-combinations test config for bag012.ash6.

    Extracted verbatim from the legacy
    ``bag012_ash6_test_config.create_bag012_ash6_constant_attribute_storage_test_config``
    factory. Validates that the amount of memory for storing pool of
    attributes remains constant regardless of the number of unique
    attribute-set combinations.

    The internal ``TestConfig.name`` field is preserved verbatim as
    ``BAG012_ASH6_BGP_CONSTANT_ATTRIBUTE_STORAGE_CONVEYOR_TEST`` (+
    ``_UPDATE_GROUP``) so the golden manifest hash is byte-wise identical.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )
    assert testbed.dut_bgp_as is not None, "factory requires dut_bgp_as on testbed"
    assert testbed.router_id, "factory requires router_id on testbed"

    device_name = testbed.device_name
    ixia_interface_mimic_ebgp = testbed.ixia_ports[0][0]
    ixia_interface_mimic_ibgp = testbed.ixia_ports[1][0]

    name = "BAG012_ASH6_BGP_CONSTANT_ATTRIBUTE_STORAGE_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"

    setup_tasks = get_update_packing_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count=8,
        ibgp_peer_count=2,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    return test_config_constant_attribute_storage_varying_combinations_on_eos(
        test_config_name=name,
        device_name=device_name,
        # EBGP configuration
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        # IBGP configuration
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        # Fixed: 8 EBGP peers + 2 IBGP peers (smaller scale)
        constant_ebgp_peer_count=8,
        constant_ibgp_peer_count=2,
        # Fixed: 800K total paths
        constant_total_paths=800_000,
        # Variable: unique combination counts
        unique_combination_counts=[
            100_000,
            200_000,
            400_000,
            600_000,
            800_000,
        ],
        soak_time_minutes=2,
        dump_attribute_assignments=True,
        test_address_families=["ipv6"],
        # Custom setup tasks (no openR)
        setup_tasks=setup_tasks,
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=_bag012_direct_ixia_connections(testbed),
        # Constant acceptance community (required by device BGP policy)
        constant_acceptance_communities=["65529:39744"],
        max_communities_per_route_from_pool=5,
        random_seed=42,
        # Device-level BGP peer group names
        peergroup_ebgp_v6=PEERGROUP_EBGP_V6,
        peergroup_ebgp_v4=PEERGROUP_EBGP_V4,
        peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
        peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
        log_collection_timeout=600,
    )


def create_ebb_bag012_queue_memory_monitor_test_config(
    testbed: Testbed,
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """Queue-memory-monitor conveyor test config for bag012.ash6.

    Extracted verbatim from the legacy
    ``bag012_ash6_test_config.create_bag012_ash6_queue_memory_monitor_test_config``
    factory. Monitors BGP++ fiber queue statistics and memory usage under
    route churn (140 EBGP peers flapping 15s up / 15s down; 63 IBGP peers).

    The internal ``TestConfig.name`` field is preserved verbatim as
    ``BAG012_ASH6_BGP_QUEUE_MEMORY_MONITOR_CONVEYOR_TEST`` (+
    ``_UPDATE_GROUP``) so the golden manifest hash is byte-wise identical.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )
    assert testbed.dut_bgp_as is not None, "factory requires dut_bgp_as on testbed"
    assert testbed.router_id, "factory requires router_id on testbed"

    device_name = testbed.device_name
    ixia_interface_mimic_ebgp = testbed.ixia_ports[0][0]
    ixia_interface_mimic_ibgp = testbed.ixia_ports[1][0]

    name = "BAG012_ASH6_BGP_QUEUE_MEMORY_MONITOR_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"

    setup_tasks = get_update_packing_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count=EBGP_PEER_COUNT_V6,
        ibgp_peer_count=IBGP_PEER_SCALE_PER_PLANE,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    # CPU stress is deployed directly by the custom step (_deploy_cpu_stress)
    # when monitor_cpu_stress=True -- no need for setup_tasks deployment.

    return test_config_bgp_queue_memory_monitoring_with_route_scale(
        test_config_name=name,
        device_name=device_name,
        # IBGP configuration
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        # EBGP configuration
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        # Test parameters
        ibgp_peer_count=IBGP_PEER_SCALE_PER_PLANE,
        ebgp_peer_count=EBGP_PEER_COUNT_V6,
        prefixes_per_ebgp_peer=10000,
        ip_version="ipv6",
        # Route acceptance communities
        ebgp_route_acceptance_communities=["65529:39744"],
        # Monitoring parameters
        monitoring_duration_minutes=60,
        monitoring_interval_seconds=120,
        # Route flapping parameters
        flap_uptime_seconds=15,
        flap_downtime_seconds=15,
        # Conveyor-specific configuration
        setup_tasks=setup_tasks,
        monitor_cpu_stress=True,
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=_bag012_direct_ixia_connections(testbed),
        log_collection_timeout=600,
    )


def create_ebb_bag012_performance_scaling_test_config(
    testbed: Testbed,
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """Performance-scaling egress IBGP peer-sweep test config for bag012.ash6.

    Extracted verbatim from the legacy
    ``bag012_ash6_test_config.create_bag012_ash6_performance_scaling_test_config``
    factory. Per Stage n in ``egress_peer_counts``, the device is configured
    with n v6 + n v4 IBGP peers via in-shell ``bgpcpp_config`` rewrite, then
    50K v6 + 50K v4 EBGP prefixes are advertised and initial convergence is
    measured. A final aggregator Stage produces one consolidated everpaste
    plot.

    The internal ``TestConfig.name`` field is preserved verbatim as
    ``BAG012_ASH6_BGP_PERFORMANCE_SCALING_CONVEYOR_TEST`` (+
    ``_UPDATE_GROUP``) so the golden manifest hash is byte-wise identical.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )
    assert testbed.dut_bgp_as is not None, "factory requires dut_bgp_as on testbed"
    assert testbed.router_id, "factory requires router_id on testbed"

    device_name = testbed.device_name
    ixia_interface_mimic_ebgp = testbed.ixia_ports[0][0]
    ixia_interface_mimic_ibgp = testbed.ixia_ports[1][0]

    name = "BAG012_ASH6_BGP_PERFORMANCE_SCALING_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"

    setup_tasks = get_update_packing_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count=1,
        ibgp_peer_count=_BAG012_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS[0],
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        # v4 enables dual-stack IBGP/EBGP at startup so the initial
        # /mnt/flash/bgpcpp_config matches the v6+v4 layout that each
        # per-iteration factory call produces.
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )
    factory = build_per_iteration_factory_v4_capable(
        device_name=device_name,
        router_id=testbed.router_id,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ebgp_v6_base=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ebgp_v4_base=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ibgp_v6_base=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ibgp_v4_base=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        peergroup_ebgp_v6=PEERGROUP_EBGP_V6,
        peergroup_ebgp_v4=PEERGROUP_EBGP_V4,
        peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
        peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
        ebgp_peer_count=1,
    )
    return test_config_for_bgp_plus_plus_on_ebb_arista_performance_scaling(
        test_config_name=name,
        device_name=device_name,
        host_driver_args=None,
        oss_mock_device_data=None,
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        direct_ixia_connections=_bag012_direct_ixia_connections(testbed),
        egress_peer_counts=_BAG012_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS,
        prefix_count=_BAG012_PERFORMANCE_SCALING_PREFIX_COUNT,
        ebgp_peer_count=1,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        log_collection_timeout=600,
        setup_tasks=setup_tasks,
        per_iteration_setup_steps_factory=factory,
    )


def create_ebb_bag012_bounded_ecmp_sets_test_config(
    testbed: Testbed,
) -> taac_types.TestConfig:
    """Bounded-ECMP-sets conveyor test config for bag012.ash6.

    Extracted verbatim from the legacy
    ``bag012_ash6_test_config.create_bag012_ash6_bounded_ecmp_sets_test_config``
    factory. Verifies BGP++ ECMP-set bounding at production peer scale (128
    EBGP + 128 IBGP per AFI) with update_group enabled. The DUT setup uses
    the standard ``get_update_packing_setup_tasks`` helper (same path as the
    other bag012 characteristic tests) so the configerator ``bgpcpp_config``
    is deployed cleanly instead of patching the image's leftover config in
    place. Bounded ECMP brings up IPv4 sessions too, so
    ``v4_peer_start_offset=IXIA_IPV4_START_OFFSET`` aligns the generated v4
    peers with the device's v4 secondary IPs.

    The internal ``TestConfig.name`` field is preserved verbatim as
    ``BAG012_ASH6_BGP_BOUNDED_ECMP_SETS_CONVEYOR_TEST_UPDATE_GROUP`` so the
    golden manifest hash is byte-wise identical.
    """
    assert testbed.ixia_ports, "factory requires IXIA port map on testbed"
    assert testbed.bgpcpp_configerator_path, (
        "factory requires bgpcpp_configerator_path on testbed"
    )
    assert testbed.dut_bgp_as is not None, "factory requires dut_bgp_as on testbed"
    assert testbed.router_id, "factory requires router_id on testbed"

    device_name = testbed.device_name
    ixia_interface_mimic_ebgp = testbed.ixia_ports[0][0]
    ixia_interface_mimic_ibgp = testbed.ixia_ports[1][0]

    setup_tasks = get_update_packing_setup_tasks(
        device_name=device_name,
        bgp_asn=testbed.dut_bgp_as,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        # Dual-stack: bounded ECMP runs v4 + v6 peers on both interfaces.
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        router_id=testbed.router_id,
        bgpcpp_configerator_path=testbed.bgpcpp_configerator_path,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        # Align v4 peers with the device v4 secondary IPs + IXIA .10 layout.
        v4_peer_start_offset=IXIA_IPV4_START_OFFSET,
        # DUT runs with BGP++ update_group enabled.
        enable_update_group=True,
    )

    return test_config_for_bgp_plus_plus_on_ebb_arista_bounded_ecmp_sets(
        test_config_name="BAG012_ASH6_BGP_BOUNDED_ECMP_SETS_CONVEYOR_TEST_UPDATE_GROUP",
        device_name=device_name,
        ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
        ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
        ebgp_peer_count_v6=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count_v6=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ebgp_peer_count_v4=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count_v4=_BAG012_BOUNDED_ECMP_PEER_COUNT,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        prefix_count=_BAG012_BOUNDED_ECMP_PREFIX_COUNT,
        direct_ixia_connections=_bag012_direct_ixia_connections(testbed),
        host_os_type_map={device_name: taac_types.DeviceOsType.ARISTA_FBOSS},
        # Standard device setup (configerator deploy + control plane + validator
        # + interface IPs + update_group), shared with the other bag012 conveyor
        # nodes. Passing setup_tasks skips case9's in-shell fallback.
        setup_tasks=setup_tasks,
        log_collection_timeout=600,
    )

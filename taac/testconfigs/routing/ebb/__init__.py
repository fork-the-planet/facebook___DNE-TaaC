# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""EBB testconfigs package — re-exports from member modules.

Allows callers to use the package-level path:
    from taac.testconfigs.routing.ebb import (
        test_config_for_bgp_plus_plus_on_ebb_arista_transient_memory_peer_scale,
    )

instead of the deeper module path.
"""

from taac.testconfigs.routing.ebb.arista_ebb_scale_test_config import (
    test_config_for_bgp_plus_plus_on_ebb_arista_with_bgp_mon,
)
from taac.testconfigs.routing.ebb.arista_mimic_ebb_test_full_scale_test_config import (
    ARISTA_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.bgp_plus_plus_verify_computational_load_test_config import (
    BGP_PLUS_PLUS_VERIFY_COMPUTATIONAL_LOAD_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.bgp_plus_plus_verify_constant_attribute_storage_test_config import (
    BGP_PLUS_PLUS_VERIFY_CONSTANT_ATTRIBUTE_STORAGE_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.case1_test_config import (
    CASE1_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.case2_test_config import (
    CASE2_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb01_arista_mimic_ebb_test_full_scale_without_open_r_test_config import (
    EB01_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITHOUT_OPEN_R_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb02_arista_bgp_plus_plus_separable_policy_1_peer_test_config import (
    EB02_ARISTA_BGP_PLUS_PLUS_SEPARABLE_POLICY_1_PEER_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb02_arista_bgp_queue_memory_monitor_ipv6_50ebgp_25ibgp_with_flapping_test_config import (
    EB02_ARISTA_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb02_arista_bgp_update_packing_validation_test_config import (
    EB02_ARISTA_BGP_UPDATE_PACKING_VALIDATION_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb02_arista_constant_attribute_storage_varying_combinations_test_config import (
    EB02_ARISTA_CONSTANT_ATTRIBUTE_STORAGE_VARYING_COMBINATIONS_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb03_arista_high_diversity_test_config import (
    EB03_ARISTA_HIGH_DIVERSITY_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb03_arista_mimic_ebb_test_full_scale_with_open_r_test_config import (
    EB03_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb04_arista_bgp_plus_plus_separable_policy_1_peer_test_config import (
    EB04_ARISTA_BGP_PLUS_PLUS_SEPARABLE_POLICY_1_PEER_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb04_arista_bgp_queue_memory_monitor_ipv6_50ebgp_25ibgp_with_flapping_test_config import (
    EB04_ARISTA_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb04_arista_mimic_ebb_test_full_scale_with_open_r_test_config import (
    EB04_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb_test_device_bgp_queue_memory_monitor_ipv6_50ebgp_25ibgp_with_flapping_test_config import (
    EB_TEST_DEVICE_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.fboss_ebb_scale_test_config import (
    test_config_for_bgp_plus_plus_ebb,
    test_config_for_bgp_plus_plus_ebb_with_bgp_mon,
)
from taac.testconfigs.routing.ebb.fsw001_qzb_single_node_topology_mimic_ebb_test_full_scale_mon_test_config import (
    FSW001_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_MON_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.fsw_qzb_single_node_topology_mimic_ebb_test_full_scale_test_config import (
    FSW_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.qzd_single_node_topology_mimic_ebb_test_full_scale_fsw002_test_config import (
    QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_FSW002_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.qzd_single_node_topology_mimic_ebb_test_full_scale_test_config import (
    QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.test_config_bgp_enforce_first_as_feature import (
    test_config_for_bgp_enforce_first_as_feature,
)
from taac.testconfigs.routing.ebb.test_config_bgp_med_feature import (
    test_config_for_bgp_med_feature,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case2 import (
    test_config_constant_attribute_storage_on_eos,
    test_config_constant_attribute_storage_varying_combinations_on_eos,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case8 import (
    test_config_for_bgp_plus_plus_on_ebb_arista_separable_policy,
)
from taac.testconfigs.routing.ebb.test_config_queue_memory_monitor import (
    test_config_bgp_queue_memory_monitoring_with_route_scale,
)
from taac.testconfigs.routing.ebb.test_config_to_verify_computational_load_of_bgp_plus_plus import (
    test_config_to_verify_computational_load_of_bgp_plus_plus,
)
from taac.testconfigs.routing.ebb.test_config_to_verify_constant_attribute_storage import (
    test_config_to_verify_constant_attribute_storage,
)
from taac.testconfigs.routing.ebb.test_config_update_packing import (
    test_config_bgp_update_packing_validation,
)

__all__ = [
    "ARISTA_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "BGP_PLUS_PLUS_VERIFY_COMPUTATIONAL_LOAD_TEST_CONFIG",
    "BGP_PLUS_PLUS_VERIFY_CONSTANT_ATTRIBUTE_STORAGE_TEST_CONFIG",
    "CASE1_TEST_CONFIG",
    "CASE2_TEST_CONFIG",
    "EB01_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITHOUT_OPEN_R_TEST_CONFIG",
    "EB02_ARISTA_BGP_PLUS_PLUS_SEPARABLE_POLICY_1_PEER_TEST_CONFIG",
    "EB02_ARISTA_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG",
    "EB02_ARISTA_BGP_UPDATE_PACKING_VALIDATION_TEST_CONFIG",
    "EB02_ARISTA_CONSTANT_ATTRIBUTE_STORAGE_VARYING_COMBINATIONS_TEST_CONFIG",
    "EB03_ARISTA_HIGH_DIVERSITY_TEST_CONFIG",
    "EB03_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG",
    "EB04_ARISTA_BGP_PLUS_PLUS_SEPARABLE_POLICY_1_PEER_TEST_CONFIG",
    "EB04_ARISTA_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG",
    "EB04_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG",
    "EB_TEST_DEVICE_BGP_QUEUE_MEMORY_MONITOR_IPV6_50EBGP_25IBGP_WITH_FLAPPING_TEST_CONFIG",
    "FSW001_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_MON_TEST_CONFIG",
    "FSW_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_FSW002_TEST_CONFIG",
    "QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "test_config_for_bgp_plus_plus_ebb",
    "test_config_for_bgp_plus_plus_ebb_with_bgp_mon",
    "test_config_for_bgp_plus_plus_on_ebb_arista_with_bgp_mon",
    "test_config_bgp_queue_memory_monitoring_with_route_scale",
    "test_config_bgp_update_packing_validation",
    "test_config_constant_attribute_storage_on_eos",
    "test_config_constant_attribute_storage_varying_combinations_on_eos",
    "test_config_for_bgp_enforce_first_as_feature",
    "test_config_for_bgp_med_feature",
    "test_config_for_bgp_plus_plus_on_ebb_arista_separable_policy",
    "test_config_to_verify_computational_load_of_bgp_plus_plus",
    "test_config_to_verify_constant_attribute_storage",
]

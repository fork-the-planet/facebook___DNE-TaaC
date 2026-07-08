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
from taac.testconfigs.routing.ebb.case1_test_config import (
    CASE1_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.case2_test_config import (
    CASE2_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb01_arista_mimic_ebb_test_full_scale_without_open_r_test_config import (
    EB01_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITHOUT_OPEN_R_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb03_arista_mimic_ebb_test_full_scale_with_open_r_test_config import (
    EB03_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.eb04_arista_mimic_ebb_test_full_scale_with_open_r_test_config import (
    EB04_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG,
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

__all__ = [
    "ARISTA_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "CASE1_TEST_CONFIG",
    "CASE2_TEST_CONFIG",
    "EB01_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITHOUT_OPEN_R_TEST_CONFIG",
    "EB03_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG",
    "EB04_ARISTA_MIMIC_EBB_TEST_FULL_SCALE_WITH_OPEN_R_TEST_CONFIG",
    "FSW001_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_MON_TEST_CONFIG",
    "FSW_QZB_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_FSW002_TEST_CONFIG",
    "QZD_SINGLE_NODE_TOPOLOGY_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
    "test_config_for_bgp_plus_plus_ebb",
    "test_config_for_bgp_plus_plus_ebb_with_bgp_mon",
    "test_config_for_bgp_plus_plus_on_ebb_arista_with_bgp_mon",
]

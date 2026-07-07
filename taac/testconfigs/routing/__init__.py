# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Routing testconfigs package — re-exports from member modules.

Allows callers to use the package-level path:
    from taac.testconfigs.routing import (
        CTE_UCMP_QZD_TEST,
    )

instead of the deeper module path.
"""

from taac.testconfigs.routing.cicd_ebb_int_tc import (
    BAG002_SNC1_CONVEYOR_TEST_CONFIG,
)
from taac.testconfigs.routing.fboss_bgp_plus_plus_chronos_node_test_config import (
    build_bgp_dc_test_config,
)
from taac.testconfigs.routing.test_config_cte_ucmp import (
    CTE_UCMP_QZD_TEST,
)
from taac.testconfigs.routing.test_config_cte_ucmp_stand_alone import (
    CTE_UCMP_STAND_ALONE,
)

__all__ = [
    "BAG002_SNC1_CONVEYOR_TEST_CONFIG",
    "CTE_UCMP_QZD_TEST",
    "CTE_UCMP_STAND_ALONE",
    "build_bgp_dc_test_config",
]

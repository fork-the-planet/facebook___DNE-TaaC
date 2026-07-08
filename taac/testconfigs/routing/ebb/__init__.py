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
from taac.testconfigs.routing.ebb.case1_test_config import (
    CASE1_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.case2_test_config import (
    CASE2_TEST_CONFIG,
)
from taac.testconfigs.routing.ebb.fboss_ebb_scale_test_config import (
    test_config_for_bgp_plus_plus_ebb,
    test_config_for_bgp_plus_plus_ebb_with_bgp_mon,
)

__all__ = [
    "CASE1_TEST_CONFIG",
    "CASE2_TEST_CONFIG",
    "test_config_for_bgp_plus_plus_ebb",
    "test_config_for_bgp_plus_plus_ebb_with_bgp_mon",
    "test_config_for_bgp_plus_plus_on_ebb_arista_with_bgp_mon",
]

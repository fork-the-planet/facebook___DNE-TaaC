# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""NPI testconfigs package — re-exports from member modules.

Allows callers to use the package-level path:
    from taac.testconfigs.npi import (
        NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG,
    )

instead of the deeper module path.
"""

from taac.testconfigs.npi.cpu_queue_test_config import (
    create_dctypef_npi_cpu_queue_test_config,
    create_npi_cpu_queue_test_config,
    get_cpu_queue_constants,
    NPI_51T_DVT_KO3_SSW_CPU_QUEUE_TEST_CONFIG,
    NPI_51T_DVT_MP3_XSW_CPU_QUEUE_TEST_CONFIG,
    NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG,
)

__all__ = [
    "NPI_51T_DVT_KO3_SSW_CPU_QUEUE_TEST_CONFIG",
    "NPI_51T_DVT_MP3_XSW_CPU_QUEUE_TEST_CONFIG",
    "NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG",
    "create_dctypef_npi_cpu_queue_test_config",
    "create_npi_cpu_queue_test_config",
    "get_cpu_queue_constants",
]

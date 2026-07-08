# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""CHRONOS_NODE_FSW_FUJI — CICD_TC TestConfig (Wave 3B re-export shim).

Wave 3B moved the concrete binding into
``testconfigs/routing/cicd_dc_bgpcpp_chronos.py``. This module stays as
a thin re-export so aggregator lists (``testconfigs/internal/all.py``
etc.) don't need to change import paths.
"""

from taac.testconfigs.routing.cicd_dc_bgpcpp_chronos import (
    CHRONOS_NODE_FSW_FUJI_TEST_CONFIG,
)


__all__ = ["CHRONOS_NODE_FSW_FUJI_TEST_CONFIG"]

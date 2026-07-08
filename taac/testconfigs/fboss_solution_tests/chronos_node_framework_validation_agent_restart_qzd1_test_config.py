# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1 (Wave 3B re-export shim).

Fast framework-validation TestConfig. Wave 3B moved the concrete binding
into ``testconfigs/routing/cicd_dc_bgpcpp_chronos.py``; this module is a
thin re-export so aggregator lists don't need to change import paths. See
the catalog file for the full docstring on scale reductions +
``ecmp_group_limit * 2 == ecmp_member_limit`` invariant.
"""

from taac.testconfigs.routing.cicd_dc_bgpcpp_chronos import (
    CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1_TEST_CONFIG,
)


__all__ = ["CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1_TEST_CONFIG"]

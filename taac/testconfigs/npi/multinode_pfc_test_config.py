# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
"""NPI Multi-Node PFC Test Configuration for IcePack (Tomahawk 6) GTSW.

Instantiates a multi-node PFC TestConfig against the shared
`gen_pfc_functionality_test_generic_4port_configs` factory in
``network_ai_test_configs``. Only the endpoints + port_speed change vs.
the reference `NSF_MULTI_NODE_PFC_TEST_CONFIG` / `MTIA_PFC_TEST_CONFIG` —
the traffic items, playbooks, HCs, and PFC-watchdog thresholds are all
derived by the factory from `port_speed`.

Topology: 3× IXIA sources on ``gtsw001.l1001.c085.ash6`` → 8× STSW spine
plane (``stsw001.s001..s008.l201.ash6``) → 1× IXIA destination on
``gtsw001.l1002.c085.ash6`` (sibling pod in the same cluster, sharing
the identical STSW plane). Backpressure propagates GTSW ← STSW ← GTSW
← Ixia across the fabric (single-node PFC would never leave the box).

Methodology doc:
https://docs.google.com/document/d/1XBnOhM67YkfaAJdvEIMehkY2PsGLsskZ-29ullzPlKA/edit?tab=t.0
"""

from taac.testbed_params.testbed_params_gtsw_th6_ash6_c085 import (
    ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_END_POINTS,
    ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_TRAFFIC_DST_ENDPOINTS,
    ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_TRAFFIC_SRC_ENDPOINTS,
)
from taac.testconfigs.fboss_solution_tests.network_ai_test_configs import (
    gen_pfc_functionality_test_generic_4port_configs,
)


# ---------------------------------------------------------------------------
# TestConfig instantiations
#
# All NPI multi-node PFC TestConfigs are constructed below by calling the
# shared `gen_pfc_functionality_test_generic_4port_configs` factory from
# ``network_ai_test_configs``. Adding a new NPI device under multi-node PFC
# coverage = add one factory call here + re-export from this package's
# `__init__.py`.
# ---------------------------------------------------------------------------

# NPI_DVT_ICEPACK_GTSW__MULTI_NODE_PFC_TEST_CONFIG — IcePack GTSW
# (`gtsw001.l1001.c085.ash6` sources + `gtsw001.l1002.c085.ash6`
# destination; both TH6 ASIC `ICECUBE800BC`; sibling pods in the same
# cluster peering with the identical 8-STSW l201.ash6 spine plane).
# `port_speed=200` matches the IXIA↔GTSW link profile currently in
# use on both DUTs (`PROFILE_200G_1_PAM4_RS544X2N_OPTICAL`,
# confirmed by Pavan 2026-07-06). The factory computes PFC-WD fps
# thresholds proportional to the port speed.
NPI_DVT_ICEPACK_GTSW__MULTI_NODE_PFC_TEST_CONFIG = (
    gen_pfc_functionality_test_generic_4port_configs(
        test_config_name="NPI_DVT_ICEPACK_GTSW__MULTI_NODE_PFC_TEST_CONFIG",
        endpoints=ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_END_POINTS,
        basset_pool="networkai.test",
        src_endpoints=ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_TRAFFIC_SRC_ENDPOINTS,
        dst_endpoints=ASH6_C085_GTSW_TH6_MULTI_NODE_PFC_TRAFFIC_DST_ENDPOINTS,
        port_speed=200,
        basic_port_configs=None,
    )
)

# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Routing testconfigs package.

Intentionally side-effect free.

Previously this ``__init__`` eagerly re-exported the aggregator test
configs from ``adhoc_cte_ucmp`` / ``cicd_ebb_int_tc`` /
``fboss_bgp_plus_plus_chronos_node_test_config``. That formed a
load-time cycle after Wave 2A hoisted the EBB helpers into
``testconfigs.routing.util.*``: any consumer of a util module would
trigger this ``__init__``, which pulled ``adhoc_cte_ucmp`` ->
``factories.cte_ucmp`` -> ``playbooks.playbook_definitions`` -> which
itself imports from ``testconfigs.routing.util``.

Consumers of the former re-exports now import from the specific member
module directly (e.g. ``from testconfigs.routing.cicd_ebb_int_tc
import ...``).
"""

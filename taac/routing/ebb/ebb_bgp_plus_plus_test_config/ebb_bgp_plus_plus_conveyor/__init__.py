# pyre-unsafe
"""EBB BGP++ Conveyor package.

Intentionally side-effect free -- the aggregated TestConfig list lives in
``conveyor_node_test_configs.py`` so importing a sibling constant from
``.conveyor_constants`` does NOT eagerly pull in every bag-conveyor
testconfig file (which would close a circular import via
``playbook_definitions`` <-> ``testconfigs.routing.ebb`` under strict Python).

Consumers that need the aggregated list should import it directly:

    from neteng.test_infra.dne.taac.routing.ebb.ebb_bgp_plus_plus_test_config \\
        .ebb_bgp_plus_plus_conveyor.conveyor_node_test_configs import (
            EBB_BGP_PLUS_PLUS_CONVEYOR_NODE_TEST_CONFIGS,
        )
"""

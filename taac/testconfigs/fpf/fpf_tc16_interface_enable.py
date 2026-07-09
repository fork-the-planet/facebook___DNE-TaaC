# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC16: GTSW<->GPU Interface Enable (link-event).

Enables (no-shut) the GTSW interface(s) of the circuits and validates that the
post-checks match stable state exactly — enable is an expected, non-disruptive
event, so nothing should regress. Reuses the stable-state v2 playbook contract.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc16_interface_enable \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_set_interface_admin_step,
    create_longevity_step,
)
from taac.task_definitions import (
    create_fpf_inject_vf_groups_task,
    create_fpf_restart_service_task,
    create_fpf_start_collectors_task,
    create_fpf_start_ib_traffic_task,
    create_fpf_stop_collectors_task,
    create_fpf_stop_ib_traffic_task,
    create_fpf_withdraw_vf_groups_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALL_LANES,
    ALL_STSWS,
    ALLOW_BASELINE_FAILURES,
    Circuit,
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    disable_interfaces_by_device,
    fpf_rf_vf_groups,
    fpf_vf_injection_groups,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    TRIGGER_STSWS,
    VF_COLLECTOR_SUBNET,
    VF_GROUP_PREFIX_COUNT,
)
from taac.test_as_a_config.types import TestConfig

# 8-plane VF-group injection (VF1 5000:dd on s001-s004 = planes 0-3, VF2 5000:ee
# on s005-s008 = planes 4-7); injected once by the setup task, withdrawn in
# teardown, so the playbook passes skip_injection=True.
INJECTION_GROUPS = fpf_vf_injection_groups()
RF_VF_GROUPS = fpf_rf_vf_groups()
PREFIX_COUNT = VF_GROUP_PREFIX_COUNT
INJECT_SETTLE_SEC = 300
INJECTED_LANES = ALL_LANES
STABILIZATION_DELAY_SEC = 300

CIRCUITS = [
    Circuit(
        a_end_device=OBSERVER_GTSWS[0],
        a_end_interface="eth1/41/5",
        z_end_device=GPU_HOSTS[0],
        z_end_gpu_id=0,
    ),
]

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]
HRT_MEMORY_HOSTS = ["rtptest1544.mwg2", "rtptest1599.mwg2"]
IB_TRAFFIC_SERVER = GPU_HOSTS[0]
IB_TRAFFIC_CLIENTS = [GPU_HOSTS[1]]
SPRAY_HOSTS = [IB_TRAFFIC_SERVER, *IB_TRAFFIC_CLIENTS]


def _enable_steps(circuits: list[Circuit]) -> list:
    """Thrift-based held enable (no-shut) of the A-end interface(s) on the DUT."""
    steps = []
    for dev, intfs in disable_interfaces_by_device(circuits).items():
        steps.append(
            create_fpf_set_interface_admin_step(
                interfaces=intfs,
                enable=True,
                description=f"Enable {intfs} on {dev} (thrift admin state)",
            )
        )
    return steps


def create_fpf_tc16_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    spray = None if skip_ssh else SPRAY_HOSTS
    playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=[
            *_enable_steps(CIRCUITS),
            create_longevity_step(
                duration=180,
                description="Settle after enable; expect stable state",
            ),
        ],
        soak_duration_sec=0,
        stabilization_delay_sec=STABILIZATION_DELAY_SEC,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc16_interface_enable",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=True,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        # Interface enabled → every plane UP on the GPU's hrtctl plane-status.
        plane_status_check=True,
        # Check all 8 injected lanes (not just the default [0,1]).
        lanes=INJECTED_LANES,
        # Prefixes injected once by the setup task (8-STSW split-per-VF).
        skip_injection=True,
        rf_vf_groups=RF_VF_GROUPS,
    )

    setup_tasks = []
    teardown_tasks = []
    if not skip_ssh:
        setup_tasks.append(
            create_fpf_start_ib_traffic_task(
                server=IB_TRAFFIC_SERVER, clients=IB_TRAFFIC_CLIENTS
            )
        )
        teardown_tasks.append(
            create_fpf_stop_ib_traffic_task(
                server=IB_TRAFFIC_SERVER, clients=IB_TRAFFIC_CLIENTS
            )
        )
    setup_tasks.append(
        create_fpf_start_collectors_task(
            gtsws=OBSERVER_GTSWS,
            hosts=GPU_HOSTS,
            subnet_prefix=VF_COLLECTOR_SUBNET,
            prod_prefixes=PROD_PREFIXES,
            prod_prefix_host=PROD_PREFIX_HOST,
            prod_prefix_device_id=PROD_PREFIX_DEVICE_ID,
            fsdb_mode=FSDB_COLLECTOR_MODE,
            allow_baseline_failures=ALLOW_BASELINE_FAILURES,
            rf_vf_groups=RF_VF_GROUPS,
        )
    )
    # Inject the two VF prefix groups on all 8 STSWs once (after collectors start).
    setup_tasks.append(
        create_fpf_inject_vf_groups_task(
            groups=INJECTION_GROUPS,
            settle_sec=INJECT_SETTLE_SEC,
        )
    )
    teardown_tasks.append(create_fpf_withdraw_vf_groups_task(groups=INJECTION_GROUPS))
    # Robust catch-all: restart bgpd on all 8 STSWs to clear injected + any
    # leftover prefixes (reloads persistent config).
    teardown_tasks.append(
        create_fpf_restart_service_task(devices=ALL_STSWS, service="BGP")
    )
    teardown_tasks.append(
        create_fpf_stop_collectors_task(
            trigger_stsws=TRIGGER_STSWS,
            withdraw=False,
            community_list=DEFAULT_COMMUNITY_LIST,
        )
    )

    return TestConfig(
        name="fpf_tc16_interface_enable",
        endpoints=create_fpf_endpoints(stsws=ALL_STSWS),
        setup_tasks=setup_tasks,
        teardown_tasks=teardown_tasks,
        playbooks=[playbook],
    )


TEST_CONFIG = create_fpf_tc16_test_config()

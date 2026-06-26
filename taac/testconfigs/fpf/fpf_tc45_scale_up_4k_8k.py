# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC45: STSW prefix scale-UP 4k -> 8k (then teardown to nothing).

Ramps the injected BGP++ scale on the trigger STSWs from 4,000 -> 8,000
prefixes, then validates the 8k steady state with the SAME stable-state signals
as fpf_stress_test_config. Teardown withdraws all 8k ("to nothing").

Two-playbook structure:
  1. Disruption-only playbook (NO checks): inject 4,000 prefixes, settle, then
     inject up to 8,000 prefixes (the 4k->8k ramp), settle.
  2. Stable-state v2 hardening playbook @ prefix_count=8,000: re-asserts the 8k
     injection (idempotent) and validates the full stable-state contract
     (convergence, HRT bulk/remote-failure/prod-prefix, FSDB session, host-spray,
     HRT mem/driver) at the 8k steady state.

ASSUMPTION: "to nothing" = the teardown withdrawal of all 8k prefixes; the
stable-state signals are validated at the 8k peak.

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc45_scale_up_4k_8k \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_bgp_prefix_injection_step,
    create_longevity_step,
)
from taac.task_definitions import (
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALLOW_BASELINE_FAILURES,
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    DEFAULT_SUBNET_PREFIX,
    EXPECTED_FSDB_SESSION_COUNT,
    fpf_clean_slate_setup_task,
    fpf_ib_traffic_tasks,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    HRT_MEMORY_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config.types import TestConfig

SCALE_LOW = 4000
SCALE_HIGH = 8000
SETTLE_SEC = 120
LONGEVITY_SEC = 300

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc45_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    # Scale bump is expected to be EXACTLY stable-state throughout — so playbook 1
    # runs the full stable-state v2 contract with the 4k->8k ramp as its
    # disruption steps (no disruption-specific relaxations).
    disrupt_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=0,
        stabilization_delay_sec=SETTLE_SEC,
        prefix_count=SCALE_HIGH,
        community_list=DEFAULT_COMMUNITY_LIST,
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        disruption_steps=[
            create_fpf_bgp_prefix_injection_step(
                devices=TRIGGER_STSWS,
                count=SCALE_LOW,
                community_list=DEFAULT_COMMUNITY_LIST,
                description=f"Inject {SCALE_LOW} prefixes on the trigger STSWs",
            ),
            create_longevity_step(
                duration=SETTLE_SEC,
                description=f"Settle {SETTLE_SEC}s at {SCALE_LOW} prefixes",
            ),
            create_fpf_bgp_prefix_injection_step(
                devices=TRIGGER_STSWS,
                count=SCALE_HIGH,
                community_list=DEFAULT_COMMUNITY_LIST,
                description=f"Scale up to {SCALE_HIGH} prefixes on the trigger STSWs",
            ),
            create_longevity_step(
                duration=SETTLE_SEC,
                description=f"Settle {SETTLE_SEC}s at {SCALE_HIGH} prefixes",
            ),
        ],
        playbook_name="fpf_tc45_scale_up_4k_8k_disrupt",
    )

    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SEC,
        stabilization_delay_sec=SETTLE_SEC,
        prefix_count=SCALE_HIGH,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc45_scale_up_4k_8k_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
    )

    return TestConfig(
        name="fpf_tc45_scale_up_4k_8k",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[
            fpf_clean_slate_setup_task(),
            *ib_setup,
            create_fpf_start_collectors_task(
                gtsws=OBSERVER_GTSWS,
                hosts=GPU_HOSTS,
                subnet_prefix=DEFAULT_SUBNET_PREFIX,
                prod_prefixes=PROD_PREFIXES,
                prod_prefix_host=PROD_PREFIX_HOST,
                prod_prefix_device_id=PROD_PREFIX_DEVICE_ID,
                fsdb_mode=FSDB_COLLECTOR_MODE,
                allow_baseline_failures=ALLOW_BASELINE_FAILURES,
            ),
        ],
        teardown_tasks=[
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                prefix_count=SCALE_HIGH,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc45_test_config()

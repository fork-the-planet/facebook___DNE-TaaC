# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC46: STSW prefix scale-DOWN 8k -> 4k (companion to tc45).

Injects 8,000 prefixes, then scales DOWN to 4,000 by withdrawing the UPPER half
(prefix indices 4000..7999, i.e. base 5000:dd:fa0::/64 — 0xFA0 = 4000), leaving
the lower 4,000 (indices 0..3999). The 4k steady state is then validated with the
SAME stable-state signals as fpf_stress_test_config.

Withdrawing the UPPER half (not the lower) is deliberate: the v2 longevity
playbook re-injects prefix_count=4,000 from the base (indices 0..3999), which
exactly matches the surviving lower half — so there is no count mismatch.

Two-playbook structure:
  1. Disruption-only playbook (NO checks): inject 8,000, settle, withdraw the
     upper 4,000 (-> 4,000 remain), settle.
  2. Stable-state v2 hardening playbook @ prefix_count=4,000: re-asserts the
     lower-4k injection (idempotent) and validates the full stable-state
     contract at the 4k steady state.

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc46_scale_down_8k_4k \\
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

SCALE_HIGH = 8000
SCALE_LOW = 4000
# Upper-half base: prefix index 4000 = 0xFA0 -> 5000:dd:fa0::/64.
UPPER_HALF_BASE = "5000:dd:fa0::/64"
SETTLE_SEC = 120
LONGEVITY_SEC = 300

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc46_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    # Scale change is expected to be EXACTLY stable-state throughout — playbook 1
    # runs the full stable-state v2 contract with the 8k->4k ramp as its
    # disruption steps (validates the 4k end state).
    disrupt_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=0,
        stabilization_delay_sec=SETTLE_SEC,
        prefix_count=SCALE_LOW,
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
                count=SCALE_HIGH,
                community_list=DEFAULT_COMMUNITY_LIST,
                description=f"Inject {SCALE_HIGH} prefixes on the trigger STSWs",
            ),
            create_longevity_step(
                duration=SETTLE_SEC,
                description=f"Settle {SETTLE_SEC}s at {SCALE_HIGH} prefixes",
            ),
            create_fpf_bgp_prefix_injection_step(
                devices=TRIGGER_STSWS,
                prefix_base=UPPER_HALF_BASE,
                count=SCALE_LOW,
                community_list=DEFAULT_COMMUNITY_LIST,
                withdraw_only=True,
                description=(
                    f"Scale down to {SCALE_LOW}: withdraw the upper {SCALE_LOW} "
                    f"prefixes (base {UPPER_HALF_BASE})"
                ),
            ),
            create_longevity_step(
                duration=SETTLE_SEC,
                description=f"Settle {SETTLE_SEC}s at {SCALE_LOW} prefixes",
            ),
        ],
        playbook_name="fpf_tc46_scale_down_8k_4k_disrupt",
    )

    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SEC,
        stabilization_delay_sec=SETTLE_SEC,
        prefix_count=SCALE_LOW,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc46_scale_down_8k_4k_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
    )

    return TestConfig(
        name="fpf_tc46_scale_down_8k_4k",
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
                prefix_count=SCALE_LOW,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc46_test_config()

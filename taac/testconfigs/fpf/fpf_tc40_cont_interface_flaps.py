# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC40: Continuous interface flaps across ALL 8 GTSWs facing one GPU host.

Picks ONE rtptest GPU host (GPU_HOSTS[0]) and, on every one of the 8 GTSWs that
host connects to (gtsw001-008.l1002.c087.mwg2), resolves the local interfaces
facing that host via LLDP and rapidly flaps them. All 8 GTSWs flap IN PARALLEL
(asyncio.gather inside one custom step) with a 7s up / 7s down symmetric cycle,
for 15 minutes — maximum cross-plane chaos on the chosen host. After the flaps
stop, a stable-state longevity playbook (same expectations as
fpf_stress_test_config) validates full recovery.

Two-playbook "longevity-anchored health check" pattern:
  1. Disruption-only playbook (NO checks): the multi-GTSW parallel flap (900s),
     then a 300s longevity settle.
  2. Stable-state v2 hardening playbook (soak 300s): every stable-state health
     check anchors at LONGEVITY START with the SAME expectations as the stress
     config; the noisy flap window is excluded.

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc40_cont_interface_flaps \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_disrupt_window_playbook,
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_bgp_prefix_injection_step,
    create_fpf_multi_gtsw_rapid_flap_step,
    create_longevity_step,
)
from taac.task_definitions import (
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
)
from taac.testconfigs.fpf.fpf_flap_contract import (
    build_flap_disrupt_postchecks,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALL_GTSWS,
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
    IB_TRAFFIC_CLIENTS,
    IB_TRAFFIC_SERVER,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config.types import TestConfig

PREFIX_COUNT = 1000
# 15-min flap window with a symmetric 7s up / 7s down cycle.
FLAP_DURATION_SEC = 900
FLAP_UP_SEC = 7
FLAP_DOWN_SEC = 7
LONGEVITY_SEC = 300

# The single GPU host whose facing links are flapped across all 8 GTSWs.
FLAP_HOST = GPU_HOSTS[0]

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc40_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disrupt_playbook = create_fpf_disrupt_window_playbook(
        postchecks=build_flap_disrupt_postchecks(
            observer_gtsws=OBSERVER_GTSWS,
            hrt_memory_hosts=HRT_MEMORY_HOSTS,
            prefix_count=PREFIX_COUNT,
            skip_ssh=skip_ssh,
        ),
        disruption_steps=[
            create_fpf_bgp_prefix_injection_step(
                devices=TRIGGER_STSWS,
                count=PREFIX_COUNT,
                community_list=DEFAULT_COMMUNITY_LIST,
                description=f"Inject {PREFIX_COUNT} test prefixes on the trigger STSWs",
            ),
            create_longevity_step(
                duration=120,
                description="Stabilize 120s before flaps (prefixes converge)",
            ),
            create_fpf_multi_gtsw_rapid_flap_step(
                gtsws=ALL_GTSWS,
                neighbor_hosts=[FLAP_HOST],
                uniform_interface_discovery=True,
                duration_sec=FLAP_DURATION_SEC,
                flap_up_time_sec=FLAP_UP_SEC,
                flap_down_time_sec=FLAP_DOWN_SEC,
                description=(
                    f"Parallel rapid-flap links facing {FLAP_HOST} across "
                    f"{len(ALL_GTSWS)} GTSWs for {FLAP_DURATION_SEC}s "
                    f"(up={FLAP_UP_SEC}s/down={FLAP_DOWN_SEC}s)"
                ),
            ),
            create_longevity_step(
                duration=LONGEVITY_SEC,
                description=f"Settle {LONGEVITY_SEC}s after flaps stop",
            ),
        ],
        playbook_name="fpf_tc40_cont_interface_flaps_disrupt",
    )

    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc40_cont_interface_flaps_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        restart_ib_traffic_server=None if skip_ssh else IB_TRAFFIC_SERVER,
        restart_ib_traffic_clients=None if skip_ssh else IB_TRAFFIC_CLIENTS,
    )

    return TestConfig(
        name="fpf_tc40_cont_interface_flaps",
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
                prefix_count=PREFIX_COUNT,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc40_test_config()

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC49: SIGKILL bgpd every 15s for 10 minutes on the DUT GTSW.

gtsw001 owns lane 0. Killing bgpd takes gtsw001's eBGP sessions + RIB down and
churns the lane-0 routes (packet loss on lane 0 during the kill), but fsdb stays
up so the HRT FSDB sessions stay CONNECTED (32).

Two-playbook structure:
  Playbook 1 (disrupt-window): inject + stabilize + record + kill loop + settle,
    then assert the DISRUPTED-STATE CONTRACT via
    ``build_kill_disrupt_postchecks(killed_service="bgpd")`` — systemctl/
    unclean-exit minus bgpd, HRT FSDB sessions stable 32 (fsdb up), HRT mem/driver
    healthy, in_dst_null/in_discard spike >=10k while congestion==0, beth1-3 keep
    spraying while beth0 (lane 0) is exempt. BGP establish / RIB convergence are
    NOT asserted in this window (bgpd is the killed service). See fpf_kill_contract.py.
  Playbook 2 (stable-state longevity, 5 min): full stable-state contract,
    convergence_settle_sec excludes the kill→recovery transient.

Headless run kills bgpd via the driver crash path — kick off from a
Kerberos-ticketed terminal (or set TAAC_SSH_VIA_LAB_SSH=1).

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc49_bgp_kill_5s_10min \\
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
    create_fpf_record_disruption_time_step,
    create_fpf_repeated_service_crash_step,
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
from taac.testconfigs.fpf.fpf_kill_contract import (
    build_kill_disrupt_postchecks,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

PREFIX_COUNT = 1000
STABILIZATION_DELAY_SEC = 120
KILL_EVERY_SEC = 15  # graceful loop-kill cadence (service recovers between kills)
KILL_DURATION_SEC = 600  # 10 min
STABLE_AFTER_KILL_SEC = 120
LONGEVITY_SOAK_SEC = 300
LONGEVITY_SETTLE_SEC = 60
SESSION_LOOKBACK_SEC = 1000

DUT_GTSW = OBSERVER_GTSWS[0]
KILLED_SERVICE = "bgpd"
KILL_SERVICE = taac_types.Service.BGP

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc49_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disrupt_steps = [
        create_fpf_bgp_prefix_injection_step(
            devices=TRIGGER_STSWS,
            count=PREFIX_COUNT,
            community_list=DEFAULT_COMMUNITY_LIST,
            description=f"Inject {PREFIX_COUNT} test prefixes on the trigger STSWs",
        ),
        create_longevity_step(
            duration=STABILIZATION_DELAY_SEC,
            description=f"Stabilize {STABILIZATION_DELAY_SEC}s before the kill loop",
        ),
        create_fpf_record_disruption_time_step(
            description="Record bgpd-kill disruption time"
        ),
        create_fpf_repeated_service_crash_step(
            service=KILL_SERVICE,
            every_sec=KILL_EVERY_SEC,
            duration_sec=KILL_DURATION_SEC,
            device_regexes=[DUT_GTSW],
            description=(
                f"SIGKILL {KILL_SERVICE.name} every {KILL_EVERY_SEC}s for "
                f"{KILL_DURATION_SEC}s on {DUT_GTSW}"
            ),
        ),
        create_longevity_step(
            duration=STABLE_AFTER_KILL_SEC,
            description=f"Stable {STABLE_AFTER_KILL_SEC}s after the kill loop stops",
        ),
    ]

    disrupt_playbook = create_fpf_disrupt_window_playbook(
        playbook_name="fpf_tc49_bgp_kill_5s_10min_disrupt",
        disruption_steps=disrupt_steps,
        postchecks=build_kill_disrupt_postchecks(
            killed_service=KILLED_SERVICE,
            observer_gtsws=OBSERVER_GTSWS,
            hrt_memory_hosts=HRT_MEMORY_HOSTS,
            spray_hosts=spray,
            kill_duration_sec=KILL_DURATION_SEC,
            prefix_count=PREFIX_COUNT,
            skip_ssh=skip_ssh,
            expected_fsdb_total=EXPECTED_FSDB_SESSION_COUNT,
            session_lookback_sec=SESSION_LOOKBACK_SEC,
        ),
    )

    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SOAK_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc49_bgp_kill_5s_10min_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        convergence_settle_sec=LONGEVITY_SETTLE_SEC,
    )

    return TestConfig(
        name="fpf_tc49_bgp_kill_5s_10min",
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
                enable_fsdb_session_collector=True,
                fsdb_session_host=GPU_HOSTS[0],
                fsdb_session_expected=EXPECTED_FSDB_SESSION_COUNT,
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


TEST_CONFIG = create_fpf_tc49_test_config()

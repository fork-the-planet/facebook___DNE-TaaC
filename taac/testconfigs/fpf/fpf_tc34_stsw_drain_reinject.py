# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC34: Cascaded STSW Plane Drain + GTSW Device Drain — case 1 (DRAIN).

Soft-drains an STSW plane via the on-box LOCAL_DRAINER, then re-injects the FPF
prefixes on the trigger STSWs (the re-injected prefixes carry an extra drain-
marker community so the drained plane is depreferenced rather than withdrawn).
After a 5-minute longevity settle, the steady state is validated against the
GTSW-DEVICE-DRAIN expectation contract (the same observable contract as a GTSW
device drain, TC19): control plane stays up, no packet loss, and the impacted
plane shows DRAINED (not unreachable) on the GPU hrtctl plane-status.

Two-playbook "longevity-anchored health check" pattern:
  1. Disruption-only playbook (NO checks): the STSW drain+reinject step pair,
     then a 300s longevity settle.
  2. v2 hardening playbook configured with the DRAIN expectation contract
     (plane_status_check + prod_prefix_recovery contract anchored at the
     longevity start). HCs measure only the post-drain steady state.

ASSUMPTIONS (documented):
  - drain_community: the canonical FPF STSW drain community is "65446:10"
    (confirmed by the test owner). Re-injecting the prefixes with this extra
    community on STSW drain marks the path as drained/depreferred.
  - gtsw-drain expectation mapping: there is no dedicated "stsw-plane-drain"
    expectation playbook helper, so we reuse create_fpf_hardening_playbook_v2
    with the SAME drain-appropriate knobs TC19 (fpf_tc19_device_drain) uses for
    its recovery/expectation playbook: use_bgp_snapshot, plane_status_check,
    prod_prefix_recovery + local_prod_prefixes + impacted_planes_by_host, with
    the FSDB-session precheck skipped (the lab may be in graceful-restart hold).

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc34_stsw_drain_reinject \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_disruption_only_playbook,
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_stsw_drain_and_reinject_steps,
    create_longevity_step,
)
from taac.task_definitions import (
    create_fpf_inject_vf_groups_task,
    create_fpf_restart_service_task,
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
    create_fpf_withdraw_vf_groups_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALL_LANES,
    ALL_STSWS,
    ALLOW_BASELINE_FAILURES,
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    EXPECTED_FSDB_SESSION_COUNT,
    fpf_ib_traffic_tasks,
    fpf_rf_vf_groups,
    fpf_vf_injection_groups,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    HRT_MEMORY_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    VF_COLLECTOR_SUBNET,
    VF_GROUP_PREFIX_COUNT,
)
from taac.test_as_a_config.types import TestConfig

# 8-plane VF-group injection (VF1 5000:dd on s001-s004 = planes 0-3, VF2 5000:ee
# on s005-s008 = planes 4-7), injected once by the setup task and withdrawn in
# teardown. The drain step below re-injects the same per-group count
# (VF_GROUP_PREFIX_COUNT) across all 8 STSWs with the drain-marker community.
INJECTION_GROUPS = fpf_vf_injection_groups()
RF_VF_GROUPS = fpf_rf_vf_groups()
PREFIX_COUNT = VF_GROUP_PREFIX_COUNT
INJECT_SETTLE_SEC = 300
INJECTED_LANES = ALL_LANES
TRIGGER_STSWS = ALL_STSWS
LONGEVITY_SEC = 300

# STSW plane to drain (the first STSW plane: stsw001.s001.l202.mwg2).
DRAIN_TARGET_STSW = TRIGGER_STSWS[0]
# Canonical FPF STSW drain community appended to the re-injected prefixes.
DRAIN_COMMUNITY = "65446:10"

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]

# The STSW drain depreferences the lane that STSW serves. stsw001.s001 -> lane 0,
# the same plane TC19 monitors on GPU0 of the first GPU host.
IMPACTED_PLANES_BY_HOST = {PROD_PREFIX_HOST: [0]}


def create_fpf_tc34_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disrupt_steps = [
        *create_fpf_stsw_drain_and_reinject_steps(
            stsw=DRAIN_TARGET_STSW,
            drained=True,
            trigger_stsws=TRIGGER_STSWS,
            prefix_count=PREFIX_COUNT,
            community_list=DEFAULT_COMMUNITY_LIST,
            drain_community=DRAIN_COMMUNITY,
        ),
        create_longevity_step(
            duration=LONGEVITY_SEC,
            description=(
                f"Settle {LONGEVITY_SEC}s after STSW {DRAIN_TARGET_STSW} drain + "
                "reinject"
            ),
        ),
    ]

    disrupt_playbook = create_fpf_disruption_only_playbook(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=disrupt_steps,
        playbook_name="fpf_tc34_stsw_drain_reinject_disrupt",
    )

    # Drain-expectation longevity playbook: mirrors TC19's device-drain
    # expectation/recovery contract. HCs anchor at this playbook's start.
    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc34_stsw_drain_reinject_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        use_bgp_snapshot=True,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        skip_fsdb_session_precheck=True,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        # Drain contract: impacted plane goes DRAINED (not unreachable) on the
        # GPU hrtctl plane-status; mirror TC19's plane/prod-prefix expectations.
        plane_status_check=True,
        prod_prefix_recovery=True,
        local_prod_prefixes=PROD_PREFIXES,
        impacted_planes_by_host=IMPACTED_PLANES_BY_HOST,
        # Check all 8 injected lanes (not just the default [0,1]).
        lanes=INJECTED_LANES,
        # Prefixes injected once by the setup task (8-STSW split-per-VF); the
        # drain step re-injects them with the drain-marker community.
        skip_injection=True,
        rf_vf_groups=RF_VF_GROUPS,
    )

    return TestConfig(
        name="fpf_tc34_stsw_drain_reinject",
        endpoints=create_fpf_endpoints(stsws=ALL_STSWS),
        setup_tasks=[
            *ib_setup,
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
            ),
            create_fpf_inject_vf_groups_task(
                groups=INJECTION_GROUPS,
                settle_sec=INJECT_SETTLE_SEC,
            ),
        ],
        teardown_tasks=[
            create_fpf_withdraw_vf_groups_task(groups=INJECTION_GROUPS),
            # Robust catch-all: restart bgpd on all 8 STSWs to clear injected +
            # any leftover prefixes (reloads persistent config).
            create_fpf_restart_service_task(devices=ALL_STSWS, service="BGP"),
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                withdraw=False,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc34_test_config()

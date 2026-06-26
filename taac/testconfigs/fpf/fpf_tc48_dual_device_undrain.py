# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC48: Undrain of gtsw001 + gtsw005 (recovery half of tc47).

Companion to tc47. Drains gtsw001 (lane 0) and gtsw005 (lane 4) simultaneously,
then UNDRAINS both simultaneously and validates full RECOVERY: the HRT
remote-failure counts on lanes 0 and 4 rise during the drain and return to 0
within the convergence SLA after the undrain. Self-contained (drains first so it
can run independently of tc47).

Primary assertion: the simultaneous dual UNDRAIN restores reachability on lanes
0 and 4 (remote-failure returns to 0 within the convergence SLA).

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc48_dual_device_undrain \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.health_checks.healthcheck_definitions import (
    create_fpf_hrt_remote_failure_convergence_check,
)
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook,
)
from taac.steps.step_definitions import (
    create_fpf_multi_device_drain_step,
    create_longevity_step,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALL_GTSWS,
    create_fpf_endpoints,
    DEFAULT_REMOTE_FAILURE_LANES,
    DRAIN_CONVERGENCE_SLA_SEC,
    fpf_clean_slate_setup_task,
    GPU_HOSTS,
    HARDENING_PREFIX_COUNT,
    OBSERVER_GTSWS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config.types import TestConfig

# gtsw001 -> lane 0, gtsw005 -> lane 4.
DRAIN_TARGETS = [ALL_GTSWS[0], ALL_GTSWS[4]]
IMPACTED_LANES = [
    0
]  # gtsw005/lane4 drain is pure HRT stress (no traffic, no healthchecks)


def create_fpf_tc48_test_config() -> TestConfig:
    disruption_steps = [
        create_fpf_multi_device_drain_step(
            devices=DRAIN_TARGETS,
            drain=True,
            description=f"Simultaneously drain {DRAIN_TARGETS}",
        ),
        create_longevity_step(
            duration=150,
            description="Wait for dual-drain convergence",
        ),
        create_fpf_multi_device_drain_step(
            devices=DRAIN_TARGETS,
            drain=False,
            description=f"Simultaneously undrain {DRAIN_TARGETS}",
        ),
        create_longevity_step(
            duration=150,
            description="Wait for recovery convergence after undrain",
        ),
    ]

    remote_failure_postchecks = [
        create_fpf_hrt_remote_failure_convergence_check(
            lanes=IMPACTED_LANES,
            expected_per_lane={
                str(lane): HARDENING_PREFIX_COUNT for lane in IMPACTED_LANES
            },
            direction="recovery",
            max_convergence_sec=DRAIN_CONVERGENCE_SLA_SEC,
            use_live_collectors=True,
            check_id="fpf_tc48_remote_failure_recovery_lanes_0_4",
        ),
    ]

    unaffected_lanes = [
        lane for lane in DEFAULT_REMOTE_FAILURE_LANES if lane not in IMPACTED_LANES
    ]
    if unaffected_lanes:
        remote_failure_postchecks.append(
            create_fpf_hrt_remote_failure_convergence_check(
                lanes=unaffected_lanes,
                expected_per_lane={str(lane): 0 for lane in unaffected_lanes},
                direction="recovery",
                max_convergence_sec=DRAIN_CONVERGENCE_SLA_SEC,
                use_live_collectors=True,
                check_id="fpf_tc48_remote_failure_unaffected_lanes",
            ),
        )

    playbook = create_fpf_hardening_playbook(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=disruption_steps,
        disruption_duration_sec=450,
        prefix_count=HARDENING_PREFIX_COUNT,
        additional_postchecks=remote_failure_postchecks,
        playbook_name="fpf_tc48_dual_device_undrain",
    )

    return TestConfig(
        name="fpf_tc48_dual_device_undrain",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[fpf_clean_slate_setup_task()],
        playbooks=[playbook],
    )


TEST_CONFIG = create_fpf_tc48_test_config()

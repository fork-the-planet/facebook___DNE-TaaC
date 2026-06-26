# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC47: Simultaneous device drain of gtsw001 + gtsw005 (lanes 0 and 4).

Soft-drains gtsw001 (lane 0) and gtsw005 (lane 4) in the l1002.c087.mwg2 pod AT
THE SAME TIME (one custom step gathers both drains in parallel). The HRT
remote-failure collector then observes negative-route counts rising from 0 to the
injected prefix count on BOTH drained lanes, while the other lanes stay at 0.
Self-cleaning: undrains both at the end so the testbed is left healthy.

Primary assertion: the simultaneous dual drain depreferences lanes 0 and 4
(remote-failure rises on both within the convergence SLA).

Usage:
  TAAC_SSH_VIA_LAB_SSH=1 buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc47_dual_device_drain \\
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


def create_fpf_tc47_test_config() -> TestConfig:
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
        # Self-clean: undrain both so the testbed is left healthy.
        create_fpf_multi_device_drain_step(
            devices=DRAIN_TARGETS,
            drain=False,
            description=f"Undrain {DRAIN_TARGETS} (cleanup)",
        ),
        create_longevity_step(
            duration=150,
            description="Wait for recovery convergence",
        ),
    ]

    remote_failure_postchecks = [
        create_fpf_hrt_remote_failure_convergence_check(
            lanes=IMPACTED_LANES,
            expected_per_lane={
                str(lane): HARDENING_PREFIX_COUNT for lane in IMPACTED_LANES
            },
            direction="drain",
            max_convergence_sec=DRAIN_CONVERGENCE_SLA_SEC,
            use_live_collectors=True,
            check_id="fpf_tc47_remote_failure_drain_lanes_0_4",
        ),
        create_fpf_hrt_remote_failure_convergence_check(
            lanes=IMPACTED_LANES,
            expected_per_lane={
                str(lane): HARDENING_PREFIX_COUNT for lane in IMPACTED_LANES
            },
            direction="recovery",
            max_convergence_sec=DRAIN_CONVERGENCE_SLA_SEC,
            use_live_collectors=True,
            check_id="fpf_tc47_remote_failure_recovery_lanes_0_4",
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
                direction="drain",
                max_convergence_sec=DRAIN_CONVERGENCE_SLA_SEC,
                use_live_collectors=True,
                check_id="fpf_tc47_remote_failure_unaffected_lanes",
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
        playbook_name="fpf_tc47_dual_device_drain",
    )

    return TestConfig(
        name="fpf_tc47_dual_device_drain",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[fpf_clean_slate_setup_task()],
        playbooks=[playbook],
    )


TEST_CONFIG = create_fpf_tc47_test_config()

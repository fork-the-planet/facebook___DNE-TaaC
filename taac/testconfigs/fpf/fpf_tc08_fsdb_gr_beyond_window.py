# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""TC8: FSDB GR — Expiry Beyond GR Window.

Unlike the loop-kill tests (tc51), this STOPS fsdb continuously on the DUT GTSW
(gtsw001 = lane 0) and holds it down past the ~120s FSDB graceful-restart hold.
Because HRT's disconnected_gr_hold timer only resets when HRT RECONNECTS, a
continuous stop lets the timer EXPIRE → lane-0 routes are purged → beth0 egress
DRAINS on the impacted GPU host. Other lanes (beth1-3) are unaffected.

Stop duration = 240s (120s GR window + 120s settle), so we stop at least 2 min
past the 120s mark; the host-spray check then reads lane 0 over the post-GR tail
([disruption+120, disruption+240]) with the default avg(1m),latest transform, so
the "latest 1-minute" reading reflects the fully-drained state, not the GR-hold
transient. Within-window behavior (stop < 120s, lane 0 keeps spraying) is the
tc7 companion.

Prefixes are injected on ALL 8 STSWs, split per VF group (VF1 5000:dd on
s001-s004 = planes 0-3, VF2 5000:ee on s005-s008 = planes 4-7), via the
fpf_inject_bgp_prefixes SETUP TASK so the netcastle run is self-contained. The
fabric is VF-segregated, so each observer GTSW / lane sees only its own VF
group's count: PREFIX_COUNT = VF_GROUP_PREFIX_COUNT. Collector subnet is 5000::/16
to count both groups. The playbook passes skip_injection=True (no in-playbook
inject) and checks all 8 lanes.

Requires ib_write_bw traffic flowing so the per-lane beth egress is observable.
"""

from taac.health_checks.healthcheck_definitions import (
    create_fpf_host_spray_check,
)
from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_record_disruption_time_step,
    create_longevity_step,
    create_service_convergence_step,
    create_service_interruption_step,
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
    TRIGGER_STSWS,
    VF_COLLECTOR_SUBNET,
    VF_GROUP_PREFIX_COUNT,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

INJECTION_GROUPS = fpf_vf_injection_groups()
RF_VF_GROUPS = fpf_rf_vf_groups()
PREFIX_COUNT = VF_GROUP_PREFIX_COUNT
INJECT_SETTLE_SEC = 300
INJECTED_LANES = ALL_LANES
STABILIZATION_DELAY_SEC = 300

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]

GR_WINDOW_SEC = 120
# Stop >= 2 min past the 120s GR mark so lane 0 is fully drained + settled.
STOP_DURATION_SEC = GR_WINDOW_SEC + 120  # 240s
SPRAY_FLOOR_GBPS = 75.0
SPRAY_IMPACTED_MAX_GBPS = 10.0


def create_fpf_tc08_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disruption_steps = [
        create_fpf_record_disruption_time_step(
            description="Record FSDB-stop disruption time (anchors the spray window)"
        ),
        create_service_interruption_step(
            service=taac_types.Service.FSDB,
            trigger=taac_types.ServiceInterruptionTrigger.SYSTEMCTL_STOP,
            description="Stop FSDB on DUT GTSW (held down past GR window)",
        ),
        create_longevity_step(
            duration=STOP_DURATION_SEC,
            description=(
                f"Hold FSDB down {STOP_DURATION_SEC}s "
                f"(>{GR_WINDOW_SEC}s GR window — lane-0 routes purge, beth0 drains)"
            ),
        ),
        create_service_interruption_step(
            service=taac_types.Service.FSDB,
            trigger=taac_types.ServiceInterruptionTrigger.SYSTEMCTL_START,
            description="Restart FSDB on DUT GTSW after GR expiry",
        ),
        create_service_convergence_step(
            services=[taac_types.Service.FSDB],
            timeout=600,
            description="Wait for FSDB convergence after GR expiry recovery",
        ),
    ]

    postchecks = []
    if spray:
        # Over the POST-GR tail [disruption+120, disruption+240] (fsdb still
        # stopped), assert lane 0 (beth0) is DRAINED (<10 Gbps) on every spray
        # host while beth1-3 stay sprayed (>75 Gbps). window_offset_sec skips the
        # GR-hold transient; the default transform is avg(1m),latest so the
        # "latest 1m" reads the fully-drained state.
        postchecks.append(
            create_fpf_host_spray_check(
                hosts=SPRAY_HOSTS,
                min_egress_gbps=SPRAY_FLOOR_GBPS,
                impacted_lanes_by_host={h: ["beth0"] for h in SPRAY_HOSTS},
                impacted_max_gbps=SPRAY_IMPACTED_MAX_GBPS,
                window_from_disruption_time=True,
                window_offset_sec=GR_WINDOW_SEC,
                window_duration_sec=STOP_DURATION_SEC - GR_WINDOW_SEC,
                label=(
                    "[fsdb-stop >GR] lane0(beth0) drained <10G; lanes1-3 spray >75G"
                ),
                check_id="fpf_tc08_host_spray_lane0_drained",
            )
        )

    playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=disruption_steps,
        stabilization_delay_sec=STABILIZATION_DELAY_SEC,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        additional_postchecks=postchecks,
        playbook_name="fpf_tc08_fsdb_gr_beyond_window",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        # 8-plane: prefixes injected once by the setup task; check all 8 lanes.
        skip_injection=True,
        rf_vf_groups=RF_VF_GROUPS,
        lanes=INJECTED_LANES,
        # fsdb is GR-restarted (beyond the GR window) on the DUT GTSW; anchor
        # reconvergence on fsdb's restart. If fsdb does not bounce the BGP
        # sessions, convergence clamps to 0 — a clean pass. Scoped to the DUT.
        assert_bgp_reconvergence=True,
        reconvergence_service="fsdb",
        reconvergence_sla_sec=60.0,
        reconvergence_hosts=[OBSERVER_GTSWS[0]],
        # fsdb/HRT are coupled: the HRT FSDB-session census dips while fsdb
        # re-subscribes after the GR — expected, not a fault. Skip the postcheck
        # (precheck still asserts the 32/32 baseline).
        skip_fsdb_session_postcheck=True,
        # HRT negative-route count blips during the GR-beyond purge and clears
        # afterwards; assert only the last sample (reconverged by end), not
        # zero-across-the-whole-window.
        remote_failure_last_sample=True,
    )

    return TestConfig(
        name="fpf_tc08_fsdb_gr_beyond_window",
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
            create_fpf_restart_service_task(devices=ALL_STSWS, service="BGP"),
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                withdraw=False,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc08_test_config()

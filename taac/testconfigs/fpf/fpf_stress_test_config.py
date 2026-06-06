#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""FPF BGP Prefix Stress Test — TC1: Stable State Validation (minimal run).

Minimal collector-validation configuration: five long-lived collectors run
continuously and are each validated by exactly one postcheck health check, so
collectors and validating health checks are 1:1.

  Collector              ->  Validating health check
  ---------------------      --------------------------------------------
  fsdb (ribMap)          ->  create_fpf_fsdb_ribmap_convergence_check
  bgp  (RIB)             ->  create_fpf_bgp_rib_convergence_check
  hrt  (bulk)            ->  create_fpf_hrt_bulk_convergence_check
  hrt_remote_failure     ->  create_fpf_hrt_remote_failure_convergence_check
  prod_hrt_prefix        ->  create_fpf_prod_hrt_prefix_stability_check
  (ODS) HRT sys memory   ->  create_fpf_hrt_system_memory_check

Scale is intentionally tiny (1,000 injected prefixes) for a fast minimal run.
Generic SSH/device-shell prechecks/postchecks (systemctl, unclean-exit, core
dumps, port/bgp state, mem/cpu) and ODS counters are skipped
(skip_ssh_dependent_checks=True) so the test runs end-to-end without device
SSH access. Prefix injection and the collectors use BGP++/HRT/FSDB thrift, not
SSH. The stabilization (bake) window is kept at 5 min — do not shrink further.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_stress_test_config \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook_v2,
)
from taac.task_definitions import (
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    DEFAULT_SUBNET_PREFIX,
    GPU_HOSTS,
    OBSERVER_GTSWS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config.types import TestConfig

# Tiny scale for a fast minimal run.
PREFIX_COUNT = 1000
# Bake/stability window — keep at 5 min (do not reduce below).
STABILIZATION_DELAY_SEC = 300

# Production VF prefix monitored by the fifth (prod_hrt_prefix) collector and
# validated by FpfProdHrtPrefixStabilityHealthCheck. Steady-state production
# reachability exists independent of the injected stress prefixes. The prefix is
# resolved from the single source-of-truth host->device->prefix map
# (libs/fpf/fpf_prod_prefix_map.py) — never hardcode the prefix string here.
PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]

# RTP test hosts whose HRT service memory is asserted (<= 8 GiB max) by
# FpfHrtSystemMemoryHealthCheck. Distinct from GPU_HOSTS.
HRT_MEMORY_HOSTS = ["rtptest1555.mwg2", "rtptest1575.mwg2"]


def create_fpf_stress_test_config() -> TestConfig:
    playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=0,
        stabilization_delay_sec=STABILIZATION_DELAY_SEC,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_stable_state",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=True,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
    )

    return TestConfig(
        name="fpf_stress_test_config",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[
            create_fpf_start_collectors_task(
                gtsws=OBSERVER_GTSWS,
                hosts=GPU_HOSTS,
                subnet_prefix=DEFAULT_SUBNET_PREFIX,
                prod_prefixes=PROD_PREFIXES,
                prod_prefix_host=PROD_PREFIX_HOST,
                prod_prefix_device_id=PROD_PREFIX_DEVICE_ID,
            ),
        ],
        teardown_tasks=[
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                prefix_count=PREFIX_COUNT,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
        ],
        playbooks=[playbook],
    )


TEST_CONFIG = create_fpf_stress_test_config()

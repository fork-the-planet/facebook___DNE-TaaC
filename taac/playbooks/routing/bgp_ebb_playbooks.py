# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGPCPP-on-EBB playbook factories (one factory = one playbook = one test case).

Naming: ``create_bgp_ebb_<usecase>_playbook``. Playbook ``name=`` field
values are GRANDFATHERED from the legacy ``playbooks/playbook_definitions.py``
home (Wave 4 will rename them to the canonical framework form).

See README.md.
"""

import typing as t

from neteng.test_infra.dne.taac.constants import BgpPlusPlusProfile, Gigabyte
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.check_profile_registry import (
    CheckProfile,
    get_profile_checks,
    ProfileContext,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.common_periodic_tasks import (
    create_standard_periodic_tasks,
)
from taac.stages.stage_definitions import (
    create_bgp_restart_test_stage,
    create_cold_start_test_stage,
)
from taac.steps.step_definitions import (
    create_bgp_restart_setup_steps,
)
from taac.utils.hardware_capacity_utils import (
    get_postcheck_thresholds,
    get_precheck_thresholds,
    HardwareCapacityThresholds,
)
from taac.test_as_a_config.types import Playbook


__all__ = [
    "create_bgp_ebb_cold_start_playbook",
    "create_bgp_ebb_daemon_restart_playbook",
]


def create_bgp_ebb_daemon_restart_playbook(
    device_name: str,
    peergroup_ibgp_v6: str,
    peergroup_ibgp_v4: str,
    profile: BgpPlusPlusProfile = BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
    cpu_baseline: float = 8.0,
    memory_threshold: int = Gigabyte.GIG_5.value,
    cpu_util_terminate_on_error: bool = False,
    memory_terminate_on_error: bool = False,
    enable_thread_cpu_monitoring: bool = False,
    thread_name_filter: t.Optional[t.List[str]] = None,
    enable_offcpu_profiling: bool = False,
    enable_perf_profiling: bool = False,
    enable_bgp_events: bool = False,
    enable_socket_monitoring: bool = False,
    precheck_thresholds: t.Optional[HardwareCapacityThresholds] = None,
    postcheck_thresholds: t.Optional[HardwareCapacityThresholds] = None,
    expected_peer_identity: t.Optional[t.Dict[str, str]] = None,
    parent_prefixes_to_ignore: t.Optional[t.List[str]] = None,
    exclude_bgp_mon: bool = True,
) -> Playbook:
    """
    Create a BGP daemon restart test playbook.

    This playbook tests the BGP daemon restart behavior by:
    1. Setting up BGP restart prerequisites
    2. Running standard prechecks (session state, hardware capacity, etc.)
    3. Executing the BGP restart test stage
    4. Running standard postchecks (convergence, service restart verification)

    Args:
        device_name: Name of the device under test
        peergroup_ibgp_v6: IPv6 iBGP peer group name for session checks
        peergroup_ibgp_v4: IPv4 iBGP peer group name for session checks
        profile: BGP++ profile (with or without Open/R)
        cpu_baseline: CPU baseline threshold for prechecks (default: 6.0)
        memory_threshold: Memory threshold in bytes (default: 5GB)
        cpu_util_terminate_on_error: Terminate test on CPU threshold breach
        memory_terminate_on_error: Terminate test on memory threshold breach
        enable_thread_cpu_monitoring: Enable per-thread CPU monitoring
        thread_name_filter: List of thread name prefixes to monitor
        enable_offcpu_profiling: Enable off-CPU profiling
        enable_perf_profiling: Enable perf profiling for flame graphs
        enable_bgp_events: Enable BGP event annotation on timeline
        enable_socket_monitoring: Enable socket statistics monitoring
        precheck_thresholds: Custom precheck thresholds (uses defaults if None)
        postcheck_thresholds: Custom postcheck thresholds (uses defaults if None)

    Returns:
        Playbook configured for BGP daemon restart testing
    """
    if thread_name_filter is None:
        thread_name_filter = ["fi"]  # Fiber threads by default

    if precheck_thresholds is None:
        precheck_thresholds = get_precheck_thresholds()

    if postcheck_thresholds is None:
        postcheck_thresholds = get_postcheck_thresholds()

    restart_checks = get_profile_checks(
        CheckProfile.DAEMON_RESTART,
        ProfileContext(
            peergroup_ibgp_v6=peergroup_ibgp_v6,
            peergroup_ibgp_v4=peergroup_ibgp_v4,
            precheck_thresholds=precheck_thresholds,
            postcheck_thresholds=postcheck_thresholds,
            cpu_baseline=cpu_baseline,
            check_ibgp_pnh=(profile == BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R),
            expected_peer_identity=expected_peer_identity,
            parent_prefixes_to_ignore=parent_prefixes_to_ignore,
            exclude_bgp_mon=exclude_bgp_mon,
        ),
    )
    return Playbook(
        name="bgp_daemon_restart_test_playbook",
        setup_steps=create_bgp_restart_setup_steps(device_name=device_name),
        prechecks=restart_checks.prechecks,
        postchecks=restart_checks.postchecks,
        snapshot_checks=restart_checks.snapshot_checks,
        periodic_tasks=create_standard_periodic_tasks(
            device_name=device_name,
            memory_threshold=memory_threshold,
            cpu_util_terminate_on_error=cpu_util_terminate_on_error,
            memory_terminate_on_error=memory_terminate_on_error,
        ),
        stages=[
            create_bgp_restart_test_stage(
                device_name=device_name,
                enable_thread_cpu_monitoring=enable_thread_cpu_monitoring,
                thread_name_filter=thread_name_filter,
                enable_offcpu_profiling=enable_offcpu_profiling,
                enable_perf_profiling=enable_perf_profiling,
                enable_bgp_events=enable_bgp_events,
            ),
        ],
    )


def create_bgp_ebb_cold_start_playbook(
    device_name: str,
    peergroup_ibgp_v6: str,
    peergroup_ibgp_v4: str,
    profile: BgpPlusPlusProfile = BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
    cpu_baseline: float = 8.0,
    memory_threshold: int = Gigabyte.GIG_5.value,
    cpu_util_terminate_on_error: bool = False,
    memory_terminate_on_error: bool = False,
    enable_thread_cpu_monitoring: bool = True,
    thread_name_filter: t.Optional[t.List[str]] = None,
    thread_cpu_monitoring_interval_seconds: int = 2,
    enable_offcpu_profiling: bool = False,
    enable_perf_profiling: bool = False,
    enable_bgp_events: bool = False,
    enable_socket_monitoring: bool = False,
    fail_on_eor_expired: bool = False,
    precheck_thresholds: t.Optional[HardwareCapacityThresholds] = None,
    postcheck_thresholds: t.Optional[HardwareCapacityThresholds] = None,
    expected_peer_identity: t.Optional[t.Dict[str, str]] = None,
    exclude_bgp_mon: bool = True,
) -> Playbook:
    """
    Create a BGP cold start test playbook.

    This playbook tests the BGP cold start behavior by:
    1. Setting up BGP restart prerequisites
    2. Running standard prechecks
    3. Executing the cold start test stage with CPU/perf profiling
    4. Running standard postchecks (with EOR expiry tolerance)

    Cold start differs from daemon restart in that:
    - It simulates a full BGP process restart from scratch
    - Thread CPU monitoring is enabled by default
    - Perf profiling is enabled by default for performance analysis
    - EOR (End of RIB) expiry is tolerated by default

    Args:
        device_name: Name of the device under test
        peergroup_ibgp_v6: IPv6 iBGP peer group name for session checks
        peergroup_ibgp_v4: IPv4 iBGP peer group name for session checks
        profile: BGP++ profile (with or without Open/R)
        memory_threshold: Memory threshold in bytes (default: 5GB)
        cpu_util_terminate_on_error: Terminate test on CPU threshold breach
        memory_terminate_on_error: Terminate test on memory threshold breach
        enable_thread_cpu_monitoring: Enable per-thread CPU monitoring (default: True)
        thread_name_filter: List of thread name prefixes to monitor
        thread_cpu_monitoring_interval_seconds: Monitoring interval (default: 2s)
        enable_offcpu_profiling: Enable off-CPU profiling
        enable_perf_profiling: Enable perf profiling for flame graphs (default: True)
        enable_bgp_events: Enable BGP event annotation on timeline
        enable_socket_monitoring: Enable socket statistics monitoring
        fail_on_eor_expired: Whether to fail if EOR expires (default: False)
        precheck_thresholds: Custom precheck thresholds (uses defaults if None)
        postcheck_thresholds: Custom postcheck thresholds (uses defaults if None)

    Returns:
        Playbook configured for BGP cold start testing
    """
    if thread_name_filter is None:
        thread_name_filter = [
            "fi",  # Fiber threads
            "pe",  # PeerManager threads
            "ri",  # RIB threads
        ]

    if precheck_thresholds is None:
        precheck_thresholds = get_precheck_thresholds()

    if postcheck_thresholds is None:
        postcheck_thresholds = get_postcheck_thresholds()

    cold_start_checks = get_profile_checks(
        CheckProfile.COLD_START,
        ProfileContext(
            peergroup_ibgp_v6=peergroup_ibgp_v6,
            peergroup_ibgp_v4=peergroup_ibgp_v4,
            precheck_thresholds=precheck_thresholds,
            postcheck_thresholds=postcheck_thresholds,
            cpu_baseline=cpu_baseline,
            check_ibgp_pnh=(profile == BgpPlusPlusProfile.BGP_PLUS_PLUS_WITH_OPEN_R),
            expected_peer_identity=expected_peer_identity,
            exclude_bgp_mon=exclude_bgp_mon,
            fail_on_eor_expired=fail_on_eor_expired,
        ),
    )
    return Playbook(
        name="bgp_cold_start_test_playbook",
        setup_steps=create_bgp_restart_setup_steps(device_name=device_name),
        prechecks=cold_start_checks.prechecks,
        postchecks=cold_start_checks.postchecks,
        snapshot_checks=cold_start_checks.snapshot_checks,
        periodic_tasks=create_standard_periodic_tasks(
            device_name=device_name,
            memory_threshold=memory_threshold,
            cpu_util_terminate_on_error=cpu_util_terminate_on_error,
            memory_terminate_on_error=memory_terminate_on_error,
        ),
        stages=[
            create_cold_start_test_stage(
                device_name=device_name,
                enable_thread_cpu_monitoring=enable_thread_cpu_monitoring,
                thread_name_filter=thread_name_filter,
                enable_offcpu_profiling=enable_offcpu_profiling,
                thread_cpu_monitoring_interval_seconds=thread_cpu_monitoring_interval_seconds,
                enable_perf_profiling=enable_perf_profiling,
                enable_bgp_events=enable_bgp_events,
                enable_socket_monitoring=enable_socket_monitoring,
            ),
        ],
    )

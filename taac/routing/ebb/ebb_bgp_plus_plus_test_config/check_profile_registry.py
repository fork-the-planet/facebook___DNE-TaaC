# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Check-profile registry — the single source of truth for *which* health
checks each Conveyor test runs and their per-(check, phase) functional params.

Background: previously every test's pre/post/snapshot policy (which checks,
convergence on/off, ``fail_on_eor_expired``, thresholds) was decided ad-hoc at
each playbook/config call site, in three parallel definition styles. That made
"what does test X check" and "flip EOR for test Y" hard to see and easy to drift
(see the dne_routing Conveyor health-check audit). This registry collapses that
into one declarative place: a playbook looks up its profile instead of
hand-assembling check lists.

Two parameter categories, deliberately kept separate:

* **Retry policy** (retry_count / delay / multiplier) — keyed by *check* alone,
  identical across pre/post and across all tests. It is NOT specified here; it
  is pulled from ``retry_policy`` (the SSOT) and baked into each check via the
  factory. Profiles never hand-pass retry numbers, which is what kills the drift.
* **Functional params** (``validate_sequence``, ``fail_on_eor_expired``,
  ``convergence_threshold``, …) — keyed by *(check, phase)* and may differ
  between the pre and post bundles of the SAME check. These ARE declared here,
  explicitly, so an EOR-type issue is a one-line edit in one visible place.

All checks are built via the ``create_*`` factories in
``healthcheck_definitions`` (never constructed inline) so the
``test_no_inline_healthcheck_construction`` gate stays satisfied.
"""

from __future__ import annotations

import enum
import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_convergence_check,
    create_bgp_rib_fib_consistency_check,
    create_bgp_session_establish_check,
    create_bgp_session_snapshot_check,
    create_core_dumps_snapshot_check,
)
from taac.health_checks.retry_policy import get_retry_kwargs
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config.types import PointInTimeHealthCheck, SnapshotHealthCheck


class CheckProfile(enum.Enum):
    """Named check profiles. Add one entry per de-facto test profile and route
    the playbook through ``get_profile_checks`` instead of inlining checks.
    """

    # bag012 perf-scaling, bounded-ECMP-sets (case9): BGP re-init + 1200s route
    # oscillation, then verify recovery.
    PERF_SCALING_BOUNDED_ECMP = "perf_scaling_bounded_ecmp"


class ProfileChecks(t.NamedTuple):
    """Resolved checks for a profile, split by phase."""

    prechecks: t.List[PointInTimeHealthCheck]
    postchecks: t.List[PointInTimeHealthCheck]
    snapshot_checks: t.List[SnapshotHealthCheck]


def _perf_scaling_bounded_ecmp() -> ProfileChecks:
    """Profile for the bag012 bounded-ECMP-sets (case9) playbook.

    Behavior-preserving vs. the prior inline list, with the one intended
    improvement: the post-test session / RIB-FIB / convergence checks now carry
    the standardized retry from the SSOT (previously single-shot), so transient
    post-disruption settling no longer trips a false failure.
    """
    return ProfileChecks(
        prechecks=[],
        postchecks=[
            create_bgp_session_establish_check(
                **get_retry_kwargs(hc_types.CheckName.BGP_SESSION_ESTABLISH_CHECK),
            ),
            create_bgp_rib_fib_consistency_check(
                **get_retry_kwargs(hc_types.CheckName.BGP_RIB_FIB_CONSISTENCY_CHECK),
            ),
            create_bgp_convergence_check(
                convergence_threshold=600,
                # Functional knob (per check, phase). Kept True to preserve the
                # current bag012 behavior (the prior call omitted it, inheriting
                # the server-side default True). Flip to False here to align with
                # the fleet standard (BGP_STANDARD_POSTCHECKS) if an expired EOR
                # timer under bounded-ECMP stress is deemed acceptable.
                fail_on_eor_expired=True,
                check_id="postcheck_bgp_convergence_time",
                **get_retry_kwargs(hc_types.CheckName.BGP_CONVERGENCE_CHECK),
            ),
        ],
        snapshot_checks=[
            create_core_dumps_snapshot_check(),
            create_bgp_session_snapshot_check(
                skip_flap_check=True, skip_uptime_check=True
            ),
        ],
    )


# Explicit profile -> builder mapping (no decorator/registration side effects, per
# the lazy-import guidance). Builders are referenced, not called, at import time.
_PROFILE_BUILDERS: t.Dict[CheckProfile, t.Callable[[], ProfileChecks]] = {
    CheckProfile.PERF_SCALING_BOUNDED_ECMP: _perf_scaling_bounded_ecmp,
}


def get_profile_checks(profile: CheckProfile) -> ProfileChecks:
    """Resolve a ``CheckProfile`` to its (prechecks, postchecks, snapshot_checks).

    Each call constructs fresh check objects (thrift structs are mutable, so
    callers must not share instances across playbooks).
    """
    builder = _PROFILE_BUILDERS.get(profile)
    if builder is None:
        raise ValueError(f"Unknown CheckProfile: {profile}")
    return builder()

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

import time
import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.libs.fpf.fpf_collector_registry import (
    get_collector,
    get_test_case_start_time,
)
from taac.libs.fpf.fpf_prod_hrt_prefix import normalize_prefix
from taac.health_check.health_check import types as hc_types

# Expected steady-state reachability for the monitored production prefixes,
# matching the validated MWG2 FPF lab data (VF1 reachable on planes 0-3, VF2
# unreachable on planes 4-7, no drains, all 8 planes UP). All four are
# overridable via check_params for tests with a different topology.
DEFAULT_EXPECTED_REACHABLE: t.List[int] = [0, 1, 2, 3]
DEFAULT_EXPECTED_DRAINED: t.List[int] = []
DEFAULT_EXPECTED_UNREACHABLE: t.List[int] = [4, 5, 6, 7]
DEFAULT_EXPECTED_PLANE_UP: t.List[int] = [0, 1, 2, 3, 4, 5, 6, 7]

# Fields that must always be present as integer lists (never null/missing).
_LIST_FIELDS = (
    "reachable_planes",
    "drained_planes",
    "unreachable_planes",
    "plane_up",
)


def _evaluate_sample(
    rb: t.Any,
    display: str,
    ts: str,
    expected: t.Dict[str, t.List[int]],
    null_issues: t.List[str],
    compliance_issues: t.List[str],
) -> bool:
    """Evaluate one prefix sample, appending any issues to the lists.

    Returns True if the sample was a valid (non-null) data point that could be
    compliance-checked, False if it was null (and recorded in null_issues).
    """
    # Every plane list must be a real integer list (never None).
    for fld in _LIST_FIELDS:
        val = getattr(rb, fld, None)
        if val is None or not isinstance(val, list):
            null_issues.append(f"{display}.{fld} is null at {ts}")
            return False
    for fld, exp in expected.items():
        actual = sorted(getattr(rb, fld))
        if actual != exp:
            compliance_issues.append(f"{display} {fld}={actual} != {exp} at {ts}")
    return True


class FpfProdHrtPrefixStabilityHealthCheck(
    AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]
):
    """Postcheck: production HRT prefix reachability stability over the test window.

    Consumes the live ``prod_hrt_prefix`` collector (registered by
    FpfStartCollectorsTask). For every data point between the test-case start
    and end time, each monitored prefix must be strictly compliant:

      - reachable_planes   == expected_reachable    (default [0,1,2,3])
      - drained_planes     == expected_drained      (default [])
      - unreachable_planes == expected_unreachable  (default [4,5,6,7])
      - plane_up           == expected_plane_up      (default [0..7])

    Two independent signals (both must pass):

      Signal 1 — Compliance: every in-window sample of every monitored prefix
        matches the expected sets above.
      Signal 2 — Data integrity: no null data points in the window. A null
        arises from a poll timeout (the collector bounds each poll at
        POLL_TIMEOUT_SEC = 120s; a poll that does not return within 2 minutes
        is recorded as null) OR a sample where a prefix is missing or any of
        its plane lists is not an integer list. Any null fails Signal 2.
    """

    CHECK_NAME = hc_types.CheckName.FPF_PROD_HRT_PREFIX_STABILITY_CHECK
    CHECK_SCOPE = hc_types.Scope.DEFAULT
    OPERATING_SYSTEMS = ["FBOSS"]

    async def _run(
        self,
        obj: TestDevice,
        input: hc_types.BaseHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        collector = get_collector("prod_hrt_prefix")
        if collector is None:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="No live prod_hrt_prefix collector in registry",
            )

        window_end = check_params.get("window_end", time.time())
        tc_start = get_test_case_start_time()
        lookback_sec = check_params.get("lookback_sec", 900)
        window_start = check_params.get(
            "window_start", tc_start if tc_start else window_end - lookback_sec
        )

        # Expected plane sets keyed by PrefixReachability field name, so the
        # evaluation helper can iterate uniformly.
        expected: t.Dict[str, t.List[int]] = {
            "reachable_planes": sorted(
                check_params.get("expected_reachable", DEFAULT_EXPECTED_REACHABLE)
            ),
            "drained_planes": sorted(
                check_params.get("expected_drained", DEFAULT_EXPECTED_DRAINED)
            ),
            "unreachable_planes": sorted(
                check_params.get("expected_unreachable", DEFAULT_EXPECTED_UNREACHABLE)
            ),
            "plane_up": sorted(
                check_params.get("expected_plane_up", DEFAULT_EXPECTED_PLANE_UP)
            ),
        }

        # Optional explicit prefix allowlist; otherwise evaluate every prefix
        # the collector saw in the window.
        prefix_filter = check_params.get("prefixes")
        normalized_filter = (
            {normalize_prefix(p) for p in prefix_filter} if prefix_filter else None
        )

        self.logger.info(
            f"  [prod HRT prefix] Evaluating window {window_start:.0f} to "
            f"{window_end:.0f} ({window_end - window_start:.0f}s span); expected "
            f"reachable={expected['reachable_planes']}, "
            f"drained={expected['drained_planes']}, "
            f"unreachable={expected['unreachable_planes']}, "
            f"plane_up={expected['plane_up']}"
        )

        rows = collector.get_rows_in_window(window_start, window_end)
        if not rows:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=(
                    f"No prod_hrt_prefix samples in window "
                    f"[{window_start:.0f}, {window_end:.0f}]"
                ),
            )

        # ── Signal 2: data integrity (null / timeout) ──
        null_issues: t.List[str] = []
        timeout_count = collector.timeout_count_in_window(window_start, window_end)
        if timeout_count > 0:
            null_issues.append(
                f"{timeout_count} poll timeout(s) recorded null data (>2min)"
            )

        # Determine the set of prefixes to assert against.
        monitored: t.Dict[str, str] = {}  # normalized -> display
        for row in rows:
            for pfx in row.prefixes:
                norm = normalize_prefix(pfx)
                if normalized_filter is not None and norm not in normalized_filter:
                    continue
                monitored.setdefault(norm, pfx)
        if normalized_filter is not None:
            for norm in normalized_filter:
                monitored.setdefault(norm, norm)

        # ── Signal 1: compliance ──
        compliance_issues: t.List[str] = []
        sample_count = 0
        for row in rows:
            row_by_norm = {normalize_prefix(k): v for k, v in row.prefixes.items()}
            for norm, display in monitored.items():
                rb = row_by_norm.get(norm)
                if rb is None:
                    null_issues.append(f"{display} missing at {row.timestamp}")
                    continue
                if _evaluate_sample(
                    rb,
                    display,
                    row.timestamp,
                    expected,
                    null_issues,
                    compliance_issues,
                ):
                    sample_count += 1

        signal1_ok = not compliance_issues
        signal2_ok = not null_issues

        self.logger.info(
            f"  [prod HRT prefix] Signal 1 — compliance "
            f"(all samples match expected sets): "
            f"[{'PASS' if signal1_ok else 'FAIL'}] "
            f"{len(monitored)} prefix(es), {sample_count} compliant sample(s)"
            + (
                ""
                if signal1_ok
                else f"; {len(compliance_issues)} violation(s): "
                + "; ".join(compliance_issues[:5])
                + ("..." if len(compliance_issues) > 5 else "")
            )
        )
        self.logger.info(
            f"  [prod HRT prefix] Signal 2 — data integrity "
            f"(no null/timeout data points): "
            f"[{'PASS' if signal2_ok else 'FAIL'}]"
            + (
                ""
                if signal2_ok
                else f"; {len(null_issues)} null issue(s): "
                + "; ".join(null_issues[:5])
                + ("..." if len(null_issues) > 5 else "")
            )
        )

        # Signal 2 (null/integrity) gates first, mirroring the convergence checks.
        if not signal2_ok:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=(
                    "Signal 2 (data integrity) FAILED — null/timeout data points: "
                    + "; ".join(null_issues[:10])
                    + ("..." if len(null_issues) > 10 else "")
                ),
            )
        if not signal1_ok:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=(
                    "Signal 1 (compliance) FAILED — "
                    + "; ".join(compliance_issues[:10])
                    + ("..." if len(compliance_issues) > 10 else "")
                ),
            )
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=(
                f"All {len(monitored)} prefix(es) compliant across {sample_count} "
                f"sample(s): reachable={expected['reachable_planes']}, "
                f"drained={expected['drained_planes']}, "
                f"unreachable={expected['unreachable_planes']}, "
                f"plane_up={expected['plane_up']}; no null data points"
            ),
        )

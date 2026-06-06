# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

import time
import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.libs.fpf.fpf_collector_registry import (
    get_all_collectors,
    get_collector,
    get_test_case_start_time,
)
from taac.libs.fpf.fpf_prod_hrt_prefix import normalize_prefix
from taac.health_check.health_check import types as hc_types

# Fallback expected steady-state reachability (validated MWG2 FPF lab: VF1
# reachable planes 0-3, VF2 unreachable 4-7, no drains, all 8 planes UP). Only
# used when baseline_mode != "per_prefix" AND no explicit expected_* override is
# supplied. The DEFAULT behaviour is per-prefix baselines (see _run).
DEFAULT_EXPECTED_REACHABLE: t.List[int] = [0, 1, 2, 3]
DEFAULT_EXPECTED_DRAINED: t.List[int] = []
DEFAULT_EXPECTED_UNREACHABLE: t.List[int] = [4, 5, 6, 7]
DEFAULT_EXPECTED_PLANE_UP: t.List[int] = [0, 1, 2, 3, 4, 5, 6, 7]

# Registry-name prefix used to discover production-prefix collectors. The single
# legacy registration ("prod_hrt_prefix") and multi-host registrations
# ("prod_hrt_prefix:<host>") both match.
_COLLECTOR_NAME_PREFIX = "prod_hrt_prefix"

# Plane-list fields that must always be present as integer lists (never null).
_LIST_FIELDS = (
    "reachable_planes",
    "drained_planes",
    "unreachable_planes",
    "plane_up",
)


def _row_ts(row: t.Any) -> t.Optional[float]:
    from taac.libs.fpf.fpf_stress_checks import _parse_ts

    try:
        return _parse_ts(row.timestamp).timestamp()
    except (ValueError, AttributeError):
        return None


def _fmt(planes: t.Optional[t.List[int]]) -> str:
    if not planes:
        return "[]"
    return "[" + ",".join(str(p) for p in planes) + "]"


def discover_prod_collectors(
    check_params: t.Dict[str, t.Any],
) -> t.List[t.Tuple[str, t.Any]]:
    """Return [(host, collector)] for every registered prod-prefix collector.

    Honors an explicit ``collector_names`` check_param; otherwise discovers all
    registry entries whose name starts with ``prod_hrt_prefix`` (covers both the
    legacy single registration and per-host ``prod_hrt_prefix:<host>`` ones).
    """
    names = check_params.get("collector_names")
    out: t.List[t.Tuple[str, t.Any]] = []
    if names:
        for n in names:
            c = get_collector(n)
            if c is not None:
                out.append((str(getattr(c, "host", n)), c))
        return out
    for name, c in get_all_collectors().items():
        if name.startswith(_COLLECTOR_NAME_PREFIX) and hasattr(c, "get_rows_in_window"):
            out.append((getattr(c, "host", name), c))
    # Stable order by host for deterministic reporting.
    out.sort(key=lambda hc: hc[0])
    return out


def _prefix_samples(
    rows: t.List[t.Any], target_norms: t.Optional[t.Set[str]]
) -> t.Dict[str, t.Dict[str, t.Any]]:
    """norm -> {display, samples: [(ts_float, ts_str, rb)] sorted}."""
    out: t.Dict[str, t.Dict[str, t.Any]] = {}
    for row in rows:
        ts = _row_ts(row)
        if ts is None:
            continue
        for raw, rb in row.prefixes.items():
            norm = normalize_prefix(raw)
            if target_norms is not None and norm not in target_norms:
                continue
            entry = out.setdefault(norm, {"display": raw, "samples": []})
            entry["samples"].append((ts, row.timestamp, rb))
    for entry in out.values():
        entry["samples"].sort(key=lambda x: x[0])
    return out


def _baseline_of(rb: t.Any) -> t.Dict[str, t.List[int]]:
    return {
        "reachable_planes": sorted(rb.reachable_planes),
        "drained_planes": sorted(rb.drained_planes),
        "unreachable_planes": sorted(rb.unreachable_planes),
        "plane_up": sorted(rb.plane_up),
    }


class _HostResult:
    """Per-host evaluation outcome."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.status = "SKIP"  # PASS / FAIL / SKIP
        self.n_prefixes = 0
        self.n_samples = 0
        self.s1_ok = True  # compliance
        self.s2_ok = True  # data integrity
        self.compliance_issues: t.List[str] = []
        self.null_issues: t.List[str] = []
        # impacted prefix -> dict(ts_str, lost, gained, baseline, post_rb)
        self.impacts: t.List[t.Dict[str, t.Any]] = []


def _evaluate_host(
    host: str,
    collector: t.Any,
    window_start: float,
    window_end: float,
    target_norms: t.Optional[t.Set[str]],
    fixed_expected: t.Optional[t.Dict[str, t.List[int]]],
) -> _HostResult:
    """Per-prefix, baseline-relative compliance + integrity for one host."""
    res = _HostResult(host)
    rows = collector.get_rows_in_window(window_start, window_end)
    timeline = _prefix_samples(rows, target_norms)
    if not timeline:
        res.status = "SKIP"
        return res

    # Signal 2 (integrity): poll timeouts → null data points.
    timeout_count = collector.timeout_count_in_window(window_start, window_end)
    if timeout_count > 0:
        res.null_issues.append(
            f"{timeout_count} poll timeout(s) recorded null data (>2min)"
        )

    res.n_prefixes = len(timeline)
    for norm in sorted(timeline):
        info = timeline[norm]
        display = info["display"]
        samples = info["samples"]
        # Each prefix uses its OWN baseline (first in-window sample) unless a
        # fixed expected set was supplied via check_params.
        baseline = fixed_expected or _baseline_of(samples[0][2])
        first_impact: t.Optional[t.Dict[str, t.Any]] = None
        for ts, ts_str, rb in samples:
            # Integrity: every plane field must be a real integer list.
            null_field = False
            for fld in _LIST_FIELDS:
                val = getattr(rb, fld, None)
                if val is None or not isinstance(val, list):
                    res.null_issues.append(f"{display}.{fld} null at {ts_str}")
                    null_field = True
            if null_field:
                continue
            res.n_samples += 1
            # Compliance: every field must match the baseline set.
            mismatch = False
            for fld in _LIST_FIELDS:
                if sorted(getattr(rb, fld)) != baseline[fld]:
                    mismatch = True
            if mismatch and first_impact is None:
                base_r = set(baseline["reachable_planes"])
                cur_r = set(rb.reachable_planes)
                first_impact = {
                    "ts_str": ts_str,
                    "lost": sorted(base_r - cur_r),
                    "gained": sorted(cur_r - base_r),
                    "baseline": baseline,
                    "rb": rb,
                }
                res.compliance_issues.append(
                    f"{display} regressed at {ts_str}: reachable "
                    f"{_fmt(baseline['reachable_planes'])}->"
                    f"{_fmt(sorted(rb.reachable_planes))}"
                )
        if first_impact is not None:
            first_impact["display"] = display
            first_impact["device_ids"] = sorted(samples[0][2].device_ids)
            res.impacts.append(first_impact)

    res.s2_ok = not res.null_issues
    res.s1_ok = not res.compliance_issues
    if not res.s2_ok or not res.s1_ok:
        res.status = "FAIL"
    else:
        res.status = "PASS"
    return res


def _format_report(host_results: t.List[_HostResult], agg: str) -> str:
    """Human-readable multi-host report (this is the everpaste'd message)."""
    lines: t.List[str] = []
    lines.append(f"Prod HRT prefix stability — {len(host_results)} host(s)")
    for r in host_results:
        lines.append(
            f"[{r.host}] VERDICT {r.status} | "
            f"S1 compliance {'PASS' if r.s1_ok else 'FAIL'} | "
            f"S2 data-integrity {'PASS' if r.s2_ok else 'FAIL'} | "
            f"{r.n_prefixes} prefix(es), {r.n_samples} sample(s)"
        )
        for imp in sorted(r.impacts, key=lambda x: x["ts_str"]):
            rb = imp["rb"]
            lines.append(
                f"    IMPACTED {imp['display']} (dev "
                f"{','.join(map(str, imp['device_ids']))}) @ {imp['ts_str']}: "
                f"lost {_fmt(imp['lost'])}"
                + (f" gained {_fmt(imp['gained'])}" if imp["gained"] else "")
                + f"; reachable {_fmt(imp['baseline']['reachable_planes'])}->"
                f"{_fmt(sorted(rb.reachable_planes))}, "
                f"drained={_fmt(sorted(rb.drained_planes))}, "
                f"unreachable={_fmt(sorted(rb.unreachable_planes))}"
            )
        if r.null_issues and not r.impacts:
            lines.append(f"    NULL: {'; '.join(r.null_issues[:5])}")
    lines.append(f"AGGREGATE: {agg}")
    return "\n".join(lines)


class FpfProdHrtPrefixStabilityHealthCheck(
    AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]
):
    """Postcheck: production HRT prefix reachability stability, per host.

    Consumes the live ``prod_hrt_prefix`` collector(s) registered in the FPF
    collector registry. Discovers ALL such collectors (one per host) and
    evaluates each host independently. For every monitored prefix on a host,
    over the test window:

      Signal 1 — Compliance: every in-window sample matches the prefix's
        baseline plane sets (reachable / drained / unreachable / plane_up).
        By default the baseline is the prefix's OWN first in-window sample
        (``baseline_mode="per_prefix"``), so local (VF1, planes 0-3) and
        remote (VF2, planes 4-7) prefixes are each validated against their own
        steady state. A fixed expected set can be pinned via the
        ``expected_*`` check_params (applied to all prefixes).
      Signal 2 — Data integrity: no null data points (poll timeout >2min,
        missing prefix, or a non-list plane field).

    The result message is a per-host report that names every IMPACTED prefix
    with the timestamp it regressed and the planes lost (before->after). When
    run through the health-check framework (TAAC) the message is uploaded to
    Everpaste automatically, so the impacted-prefix detail is shareable without
    any binary involvement.

    The overall status is FAIL if any host fails Signal 1 or Signal 2, SKIP if
    no host produced in-window data, else PASS.
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
        collectors = discover_prod_collectors(check_params)
        if not collectors:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="No prod_hrt_prefix collector(s) in registry",
            )

        window_end = check_params.get("window_end", time.time())
        tc_start = get_test_case_start_time()
        lookback_sec = check_params.get("lookback_sec", 900)
        window_start = check_params.get(
            "window_start", tc_start if tc_start else window_end - lookback_sec
        )

        prefix_filter = check_params.get("prefixes")
        target_norms = (
            {normalize_prefix(p) for p in prefix_filter} if prefix_filter else None
        )

        # Per-prefix baselines by default; a fixed expected set is used only if
        # any expected_* is supplied or baseline_mode is explicitly "fixed".
        baseline_mode = check_params.get("baseline_mode", "per_prefix")
        has_expected = any(
            check_params.get(k) is not None
            for k in (
                "expected_reachable",
                "expected_drained",
                "expected_unreachable",
                "expected_plane_up",
            )
        )
        fixed_expected: t.Optional[t.Dict[str, t.List[int]]] = None
        if baseline_mode != "per_prefix" or has_expected:
            fixed_expected = {
                "reachable_planes": sorted(
                    check_params.get("expected_reachable", DEFAULT_EXPECTED_REACHABLE)
                ),
                "drained_planes": sorted(
                    check_params.get("expected_drained", DEFAULT_EXPECTED_DRAINED)
                ),
                "unreachable_planes": sorted(
                    check_params.get(
                        "expected_unreachable", DEFAULT_EXPECTED_UNREACHABLE
                    )
                ),
                "plane_up": sorted(
                    check_params.get("expected_plane_up", DEFAULT_EXPECTED_PLANE_UP)
                ),
            }

        host_results: t.List[_HostResult] = []
        for host, collector in collectors:
            res = _evaluate_host(
                host,
                collector,
                window_start,
                window_end,
                target_norms,
                fixed_expected,
            )
            host_results.append(res)
            self.logger.info(
                f"  [prod HRT prefix][{host}] VERDICT {res.status} — "
                f"S1 {'PASS' if res.s1_ok else 'FAIL'}, "
                f"S2 {'PASS' if res.s2_ok else 'FAIL'}, "
                f"{len(res.impacts)} impacted prefix(es)"
            )

        if all(r.status == "SKIP" for r in host_results):
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=(
                    "No in-window prod_hrt_prefix samples on any host "
                    f"[{window_start:.0f}, {window_end:.0f}]"
                ),
            )

        if any(r.status == "FAIL" for r in host_results):
            agg = "FAIL"
            status = hc_types.HealthCheckStatus.FAIL
        else:
            agg = "PASS"
            status = hc_types.HealthCheckStatus.PASS

        return hc_types.HealthCheckResult(
            status=status,
            message=_format_report(host_results, agg),
        )

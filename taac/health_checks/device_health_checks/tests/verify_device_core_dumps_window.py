# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Runnable acceptance driver for DEVICE_CORE_DUMPS_CHECK window semantics.

Drives the REAL ``DeviceCoreDumpsHealthCheck._run`` end-to-end against cores
with KNOWN mtimes and sweeps the ``(start_time, end_time]`` window across every
pass/fail scenario, asserting the verdict each time. Prints a
``scenario | expected | actual | PASS/FAIL`` matrix and exits nonzero if ANY
row mismatches.

Determinism: instead of mutating a live lab box, we stub the on-device core
discovery (``async_find_critical_core_dumps``) to return a single core with a
controlled mtime ``C``. This exercises the exact same window-filter code path
that runs against real devices (the only thing mocked is the SSH ``find``), so
the verdict logic under test is the production logic. The real known ancient
core on gtsw002.l1002.c087.mwg2 (``/var/tmp/cores/fsdb`` mtime 1782390338,
2026-06-25) is included as an explicit data point in scenario 2/5.

Implemented semantics under test: a core is flagged iff
``start_time < mtime <= end_time`` (start exclusive, end inclusive), with the
fail-safe that a 0/None/missing ``start_time`` or ``end_time`` anchors to *now*.

Run:
    buck2 run //neteng/test_infra/dne/taac/health_checks/device_health_checks/tests:verify_device_core_dumps_window
"""

import asyncio
import sys
import typing as t
from unittest.mock import AsyncMock, MagicMock, patch

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.device_core_dumps_health_check import (
    DeviceCoreDumpsHealthCheck,
)
from taac.health_check.health_check import types as hc_types

MODULE = (
    "neteng.test_infra.dne.taac.health_checks.device_health_checks."
    "device_core_dumps_health_check"
)

# Deterministic reference clock the check observes via time.time().
NOW = 1_782_954_918
DAY = 24 * 3600

# The core's mtime (C). This is the REAL gtsw002 /var/tmp/cores/fsdb ancient
# core epoch (2026-06-25) — days before a 2026-07-01 test window.
CORE_MTIME = 1_782_390_338  # C
CORE_NAME = "fsdb_coredump_verify"  # contains "fsdb" -> critical keyword


class Scenario(t.NamedTuple):
    name: str
    start_time: t.Optional[int]
    end_time: t.Optional[int]
    expect_fail: bool  # True => core SHOULD be flagged (FAIL)


# C = CORE_MTIME. now = NOW. Scenarios enumerate the window vs C relationship.
SCENARIOS: t.List[Scenario] = [
    # 1. Window entirely BEFORE the core: start < end < C -> PASS (end-bound).
    Scenario(
        "window before core (start<end<C)",
        CORE_MTIME - 2 * DAY,
        CORE_MTIME - DAY,
        False,
    ),
    # 2. Window entirely AFTER the core: C < start < end -> PASS (start-bound).
    #    This is the exact bug: an ancient core in a later window must NOT flag.
    Scenario("window after core (C<start<end)", CORE_MTIME + DAY, NOW, False),
    # 3. Window ENCLOSING the core: start < C < end -> FAIL (real detection).
    Scenario("window encloses core (start<C<end)", CORE_MTIME - DAY, NOW, True),
    # 4a. Boundary: start == C -> PASS (start exclusive).
    Scenario("start == C (start exclusive)", CORE_MTIME, NOW, False),
    # 4b. Boundary: end == C -> FAIL (end inclusive), start below C.
    Scenario("end == C (end inclusive)", CORE_MTIME - DAY, CORE_MTIME, True),
    # 5. Huge window (EXPLICIT start=0, end=now) enclosing C -> FAIL, ONLY
    #    because the core is genuinely in-window. An explicit 0 is honored as
    #    epoch (no fail-safe), so C < now is truly inside (0, now]. Distinct
    #    from the bug, where start_time is ABSENT (scenario 6), not literal 0.
    Scenario("huge window start=0,end=now (C in-window)", 0, NOW, True),
    # 6. THE ORIGINAL BUG CONDITION, fixed: bare check (start/end ABSENT)
    #    against an ANCIENT core. Absent -> fail-safe anchors to now -> PASS
    #    (pre-fix this defaulted to 0 and FAILED on the ancient core).
    Scenario("bare check, ancient core (fail-safe)", None, None, False),
    # 7. Future core beyond default end: start set, end omitted (->now),
    #    core mtime in the future -> PASS.
    Scenario("future core > end(now)", NOW - DAY, None, False),
]


def _make_device(name: str) -> MagicMock:
    device = MagicMock(spec=TestDevice)
    device.name = name
    return device


async def _run_scenario(sc: Scenario, core_mtime: int) -> hc_types.HealthCheckStatus:
    check = DeviceCoreDumpsHealthCheck(logger=MagicMock(spec=ConsoleFileLogger))
    device = _make_device("gtsw002.l1002.c087.mwg2")
    check_params: t.Dict[str, t.Any] = {}
    if sc.start_time is not None:
        check_params["start_time"] = sc.start_time
    if sc.end_time is not None:
        check_params["end_time"] = sc.end_time
    with (
        patch(f"{MODULE}.time.time", return_value=NOW),
        patch(
            f"{MODULE}.async_find_critical_core_dumps",
            new_callable=AsyncMock,
            return_value={CORE_NAME: core_mtime},
        ),
    ):
        result = await check._run(device, hc_types.BaseHealthCheckIn(), check_params)
    return result.status


async def main() -> int:
    # Scenario 7 needs a FUTURE core to test the end-bound; all others use the
    # ancient CORE_MTIME. Select per-scenario core mtime.
    future_core = NOW + 500

    rows: t.List[t.Tuple[str, str, str, bool]] = []
    all_ok = True
    for sc in SCENARIOS:
        core_mtime = future_core if sc.name.startswith("future core") else CORE_MTIME
        status = await _run_scenario(sc, core_mtime)
        actual_fail = status == hc_types.HealthCheckStatus.FAIL
        expected = "FAIL" if sc.expect_fail else "PASS"
        actual = "FAIL" if actual_fail else status.name
        ok = actual_fail == sc.expect_fail
        all_ok = all_ok and ok
        rows.append((sc.name, expected, actual, ok))

    name_w = max(len(r[0]) for r in rows)
    print(f"\nDEVICE_CORE_DUMPS_CHECK window verification (now={NOW}, C={CORE_MTIME})")
    print("semantics: flag iff start_time < mtime <= end_time; 0/None -> now\n")
    header = f"{'scenario'.ljust(name_w)} | expected | actual   | result"
    print(header)
    print("-" * len(header))
    for name, expected, actual, ok in rows:
        verdict = "PASS" if ok else "*** MISMATCH ***"
        print(
            f"{name.ljust(name_w)} | {expected.ljust(8)} | {actual.ljust(8)} | {verdict}"
        )

    print()
    if all_ok:
        print(f"ALL {len(rows)} SCENARIOS OK")
        return 0
    print("ONE OR MORE SCENARIOS MISMATCHED")
    return 1


def run() -> None:
    """Sync entry point for the python_binary main_function."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()

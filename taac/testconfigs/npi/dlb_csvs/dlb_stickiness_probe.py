#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Standalone probe for the DLB resource-stickiness analysis.

Wraps the same `dlb_resource_analysis.analyze()` library used by
`DlbResourceStickinessHealthCheck` (CheckName 66). Unlike Pavan's
`prefix_to_dlb_resource_stickiness_bin` (hard-coded to 6000:dd/6000:ee), this
takes configurable prefix patterns so we can probe our 5000:dd / 5000:ee
DLB setup on gtsw001 and confirm the HC counts match our CSV intent.

Usage:
  buck2 run fbcode//neteng/test_infra/dne/taac/testconfigs/npi/dlb_csvs:dlb_stickiness_probe -- \\
    gtsw001.l1001.c085.ash6 --prefixes 5000:dd::,5000:ee::

Output: the same per-category table the HC would emit, plus expected vs
actual for any `--expect-dlb`, `--expect-total`, `--expect-width` flags.
"""

import argparse
import logging
import sys

from libfb.py.asyncio.await_utils import await_sync
from neteng.netcastle.logger import get_root_logger
from taac.health_checks.device_health_checks.dlb_resource_analysis import (
    analyze,
)
from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)


def _fetch_routes(driver):
    async def _go():
        async with driver.async_agent_client as client:
            return await client.getRouteTable()

    return await_sync(_go())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("device", help="DUT hostname, e.g. gtsw001.l1001.c085.ash6")
    ap.add_argument(
        "--prefixes",
        default="5000:dd::,5000:ee::",
        help="Comma-separated prefix patterns to categorize (default: 5000:dd::,5000:ee::)",
    )
    ap.add_argument(
        "--expect-dlb",
        type=int,
        default=None,
        help="Expected total DLB groups (cross-category) — fails if mismatched",
    )
    ap.add_argument(
        "--expect-total",
        type=int,
        default=None,
        help="Expected total ECMP groups (cross-category)",
    )
    ap.add_argument(
        "--cat-dlb",
        action="append",
        default=[],
        metavar="CATEGORY=COUNT",
        help='Per-category DLB expectation, e.g. "5000:dd prefixes=1". Repeatable.',
    )
    ap.add_argument(
        "--cat-width",
        action="append",
        default=[],
        metavar="CATEGORY=WIDTH",
        help="Per-category widest-group expectation. Repeatable.",
    )
    args = ap.parse_args()

    logger = get_root_logger()
    logger.setLevel(logging.INFO)

    prefix_patterns = [p.strip() for p in args.prefixes.split(",") if p.strip()]
    print(f"Device:           {args.device}")
    print(f"Prefix patterns:  {prefix_patterns}")

    expected_counts = {}
    for entry in args.cat_dlb:
        cat, val = entry.rsplit("=", 1)
        expected_counts.setdefault(cat, {})["dlb"] = int(val)
    for entry in args.cat_width:
        cat, val = entry.rsplit("=", 1)
        expected_counts.setdefault(cat, {})["ecmp_width"] = int(val)
    expected_totals = {}
    if args.expect_dlb is not None:
        expected_totals["dlb"] = args.expect_dlb
    if args.expect_total is not None:
        expected_totals["total"] = args.expect_total

    driver = FbossSwitchInternal(args.device, logger)
    routes = _fetch_routes(driver)
    print(f"Routes fetched:   {len(routes)}\n")

    result = analyze(
        routes,
        driver.ip_ntop,
        prefix_patterns,
        expected_counts,
        expected_totals,
    )

    print(result.message)
    print()
    print(f"Total unique nexthop groups: {result.total_unique_nhgs}")
    print(f"ECMP groups (>1 nexthop):    {result.ecmp_groups}")
    print(f"Single-nexthop groups:       {result.single_hop_groups}")
    print(f"Verdict:                     {'PASS' if result.passed else 'FAIL'}")
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()

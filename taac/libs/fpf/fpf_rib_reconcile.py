#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""FPF RIB reconciliation — BGP vs agent-FIB vs FSDB canonicalRib.

For one GTSW and one injected prefix family (e.g. ``5000:dd::/64`` stepping
``0:0:1::`` for N prefixes), snapshot the same prefixes across the three layers
and report which prefixes are present in each:

  1. BGP RIB          (``fboss2 show bgp table``)
  2. agent route/FIB  (``fboss2 show route``)
  3. FSDB canonicalRib(``fboss2 show fsdb state /bgp/canonicalRib``)

Then print per-layer counts (with the UTC timestamp each query was taken) and a
``prefix | bgp | agent | fsdb`` (yes/no) reconciliation for all N prefixes.

WHY: HRT subscribes to FSDB canonicalRib, so if BGP+FIB have the full scale but
FSDB is short (under-publish) or long (stale/over-publish), HRT diverges and the
FPF convergence checks fail. This tool localizes the divergence to a layer +
lists the exact offending prefixes. The bug is intermittent — re-run the
inject/observe cycle a few times to catch a GTSW where a plane is not at N.

With ``--paste`` it uploads the per-layer dumps + the reconciliation + the
absent-from-FSDB list to Everpaste and prints the URLs.

Usage:
  buck2 run fbcode//scripts/pavanpatil:fpf_rib_reconcile -- \\
    --device gtsw003.l1002.c087.mwg2 \\
    --prefix-base 5000:dd::/64 --increment-step 0:0:1:: --count 1000 --paste

Run from an environment whose thrift/SSH reaches the device; for agent-sandbox
runs prefix with ``TAAC_SSH_VIA_LAB_SSH=1``.
"""

import argparse
import asyncio
import ipaddress
import logging
import re
import typing as t
from datetime import datetime, timezone

from neteng.netcastle.logger import get_root_logger
from neteng.netcastle.utils.everpaste_utils import async_everpaste_str
from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)
from taac.libs.fpf.fpf_fsdb_ribmap import get_fsdb_rib_map

logging.basicConfig(level=logging.INFO, format="%(asctime)s|%(levelname)s| %(message)s")
logger: logging.Logger = get_root_logger()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(p: str) -> t.Optional[str]:
    try:
        return ipaddress.ip_network(p, strict=False).compressed
    except ValueError:
        return None


def _family(prefix_base: str) -> str:
    """Leading constant string shared by every prefix in the family, derived
    from the base network address (e.g. ``5000:dd::/64`` -> ``5000:dd``). Assumes
    the increment lands in a lower hextet than the family id (true for the FPF
    5000:dd / 5000:ee injection scheme)."""
    net = ipaddress.ip_network(prefix_base, strict=False)
    return net.network_address.compressed.rstrip(":")


def _canonical(prefix_base: str, increment_step: str, count: int) -> t.List[str]:
    start = int(ipaddress.ip_network(prefix_base, strict=False).network_address)
    step = int(ipaddress.IPv6Address(increment_step))
    if step == 0:
        raise ValueError(f"--increment-step {increment_step!r} is zero")
    return [
        ipaddress.ip_network((start + i * step, 64), strict=False).compressed
        for i in range(count)
    ]


def _extract(text: str, fam_rx: "re.Pattern[str]") -> t.Set[str]:
    return {n for n in (_norm(m) for m in fam_rx.findall(text)) if n}


def _grep_family(text: str, family: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if family in ln)


def _print_box(
    title_lines: t.List[str],
    headers: t.List[str],
    rows: t.List[t.Tuple[str, ...]],
) -> None:
    """Render a box-drawing table (auto-sized columns) to stdout."""
    cols = range(len(headers))
    w = [max([len(str(headers[c]))] + [len(str(r[c])) for r in rows]) for c in cols]

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w[c] + 2) for c in cols) + right

    def row(cells: t.Sequence[str]) -> str:
        return "│" + "│".join(" " + str(cells[c]).ljust(w[c]) + " " for c in cols) + "│"

    for tl in title_lines:
        print("  " + tl)
    print("  " + border("┌", "┬", "┐"))
    print("  " + row(headers))
    print("  " + border("├", "┼", "┤"))
    for r in rows:
        print("  " + row(r))
    print("  " + border("└", "┴", "┘"))


async def reconcile(args: argparse.Namespace) -> int:
    family = _family(args.prefix_base)
    fam_rx = re.compile(re.escape(family) + r"[:0-9a-f]*::/64")
    canon = _canonical(args.prefix_base, args.increment_step, args.count)
    driver = FbossSwitchInternal(args.device, logger)

    # --- snapshot each layer with a per-query timestamp ---
    bgp_ts = _now()
    bgp_txt = await driver.async_run_cmd_on_shell("fboss2 show bgp table", timeout=120)
    route_ts = _now()
    route_txt = await driver.async_run_cmd_on_shell("fboss2 show route", timeout=120)
    fsdb_ts = _now()
    fsdb_rib = await get_fsdb_rib_map(driver, mode="canonical")

    B = _extract(bgp_txt, fam_rx)
    A = _extract(route_txt, fam_rx)
    F = {n for n in (_norm(k) for k in (fsdb_rib or {}).keys()) if n and family in n}

    setB, setA, setF = set(B), set(A), set(F)
    missing_fsdb = [p for p in canon if p not in setF]
    missing_bgp = [p for p in canon if p not in setB]
    missing_agent = [p for p in canon if p not in setA]

    # --- per-prefix reconciliation (prefix | bgp | agent | fsdb) ---
    lines = [
        f"# {args.device} — {family} ({args.count} prefixes) presence: BGP / AGENT-FIB / FSDB",
        f"# BGP query   : {bgp_ts}   (fboss2 show bgp table)",
        f"# AGENT query : {route_ts}   (fboss2 show route)",
        f"# FSDB query  : {fsdb_ts}   (fboss2 show fsdb state /bgp/canonicalRib)",
        f"# Totals: BGP={len(B)}  AGENT={len(A)}  FSDB={len(F)}  (FSDB missing {len(missing_fsdb)})",
        "",
        f"{'prefix':<26} {'bgp':<4} {'agent':<6} {'fsdb':<4}",
    ]
    for p in canon:
        lines.append(
            f"{p:<26} {'yes' if p in setB else 'no':<4} "
            f"{'yes' if p in setA else 'no':<6} {'yes' if p in setF else 'no':<4}"
        )
    recon = "\n".join(lines) + "\n"

    if args.out:
        with open(args.out, "w") as fh:
            fh.write(recon)

    # --- optional Everpaste upload of the 3 dumps + reconciliation + absent list ---
    bgp_url = route_url = fsdb_url = recon_url = miss_url = "(run with --paste)"
    if args.paste:
        hdr = f"{args.device} {family} query bgp={bgp_ts} route={route_ts} fsdb={fsdb_ts}\n"
        bgp_url = await async_everpaste_str(
            hdr + _grep_family(bgp_txt, family), logger=logger
        )
        route_url = await async_everpaste_str(
            hdr + _grep_family(route_txt, family), logger=logger
        )
        fsdb_url = await async_everpaste_str(hdr + "\n".join(sorted(F)), logger=logger)
        recon_url = await async_everpaste_str(recon, logger=logger)
        miss_url = await async_everpaste_str(
            "\n".join(missing_fsdb) + "\n", logger=logger
        )

    # --- boxed summary table (same shape every run) ---
    dash = "—"
    _print_box(
        [f"{args.device}   family={family}   count={args.count}"],
        ["#", "Layer", "Query (UTC)", family, "Paste"],
        [
            ("1", "BGP table  (show bgp table)", bgp_ts, str(len(B)), bgp_url),
            ("2", "Agent route/FIB  (show route)", route_ts, str(len(A)), route_url),
            (
                "3",
                "FSDB canonicalRib (fsdb state /bgp/canonicalRib)",
                fsdb_ts,
                str(len(F)),
                fsdb_url,
            ),
            (
                "4",
                f"Reconciliation {dash} {args.count} rows bgp·agent·fsdb",
                dash,
                dash,
                recon_url,
            ),
            (
                "5",
                "FSDB-absent list (in BGP+agent, not FSDB)",
                dash,
                str(len(missing_fsdb)),
                miss_url,
            ),
        ],
    )
    print(
        f"  Result: BGP={len(B)}, AGENT={len(A)}, FSDB={len(F)}  ->  "
        f"BGP missing {len(missing_bgp)}, AGENT missing {len(missing_agent)}, "
        f"FSDB missing {len(missing_fsdb)}"
    )

    # nonzero exit if any layer is short of the expected scale (useful in loops)
    return 1 if (missing_fsdb or missing_bgp or missing_agent) else 0


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", required=True, help="GTSW hostname to query.")
    ap.add_argument(
        "--prefix-base",
        default="5000:dd::/64",
        help="First /64 of the injected family (default 5000:dd::/64).",
    )
    ap.add_argument(
        "--increment-step",
        default="0:0:1::",
        help="Per-prefix IPv6 increment (default 0:0:1::, matches injection).",
    )
    ap.add_argument(
        "--count", type=int, default=1000, help="Prefixes injected (default 1000)."
    )
    ap.add_argument(
        "--paste",
        action="store_true",
        help="Upload dumps + reconciliation to Everpaste.",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Also write the reconciliation table to this local file.",
    )
    return ap.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(reconcile(_parse_args())))


if __name__ == "__main__":
    main()

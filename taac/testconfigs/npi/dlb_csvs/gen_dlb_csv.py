#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""IcePack DLB CSV generator — IXIA add-path (prefix, next-hop) upload files.

Produces the *DLB-side* CSVs only. ECMP (Silver/Rouge) stays FORMULAIC
(`CustomNetworkGroupConfig` multiplier/width, per Sriram's
`wedge400_ecmp_resource_testing_config.py`) — do NOT enumerate ECMP here.

Hardware model (TH6/IcePack `gtsw001`, post-T277302860 silicon fix
verified live 2026-06-26 via `dlb_resource_stickiness_runner`):
  - `getMaxArsWidth()  = 128`  ← MEMBERS per single ARS super-group
                                  (was 64 pre-fix; now 128 — silicon
                                  fix landed and confirmed: ECMP Width
                                  column shows 120 on a 511×120 advert)
  - `getMaxArsGroups() = 128`  ← per-stage chip slot count; **usable**
                                  device-wide ARS group budget = 381
                                  (= int(511 * 0.75 − 2), the ECMP
                                  formula; confirmed empirically)
  - `getMaxEcmpMembers() = 128000` (global ECMP member table)
  - 128-unique-NH limit per DLB super-group pool (device-wide budget;
    spine NHs consume slots, so the spine-disable patcher MUST run
    before bgpd FIB sync — see icepack_ecmp_resource_testing_config.py
    + memory entry icepack-dlb-bgpd-multipath-blocker for details).

For DISTINCT-supergroup tests (the whole point of fill_511): every
prefix MUST have a DIFFERENT NH subset, otherwise FBOSS Agent's
EcmpResourceManager DEDUPLICATES same-NH-set prefixes into ONE shared
ARS supergroup. To actually hit the 381-usable-group cap and observe
spillover (post-fix), each prefix's NH set must be unique. Spillover
prefixes get `overrideEcmpSwitchingMode = PER_PACKET_RANDOM` — that's
the silicon's "ARS budget exhausted, fall back to plain ECMP" path.

CSV format (matches the IXIA sample `ixia_data_upload_*.csv`): full
8-hextet IPv6, no leading zeros, no `::` compression. Header:
`Address,Ipv6 Next Hop`. Same Address on N rows = an N-wide ECMP group
formed once IxNetwork advertises via add-path. Different prefixes with
DIFFERENT NH subsets => distinct ECMP groups on silicon. Different
prefixes with the SAME NH subset => dedup'd to ONE shared group.

Outputs (default `./csv`) — post-T277302860 silicon (width cap = 128):
  dlb_fill_511_w64.csv   511 prefixes × 64 DISTINCT NH subsets of 128 NHs
                         → 381 ARS + 130 PER_PACKET_RANDOM spillover
                         (TC#211 / DLB_005 — old-silicon-parity regression)
  dlb_fill_511_w120.csv  511 prefixes × 120 DISTINCT NH subsets of 128 NHs
                         (select 120 of 128) → 381 ARS + 130 spillover at
                         post-fix width (TC#211, DLB_005 — verified
                         working 2026-06-26)
  dlb_members_128.csv    groups whose union = all 128 unique NHs
                         → TC#215 / DLB_006 (fill DLB members)
  dlb_width_128.csv      1 group × 128 NHs (TH6 silicon max width, post-fix)
                         → TC#221 (verifies per-group width cap)
  dlb_overflow_129.csv   128 unique + a 129th NH (a081) → must spill/reject
                         → TC#212 / TC#213 (unique-NH-pool overflow)

Usage:
  python3 gen_dlb_csv.py                       # defaults: 511 groups, width 120, 128 NH pool
  python3 gen_dlb_csv.py --groups 512          # group-count spillover (512th group) → TC#213
  python3 gen_dlb_csv.py --width 128           # exercise the silicon width cap exactly
  python3 gen_dlb_csv.py --out /path/to/dir
"""

import argparse
import csv
import ipaddress
import os

# ---- Default addressing (Gold / DLB-eligible pool on rogue port) ----
# Kept as module constants for backward compatibility with callers that
# don't pass NH-pool kwargs. New callers should pass an NhPool (see
# `dlb_asic_profiles.py`) and use the `_for_pool` wrappers instead.
NH_NETWORK = (
    "2401:db00:206a:c002"  # uplink NH-supporting /64 (the 130-iface DG lives here)
)
NH_HOST_START = 0xA001  # first NH host → ::a001
DLB_PREFIX_NET = "5000:dd"  # advertised DLB (Gold) prefixes → 5000:dd:0:N::


def fmt(addr: str) -> str:
    """Full 8-hextet, no leading zeros, no `::` — matches the IXIA upload sample."""
    return ":".join(
        f"{int(g, 16):x}" for g in ipaddress.IPv6Address(addr).exploded.split(":")
    )


def nh(i: int, network: str = NH_NETWORK, host_start: int = NH_HOST_START) -> str:
    """i-th next-hop address within ``network``, starting at ``host_start``."""
    return fmt(f"{network}::{host_start + i:x}")


def prefix(n: int, prefix_base: str = DLB_PREFIX_NET) -> str:
    """n-th advertised prefix: ``{prefix_base}:0:n::``.

    ``prefix_base`` is the /48 or shorter prefix the route range lives
    in. For Gold (DLB) the default is ``5000:dd``; for Silver use
    ``5000:ee`` (or whatever the NhPool defines).
    """
    # Strip trailing colons so we can splice in ``:0:n::`` without
    # duplicating separators. Accepts both "5000:dd" and "5000:dd::".
    base = prefix_base.rstrip(":")
    return fmt(f"{base}:0:{n:x}::")


def write_csv(path: str, rows) -> int:
    # `lineterminator="\n"`: csv.writer defaults to "\r\n" (Windows
    # CRLF). IxNetwork's ImportBgpRoutes accepts either, but the TAAC
    # `ixia.py::import_bgp_routes` wrapper re-chunks the CSV server-side
    # and treats "\n" as the row separator — keeping the source LF-only
    # avoids the need for CRLF normalisation downstream.
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Address", "Ipv6 Next Hop"])
        w.writerows(rows)
    return len(rows)


def _included_set(g: int, width: int, nh_count: int) -> frozenset:
    """A distinct `width`-NH subset for prefix g, drawn from `nh_count`
    candidates via seeded RNG.

    The earlier mod-arithmetic generator (`base = g*7 % nh_count, step
    = 1 + g // nh_count`) collapsed in tier 2 (step=2 partitioned
    {0..127} into evens vs odds → only 2 distinct sets per tier). RNG
    approach guarantees uniqueness for any `groups <= C(nh_count,
    width)` — for our defaults (C(128,64) ≈ 2.4e37) collisions are
    statistically impossible for 511 groups. Caller wraps a
    deduplicating `while incl in seen: g += nh_count` fallback as a
    belt-and-braces safety net.

    Why include (not exclude): with TH6 `getMaxArsWidth()=64`, the
    INCLUDE side is the small dimension (64 of 128). Earlier
    `_excluded_set` form used 8-of-128 excludes for 120-wide groups
    (assumed 128-wide silicon support; TH6 reality is width=64).
    """
    import random

    rng = random.Random(g)
    return frozenset(rng.sample(range(nh_count), width))


def gen_fill(
    groups: int,
    width: int,
    nh_count: int,
    nh_network: str = NH_NETWORK,
    nh_host_start: int = NH_HOST_START,
    prefix_base: str = DLB_PREFIX_NET,
):
    """`groups` DISTINCT `width`-wide NH subsets of `nh_count` NHs.

    Each prefix gets its OWN unique NH subset → each becomes a distinct
    ECMP group on FBOSS Agent (no dedup by EcmpResourceManager). Union
    of all subsets covers all nh_count NHs (so the super-group both
    reaches `groups` distinct groups AND fills the member pool).

    NH-pool addressing parameters (``nh_network``, ``nh_host_start``,
    ``prefix_base``) default to the Gold pool for backward compat. Pass
    Silver pool fields (or use :func:`gen_fill_for_pool`) for non-DLB
    ECMP test setups.
    """
    # When width >= nh_count, every "subset" is the full pool — there
    # is mathematically only one. Skip the dedup loop so callers can
    # still emit N prefixes all sharing the same NH set
    # (EcmpResourceManager dedups them silicon-side into one shared
    # ECMP group, which is the intended test semantic for width-cap
    # cases like TC#221 / case_12_dlb_width_max).
    skip_dedup = width >= nh_count
    rows, seen = [], set()
    for g in range(groups):
        incl = _included_set(g, min(width, nh_count), nh_count)
        if not skip_dedup:
            bump = 0
            while incl in seen:
                bump += 1
                incl = _included_set(g + bump * nh_count, width, nh_count)
            seen.add(incl)
        for i in sorted(incl):
            rows.append((prefix(g, prefix_base), nh(i, nh_network, nh_host_start)))
    return rows


def gen_members(
    nh_count: int,
    width: int,
    nh_network: str = NH_NETWORK,
    nh_host_start: int = NH_HOST_START,
    prefix_base: str = DLB_PREFIX_NET,
):
    """Minimal groups whose union = all nh_count unique NHs (isolates the
    member dimension)."""
    rows = []
    g = 0
    covered = 0
    start = 0
    while covered < nh_count:
        ids = [i % nh_count for i in range(start, start + width)]
        for i in ids:
            rows.append((prefix(g, prefix_base), nh(i, nh_network, nh_host_start)))
        covered = max(covered, start + width)
        start += width
        g += 1
    return rows


def gen_width(
    width: int = 128,
    nh_network: str = NH_NETWORK,
    nh_host_start: int = NH_HOST_START,
    prefix_base: str = DLB_PREFIX_NET,
):
    """One group using `width` NHs (TH6 silicon max width = 128 post-T277302860 fix)."""
    return [
        (prefix(0, prefix_base), nh(i, nh_network, nh_host_start)) for i in range(width)
    ]


def gen_overflow(
    width: int,
    nh_count: int,
    nh_network: str = NH_NETWORK,
    nh_host_start: int = NH_HOST_START,
    prefix_base: str = DLB_PREFIX_NET,
):
    """Fill the nh_count pool, then add one group that introduces the
    (nh_count+1)-th unique NH → projected unique = nh_count+1 > limit →
    must spill to ECMP / be rejected."""
    rows = gen_members(nh_count, width, nh_network, nh_host_start, prefix_base)
    overflow_group = nh_count  # the (nh_count+1)-th NH (index 128 → a081)
    ids = [overflow_group] + list(range(width - 1))
    rows += [(prefix(900, prefix_base), nh(i, nh_network, nh_host_start)) for i in ids]
    return rows


# ---------------------------------------------------------------------------
# NhPool convenience wrappers — accept an NhPool and dispatch to the
# parameterized generator. Caller doesn't need to know the addressing
# triple. The NhPool type is defined in ``dlb_asic_profiles.py``; we
# duck-type here to avoid an import cycle (this module is a leaf with
# zero TAAC deps).
# ---------------------------------------------------------------------------


def gen_fill_for_pool(pool, groups: int, width: int):
    """:func:`gen_fill` parameterized from an ``NhPool``."""
    return gen_fill(
        groups=groups,
        width=width,
        nh_count=pool.size,
        nh_network=pool.nh_network,
        nh_host_start=pool.nh_host_start,
        prefix_base=pool.prefix_base,
    )


def gen_members_for_pool(pool, width: int):
    """:func:`gen_members` parameterized from an ``NhPool``."""
    return gen_members(
        nh_count=pool.size,
        width=width,
        nh_network=pool.nh_network,
        nh_host_start=pool.nh_host_start,
        prefix_base=pool.prefix_base,
    )


def gen_width_for_pool(pool, width: int):
    """:func:`gen_width` parameterized from an ``NhPool``."""
    return gen_width(
        width=width,
        nh_network=pool.nh_network,
        nh_host_start=pool.nh_host_start,
        prefix_base=pool.prefix_base,
    )


def gen_overflow_for_pool(pool, width: int):
    """:func:`gen_overflow` parameterized from an ``NhPool``."""
    return gen_overflow(
        width=width,
        nh_count=pool.size,
        nh_network=pool.nh_network,
        nh_host_start=pool.nh_host_start,
        prefix_base=pool.prefix_base,
    )


# ---------------------------------------------------------------------------
# Community sidecar CSV — needed because the GTSW `PROPAGATE_GTSW_STSW_IN`
# policy chain gates FIB install on 3 specific community values. Verified
# missing-community failure mode on gtsw001.l1001.c085.ash6 (2026-06-23
# pilot V1): peer ESTABLISHED + PR=1, PA=0. Format is no-header,
# comma-separated AS:Value pairs per row; IXIA round-robins through them.
# A single row applies to all advertised routes uniformly.
#
#   65446:30   — LIVE: rule 1 sets LP=100
#   65441:323  — PATH_COMMUNITY_GTSW_E_HOP3 (rule 4 DENY on miss)
#   65456:323  — LP=90 marker (rule 17 DENY on miss)
# ---------------------------------------------------------------------------
GTSW_GATING_COMMUNITIES: tuple = ("65446:30", "65441:323", "65456:323")


def write_communities_csv(path: str, communities: tuple = GTSW_GATING_COMMUNITIES):
    """Write a 1-row community CSV.

    Format expected by `ixia.py::_parse_communities_file`:
    `AS,LastTwoOctets,AS,LastTwoOctets,...` (pairs of comma-separated
    fields, NOT `AS:LastTwoOctets` colon-separated). The parser does
    `row.split(",")` then walks pairwise. A single row applies to all
    advertised routes uniformly under round-robin distribution.
    """
    flat: list[str] = []
    for c in communities:
        as_num, octets = c.split(":")
        flat.append(as_num)
        flat.append(octets)
    with open(path, "w") as f:
        f.write(",".join(flat) + "\n")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv"),
    )
    ap.add_argument("--groups", type=int, default=511)
    # TH6 silicon cap: getMaxArsWidth() = 128 (members per single ARS
    # group) post-T277302860 fix, confirmed live on gtsw001 2026-06-26
    # via dlb_resource_stickiness_runner — ECMP Width column = 120 on
    # a 511×120 advertisement. Pre-fix the silicon capped at 64 and
    # truncated wider advertisements; that's been fixed.
    ap.add_argument("--width", type=int, default=120)
    ap.add_argument("--nh-count", type=int, default=128)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    jobs = {
        # Old-silicon parity / regression: 511 prefixes × 64 NH subsets.
        # Pre-T277302860 fix this was the only working width; kept so
        # any silicon regression in width handling surfaces immediately.
        # Expected post-fix: 381 ARS (Default DLB) + 130 PER_PACKET_RANDOM
        # spillover (= 511 − int(511 * 0.75 − 2)).
        "dlb_fill_511_w64.csv": gen_fill(a.groups, 64, a.nh_count),
        # Post-fix exercise: 511 prefixes × 120 NH subsets (select 120
        # of 128 NHs per prefix). Each prefix's group is 120 wide — well
        # below the post-fix silicon cap of 128 but exercises the full
        # member-table dimension. Expected: 381 ARS + 130 spillover at
        # ECMP Width = 120. Verified working on gtsw001 2026-06-26.
        "dlb_fill_511_w120.csv": gen_fill(a.groups, 120, a.nh_count),
        # Member coverage: groups whose union covers all 128 unique NHs
        # in the DLB pool. TC#215 (DLB member-table fill).
        "dlb_members_128.csv": gen_members(a.nh_count, a.width),
        # Per-group width cap exercise: 1 group × 128 NHs at silicon
        # max width (post-fix). TC#221 — validates per-group width
        # programs to 128. Pre-fix this used to be `dlb_width_64.csv`
        # at the pre-fix silicon cap.
        "dlb_width_128.csv": gen_width(a.width),
        # Unique-NH-pool overflow: 128 unique + a 129th NH (a081) →
        # must spill/reject (TH6 DLB unique-NH pool size = 128).
        "dlb_overflow_129.csv": gen_overflow(a.width, a.nh_count),
    }
    for name, rows in jobs.items():
        n = write_csv(os.path.join(a.out, name), rows)
        groups = len({r[0] for r in rows})
        nhs = len({r[1] for r in rows})
        print(f"{name:24s} rows={n:>7d}  groups={groups:>4d}  unique_nh={nhs:>4d}")
    print(f"\nWrote to {a.out}  (DLB only; ECMP stays formulaic — see KB blueprint)")


if __name__ == "__main__":
    main()

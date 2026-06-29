#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Drive an existing IxNetwork session from a 2-column (prefix, NH) CSV.

Each prefix becomes one IP Route Range entry; each NH per prefix becomes
one add-path advertisement. Uses per-column
`Multivalue.ValueList(filename)` to populate Address + Ipv6NextHop
columns from the CSV's two columns.

CRITICAL — IxNetwork geometry requires THREE parameters to multiply
correctly into per-prefix add-path advertisements (research with Pavan
2026-06-25):

  total_advertisements = pool.NumberOfAddresses * NG.Multiplier

  - `pool.NumberOfAddresses` = distinct prefix count (e.g. 511)
  - `NG.Multiplier`           = per-prefix add-path replication (e.g. 64
                                or 120). MUST be set in concert with
                                NumberOfAddresses for the NH ValueList
                                to actually multiply into 64/120 paths
                                per prefix. With NG.Multiplier=1 (the
                                default), each prefix gets EXACTLY ONE
                                NH from the ValueList regardless of how
                                many entries the list contains — that
                                was the silent-failure mode for our
                                pre-2026-06-25 attempts which only
                                produced bgpd Rcvd=511 not 32704.
  - `Ipv6NextHop.ValueList`   = list of `total_advertisements` NH
                                values, cycled across the (prefix,
                                replica) tuple positions.

For a CSV with N distinct prefixes × W NHs each (so the file has N*W
rows), the right knobs are:

  pool.NumberOfAddresses = N    (parsed from CSV: distinct prefix count)
  NG.Multiplier          = W    (parsed from CSV: rows-per-prefix)
  Ipv6NextHop.ValueList  = N*W NHs (the CSV's NH column in order)
  AddPathId.ValueList    = 1..N*W (unique add-path IDs)
  MvNextHopCount         = W    (NHs per route advertisement)

Usage:
  buck2 run fbcode//neteng/test_infra/dne/taac/testconfigs/npi/dlb_csvs:ixia_csv_inject -- \\
    --csv /tmp/icepack_dlb_csvs/dlb_fill_511_w64.csv \\
    --api-server 2401:db00:2066:31fb::3019 --session-id 220
"""

import argparse
import logging

from ixnetwork_restpy.assistants.sessions.sessionassistant import SessionAssistant
from taac.ixia.ixia import Ixia


def split_csv(path: str, prefix_out: str, nh_out: str) -> tuple[int, int, int]:
    """Read 2-col CSV (header + rows), write column 1 to prefix_out,
    column 2 to nh_out. Returns (total_rows, distinct_prefixes, nhs_per_prefix).

    Both prefix_out and nh_out get the FULL N*W entries (row-major repeated:
    each prefix appears W times consecutively, paired with its W NHs in CSV
    order). This is the FLAT geometry Pavan's hand-import produces — IxNetwork
    reads NetworkAddress.ValueList sequentially across NG copies, so to get
    "511 prefixes × 64 NHs each as true multipath" we feed it 32704 (addr, NH)
    slots with NG.Multiplier=32704 and pool.NumberOfAddresses=1. Result: each
    prefix appears 64× from the same BGP session (same router-id) and bgpd
    installs all 64 as ECMP. Verified live on session 220 2026-06-25.
    """
    prefixes_in_order: list[str] = []
    nhs_in_order: list[str] = []
    with open(path) as f:
        f.readline()  # skip header
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            cols = line.split(",")
            if len(cols) < 2:
                continue
            prefixes_in_order.append(cols[0])
            nhs_in_order.append(cols[1])

    distinct_prefixes = list(dict.fromkeys(prefixes_in_order))
    rows_per_prefix = (
        len(prefixes_in_order) // len(distinct_prefixes) if distinct_prefixes else 0
    )

    with open(prefix_out, "w") as f:
        for p in prefixes_in_order:
            f.write(p + "\n")
    with open(nh_out, "w") as f:
        for n in nhs_in_order:
            f.write(n + "\n")
    return len(prefixes_in_order), len(distinct_prefixes), rows_per_prefix


def main() -> None:  # noqa: C901
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="2-col CSV (Address, Ipv6 Next Hop)")
    ap.add_argument("--api-server", default="2401:db00:2066:31fb::3019")
    ap.add_argument("--session-id", type=int, default=220)
    ap.add_argument("--pool-name", default="DLB_GOLD_PREFIX_POOL")
    ap.add_argument(
        "--ng-multiplier",
        type=int,
        default=None,
        help=(
            "NetworkGroup.Multiplier override. Default behavior: "
            "1 (flat geometry — single emulated peer, per-prefix add-path "
            "via MvNextHopCount=W). Passing W gives the triangle geometry "
            "(W NG copies, each advertising N sequential prefixes with "
            "copy-index offset). Triangle empirically gets routes into "
            "FIB (2026-06-25 ~21:00 PT, 574 prefixes, ~448 with 64-NH "
            "multipath). Flat is what Pavan's manual import produces."
        ),
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)

    prefix_csv = "/tmp/icepack_dlb_csvs/_inject_prefixes.csv"
    nh_csv = "/tmp/icepack_dlb_csvs/_inject_nhs.csv"
    print(f"[1/7] Splitting {args.csv} into per-column files")
    total_rows, distinct_prefixes, w = split_csv(args.csv, prefix_csv, nh_csv)
    print(f"      rows={total_rows}  distinct_prefixes={distinct_prefixes}  width={w}")

    print(f"[2/7] Connecting to session {args.session_id}")
    password = Ixia.fetch_ixia_credentials(secret_name="", secret_group="")
    sa = SessionAssistant(
        IpAddress=args.api_server,
        RestPort=None,
        UserName="admin",
        Password=password,
        SessionId=args.session_id,
    )
    ixn = sa.Ixnetwork
    print(f"      session {sa.Session.Id}")

    print("[3/7] Locating BgpV6IPRouteProperty + parent pool/NG/DG")
    route_prop = None
    parent_pool = None
    parent_ng = None
    parent_dg = None
    for topo in ixn.Topology.find():
        for dg in topo.DeviceGroup.find():
            for ng in dg.NetworkGroup.find():
                if ng.Name != args.pool_name:
                    continue
                parent_ng = ng
                parent_dg = dg
                for pool in ng.Ipv6PrefixPools.find():
                    parent_pool = pool
                    for rp in pool.BgpV6IPRouteProperty.find():
                        route_prop = rp
                        break
                    if route_prop:
                        break
                break
            if route_prop:
                break
        if route_prop:
            break
    if (
        route_prop is None
        or parent_pool is None
        or parent_ng is None
        or parent_dg is None
    ):
        raise SystemExit(f"No BgpV6IPRouteProperty in NG '{args.pool_name}'")
    # Narrow Optional types post-locate for pyre (the SystemExit above is
    # the early-return guard; pyre doesn't propagate that into the
    # downstream attribute accesses without these asserts).
    assert route_prop is not None
    assert parent_pool is not None
    assert parent_ng is not None
    assert parent_dg is not None
    print(
        f"      route_prop={route_prop.href}; pool={parent_pool.Name}; "
        f"ng={parent_ng.Name}; dg={parent_dg.Name}"
    )

    # CORRECT IxNetwork mutation sequence (Pavan rule, 2026-06-25):
    #   1) dg.Stop()       — disable the device group
    #   2) mutate routes   — pool/NG/route_prop changes
    #   3) dg.Start()      — re-enable; commits all mutations atomically
    #
    # Earlier attempts only called StopAllProtocols + topo.Stop() +
    # ng.Stop() — none of which actually cycle the DeviceGroup, the unit
    # that owns the BGP session and commits prefix pool / route-property
    # mutations. Result: PR=1 / NH=1 on session 220 even after
    # NG.Multiplier and ValueList went through without error.
    print(f"[3.5/7] dg.Stop() + ng.Stop() on {parent_dg.Name} / {parent_ng.Name}")
    # Both layers must be stopped before mutating NG.Multiplier.
    # IxNetwork rejects "Changing the Multiplier in a started Network
    # Group" with BadRequestError if only the DG was stopped — observed
    # empirically 2026-06-25.
    try:
        parent_dg.Stop()
        print("        dg.Stop() OK")
    except Exception as e:
        print(f"        dg.Stop() failed (continuing): {e}")
    try:
        parent_ng.Stop()
        print("        ng.Stop() OK")
    except Exception as e:
        print(f"        ng.Stop() failed (continuing): {e}")

    if args.ng_multiplier is None:
        ng_mult = total_rows
        num_addrs = 1
        mode = "FLAT (Pavan)"
    else:
        ng_mult = args.ng_multiplier
        num_addrs = distinct_prefixes
        mode = f"TRIANGLE (--ng-multiplier={ng_mult})"
    expected_total = num_addrs * ng_mult
    print(
        f"[4/7] {mode}: NG.Multiplier={ng_mult}, NumberOfAddresses={num_addrs} "
        f"→ {expected_total} advertisements"
    )
    parent_ng.Multiplier = ng_mult
    parent_pool.NumberOfAddresses = num_addrs
    parent_pool.PrefixLength.Single(64)
    print(
        f"      pool NumberOfAddresses={parent_pool.NumberOfAddresses}, "
        f"NG.Multiplier={parent_ng.Multiplier} (CSV W={w})"
    )

    print(f"[5/7] Address column ValueList from {prefix_csv}")
    parent_pool.NetworkAddress.ValueList(prefix_csv)
    print("      OK")

    print(f"[6/7] Ipv6NextHop ValueList from {nh_csv} ({total_rows} values)")
    print(f"      EnableAddPath, MvNextHopCount={w}, AddPathId 1..{total_rows}")
    route_prop.Ipv6NextHop.ValueList(nh_csv)
    route_prop.EnableAddPath.Single(True)
    # MvNextHopCount = number of NHs per route = constant width per prefix.
    route_prop.MvNextHopCount.Single(w)
    # AddPathId per (prefix, NH) row — total_rows = distinct_prefixes * w
    route_prop.AddPathId.ValueList([str(i + 1) for i in range(total_rows)])
    # Defensively disable any stale route-flap regime left over from
    # previous IxNetwork-UI experimentation. Without this, prior
    # EnableFlap=True + Uptime/Downtime settings would resume after
    # dg.Start and cause the DUT's BGP Prefixes-Received count to
    # oscillate down over time (observed on session 220 2026-06-25 with
    # PR shrinking 20951 → 16863 over 30 min).
    for attr_name in ("EnableFlap", "EnableFlapping", "RouteFlap"):
        attr = getattr(route_prop, attr_name, None)
        if attr is None:
            continue
        try:
            attr.Single(False)
            print(f"      {attr_name}=False")
            break
        except Exception as e:
            print(f"      {attr_name} disable failed (continuing): {e}")
    print("      OK")

    print(f"[7/7] ng.Start() + dg.Start() on {parent_ng.Name} / {parent_dg.Name}")
    # Start inner-to-outer (NG then DG) to match the Stop order
    # (outer-to-inner). NG.Start commits the multiplier/pool mutations;
    # DG.Start brings the BGP session back up with the new route set.
    try:
        parent_ng.Start()
        print("      ng.Start() OK")
    except Exception as e:
        print(f"      ng.Start() failed (continuing): {e}")
    try:
        parent_dg.Start()
        print("      dg.Start() OK")
    except Exception as e:
        print(f"      dg.Start() failed (continuing): {e}")
    try:
        ixn.StartAllProtocols(Arg1="sync")
        print("      StartAllProtocols OK")
    except Exception as e:
        print(f"      StartAllProtocols failed: {e}")

    print("\nDone. Wait ~60-90s for BGP convergence then probe DUT.")


if __name__ == "__main__":
    main()

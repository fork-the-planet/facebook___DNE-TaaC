#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Inject a per-column NH ValueList into the live IxNetwork session's
DLB_GOLD_PREFIX_POOL — bypasses CNG's "fixed/incremented" NH mode by
populating the Ipv6NextHop MultiValue via `ValueList(filename)`.

This is the SINGLE-PREFIX × N add-path pattern (one prefix advertised
with N NHs). For MULTI-PREFIX × N add-paths use `ixia_csv_inject.py`
(reads a 2-column prefix,NH CSV).

CRITICAL — IxNetwork advertisement geometry (research w/ Pavan
2026-06-25): per-prefix add-path replication is governed by
NG.Multiplier, NOT just the NH ValueList length:

  total_advertisements = pool.NumberOfAddresses * NG.Multiplier

To get 1 prefix × 128 add-paths, set:
  --num-prefixes 1
  --ng-multiplier 128
  --nh-count 128
  (= 1 * 128 = 128 advertisements, NH ValueList of 128 values)

With NG.Multiplier=1 the NH ValueList collapses to 1 NH per prefix
regardless of how many entries you provide — silent failure mode.

Usage:
  buck2 run fbcode//neteng/test_infra/dne/taac/testconfigs/npi/dlb_csvs:ixia_nh_inject -- \\
    --api-server 2401:db00:2066:31fb::3019 \\
    --session-id 220 \\
    --nh-count 64 --num-prefixes 1 --ng-multiplier 64
"""

import argparse
import logging
import os

from ixnetwork_restpy.assistants.sessions.sessionassistant import SessionAssistant
from taac.ixia.ixia import Ixia


def gen_nh_csv(path: str, start_hex: int = 0xA001, count: int = 128) -> None:
    """Generate a single-column NH CSV (one fully-exploded IPv6 NH per line)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        for i in range(count):
            f.write(f"2401:db00:206a:c002:0:0:0:{start_hex + i:x}\n")


def main() -> None:  # noqa: C901
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-server", default="2401:db00:2066:31fb::3019")
    ap.add_argument("--session-id", type=int, default=220)
    ap.add_argument(
        "--nh-csv",
        default="/tmp/icepack_dlb_csvs/dlb_nh_only_128.csv",
        help="Single-column NH CSV (will be regenerated)",
    )
    ap.add_argument("--nh-count", type=int, default=128)
    ap.add_argument(
        "--num-prefixes",
        type=int,
        default=1,
        help="NumberOfAddresses on the prefix pool (= distinct prefix count)",
    )
    ap.add_argument(
        "--ng-multiplier",
        type=int,
        default=None,
        help="NetworkGroup multiplier (default: nh-count)",
    )
    ap.add_argument(
        "--pool-name",
        default="DLB_GOLD_PREFIX_POOL",
        help="Network group name to locate the prefix pool in",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)

    print(f"[1/6] Generating {args.nh_count}-NH CSV at {args.nh_csv}")
    gen_nh_csv(args.nh_csv, count=args.nh_count)
    with open(args.nh_csv) as f:
        lines = f.read().splitlines()
    print(f"      {len(lines)} lines; first 3: {lines[:3]}; last: {lines[-1]}")

    print(f"[2/6] Connecting to session {args.session_id}")
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

    print("[3/6] Locating BgpV6IPRouteProperty inside DLB_GOLD_PREFIX_POOL NG")
    route_prop = None
    for topo in ixn.Topology.find():
        for dg in topo.DeviceGroup.find():
            for ng in dg.NetworkGroup.find():
                if ng.Name != args.pool_name:
                    continue
                pools = ng.Ipv6PrefixPools.find()
                for pool in pools:
                    for rp in pool.BgpV6IPRouteProperty.find():
                        route_prop = rp
                        print(
                            f"      found: topo={topo.Name} dg={dg.Name}"
                            f" ng={ng.Name} pool={pool.Name}"
                            f" route_prop_href={rp.href}"
                        )
                        break
                    if route_prop is not None:
                        break
            if route_prop is not None:
                break
        if route_prop is not None:
            break
    if route_prop is None:
        raise SystemExit(f"No BgpV6IPRouteProperty found in NG '{args.pool_name}'")

    print("[3.5/6] Locating parent_dg/ng/pool for the named NG")
    # Locate parent_dg in addition to parent_ng/pool — the DG is the
    # IxNetwork unit that owns BGP session emulation and commits prefix
    # pool / route-property mutations at Start time. Per Pavan rule
    # (2026-06-25): dg.Stop() → mutate → dg.Start().
    parent_dg = None
    parent_ng = None
    parent_pool = None
    for topo in ixn.Topology.find():
        for dg in topo.DeviceGroup.find():
            for ng in dg.NetworkGroup.find():
                if ng.Name != args.pool_name:
                    continue
                parent_dg = dg
                parent_ng = ng
                for pool in ng.Ipv6PrefixPools.find():
                    parent_pool = pool
                    break
                break
            if parent_ng:
                break
        if parent_ng:
            break
    if parent_dg is None or parent_ng is None or parent_pool is None:
        raise SystemExit(f"No DeviceGroup parent found for NG '{args.pool_name}'")
    # Narrow Optional types post-locate for pyre.
    assert parent_dg is not None
    assert parent_ng is not None
    assert parent_pool is not None
    print(f"      dg={parent_dg.Name}; ng={parent_ng.Name}; pool={parent_pool.Name}")

    print(f"[3.6/6] dg.Stop() + ng.Stop() on {parent_dg.Name} / {parent_ng.Name}")
    # Both layers must be stopped before mutating NG.Multiplier
    # ("Changing the Multiplier in a started Network Group is not
    # permitted" — observed 2026-06-25).
    try:
        parent_dg.Stop()
        print("      dg.Stop() OK")
    except Exception as e:
        print(f"      dg.Stop() failed (continuing): {e}")
    try:
        parent_ng.Stop()
        print("      ng.Stop() OK")
    except Exception as e:
        print(f"      ng.Stop() failed (continuing): {e}")

    print(
        "[3.7/6] Set NetworkGroup.Multiplier and pool.NumberOfAddresses "
        "(geometry knobs — see docstring)"
    )
    mult = args.ng_multiplier if args.ng_multiplier is not None else args.nh_count
    try:
        parent_ng.Multiplier = mult
        print(f"      NG.Multiplier -> {mult}")
    except Exception as e:
        print(f"      NG.Multiplier set failed: {e}")
    try:
        parent_pool.NumberOfAddresses = args.num_prefixes
        print(f"      pool.NumberOfAddresses -> {args.num_prefixes}")
    except Exception as e:
        print(f"      pool resize failed: {e}")
    print(
        f"      expected total advertisements = "
        f"{args.num_prefixes} * {mult} = {args.num_prefixes * mult}"
    )

    print(
        f"[5a/6] Setting MvNextHopCount = {args.nh_count} (NHs per route advertisement)"
    )
    try:
        route_prop.MvNextHopCount.Single(args.nh_count)
        print(f"      MvNextHopCount -> {args.nh_count}")
    except Exception as e:
        print(f"      MvNextHopCount set failed: {e}")
    print("[5b/6] Enabling AddPath on the route property")
    try:
        route_prop.EnableAddPath.Single(True)
        print("      EnableAddPath -> True")
    except Exception as e:
        print(f"      EnableAddPath set failed: {e}")
    print("[5c/6] Setting Ipv6NextHop ValueList from file")
    nh_mv = route_prop.Ipv6NextHop
    nh_mv.ValueList(args.nh_csv)
    print(f"      assigned {args.nh_count} NHs to Ipv6NextHop")

    print(
        f"[5d/6] Setting AddPathId ValueList = [1..{args.nh_count}] "
        f"(unique add-path ID per advertisement)"
    )
    try:
        ids = [str(i + 1) for i in range(args.nh_count)]
        route_prop.AddPathId.ValueList(ids)
        print(f"      AddPathId ValueList = 1..{args.nh_count}")
    except Exception as e:
        print(f"      AddPathId set failed: {e}")

    print(f"[6/6] ng.Start() + dg.Start() on {parent_ng.Name} / {parent_dg.Name}")
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

    print("[verify] reading back NH values from the MultiValue")
    try:
        vals = list(nh_mv.Values)
        unique = set(vals)
        print(
            f"      NH count: {len(vals)}; unique: {len(unique)};"
            f" first 3: {vals[:3]}; last: {vals[-1] if vals else '(empty)'}"
        )
    except Exception as e:
        print(f"      verify failed: {e}")

    print("\nDone. To apply on-the-fly: ixn.Globals.Topology.ApplyOnTheFly()")
    print("Or restart protocols: ixn.StopAllProtocols(); ixn.StartAllProtocols()")


if __name__ == "__main__":
    main()

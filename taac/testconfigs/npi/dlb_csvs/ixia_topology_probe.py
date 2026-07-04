#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Probe an existing IxNetwork session and dump the live BGP route-range shape.

Attaches to a running IxNetwork session by ID, walks
Topology -> DeviceGroup -> NetworkGroup -> Ipv6PrefixPools -> BgpV6IPRouteProperty,
and prints the configured shape (address count, NH count, NH list, communities) so
we can verify what IxNetwork is *actually* advertising vs what we *expect* from
the testconfig.

Usage:
  buck2 run fbcode//neteng/test_infra/dne/taac/testconfigs/npi/dlb_csvs:ixia_topology_probe -- \\
    --api-server 2401:db00:2066:31fb::3019 --session-id 212

Defaults match the IcePack GTSW setup (chassis ixia19.netcastle.ash6).
"""

import argparse
import logging

from ixnetwork_restpy.assistants.sessions.sessionassistant import SessionAssistant
from taac.ixia.ixia import Ixia


logger = logging.getLogger(__name__)


def _values_of(multivalue):
    """Best-effort extraction of all values from a MultiValue object."""
    try:
        return list(multivalue.Values)
    except Exception as e:
        return [f"<error reading values: {e}>"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--api-server",
        default="2401:db00:2066:31fb::3019",
        help="IxNetwork API server (= chassis IP for our setup)",
    )
    ap.add_argument("--session-id", type=int, default=212, help="IxNetwork session ID")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)

    print(f"Connecting to {args.api_server} session {args.session_id}...")
    password = Ixia.fetch_ixia_credentials(secret_name="", secret_group="")
    sa = SessionAssistant(
        IpAddress=args.api_server,
        RestPort=None,
        UserName="admin",
        Password=password,
        SessionId=args.session_id,
    )
    ixn = sa.Ixnetwork
    print(f"Connected — session {sa.Session.Id}")

    # List ALL sessions visible to this user on this API server.
    try:
        all_sessions = sa.TestPlatform.Sessions.find()
        print("\n=== All sessions on this API server ===")
        for s in all_sessions:
            print(
                f"  Session ID={s.Id}  Name={s.Name}  State={getattr(s, 'State', '?')}  UserId={getattr(s, 'UserId', '?')}"
            )
    except Exception as e:
        print(f"  (session-list failed: {e})")

    for topo in ixn.Topology.find():
        print(f"\n=== Topology: {topo.Name} ===")
        for dg in topo.DeviceGroup.find():
            # Runtime status fields (vs. config-only Enabled).
            status = getattr(dg, "Status", "?")
            print(
                f"  Device group: {dg.Name}  Multiplier={dg.Multiplier}"
                f"  Enabled={dg.Enabled}  Status={status}"
            )
            # Probe Ethernet/IPv6/BGPv6 runtime state per DG (root cause
            # hunt for Silver-not-landing 2026-06-29 — DG marked Enabled
            # but Silver's L2/L3/BGP never come up).
            for eth in dg.Ethernet.find():
                eth_macs = _values_of(eth.Mac)
                eth_status = getattr(eth, "Status", "?")
                print(
                    f"    Ethernet: Name={eth.Name}  Mac={eth_macs[:1]}  Status={eth_status}"
                )
                for ip6 in eth.Ipv6.find():
                    ip6_addrs = _values_of(ip6.Address)
                    ip6_status = getattr(ip6, "Status", "?")
                    ip6_gw = _values_of(ip6.GatewayIp)
                    print(
                        f"      IPv6: Name={ip6.Name}  Addr={ip6_addrs[:1]}"
                        f"  Gateway={ip6_gw[:1]}  Status={ip6_status}"
                    )
                    for bgp in ip6.BgpIpv6Peer.find():
                        try:
                            ss = bgp.SessionStatus
                        except Exception as e:
                            ss = f"<err: {e}>"
                        bgp_dut = _values_of(bgp.DutIp)
                        bgp_status = getattr(bgp, "Status", "?")
                        print(
                            f"        BGPv6Peer: Name={bgp.Name}  PeerAddr={bgp_dut[:1]}"
                            f"  Status={bgp_status}  SessionStatus={ss}"
                        )
            for ng in dg.NetworkGroup.find():
                print(
                    f"    Network group: {ng.Name}  Multiplier={ng.Multiplier}  Enabled={ng.Enabled}"
                )
                for pool in ng.Ipv6PrefixPools.find():
                    addresses = _values_of(pool.NetworkAddress)
                    print(f"      IPv6 prefix pool: {pool.Name}")
                    print(f"        NumberOfAddresses: {pool.NumberOfAddresses}")
                    print(f"        PrefixLength: {pool.PrefixLength}")
                    print(
                        f"        NetworkAddress count: {len(addresses)}  first 3: {addresses[:3]}  last 3: {addresses[-3:]}"
                    )
                    for rp in pool.BgpV6IPRouteProperty.find():
                        nh_vals = _values_of(rp.Ipv6NextHop)
                        nh_mode = _values_of(rp.NextHopType)
                        nh_inc_mode = _values_of(rp.NextHopIncrementMode)
                        print("        BgpV6IPRouteProperty:")
                        print(f"          NextHopType (Single/Manually): {nh_mode}")
                        print(f"          NextHopIncrementMode: {nh_inc_mode}")
                        print(
                            f"          IPv6 NextHop count: {len(nh_vals)}  unique: {len(set(nh_vals))}"
                        )
                        print(f"          IPv6 NextHop first 5: {nh_vals[:5]}")
                        print(f"          IPv6 NextHop last 5: {nh_vals[-5:]}")
                        try:
                            print(
                                f"          EnableCommunity: {_values_of(rp.EnableCommunity)}"
                            )
                            print(f"          NoOfCommunities: {rp.NoOfCommunities}")
                            for ci, c in enumerate(rp.BgpCommunitiesList.find()):
                                ass = _values_of(c.AsNumber)
                                lto = _values_of(c.LastTwoOctets)
                                ctype = _values_of(c.Type)
                                print(
                                    f"          Community[{ci}]: AS={ass}  Octets={lto}  Type={ctype}"
                                )
                        except Exception as e:
                            print(f"          (community read failed: {e})")


if __name__ == "__main__":
    main()

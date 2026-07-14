# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe

"""IxNetwork next-hop pool definitions for KO3 ECMP-only resource testing.

An ``EcmpNhPool`` is the single build-time source of truth that ties together
the prefix/next-hop addressing baked into the generated CSV (via
``gen_ecmp_csv.*_for_pool``) and the IxNetwork NetworkGroup the CSV is later
injected into. It is deliberately independent of the DLB ``NhPool`` in
``dlb_asic_profiles.py`` -- KO3 has no DLB, so this tree carries no DLB deps.

The pool's ``size`` is the device-wide UNIQUE next-hop budget (KO3 = 500). The
generator draws every group's next-hop subset from ``range(size)``, so the union
of unique NHs across all groups can never exceed it -- which is exactly what the
sliding-window ``CustomNetworkGroupConfig`` approach could not guarantee.

Consistency contract (all must agree or routes blackhole / the mutate step
raises "No NetworkGroup named ..."):
  * ``prefix_base`` / ``nh_network`` / ``nh_host_start`` must match the baseline
    ``CustomNetworkGroupConfig`` (``prefix_start_value`` / ``nexthop_start_value``)
    in the testconfig, and the NDP-supporting device group must cover
    ``nh_network::(nh_host_start .. nh_host_start + size - 1)``.
  * the IxNetwork NetworkGroup name (see ``pool_name`` / the testconfig's
    ``network_group_name``) is the runtime match key for ``apply_pool_mutations``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EcmpNhPool:
    """An IxNetwork-side NH range that ECMP route advertisements draw from.

    ``name``          : label, also used as an on-disk CSV sub-path component.
    ``prefix_base``   : IPv6 prefix the advertised routes live in (e.g. ``5000:dd::``).
    ``nh_network``    : /64 the next-hops live in; must be NDP-resolvable from the DUT.
    ``nh_host_start`` : first NH host offset within ``nh_network`` (e.g. ``0xA001``).
    ``size``          : pool size in UNIQUE next-hops -- the device-wide cap
                        (KO3/G200 = 500).
    ``pool_name``     : the IxNetwork NetworkGroup name the CSV mutates in place.
    """

    name: str
    prefix_base: str
    nh_network: str
    nh_host_start: int
    size: int
    pool_name: str


# KO3 Main ECMP pool for rb002-02.qxt1 (rogue port `eth1/64/5`, parent /64
# `2401:db00:206a:1::`). `size=500` is the KO3 unique-NH cap; the NDP-supporting
# device group must advertise at least 500 NHs starting at ::a001. `pool_name`
# matches the baseline `CustomNetworkGroupConfig.network_group_name` on the Main
# device group.
KO3_MAIN_ECMP_POOL: EcmpNhPool = EcmpNhPool(
    name="ko3_main",
    prefix_base="5000:dd::",
    nh_network="2401:db00:206a:1",
    nh_host_start=0xA001,
    size=500,
    pool_name="MAIN_ECMP_PREFIXES",
)

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe

"""ASIC-level profiles + IxNetwork NH-pool definitions for DLB/ECMP
hardening tests.

Per-ASIC silicon caps come from the platform spec sheet. "Usable" caps
are derived via the ECMP `int(N * 0.75 - 2)` formula (the device-wide
budget that bounds how many groups/members can actually be programmed
before spillover). Empirically confirmed on TH6 / IcePack 2026-06-25 via
`dlb_resource_stickiness_runner` on `gtsw001.l1001.c085.ash6`: 511 raw
DLB groups → 381 usable, with 130 spilling to `PER_PACKET_RANDOM`.

NhPool selects which IxNetwork NH range a test draws from. Gold uses
NHs inside the per-chip DLB NH-table (128 unique entries on TH6) so
silicon classifies the prefix as ARS-eligible. Silver uses NHs outside
that pool so silicon classifies as plain ECMP. Adding a new pool = new
NhPool constant, no factory change.

For future NPI ASICs: add a new `DlbEcmpAsicProfile` constant plus any
new `NhPool` instances. The factory + generator + healthcheck layer
re-uses without per-ASIC editing.
"""

from dataclasses import dataclass


def usable_from_raw(raw: int) -> int:
    """ECMP-formula usable cap: ``int(N * 0.75 - 2)``.

    Empirically confirmed on TH6 for DLB groups: raw=511 → usable=381
    (matches stickiness-runner observed split 381 DLB + 130
    PER_PACKET_RANDOM). Same formula applies to ECMP groups and ECMP
    member-table entries device-wide.
    """
    return int(raw * 0.75 - 2)


@dataclass(frozen=True)
class NhPool:
    """An IxNetwork-side NH range that BGP route advertisements draw from.

    ``name``           : label, also used as a sub-path component in CSV
                         output (``/tmp/dlb_csvs/<asic>/<name>/...``).
    ``prefix_base``    : IPv6 prefix the test routes live in
                         (e.g. ``"5000:dd::"`` for the DLB Gold range).
    ``nh_network``     : /64 the NHs live in. Must be NDP-resolvable
                         from the DUT via the rogue-port interface.
    ``nh_host_start``  : First NH host offset within ``nh_network``
                         (e.g. ``0xA001`` → ``::a001``).
    ``size``           : Pool size in unique NHs. For Gold this must be
                         ≤ the per-chip DLB unique-NH limit
                         (``DlbEcmpAsicProfile.dlb_max_unique_nhs``).
                         For Silver it's bounded by ECMP member budget.
    """

    name: str
    prefix_base: str
    nh_network: str
    nh_host_start: int
    size: int


@dataclass(frozen=True)
class DlbEcmpAsicProfile:
    """Per-ASIC silicon caps for DLB/ECMP hardening test derivation.

    Raw values mirror the platform spec sheet columns. Usable values
    are computed via :func:`usable_from_raw`. Per-test scale points
    (50% occupancy, 100% groups, etc.) are derived in the factory from
    these caps so an ASIC swap re-computes everything automatically.
    """

    name: str
    dlb_max_groups_raw: int
    dlb_max_unique_nhs: int  # per-chip DLB NH-table size
    dlb_max_width: int  # per-group max NHs (silicon cap)
    dlb_max_members_raw: int  # DLB member-entry table (sum of widths across DLB groups)
    ecmp_max_groups_raw: int
    ecmp_max_members_raw: int  # device-wide ECMP member-table size
    ecmp_max_width: int  # per-group max NHs (silicon cap, non-DLB)

    @property
    def dlb_max_groups_usable(self) -> int:
        return usable_from_raw(self.dlb_max_groups_raw)

    @property
    def ecmp_max_groups_usable(self) -> int:
        return usable_from_raw(self.ecmp_max_groups_raw)

    @property
    def ecmp_max_members_usable(self) -> int:
        # Note: N*0.75-2 formula is empirically confirmed for GROUPS (381 of 511);
        # whether it also applies to member-entry tables is not empirically
        # verified. We use it here for symmetry but member-cap-stress tests
        # should treat this as conservative (real ceiling may be higher).
        return usable_from_raw(self.ecmp_max_members_raw)

    @property
    def dlb_max_members(self) -> int:
        """Hard cap on DLB member entries (sum of widths across DLB groups).

        Not the N*0.75-2 budget — DLB member table is allocated separately
        from groups, treated as hard cap. Per Pavan's spec sheet column +
        2026-06-25 confirmation: 4K on TH6.
        """
        return self.dlb_max_members_raw


# IxNetwork NH pools for the IcePack/TH6 DLB hardening setup on
# gtsw001.l1001.c085.ash6 (rogue port `eth1/1/3`, parent /64
# `2401:db00:206a:c002::`).
#
# Gold draws from the first 128 NHs in the rogue /64 — these match the
# per-chip DLB unique-NH table, so silicon classifies advertised
# prefixes via this pool as ARS supergroups.
# Silver draws from NHs at offset ::b001+ in the same /64 — beyond the
# DLB unique-NH window, so silicon classifies as plain ECMP. Sized for
# the full non-DLB ECMP budget on TH6.
ICEPACK_GOLD_POOL: NhPool = NhPool(
    name="gold",
    prefix_base="5000:dd::",
    nh_network="2401:db00:206a:c002",
    nh_host_start=0xA001,
    size=128,
)

ICEPACK_SILVER_POOL: NhPool = NhPool(
    name="silver",
    prefix_base="5000:ee::",
    nh_network="2401:db00:206a:c002",
    nh_host_start=0xB001,
    size=3072,
)


# TH6 / Tomahawk6 / IcePack silicon profile.
#
# Spec sheet (confirmed by Pavan 2026-06-25):
#   ECMP Groups   = 4K   raw
#   ECMP Members  = 128K raw
#   ECMP Width    = 128
#   DLB Groups    = 511  raw
#   DLB unique NHs = 128 (per-chip pool)
#   DLB Width     = 128  (post-T277302860 silicon fix; current chip caps at 64)
#
# Usable derivations via int(N * 0.75 - 2):
#   dlb_max_groups_usable    = 381
#   ecmp_max_groups_usable   = 3070
#   ecmp_max_members_usable  = 98302
#
# Empirical confirmation 2026-06-25 on gtsw001.l1001.c085.ash6 via
# dlb_resource_stickiness_runner: 511 prefixes × 64 NH multipath →
# 381 Default (DLB) + 130 PER_PACKET_RANDOM, ECMP Width = 64.
ICEPACK_TH6_PROFILE: DlbEcmpAsicProfile = DlbEcmpAsicProfile(
    name="icepack_th6",
    dlb_max_groups_raw=511,
    dlb_max_unique_nhs=128,
    # T277302860 silicon fix LANDED + confirmed 2026-06-26 on
    # gtsw001.l1001.c085.ash6 via dlb_resource_stickiness_runner —
    # ECMP Width = 120 on a 511×120 advertisement. Silicon now supports
    # the full 128-wide ARS group.
    dlb_max_width=128,
    dlb_max_members_raw=4096,  # 4K DLB member entries (Pavan spec)
    ecmp_max_groups_raw=4096,
    ecmp_max_members_raw=131072,  # 128K total ECMP member entries
    ecmp_max_width=128,
)

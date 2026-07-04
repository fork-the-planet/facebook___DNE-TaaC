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
    ecmp_max_members_raw: int
    """Effective ECMP member-table budget for test advertisements.

    NOT the raw ASIC hardware cap. Per Midhun (T278221890 2026-07-02),
    fboss_sw_agent's ``ResourceAccountant`` runs two checks against each
    syncFib update batch:

      1. **Per-route order check** at 100% of the ASIC cap. For each
         route in the order it appears in the batch, verify it fits into
         100% of remaining capacity (128,000 on TH6).
      2. **Final-state usage check** at 75% of the ASIC cap. After
         processing the whole batch, verify total occupancy is under
         75% of the ASIC cap (128,000 × 0.75 = 96,000 on TH6).

    The 25% headroom exists because syncFib processes ADDS BEFORE
    DELETES; if a batch says "add 30, delete 20", the transient peak is
    current + 30 before the delete lands. Reserving 25% protects
    against that transient overshoot; without it, an add-before-delete
    batch that has a valid steady final state can still fail during
    intermediate processing.

    Practical consequence: test advertisements must be sized against
    the 75% cap (96K on TH6), not the 100% cap (128K), and must include
    Gold DLB baseline + system routes. e.g. Silver budget = 96,000 −
    Gold(~4K) = 92,000 → ``_w_for(92000, 2689, 128)`` = 34 → Silver
    advertisement 2689 × 34 = 91,426 members → total demand ~95,426.

    Set to the SILVER-ONLY budget (raw 92,000 on TH6) rather than the
    ASIC cap so that ``_w_for`` derivations that use this value directly
    are conservative-safe.
    """
    ecmp_max_width: int  # per-group max NHs (silicon cap, non-DLB)

    @property
    def dlb_max_groups_usable(self) -> int:
        return usable_from_raw(self.dlb_max_groups_raw)

    @property
    def ecmp_max_groups_usable(self) -> int:
        return usable_from_raw(self.ecmp_max_groups_raw)

    @property
    def ecmp_max_members_usable(self) -> int:
        """Legacy usable-members property; see ``ecmp_max_members_raw`` docstring.

        Historically applied the N*0.75-2 formula (empirical for GROUPS) here
        for member-entry tables too. That was pre-Midhun-clarification —
        we now know the ASIC ResourceAccountant already enforces a 75%
        headroom (see ``ecmp_max_members_raw`` docstring for details), so
        ``ecmp_max_members_raw`` is already sized to the effective budget.
        Applying N*0.75-2 on top of that would double-discount.

        Kept here for backwards compatibility with any caller that references
        the property; new callers should use ``ecmp_max_members_raw`` directly.
        """
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


# l1002 pod DUTs use `d002::` for their rogue-port /64 (vs `c002::` on l1001).
# Same silicon pool sizes and DLB-window classification (::a001..a080 in
# unique-NH table = Gold ARS-eligible; ::b001+ = plain ECMP for Silver).
# Distinct `.name` so CSVs render to a separate on-disk directory and both
# DUT families can coexist without clobbering each other's fixtures.
ICEPACK_L1002_GOLD_POOL: NhPool = NhPool(
    name="gold_l1002",
    prefix_base="5000:dd::",
    nh_network="2401:db00:206a:d002",
    nh_host_start=0xA001,
    size=128,
)

ICEPACK_L1002_SILVER_POOL: NhPool = NhPool(
    name="silver_l1002",
    prefix_base="5000:ee::",
    nh_network="2401:db00:206a:d002",
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
    # Effective ECMP member budget = **75% of the 128K ASIC hardware cap =
    # 96,000**. Per Midhun (T278221890 2026-07-02): fboss_sw_agent's
    # `ResourceAccountant` runs two checks:
    #   (1) Per-route order: 100% cap = 128,000.
    #   (2) Final-state usage: 75% cap = 96,000. This 25% headroom exists
    #       because syncFib processes adds-before-deletes → transient peak
    #       = current + adds before the deletes land. 75% protects against
    #       that transient overshoot.
    # We must size Silver so total demand (Silver + Gold + baseline) fits
    # under the 75% cap (96,000), not the 100% cap.
    #
    # Gold DLB + baseline observed on-device (2026-07-02): ~4,000 members
    # (381 DLB × ~10 + ~200 baseline routes). Silver budget = 96,000 −
    # 4,000 = 92,000. `_w_for(92000, 2689, 128) = min(128, 34.2) = 34` →
    # Silver 2689 × 34 = 91,426 + Gold 4,000 ≈ 95,426 → ~574 slack.
    ecmp_max_members_raw=92000,
    ecmp_max_width=128,
)

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe

"""Per-test CSV parameter derivation for the 23 DLB/ECMP hardening test
cases (TC#210–TC#232 in Pavan's catalog).

Decouples the test catalog from any specific silicon: each test_id maps
to a function of ``(profile, gold_pool, silver_pool)`` returning the
per-pool generator params ``(groups, width)``. Swapping the ASIC =
swapping :data:`ICEPACK_TH6_PROFILE` for another :class:`DlbEcmpAsicProfile`
constant — all 23 test scales recompute automatically.

Test catalog references (Pavan spreadsheet TC# / inherited DLB_NNN ID):
    case_01_baseline                — TC#210
    case_02_dlb_fill_50pct          — TC#211, DLB_005
    case_03_dlb_member_overcommit   — TC#212
    case_04_dlb_spillover_plus_one  — TC#213, DLB_017
    case_05_ecmp_full_50pct_mixed   — TC#214, DLB_001
    case_06_dlb_member_100pct       — TC#215
    case_07_dlb_coldboot            — TC#216
    case_08_ecmp_members_100pct     — TC#217
    case_09_ecmp_coldboot           — TC#218
    case_10_ecmp_group_overcommit   — TC#219
    case_11_ecmp_member_overcommit  — TC#220
    case_12_dlb_width_max           — TC#221
    case_13_ecmp_width_max          — TC#222, DLB_009
    case_14_ecmp_width_tipover      — TC#223, DLB_013
    case_15_rollback_ecmp_to_dlb    — TC#224
    case_16_background_warmboot     — TC#225 (longevity)
    case_17_background_bgp_gr       — TC#226 (longevity)
    case_18_dlb_ecmp_flap_longevity — TC#227 (longevity)
    case_19_switch_dlb_ecmp         — TC#228 (longevity)
    case_20_flap_warmboot_longevity — TC#229 (longevity)
    case_21_ndp_flap                — TC#230
    case_22_ar_bit_negative         — TC#231
    case_23_cold_start_cycle        — TC#232
"""

import dataclasses
import os
from typing import Dict, Tuple

from taac.testconfigs.npi.dlb_asic_profiles import (
    DlbEcmpAsicProfile,
    NhPool,
)
from taac.testconfigs.npi.dlb_csvs import gen_dlb_csv


# Mapping: test_id → {NhPool: (groups, width)}.
# Empty dict means the test reuses another case's CSV shape and only
# adds playbook-level orchestration (background tasks, traffic mode
# toggles, NDP flap). See `BACKGROUND_TASK_REUSES_SHAPE` for which
# baseline shape each background-orchestration test reuses.
TestPoolParams = Dict[NhPool, Tuple[int, int]]


BACKGROUND_TASK_REUSES_SHAPE: Dict[str, str] = {
    # Cases 16/17 run prior cases inside a long disruption wrapper —
    # the CSV is whatever the wrapped cases emit. We default to
    # case_02's shape as the baseline; the playbook orchestrates the
    # actual case sequence and may re-mutate per inner case.
    "case_16_background_warmboot": "case_02_dlb_fill_50pct",
    "case_17_background_bgp_gr": "case_02_dlb_fill_50pct",
}


def derive_test_params(
    profile: DlbEcmpAsicProfile,
    gold_pool: NhPool,
    silver_pool: NhPool,
) -> Dict[str, TestPoolParams]:
    """Return ``{test_id: {pool: (groups, width)}}`` for all 23 cases.

    Per-test math is purely a function of the profile + which pool the
    case targets. Percentages from the Pavan spec (50% member
    occupancy, 100% groups, etc.) are applied to the profile's
    silicon-derived caps. Width overcommit cases pass widths that
    exceed the silicon cap on purpose — IxNetwork will accept the
    advertisement but the DUT is expected to either truncate or
    reject; both are validated by the post-check HC.
    """
    # Usable group counts (int(N * 0.75 - 2) — ECMP-formula budget for groups).
    g_dlb = profile.dlb_max_groups_usable  # 381 on TH6
    g_ecmp = profile.ecmp_max_groups_usable  # 3070 on TH6
    # Non-DLB ECMP group budget = total ECMP usable minus DLB usable.
    g_silver = g_ecmp - g_dlb  # 2689 on TH6

    # Per-group max widths (silicon hard caps).
    w_dlb_cap = profile.dlb_max_width  # 128 on TH6 (post-T277302860 fix)
    w_ecmp_cap = profile.ecmp_max_width  # 128 on TH6

    # Member-entry budgets (raw silicon caps for the per-group-sum).
    # IMPORTANT — these are MEMBER ENTRIES (sum of widths across all
    # groups of that class), NOT per-group width. Per-test scale points
    # like "100% member util" or "50% member occupancy" derive WIDTH
    # from these budgets divided by GROUP COUNT.
    m_dlb = profile.dlb_max_members  # 4K on TH6 (per Pavan spec sheet)
    m_ecmp = profile.ecmp_max_members_raw  # 128K on TH6

    # Derived widths for "100% groups × X% member" scale points.
    # Clamped to >=1 (some ratios round to 0 on small DUTs).
    def _w_for(target_members: int, group_count: int, cap: int) -> int:
        return max(1, min(cap, target_members // max(1, group_count)))

    # DLB widths at common scale points (with full g_dlb=381 groups):
    w_dlb_50pct_mem = _w_for(m_dlb // 2, g_dlb, w_dlb_cap)  # ~5 (2K/381)
    w_dlb_100pct_mem = _w_for(m_dlb, g_dlb, w_dlb_cap)  # ~10 (4K/381)

    # Non-DLB ECMP widths at common scale points (with full g_silver=2689 groups):
    w_ecmp_50pct_mem = _w_for(m_ecmp // 2, g_silver, w_ecmp_cap)  # ~24 (64K/2689)
    w_ecmp_100pct_mem = _w_for(m_ecmp, g_silver, w_ecmp_cap)  # ~48 (128K/2689)

    return {
        # TC#210 — baseline signal sanity (small stable shape).
        "case_01_baseline": {gold_pool: (g_dlb, w_dlb_50pct_mem)},
        # TC#211 / DLB_005 — 100% DLB groups, 50% member occupancy.
        # 381 × ~5 width = ~2K DLB members (= 50% of 4K cap).
        "case_02_dlb_fill_50pct": {gold_pool: (g_dlb, w_dlb_50pct_mem)},
        # TC#212 — overcommit DLB member threshold.
        # 25% past 4K cap = 5120 target members; 381 × 14 width ≈ 5334.
        "case_03_dlb_member_overcommit": {
            gold_pool: (g_dlb, _w_for(int(m_dlb * 1.25), g_dlb, w_dlb_cap)),
        },
        # TC#213 / DLB_017 — group spillover at cap + 1.
        # NOTE: this case targets the GROUP cap (381 → 382), not the
        # member cap. Width is **deliberately minimal (2)** so 382 × 2 =
        # 764 members fits comfortably under the 4K DLB member cap and
        # the test isolates the GROUP-cap behaviour. Width=128 (silicon
        # cap) confounds the test because 382 × 128 = 48896 members ≈
        # 12× the DLB member cap, which is also impossible — empirically
        # only 1 group installed in Run 1 + Run 2 (2026-06-29 pilots).
        # Width=1 would degrade groups to single-NH (excluded from the
        # ECMP matrix), so 2 is the minimum "real" multipath width.
        "case_04_dlb_spillover_plus_one": {gold_pool: (g_dlb + 1, 2)},
        # TC#214 / DLB_001 — 100% ECMP groups (DLB + non-DLB), 50% member util.
        # Gold: 381 × ~5 = ~2K (50% DLB members)
        # Silver: 2689 × ~24 = ~64K (50% ECMP members)
        "case_05_ecmp_full_50pct_mixed": {
            gold_pool: (g_dlb, w_dlb_50pct_mem),
            dataclasses.replace(silver_pool, size=128): (g_silver, w_ecmp_50pct_mem),
        },
        # TC#215 — 100% DLB member utilization.
        # 381 × ~10 = ~4K DLB members (= 100% of 4K cap).
        "case_06_dlb_member_100pct": {gold_pool: (g_dlb, w_dlb_100pct_mem)},
        # TC#216 — coldboot at 100% DLB (same shape as case_06; playbook layers coldboot).
        "case_07_dlb_coldboot": {gold_pool: (g_dlb, w_dlb_100pct_mem)},
        # TC#217 — 100% non-DLB ECMP member utilization.
        # 2689 × ~48 = ~129K members ≈ 100% of 128K ECMP member cap.
        "case_08_ecmp_members_100pct": {
            dataclasses.replace(silver_pool, size=128): (
                g_silver,
                w_ecmp_100pct_mem,
            ),
        },
        # TC#218 — coldboot at 100% non-DLB ECMP. Silver pool constrained to
        # 128 NHs to match the silicon Virtual ARS Supergroup unique-member
        # limit (empirically observed via Midhun 2026-07-01 log evidence in
        # T278073224: `ResourceAccountant.cpp:252 Virtual ARS supergroup
        # unique member limit would be exceeded. Projected: 129 limit: 128`).
        # T278029631 documents silicon collapsing prefixes with overlapping
        # NH sets into a single virtual supergroup; that supergroup's union
        # of NHs across 2689 CASE_09 prefixes approaches the full pool. If
        # pool=130 → union=129-130 → over the 128 supergroup cap → syncFib
        # batch atomically rejected. Pool=128 keeps every RNG-picked 48-of-
        # 128 subset inside the silicon-supported supergroup boundary.
        "case_09_ecmp_coldboot": {
            dataclasses.replace(silver_pool, size=128): (
                g_silver,
                w_ecmp_100pct_mem,
            ),
        },
        # TC#219 — overcommit ECMP groups beyond cap (graceful reject expected).
        # 10% past g_ecmp usable (3070 → 3377). Width MINIMUM-VIABLE = 2
        # (min for real multi-NH group). GROUP dimension IS the overcommit;
        # widening past 2 only inflates advertisement time without adding
        # signal — 3377 × 2 = 6754 vs 3377 × 24 = 81048 (12× advertisement
        # cost). Spec preserved: still exercises 10% group overcommit.
        "case_10_ecmp_group_overcommit": {
            dataclasses.replace(silver_pool, size=128): (int(g_ecmp * 1.10), 2),
        },
        # TC#220 — overcommit ECMP MEMBER cap beyond 128K (graceful reject expected).
        # 25% past 128K cap = 160K target; 2689 × ~60 width ≈ 161K members.
        "case_11_ecmp_member_overcommit": {
            dataclasses.replace(silver_pool, size=128): (
                g_silver,
                _w_for(int(m_ecmp * 1.25), g_silver, w_ecmp_cap * 2),
            ),
        },
        # TC#221 — DLB max-width validation. Spec asks for 10 groups × 128
        # wide, but that requires 10 × 128 = 1280 unique NHs while silicon's
        # DLB unique-NH table is capped at 128 per chip on TH6. Test PARKED
        # as (1, 128): a single DLB group programmed at silicon's per-group
        # width cap (128 post-T277302860 fix). Physically-realizable
        # equivalent that still exercises the width-cap boundary.
        # Phabricator T278029631 tracks the spec ambiguity.
        "case_12_dlb_width_max": {gold_pool: (1, w_dlb_cap)},
        # TC#222 / DLB_009 — max ECMP width. Silicon supergroup unique-NH
        # cap = 128, so a single group at width=128 (using every NH in the
        # 128-NH pool) is the truest realization of "max ECMP width".
        # Proves silicon accepts an ECMP group at ecmp_max_width without
        # colliding with the supergroup cap.
        "case_13_ecmp_width_max": {
            dataclasses.replace(silver_pool, size=128): (1, w_ecmp_cap),
        },
        # TC#223 / DLB_013 — width tip-over: spec says silicon must
        # "gracefully reject more than 64 members per non-DLB ECMP group"
        # (TH6 silicon cap is actually 128 unique NHs per supergroup).
        # Advertise a single group of width 130 (pool sized to match) →
        # silicon supergroup unique-NH check fires (130 > 128) → syncFib
        # rejects the batch cleanly. HC asserts 0 groups installed +
        # agent stability post-reject.
        "case_14_ecmp_width_tipover": {
            dataclasses.replace(silver_pool, size=130): (1, 130),
        },
        # TC#224 — rollback ECMP→DLB. Playbook starts mixed, then
        # SilverPoolToggleStep disables Silver. Loss-during-transition
        # post-check verifies traffic continuity. Spec = "rollback
        # mechanism works" — needs Silver PRESENT to toggle, not at scale.
        # MINIMUM-VIABLE: 128 × 2 = 256 Silver advertisements is enough to
        # prove rollback removes them cleanly. Gold stays at 100% to keep
        # the DLB side realistic post-rollback.
        "case_15_rollback_ecmp_to_dlb": {
            gold_pool: (g_dlb, w_dlb_100pct_mem),
            dataclasses.replace(silver_pool, size=128): (128, 2),
        },
        # TC#225/226 — background-disruption wrappers, no own CSV
        # (playbook orchestrates re-mutate per inner case during the
        # warmboot/GR loop). Baseline at case_02 shape.
        "case_16_background_warmboot": {},
        "case_17_background_bgp_gr": {},
        # TC#227 — DLB+ECMP flap longevity at 100% util on both sides.
        "case_18_dlb_ecmp_flap_longevity": {
            gold_pool: (g_dlb, w_dlb_100pct_mem),
            dataclasses.replace(silver_pool, size=128): (g_silver, w_ecmp_100pct_mem),
        },
        # TC#228 — continuous DLB-only ↔ DLB+ECMP switching at 100% util.
        "case_19_switch_dlb_ecmp": {
            gold_pool: (g_dlb, w_dlb_100pct_mem),
            dataclasses.replace(silver_pool, size=128): (g_silver, w_ecmp_100pct_mem),
        },
        # TC#229 — flap + continuous warmboot at 100% util on both sides.
        "case_20_flap_warmboot_longevity": {
            gold_pool: (g_dlb, w_dlb_100pct_mem),
            dataclasses.replace(silver_pool, size=128): (g_silver, w_ecmp_100pct_mem),
        },
        # TC#230 — NDP entry flap (50%-util baseline; playbook flaps NDP DG).
        "case_21_ndp_flap": {gold_pool: (g_dlb, w_dlb_50pct_mem)},
        # TC#231 — negative: AR bit=0 traffic, expect static hash only.
        # Shape unchanged — test is about HASH staticness, not group shape.
        "case_22_ar_bit_negative": {gold_pool: (g_dlb, w_dlb_50pct_mem)},
        # TC#232 — cold-start cycle: StopAllProtocols → 2min → StartAllProtocols.
        # Full-util to maximize re-program stress.
        "case_23_cold_start_cycle": {gold_pool: (g_dlb, w_dlb_100pct_mem)},
    }


# Test ids that need playbook-level orchestration on top of (or instead
# of) a CSV mutation. Hardening testconfig lists the first three sets;
# longevity testconfig lists the last set.
TESTS_HARDENING: list = [
    "case_01_baseline",
    "case_02_dlb_fill_50pct",
    "case_03_dlb_member_overcommit",
    "case_04_dlb_spillover_plus_one",
    "case_05_ecmp_full_50pct_mixed",
    "case_06_dlb_member_100pct",
    "case_07_dlb_coldboot",
    "case_08_ecmp_members_100pct",
    "case_09_ecmp_coldboot",
    "case_10_ecmp_group_overcommit",
    "case_11_ecmp_member_overcommit",
    "case_12_dlb_width_max",
    "case_13_ecmp_width_max",
    "case_14_ecmp_width_tipover",
    "case_15_rollback_ecmp_to_dlb",
    "case_21_ndp_flap",
    "case_22_ar_bit_negative",
    "case_23_cold_start_cycle",
]

TESTS_LONGEVITY: list = [
    "case_16_background_warmboot",
    "case_17_background_bgp_gr",
    "case_18_dlb_ecmp_flap_longevity",
    "case_19_switch_dlb_ecmp",
    "case_20_flap_warmboot_longevity",
]


def generate_all_csvs(
    profile: DlbEcmpAsicProfile,
    gold_pool: NhPool,
    silver_pool: NhPool,
    out_dir: str = "/tmp/dlb_csvs",
) -> Dict[str, Dict[NhPool, str]]:
    """Generate the per-test-per-pool CSV files for every case in
    :func:`derive_test_params`.

    Layout: ``<out_dir>/<profile.name>/<pool.name>/<test_id>.csv``.
    Idempotent: same profile/pools/params yield byte-identical files,
    safe to re-run on every testconfig load.

    Returns a nested dict ``{test_id: {pool: csv_path}}`` so the
    factory can wire the right path into each playbook's
    :class:`ImportCsvStep` setup task.
    """
    params = derive_test_params(profile, gold_pool, silver_pool)
    paths: Dict[str, Dict[NhPool, str]] = {}
    for test_id, pool_params in params.items():
        paths[test_id] = {}
        for pool, (groups, width) in pool_params.items():
            csv_path = os.path.join(out_dir, profile.name, pool.name, f"{test_id}.csv")
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            rows = gen_dlb_csv.gen_fill_for_pool(pool, groups, width)
            gen_dlb_csv.write_csv(csv_path, rows)
            paths[test_id][pool] = csv_path
    return paths

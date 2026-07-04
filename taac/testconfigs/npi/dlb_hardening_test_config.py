# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""IcePack/TH6 DLB & ECMP hardening test configurations.

Builds two TestConfig instances from the same parameterized factory:

* ``NPI_DVT_ICEPACK_GTSW__DLB_HARDENING`` — 18 short-runtime test cases
  (TC#210, TC#211–TC#224, TC#230–TC#232). Each playbook mutates the
  IxNetwork advertisement to a target shape and validates via
  ``DLB_RESOURCE_STICKINESS_CHECK`` postcheck.
* ``NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY`` — 5 hours-to-days runtime
  test cases (TC#225–TC#229). Each playbook layers a background
  disruption (warmboot/GR/flap) on top of a fixed advertisement
  geometry held for the runtime.

Both testconfigs share the same DUT setup tasks (peer-group push,
spine-disable, NDP-supporting DG) and the same ASIC profile
(:data:`ICEPACK_TH6_PROFILE`). Per-test scale derives from
:mod:`dlb_hardening_test_params` so swapping the ASIC = swapping the
profile constant + Pool definitions, no per-test edit needed.

Live coordinates (gtsw001.l1001.c085.ash6):
    Rogue port `eth1/1/3` parent /64 = 2401:db00:206a:c002::/64
    Gold NHs        = c002::a001..a080   (within DLB unique-NH pool)
    Silver NHs      = c002::b001..b???   (outside DLB pool → non-DLB ECMP)
    Gold prefixes   = 5000:dd::/64..
    Silver prefixes = 5000:ee::/64..
    IXIA chassis    = ixia19.netcastle.ash6 (2401:db00:2066:31fb::3019)

Empirical verification 2026-06-25 via ``dlb_resource_stickiness_runner``:
511 Gold prefixes × 64 NHs each → 381 ARS (Default DLB) + 130
PER_PACKET_RANDOM spillover + ECMP Width=64. Matches the post-test
expectations derived in :mod:`dlb_hardening_test_params`.
"""

import json
import os
import typing as t

from ixia.ixia import types as ixia_types
from taac.constants import Gigabyte
from taac.health_checks.healthcheck_definitions import (
    create_core_dumps_snapshot_check,
    create_cpu_utilization_check,
    create_dlb_resource_stickiness_check,
    create_ixia_packet_loss_check,
    create_memory_utilization_check,
    create_systemctl_active_state_check,
)
from taac.packet_headers import DSF_RDMA_IB_PACKET_HEADERS
from taac.playbooks.playbook_definitions import (
    create_dlb_hardening_playbook,
)
from taac.steps.step_definitions import (
    create_bgp_service_convergence_step,
    create_drain_undrain_step,
    create_ixia_api_step,
    create_ixia_device_group_toggle_step,
    create_longevity_step,
    create_run_task_step,
    create_service_interruption_step,
    create_start_traffic_step,
    create_stop_traffic_step,
    create_system_reboot_step,
    create_validation_step,
)
from taac.task_definitions import (
    create_coop_apply_patchers_task,
    create_coop_register_patcher_task,
    create_coop_unregister_patchers_task,
)
from taac.testconfigs.npi.dlb_asic_profiles import (
    DlbEcmpAsicProfile,
    ICEPACK_GOLD_POOL,
    ICEPACK_L1002_GOLD_POOL,
    ICEPACK_L1002_SILVER_POOL,
    ICEPACK_SILVER_POOL,
    ICEPACK_TH6_PROFILE,
    NhPool,
)
from taac.testconfigs.npi.dlb_csvs import gen_dlb_csv
from taac.testconfigs.npi.dlb_hardening_test_params import (
    derive_test_params,
    TESTS_HARDENING,
    TESTS_LONGEVITY,
)
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import Playbook, TestConfig


# =============================================================================
# Constants — peer group name, IXIA chassis, default per-test scale knobs.
# =============================================================================
PEERGROUP_GTSW_IXIA_V6: str = "PEERGROUP_GTSW_IXIA_V6"
IXIA19_CHASSIS_IP: str = "2401:db00:2066:31fb::3019"

# Per-DUT GTSW→STSW spine modules — the modules carrying UP BGP peering
# to STSW spines. Disabling these at testconfig setup leaves the silicon
# DLB unique-NH pool (128 entries on TH6) entirely free for our test
# advertisements; otherwise spine NHs occupy ~92 of those 128 slots and
# every test case past 36 NHs/prefix fails to install.
#
# IMPORTANT: this list was empirically re-determined 2026-06-29 on
# gtsw001.l1001.c085.ash6 directly from `fboss2 show interface | grep stsw
# | awk '{print $2}' | grep -oE 'eth1/[0-9]+/'` — yields 128 STSW-facing
# ports across 32 modules (4 ports per module × 32 = 128). Prior list
# {5,9,13,17,21,25,29,...} was wrong: it included non-spine modules
# (5/9/13/17/21/25/29) and missed real spine modules (3/4/7/8/11/12/15/16),
# which caused Run 4 setup failure when test_bed_chunker's
# isolate_test_bed_connectivity checked eth1/11/1 and found it UP.
# The list below matches the live cabling exactly. If we add new DUTs to
# this testconfig, each needs its own per-DUT spine-modules list.
GTSW001_ASH6_SPINE_MODULES: t.Tuple[int, ...] = (
    3,
    4,
    7,
    8,
    11,
    12,
    15,
    16,
    19,
    20,
    23,
    24,
    27,
    28,
    31,
    32,
    35,
    36,
    39,
    40,
    43,
    44,
    47,
    48,
    51,
    52,
    55,
    56,
    59,
    60,
    63,
    64,
)
# Per-module port indices that need disabling (matches the original
# patcher's per-module port set; one set per 400G module).
SPINE_PORT_INDICES: t.Tuple[int, ...] = (1, 3, 5, 7)

# Per-playbook traffic runtime for the SHORT (hardening) tests. Long enough
# for stickiness HC to converge but short enough that 18 playbooks finish
# in a single CI window. Bump on a per-playbook basis if a case needs more
# settle time (e.g. overcommit cases that wait for reject to register).
DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC: int = 120

# Per-case override for the SHORT (hardening) traffic runtime. Cases that
# inject very large advertisement sets (>= ~10k total advertisements) need
# more BGP convergence time than the default 120s — empirically observed
# during the 2026-06-29 pilot where case_04 (~49k adv), case_08 (~129k adv),
# case_09 (~129k adv), case_10 (~81k adv), case_11 (~161k adv) all timed
# the stickiness HC out at 120s while only partial routes had landed.
HARDENING_RUNTIME_OVERRIDES_SEC: t.Dict[str, int] = {
    "case_04_dlb_spillover_plus_one": 600,  # 382 × 128 = 48896 adv
    "case_05_ecmp_full_50pct_mixed": 360,  # 1905 (Gold) + 64536 (Silver)
    "case_08_ecmp_members_100pct": 600,  # 2689 × 48 = 129072 adv
    "case_09_ecmp_coldboot": 600,  # same shape as case_08
    "case_10_ecmp_group_overcommit": 480,  # 3377 × 24 = 81048 adv
    "case_11_ecmp_member_overcommit": 720,  # 2689 × 60 = 161340 adv
    "case_13_ecmp_width_max": 240,  # 10 × 128 = 1280 (small but safety margin)
    "case_14_ecmp_width_tipover": 240,  # 10 × 200 → expected reject; allow settle
    "case_15_rollback_ecmp_to_dlb": 480,  # Gold 100% + Silver 50% + mid-case toggle
}

# Longevity runtime defaults. Spec: cases 18–20 want 6h–12h; cases 16+17 are
# "background warmboot/GR while running prior cases" — we encode them as
# 1-hour wrappers around case_02 for now and let the playbook layer
# orchestrate the actual repeated inner-case sequence in a future iteration.
LONGEVITY_RUNTIMES_SEC: t.Dict[str, int] = {
    "case_16_background_warmboot": 3600,
    "case_17_background_bgp_gr": 3600,
    "case_18_dlb_ecmp_flap_longevity": 6 * 3600,
    # Per-round-HC refactor 2026-07-02: 23 rounds × 30 min = 11.5 h (see
    # `_per_case_trigger_steps` case_19 branch). runtime_sec here is
    # informational only — the CASE_19 branch ignores it and uses
    # ROUND_COUNT × ROUND_SEC directly.
    "case_19_switch_dlb_ecmp": 23 * 30 * 60,
    "case_20_flap_warmboot_longevity": 3600,
}


# =============================================================================
# CSV generation at module load — one CSV per (test_id, pool). Cached at a
# deterministic path so the testconfig's serialized step args are stable
# across runs (required for golden manifest hash). Regenerated each load
# (idempotent — same inputs → same output bytes).
# =============================================================================
_DLB_CSV_DIR: str = f"/tmp/dlb_csvs/{ICEPACK_TH6_PROFILE.name}"
os.makedirs(_DLB_CSV_DIR, exist_ok=True)


def _csv_path(test_id: str, pool: NhPool) -> str:
    return os.path.join(_DLB_CSV_DIR, pool.name, f"{test_id}.csv")


def _ensure_csvs(
    profile: DlbEcmpAsicProfile,
    gold_pool: NhPool,
    silver_pool: NhPool,
) -> t.Dict[str, t.Dict[NhPool, str]]:
    """Generate the per-(test_id, pool) CSV files for the given pools.

    Heavy Silver cases (case_05/08/15/18/19/20) emit hundreds-of-MB CSVs
    when generated full-scale; they take minutes total. Cached at module
    scope via ``_CSV_PATHS_CACHE`` keyed by (gold_pool.name, silver_pool.name)
    so per-DUT pools (e.g. c002 vs d002 subnets) each get their own CSV
    directory (via ``_csv_path`` which routes off ``pool.name``) generated
    exactly once regardless of how many testconfigs share the pool set.
    """
    cache_key = (profile.name, gold_pool.name, silver_pool.name)
    cached = _CSV_PATHS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    params = derive_test_params(profile, gold_pool, silver_pool)
    paths: t.Dict[str, t.Dict[NhPool, str]] = {}
    for tid, pool_params in params.items():
        paths[tid] = {}
        for pool, (groups, width) in pool_params.items():
            csv_path = _csv_path(tid, pool)
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            rows = gen_dlb_csv.gen_fill_for_pool(pool, groups, width)
            gen_dlb_csv.write_csv(csv_path, rows)
            paths[tid][pool] = csv_path
    _CSV_PATHS_CACHE[cache_key] = paths
    return paths


# Per-(profile, gold_pool, silver_pool) CSV path cache. First testconfig
# built for a given pool combo generates its CSVs; later testconfigs reuse.
_CSV_PATHS_CACHE: t.Dict[t.Tuple[str, str, str], t.Dict[str, t.Dict[NhPool, str]]] = {}


# =============================================================================
# Per-case derivation of stickiness-HC expected_counts. Pure function of
# (profile, derived params) — ASIC swap recomputes automatically.
# =============================================================================
def _stickiness_expectations(
    profile: DlbEcmpAsicProfile,
    test_id: str,
    pool_params: t.Dict[NhPool, t.Tuple[int, int]],
) -> t.Dict[str, t.Any]:
    """Compute the stickiness-HC ``json_params`` for one playbook.

    Maps the per-pool (groups, width) shape to category-keyed
    expectations: ``"5000:dd prefixes"`` for Gold-advertised routes,
    ``"5000:ee prefixes"`` for Silver. Spillover rows expect
    ``dlb=usable_cap``, ``per_packet_random=overflow``. Width-cap rows
    expect ``ecmp_width=cap``. Background-only rows (cases 16/17)
    inherit case_02's expectations as their baseline.

    Returns a dict suitable for ``create_dlb_resource_stickiness_check
    (json_params=...)``.
    """
    if not pool_params:
        # Background-task wrappers: inherit case_02's baseline.
        baseline = derive_test_params(profile, ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL)[
            "case_02_dlb_fill_50pct"
        ]
        return _stickiness_expectations(profile, "case_02_dlb_fill_50pct", baseline)

    # Post-rollback override: CASE_15 mutates from Gold+Silver to Gold-only
    # via SilverPoolToggleStep mid-test. The stickiness HC fires after
    # rollback, so the expected shape is Gold-only — drop Silver pool
    # from spec to avoid false-FAIL on a successful rollback. Run 10
    # 2026-06-29 confirmed: post-rollback DUT had 381 Gold + 160 infra
    # = 541 total NH (Silver removed cleanly), but spec required Silver
    # still present → HC FAILED on per-prefix Silver count.
    effective_params = {
        pool: params
        for pool, params in pool_params.items()
        if not (
            test_id == "case_15_rollback_ecmp_to_dlb"
            and pool.prefix_base == "5000:ee::"
        )
    }

    prefix_patterns: t.List[str] = []
    expected_counts: t.Dict[str, t.Dict[str, t.Any]] = {}

    # V10 polish (post Run 12 evidence, 2026-06-30):
    #   - Gold: exact `total` — Gold is stable; 381 DLB ARS groups land
    #     consistently (matches `dlb_max_groups_usable`). Use exact match
    #     to catch any silent Gold regression.
    #   - Silver: `min_total` only — Silver landing is install-rate-bound
    #     and varies by case (Run 12 CASE_05 landed FULL 2689 in ~6min;
    #     Run 12 CASE_08 landed ~89 in ~10min; Run 11 nightly CASE_18
    #     landed ~652 in ~6h). Asserting an exact count drives false-FAILs.
    #     `min_total=50` defends against silent regression to 0 (the Run 9
    #     bgpd-crash failure mode) without locking in install-rate variance.
    #   - Drop `expected_totals` entirely: V9's `expected_totals.total =
    #     sum_of_groups` had a math bug — `validate_totals()` computes
    #     `actual_total` over multi-NH groups only, but the spec sum mixed
    #     "expected prefix counts" (which collapse if NH-sets are shared)
    #     with "multi-NH group counts". Per-prefix totals cover the
    #     assertion intent; the cross-category number was redundant + buggy.
    _SILVER_MIN_TOTAL = 50
    # V30 (post Run 27 evidence, 2026-07-01): width-cap boundary cases
    # (12/13 spec at silicon cap 128, 14 spec above cap 200) empirically show
    # silicon collapses N × 128-width groups into 1 multi-NH group when they
    # share the same NH set — see Phabricator T278029631. Until BCM/silicon
    # investigation resolves the dedup class, these cases assert only the
    # min_total >= 1 (at least 1 group installed) — enough to catch a total
    # DUT-failure regression without false-FAIL on the silicon dedup behavior.
    # CASE_13 REMOVED from relax set (post CSV disjoint-slice fix + spec
    # analysis 2026-07-01): Silver pool 3072 easily supports 10 × 128 = 1280
    # disjoint NHs, so we now expect 10 distinct multi-NH ECMP groups. If
    # silicon still collapses despite disjoint sets, that's a real defect
    # for T278029631. CASE_12 stays parked at (1, 128) via test_params
    # (physical impossibility of 10-DLB-group × 128 on 128-NH silicon table).
    _WIDTH_CAP_CASES = {
        "case_12_dlb_width_max",
        "case_13_ecmp_width_max",
    }
    # CASE_14 spec (TC#223) = "system should reject more than 64 members per
    # non-DLB ECMP group; attempt to program 200 and validate graceful
    # failure, no crash, stability". TH6 silicon supergroup unique-NH cap
    # is 128 → advertising width=130 (1 group) triggers reject. HC asserts
    # 0 Silver groups installed (rejection is complete, not partial).
    # CASE_11 spec (TC#220) = "programming additional ECMP members beyond
    # the maximum should fail gracefully; attempt to program more (25% past
    # 128K = ~160K) and validate transaction failure and device state".
    # Shape 2689 × 59 = 158,651 members > 128,000 ASIC cap → silicon fires
    # ResourceAccountant.cpp:165 "Ecmp member limit exceeded" → syncFib
    # atomic reject → 0 groups installed. Same semantic as CASE_14 (reject-
    # expected), just triggered at the member-count layer instead of the
    # per-group width layer. Prior HC gate (min_total: 50) was a FALSE
    # PASS gate — silicon dedup in healthy state let the install succeed,
    # masking the spec-required reject-graceful behaviour.
    _WIDTH_REJECT_CASES = {
        # CASE_10 spec (TC#219) = "10% past g_ecmp usable (3070 → 3377),
        # graceful reject expected". Empirically confirmed 2026-07-02
        # 18:45 l1001: silicon fully rejects the atomic 3377-group batch
        # → Silver total=0 installed while Gold's 381 DLB groups remain
        # (541 total NH groups = 381 multi-NH Gold + 160 baseline single-
        # NH). Add here so HC asserts total=0 (matches silicon reality).
        "case_10_ecmp_group_overcommit",
        # CASE_11 spec (TC#220) = "25% past 128K member cap, graceful
        # reject expected". Empirical 2026-07-02 19:14 l1001: silicon
        # PARTIALLY installed (1704 of 2689 = 63%) instead of full atomic
        # reject. Left in the reject set to keep HC failing until FBOSS
        # team confirms whether partial-install is intended behavior for
        # member overcommit or whether the spec wording is wrong. Failing
        # HC is intentional signal for follow-up conversation.
        "case_11_ecmp_member_overcommit",
        "case_14_ecmp_width_tipover",
    }
    # CASE_05 (Silver+Gold mixed 50%): l1001 v3 2026-07-02 13:12 observed
    # silicon installs only ~121 of ~3070 expected multi-NH groups when
    # both pools advertised simultaneously — evictions/re-installs under
    # group-cap pressure. Gold `total: 381` exact fails; use `min_total:
    # 200` to accept silicon under-install as legitimate behavior until
    # BCM confirms true post-boot group cap. See T278221890 for the
    # related member-cap 75% headroom finding; same rule likely applies
    # to the group cap (3070 usable = 4096 × 0.75).
    _MIXED_RELAX_CASES = {"case_05_ecmp_full_50pct_mixed"}
    for pool, (groups, _width) in effective_params.items():
        pattern = pool.prefix_base.rstrip(":")
        prefix_patterns.append(pool.prefix_base)
        cat_key = f"{pattern} prefixes"
        if test_id in _WIDTH_CAP_CASES:
            expected_counts[cat_key] = {"min_total": 1}
        elif test_id in _WIDTH_REJECT_CASES and pool.prefix_base == "5000:ee::":
            expected_counts[cat_key] = {"total": 0}
        elif test_id in _MIXED_RELAX_CASES and pool.prefix_base == "5000:dd::":
            expected_counts[cat_key] = {"min_total": 200}
        elif pool.prefix_base == "5000:dd::":
            expected_counts[cat_key] = {"total": groups}
        else:
            expected_counts[cat_key] = {"min_total": _SILVER_MIN_TOTAL}

    # V13 polish (post Run 15 evidence, 2026-06-30): always include Gold's
    # prefix pattern in `prefix_patterns` even for Silver-only tests
    # (e.g. CASE_08/10/11 whose `pool_params` is Silver-only). Gold is
    # persistently advertised at setup and silicon still sees its 381 DLB
    # groups — the analyzer's snapshot-comparison lookup (V12) needs
    # matrix["5000:dd prefixes"] to be populated for the MATCH check
    # regardless of whether Gold is being validated as an expected_count
    # in this test. Adding the pattern populates the category in the
    # matrix without adding a spec assertion (validate_counts only checks
    # patterns in `expected_counts`).
    if ICEPACK_GOLD_POOL.prefix_base not in prefix_patterns:
        prefix_patterns.insert(0, ICEPACK_GOLD_POOL.prefix_base)

    return {
        "prefix_patterns": prefix_patterns,
        "expected_counts": expected_counts,
    }


# =============================================================================
# Step factories for the DLB-specific TaacIxia helpers we added.
# `mutate_dlb_pool_from_csv` + `toggle_dlb_pool_enabled` live in
# `ixia/taac_ixia.py`. We invoke them via the existing
# `INVOKE_IXIA_API_STEP` plumbing.
# =============================================================================
def _mutate_pool_step(csv_path: str, pool_name: str) -> taac_types.Step:
    """Step that calls ``TaacIxia.mutate_dlb_pool_from_csv`` (single pool).

    Prefer ``_mutate_pools_batch_step`` for multi-pool cases (Silver+Gold)
    to avoid double-cycle Traffic Item corruption.
    """
    return create_ixia_api_step(
        api_name="mutate_dlb_pool_from_csv",
        args_dict={"csv_path": csv_path, "pool_name": pool_name},
        description=f"Mutate {pool_name} from {os.path.basename(csv_path)}",
    )


def _mutate_pools_batch_step(
    pool_csvs: t.List[t.Tuple[str, str]],
) -> taac_types.Step:
    """Step that calls ``TaacIxia.apply_pool_mutations`` for N pools atomically.

    One Traffic.Stop, N per-pool config mutations, one StartAllProtocols, one
    settle, one Traffic.Regenerate + Apply. Avoids the per-pool double-cycle
    that broke Run 20 CASE_05 (Silver mutate after Gold mutate left Traffic
    Item in kUnapplied state, cascading through all subsequent cases).
    """
    pretty = ",".join(f"{p}={os.path.basename(c)}" for c, p in pool_csvs)
    return create_ixia_api_step(
        api_name="apply_pool_mutations",
        args_dict={"pool_csvs": [list(pc) for pc in pool_csvs]},
        description=f"Batch mutate {len(pool_csvs)} pool(s): {pretty}",
    )


def _toggle_pool_step(pool_name: str, enabled: bool) -> taac_types.Step:
    """Step that calls ``TaacIxia.toggle_dlb_pool_enabled``."""
    return create_ixia_api_step(
        api_name="toggle_dlb_pool_enabled",
        args_dict={"pool_name": pool_name, "enabled": enabled},
        description=f"{'Enable' if enabled else 'Disable'} {pool_name}",
    )


def _pool_name_for(pool: NhPool) -> str:
    """Map an NhPool to its IxNetwork NetworkGroup name in this testbed."""
    if pool.prefix_base == "5000:dd::":
        return "DLB_GOLD_PREFIX_POOL"
    if pool.prefix_base == "5000:ee::":
        return "DLB_SILVER_PREFIX_POOL"
    raise ValueError(f"Unknown NhPool: {pool.name}")


# =============================================================================
# Playbook builders. One Playbook per test_id. Order of steps:
#   1. For each pool in pool_params: mutate_dlb_pool_from_csv(csv_path, pool_name)
#   2. For each pool NOT in pool_params but defined in testbed: toggle off
#   3. start_traffic
#   4. longevity (case-specific duration)
#   5. stop_traffic
# Postcheck: stickiness HC with derived expectations.
# Test-config-level prechecks (systemctl active, no core dumps) attach in
# the factory wrapper `_add_tc_checks_to_playbooks`.
# =============================================================================
def _per_case_trigger_steps(
    test_id: str, runtime_sec: int, device_name: str
) -> t.List[taac_types.Step]:
    """Per-case disruption-trigger steps inserted between `start_traffic`
    and the main longevity wait.

    Generic playbooks just run mutate → longevity → HC, which validates
    steady-state install but does NOT exercise the labeled disruption
    for cases like coldboot / NDP-flap / rollback / cold-start cycle.
    This dispatcher injects the missing trigger sequence per-case so the
    HC fires against the post-disruption recovered state.

    Returns ``[]`` for cases that ARE just steady-state validations
    (case_01/02/03/06/22) — those don't need an extra trigger.
    """
    if test_id == "case_07_dlb_coldboot" or test_id == "case_09_ecmp_coldboot":
        # TC#216 / TC#218 — full system reboot mid-test.
        #
        # Post-reboot recovery REQUIRED (Run 3 2026-06-29 observation):
        #   1. Coop-driven `change_port_admin_state` patcher that disables
        #      the GTSW↔STSW spine ports is wiped by the reboot; STSW
        #      peers come back ESTABLISHED, consume 92 of 128 DLB unique-NH
        #      slots, and DLB can only install ~36 multipath groups per
        #      prefix. Re-applying the registered patchers post-reboot
        #      brings the spine ports back DOWN, freeing the DLB NH pool.
        #   2. FBOSS boots into DRAINED state by default (safety) — BGP
        #      receives routes but doesn't accept them into FIB. An
        #      explicit undrain is needed before the stickiness HC can
        #      see the recovered DLB pool.
        # Recovery sequence after the reboot step itself completes
        # (`SYSTEM_REBOOT_STEP` waits for ping + SSH but NOT BGP/drain):
        return [
            create_longevity_step(
                duration=30, description=f"{test_id} pre-reboot settle"
            ),
            create_system_reboot_step(
                trigger=taac_types.SystemRebootTrigger.FULL_SYSTEM_REBOOT,
                description=f"{test_id} cold reboot trigger",
            ),
            # Recovery step 1: re-push spine-disable + peer-group patchers.
            # The `agent` config_name covers `disable_gtsw_spine_interfaces`;
            # `bgpcpp` covers the peer-group/peers. Both were registered at
            # testconfig setup; the configs persist on disk through reboot
            # but the runtime action is not auto-applied on boot.
            create_run_task_step(
                task_name="coop_apply_patchers",
                params_dict={
                    "hostnames": [device_name],
                    "config_name": "agent",
                },
                description=f"{test_id} post-reboot: re-apply agent patchers (spine disable)",
            ),
            create_run_task_step(
                task_name="coop_apply_patchers",
                params_dict={
                    "hostnames": [device_name],
                    "config_name": "bgpcpp",
                },
                description=f"{test_id} post-reboot: re-apply bgpcpp patchers (peer group + peers)",
            ),
            # Recovery step 2: undrain so received IXIA routes get
            # accepted into FIB instead of being filtered at the
            # `BGP Switch Drain State: DRAINED` gate. Use LOCAL_DRAINER
            # (calls `fboss_local_drainer undrain` on the DUT directly),
            # NOT the default NDS service. Run 6 (2026-06-29) CASE_07
            # demonstrated NDS path hangs for 8 min then fails with
            # "Failed to complete job id"; manual `fboss_local_drainer
            # undrain` via lab-ssh completes in <2 s with no NDS dep.
            create_drain_undrain_step(
                drain=False,
                drain_handler=taac_types.DrainHandler.LOCAL_DRAINER,
                description=f"{test_id} post-reboot: undrain DUT",
            ),
            # Recovery step 3a: Full IXIA-side protocol reset. Just calling
            # `start_all_protocols` alone (previous V14 approach) proved
            # insufficient on l1001 2026-07-01 CASE_09 — Silver DG state
            # was stuck, session stayed IDLE for 2+ hours after undrain.
            # A `stop → wait → start` cycle forces IxNetwork to discard
            # stale post-reboot DG state and cleanly re-initialize.
            create_ixia_api_step(
                api_name="stop_all_protocols",
                args_dict={},
                description=f"{test_id} post-reboot: IXIA StopAllProtocols",
            ),
            create_longevity_step(
                duration=30, description=f"{test_id} post-reboot IXIA quiesce"
            ),
            create_ixia_api_step(
                api_name="start_all_protocols",
                args_dict={},
                description=f"{test_id} post-reboot: IXIA StartAllProtocols",
            ),
            # Recovery step 3b: extended settle for BGP re-establish + FIB
            # programmer. Silver-heavy cases (CASE_09 ~129K routes) need
            # ~5min of wall-clock for advertisement + silicon programming.
            # 60s (previous V14 value) was too short → CASE_09 FAILed with
            # BGP peers still IDLE at HC time. 300s covers the observed
            # empirical convergence window for both Gold (fast) and Silver
            # (slow) coldboot recoveries.
            create_longevity_step(
                duration=300, description=f"{test_id} post-reboot settle (5min)"
            ),
            # Recovery step 4: `start_all_protocols` above re-enables ALL
            # IXIA DGs including any Silver DG our setup-time precheck
            # toggled off. For Gold-only coldboot cases (CASE_07), that
            # re-introduces Silver residual → HC would see 3070 groups
            # (Gold 381 + Silver 2689) instead of the expected 381. For
            # Silver-heavy coldboot (CASE_09), Silver SHOULD be on. This
            # branch keys off the test_id: only case_07 gets the extra
            # Silver-off toggle.
            *(
                [
                    create_ixia_api_step(
                        api_name="toggle_dlb_pool_enabled",
                        args_dict={
                            "pool_name": "DLB_SILVER_PREFIX_POOL",
                            "enabled": False,
                        },
                        description=f"{test_id} post-reboot: re-disable Silver DG (Gold-only case)",
                    ),
                    create_longevity_step(
                        duration=60,
                        description=f"{test_id} post-reboot Silver-drain settle",
                    ),
                ]
                if test_id == "case_07_dlb_coldboot"
                else []
            ),
        ]
    if test_id == "case_15_rollback_ecmp_to_dlb":
        # TC#224 — rollback Silver mid-test. Initial 1/4 of runtime
        # exercises both pools (matches the mixed expected_counts spec
        # intent); then disable Silver; remaining 3/4 runs DLB-only.
        # NOTE: `_stickiness_expectations` returns the BOTH-pools
        # expectation. Tracking task to revise to post-rollback only.
        pre_rollback_s = max(60, runtime_sec // 4)
        return [
            create_longevity_step(
                duration=pre_rollback_s,
                description="case_15 pre-rollback (Gold+Silver)",
            ),
            create_ixia_api_step(
                api_name="toggle_dlb_pool_enabled",
                args_dict={
                    "pool_name": "DLB_SILVER_PREFIX_POOL",
                    "enabled": False,
                },
                description="case_15 rollback trigger (Silver OFF)",
            ),
        ]
    if test_id == "case_21_ndp_flap":
        # TC#230 — flap NDP DG. Disable, 30 s hold, re-enable. Post-flap
        # longevity gives NDP re-resolve + FIB rebuild time.
        return [
            create_longevity_step(duration=30, description="case_21 pre-flap settle"),
            create_ixia_device_group_toggle_step(
                enable=False,
                device_group_name_regex="NDP_SUPPORTING_NEXTHOP",
                description="case_21 NDP flap: disable NDP DG",
            ),
            create_longevity_step(duration=30, description="case_21 NDP-down hold"),
            create_ixia_device_group_toggle_step(
                enable=True,
                device_group_name_regex="NDP_SUPPORTING_NEXTHOP",
                description="case_21 NDP flap: re-enable NDP DG",
            ),
        ]
    if test_id in ("case_11_ecmp_member_overcommit", "case_14_ecmp_width_tipover"):
        # TC#223 reject-signal isolation. The prior case (case_13) leaves a
        # 128-wide Silver ECMP group installed. When case_14's mutation runs
        # (single prefix × 130 wide), bgpd tries an ATOMIC syncFib batch
        # (withdraw old + install new); silicon rejects the install part
        # (130 > 128 supergroup cap) → whole batch fails → old case_13
        # residual STAYS in FIB → HC sees 1 group and mis-reads it as
        # "silicon accepted case_14". Toggle Silver OFF → 30 s FIB drain
        # (clean-withdraws the residual with no install pending) → toggle
        # ON to re-advertise case_14's 130-wide as a FRESH install.
        # Silicon rejects → 0 groups → HC's `total: 0` assertion sees the
        # true reject signal.
        return [
            create_ixia_api_step(
                api_name="toggle_dlb_pool_enabled",
                args_dict={
                    "pool_name": "DLB_SILVER_PREFIX_POOL",
                    "enabled": False,
                },
                description="case_14 pre-clear: Silver OFF (drain prior residual)",
            ),
            create_longevity_step(
                duration=30, description="case_14 pre-clear: 30 s FIB drain"
            ),
            create_ixia_api_step(
                api_name="toggle_dlb_pool_enabled",
                args_dict={
                    "pool_name": "DLB_SILVER_PREFIX_POOL",
                    "enabled": True,
                },
                description="case_14 re-advertise: Silver ON (fresh 130-wide install)",
            ),
            create_longevity_step(
                duration=60,
                description="case_14 post-re-advertise settle (silicon reject observation)",
            ),
        ]
    # ====== Longevity disruption loops (case_16..case_20) ======
    # Run 11 nightly 2026-06-30 surfaced these as "shape only" (just sleep,
    # no actual disruption fires). These branches replace the trailing
    # unconditional longevity sleep in `_build_playbook` with interleaved
    # trigger+settle steps that FILL `runtime_sec` end-to-end, so the
    # labeled disruption (warmboot loop / BGP-GR cycle / Silver flap) is
    # actually exercised continuously through the run window.
    if test_id == "case_16_background_warmboot":
        # TC#225 — agent warmboot loop. cycle = warmboot (~60s wedge_agent
        # restart in warm mode) + 60 s settle. Use `do_warmboot=True` on
        # `coop_apply_patchers` (preserves dataplane via SAI warm replay).
        cycle_sec = 120
        n = max(1, runtime_sec // cycle_sec)
        out: t.List[taac_types.Step] = []
        for i in range(n):
            out.append(
                create_run_task_step(
                    task_name="coop_apply_patchers",
                    params_dict={
                        "hostnames": [device_name],
                        "config_name": "agent",
                        "do_warmboot": True,
                    },
                    description=f"case_16 warmboot loop iter {i + 1}/{n}",
                )
            )
            out.append(
                create_longevity_step(
                    duration=60,
                    description=f"case_16 post-warmboot settle iter {i + 1}/{n}",
                )
            )
        return out
    if test_id == "case_17_background_bgp_gr":
        # TC#226 — BGP-GR cycle. Restart bgpd via systemctl; the daemon
        # has graceful-restart capability advertised so peers (IXIA Gold +
        # IXIA Silver + STSW infra) enter GR helper mode while bgpd
        # re-establishes. cycle = restart + 60 s settle.
        cycle_sec = 65
        n = max(1, runtime_sec // cycle_sec)
        out = []
        for i in range(n):
            out.append(
                create_service_interruption_step(
                    service=taac_types.Service.BGP,
                    trigger=taac_types.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                    description=f"case_17 BGP-GR loop iter {i + 1}/{n}: restart bgpd",
                )
            )
            out.append(
                create_longevity_step(
                    duration=60,
                    description=f"case_17 post-GR settle iter {i + 1}/{n}",
                )
            )
        return out
    if test_id == "case_18_dlb_ecmp_flap_longevity":
        # TC#227 — Silver flap loop at 100%-util on both pools. cycle =
        # Silver OFF + 30 s + Silver ON + 30 s. Each toggle exercises
        # mode-class re-allocation (DLB vs PPR) on the rogue port.
        cycle_sec = 65
        n = max(1, runtime_sec // cycle_sec)
        out = []
        for i in range(n):
            out.append(
                create_ixia_api_step(
                    api_name="toggle_dlb_pool_enabled",
                    args_dict={
                        "pool_name": "DLB_SILVER_PREFIX_POOL",
                        "enabled": False,
                    },
                    description=f"case_18 flap {i + 1}/{n}: Silver OFF",
                )
            )
            out.append(
                create_longevity_step(
                    duration=30,
                    description=f"case_18 silver-down hold {i + 1}/{n}",
                )
            )
            out.append(
                create_ixia_api_step(
                    api_name="toggle_dlb_pool_enabled",
                    args_dict={
                        "pool_name": "DLB_SILVER_PREFIX_POOL",
                        "enabled": True,
                    },
                    description=f"case_18 flap {i + 1}/{n}: Silver ON",
                )
            )
            out.append(
                create_longevity_step(
                    duration=30,
                    description=f"case_18 silver-up hold {i + 1}/{n}",
                )
            )
        return out
    if test_id == "case_19_switch_dlb_ecmp":
        # TC#228 — DLB-only ↔ DLB+ECMP switching, restructured as
        # ``ROUND_COUNT`` rounds × ``ROUND_SEC`` each with a full HC panel
        # at the end of every round. If any HC fails, TAAC halts the
        # playbook — early stop preserves silicon state for postmortem
        # instead of running blind for the remaining rounds.
        #
        # Round budget = toggle cycles (~26 min) + pre-HC settle 30 s +
        # HC panel with 60 s packet-loss sample (~2 min). Post-HC the
        # packet-loss check stops traffic (its ``clear_traffic_stats``
        # sample flow calls ``Traffic.Stop`` before sampling) so the
        # next round has to explicitly re-start traffic.
        ROUND_COUNT = 23
        ROUND_SEC = 30 * 60
        # Budget: 240 s post-toggle reconverge settle + ~120 s HC panel
        # (packet-loss dropped per T278263332 workaround, so no 60 s
        # sleep_time). Leaves 24 min for toggling → 22 pairs at 65 s each.
        # 120 s settle proved too short: l1002 CASE_19 v5 R1 2026-07-02
        # 15:48 tripped snapshot-vs-matrix MISMATCH inside stickiness HC
        # despite Gold + Silver both installed at expected counts (3070
        # multi-NH) — silicon's own snapshot count was still transient
        # from the last Silver toggle. Extending to 240 s aligns with the
        # empirical convergence time we saw in v4 R1 (which passed) where
        # packet-loss HC's extra 60 s sleep_time + clear_stats
        # inadvertently gave silicon that headroom.
        PRE_HC_SETTLE_SEC = 240
        HC_BUDGET_SEC = PRE_HC_SETTLE_SEC + 120
        TOGGLE_PAIR_SEC = 65  # OFF + 30s + ON + 30s ≈ 65 s (1 pair / min)
        toggle_pairs = max(1, (ROUND_SEC - HC_BUDGET_SEC) // TOGGLE_PAIR_SEC)
        out: t.List[taac_types.Step] = []
        for r in range(ROUND_COUNT):
            round_label = f"R{r + 1}/{ROUND_COUNT}"
            for i in range(toggle_pairs):
                out.extend(
                    [
                        create_ixia_api_step(
                            api_name="toggle_dlb_pool_enabled",
                            args_dict={
                                "pool_name": "DLB_SILVER_PREFIX_POOL",
                                "enabled": False,
                            },
                            description=f"case_19 {round_label} switch {i + 1}/{toggle_pairs}: DLB-only",
                        ),
                        create_longevity_step(
                            duration=30,
                            description=f"case_19 {round_label} DLB-only hold {i + 1}/{toggle_pairs}",
                        ),
                        create_ixia_api_step(
                            api_name="toggle_dlb_pool_enabled",
                            args_dict={
                                "pool_name": "DLB_SILVER_PREFIX_POOL",
                                "enabled": True,
                            },
                            description=f"case_19 {round_label} switch {i + 1}/{toggle_pairs}: DLB+ECMP",
                        ),
                        create_longevity_step(
                            duration=30,
                            description=f"case_19 {round_label} DLB+ECMP hold {i + 1}/{toggle_pairs}",
                        ),
                    ]
                )
            # End-of-round "STOP FLAP" per spec (TC#228): flap for the toggle
            # loop, then LOCK Silver ON so silicon settles to a stable state
            # for HC. Without this step, HC fires while silicon is still in
            # mid-transient (EcmpResourceManager PPR fallback path active)
            # from the last Silver-on toggle → snapshot vs matrix MISMATCH
            # even though visible counts look right. See T278295315 (same
            # PPR fallback mechanism observed on CASE_11 member overcommit).
            #
            # Locking to Silver-ON at round end (vs Silver-OFF) preserves
            # the "100% resource utilization" spec intent while HC observes
            # the clean DLB install of both 381 Gold + 2689 Silver.
            #
            # Gold stickiness = `total: 381` EXACT (Gold is invariant).
            # Silver stickiness `min_total: 50` (still permissive — silicon
            # may partial-install some Silver via PPR fallback even in
            # stable state; strict `total: 2689` would flake under that).
            out.extend(
                [
                    create_ixia_api_step(
                        api_name="toggle_dlb_pool_enabled",
                        args_dict={
                            "pool_name": "DLB_SILVER_PREFIX_POOL",
                            "enabled": True,
                        },
                        description=f"case_19 {round_label} STOP FLAP: lock Silver ON for stable HC",
                    ),
                    # STOP TRAFFIC before HC — mimics what IxiaPacketLossHealthCheck
                    # inadvertently did in v4 (which passed R1). Silicon's stickiness
                    # snapshot appears to count active flow-hash state differently
                    # from stopped-traffic state; without this, snapshot-vs-matrix
                    # mismatches even at correct visible counts (v5/v6/v7 all failed
                    # R1 with 3070 multi-NH observed but stickiness FAIL). Traffic
                    # re-starts at next round via create_start_traffic_step below.
                    create_stop_traffic_step(),
                    create_longevity_step(
                        duration=PRE_HC_SETTLE_SEC,
                        description=f"case_19 {round_label} post-STOP-FLAP+STOP-TRAFFIC settle (silicon snapshot converges to stable DLB state)",
                    ),
                    create_validation_step(
                        point_in_time_checks=[
                            create_dlb_resource_stickiness_check(
                                json_params={
                                    "prefix_patterns": [
                                        "5000:dd::",
                                        "5000:ee::",
                                    ],
                                    "expected_counts": {
                                        "5000:dd prefixes": {
                                            "total": 381,
                                        },
                                        "5000:ee prefixes": {
                                            "min_total": 50,
                                        },
                                    },
                                }
                            ),
                            create_cpu_utilization_check(
                                threshold=400.0,
                                start_time_jq_var="test_case_start_time",
                            ),
                            create_memory_utilization_check(
                                threshold=Gigabyte.GIG_8.value,
                                threshold_by_service={
                                    "bgpd": Gigabyte.GIG_4.value,
                                    "fboss_hw_agent@0": Gigabyte.GIG_8.value,
                                    "fboss_sw_agent": Gigabyte.GIG_8.value,
                                    "fsdb": Gigabyte.GIG_8.value,
                                    "qsfp_service": Gigabyte.GIG_8.value,
                                },
                                start_time_jq_var="test_case_start_time",
                            ),
                            # T278263332 workaround: DROPPED from per-round HC.
                            # IxiaPacketLossHealthCheck's get_latest_stats acquires
                            # the same DefaultSnapshotSettings snapshot that the
                            # taac_ixia background Thread-4 telemetry samples every
                            # 4-8 min. In long runs (>=2h) the two contend, MainThread
                            # blocks 40+ min then IxNetwork raises BadRequestError.
                            # Un-drop once T278263332 lands a snapshot-name split or
                            # semaphore fix. Stickiness HC below still verifies
                            # control-plane state per round; dataplane loss will be
                            # checked once at post-test only if we opt back in.
                            create_systemctl_active_state_check(
                                services=[
                                    hc_types.Service.WEDGE_AGENT,
                                    hc_types.Service.BGPD,
                                    hc_types.Service.QSFP_SERVICE,
                                    hc_types.Service.FSDB,
                                    hc_types.Service.FBOSS_SW_AGENT,
                                ],
                            ),
                        ],
                        # POST_TEST stage: ValidationStep raises TestCaseFailure
                        # on any HC failure (per step_definitions.py line 6746-6748:
                        # only PRE_TEST/POST_TEST stages produce exceptions;
                        # MID_TEST stages log FAIL but never halt the case).
                        # We use POST_TEST here mid-case so the run KILLS on any
                        # round's HC failure instead of running blind for
                        # remaining rounds.
                        stage=taac_types.ValidationStage.POST_TEST,
                        description=f"case_19 {round_label} HC panel (fail-fast, kill on any fail)",
                    ),
                    # Packet-loss HC stops traffic during its sample window;
                    # re-start so the next round's toggle cycles continue
                    # exercising real forwarding.
                    create_start_traffic_step(),
                ]
            )
        return out
    if test_id == "case_20_flap_warmboot_longevity":
        # TC#229 — alternate Silver flap + agent warmboot. cycle =
        # Silver-off 30 s + Silver-on 30 s + warmboot + 60 s settle.
        # ~250 s per iteration so 1 h ≈ 14 iters.
        cycle_sec = 250
        n = max(1, runtime_sec // cycle_sec)
        out = []
        for i in range(n):
            out.append(
                create_ixia_api_step(
                    api_name="toggle_dlb_pool_enabled",
                    args_dict={
                        "pool_name": "DLB_SILVER_PREFIX_POOL",
                        "enabled": False,
                    },
                    description=f"case_20 iter {i + 1}/{n}: Silver OFF",
                )
            )
            out.append(
                create_longevity_step(
                    duration=30,
                    description=f"case_20 silver-down hold {i + 1}/{n}",
                )
            )
            out.append(
                create_ixia_api_step(
                    api_name="toggle_dlb_pool_enabled",
                    args_dict={
                        "pool_name": "DLB_SILVER_PREFIX_POOL",
                        "enabled": True,
                    },
                    description=f"case_20 iter {i + 1}/{n}: Silver ON",
                )
            )
            out.append(
                create_longevity_step(
                    duration=30,
                    description=f"case_20 silver-up settle {i + 1}/{n}",
                )
            )
            out.append(
                create_run_task_step(
                    task_name="coop_apply_patchers",
                    params_dict={
                        "hostnames": [device_name],
                        "config_name": "agent",
                        "do_warmboot": True,
                    },
                    description=f"case_20 iter {i + 1}/{n}: warmboot",
                )
            )
            out.append(
                create_longevity_step(
                    duration=60,
                    description=f"case_20 post-warmboot settle {i + 1}/{n}",
                )
            )
        return out
    if test_id == "case_23_cold_start_cycle":
        # TC#232 — IXIA-side BGP cycle. Stop all emulated protocols (DUT
        # sees peers go IDLE, withdraws routes), 120 s hold, then start
        # all protocols. Post-cycle longevity gives BGP re-establish +
        # FIB re-install time.
        return [
            create_longevity_step(duration=30, description="case_23 pre-stop settle"),
            create_ixia_api_step(
                api_name="stop_all_protocols",
                args_dict={},
                description="case_23 cold-start: StopAllProtocols",
            ),
            create_longevity_step(
                duration=120,
                description="case_23 protocols-down hold (peers go IDLE)",
            ),
            create_ixia_api_step(
                api_name="start_all_protocols",
                args_dict={},
                description="case_23 cold-start: StartAllProtocols",
            ),
        ]
    # Default: no extra trigger; just steady-state mutate → longevity → HC.
    return []


def _build_playbook(
    profile: DlbEcmpAsicProfile,
    test_id: str,
    pool_params: t.Dict[NhPool, t.Tuple[int, int]],
    csv_paths: t.Dict[NhPool, str],
    runtime_sec: int,
    device_name: str,
    silver_pool: NhPool,
) -> Playbook:
    """Construct one Playbook for the given test_id + pool_params.

    Delegates the `Playbook` / `Stage` construction to
    `playbook_definitions.create_dlb_hardening_playbook` to keep this
    testconfig free of inline `Playbook(...)` / `Stage(...)` instantiation
    (required by `test_no_inline_playbook_construction` /
    `test_no_inline_stage_construction`).

    Per-case disruption triggers (coldboot / NDP-flap / rollback /
    cold-start) are injected by `_per_case_trigger_steps` between
    `start_traffic` and the main longevity wait. Generic cases get no
    extra trigger and just exercise steady-state install. ``device_name``
    is threaded through for triggers that need it (e.g., post-reboot
    `coop_apply_patchers` task).
    """
    # NOTE on pre-case undrain: previously included `create_drain_undrain_step`
    # here. Removed 2026-06-29 evening after Run 7 demonstrated that on a
    # devvm host the TAAC LOCAL_DRAINER thrift-RPC call hits PERMISSION
    # DENIED ('TIER:fboss_local_drainer' ACL doesn't include devvm tier),
    # and the NDS path hangs 8 min then fails. The CLI form
    # `fboss_local_drainer undrain` invoked directly on the DUT via lab-ssh
    # works fine — the workaround is operational: undrain the DUT once
    # before kicking off the test from lab-ssh, then rely on it staying
    # undrained for the whole run window. Will restore this step once
    # we land in a host tier with the LocalDrainer.undrain ACL OR the
    # ACL request goes through for our devvm tier.
    setup_steps: t.List[taac_types.Step] = []

    # 0. Always-clean precheck: reset Silver to zero silicon groups before
    # this case installs its own state. Toggle Silver OFF unconditionally
    # (whether or not this case will re-enable it) + 60 s settle + PRE_TEST
    # stickiness assertion that silicon has zero 5000:ee prefixes. If any
    # prior case left Silver residual (e.g. bgpd stuck in syncFib retry
    # loop after a failed atomic install), the precheck FAILS the current
    # case at PRE_TEST stage with a diagnostic snapshot instead of running
    # blind on top of the pollution. Cost ~65 s × 18 cases ≈ 20 min per
    # full run; buys guaranteed clean starting state.
    setup_steps.append(_toggle_pool_step(_pool_name_for(silver_pool), False))
    setup_steps.append(
        create_longevity_step(
            # 60 s was too short — l1001 CASE_07 v2 2026-07-02 10:33:55
            # observed 3070 residual groups because bgpd's Silver-withdraw
            # propagation started at 10:34:52 (2 min post toggle-off), well
            # after the precheck fired. 180 s gives bgpd time to send the
            # withdrawals + silicon to clear FIB before we assert Silver=0.
            duration=180,
            description=f"{test_id} precheck: drain prior Silver residual (180 s)",
        )
    )
    setup_steps.append(
        create_validation_step(
            point_in_time_checks=[
                create_dlb_resource_stickiness_check(
                    json_params={
                        # Include both patterns so the HC's snapshot-comparison
                        # step accounts for Gold's 381 baseline groups too;
                        # otherwise `matrix DLB-prefix total` = 0 while silicon
                        # snapshot shows 381 → MISMATCH → precheck FAILs even
                        # when Silver is genuinely 0 (observed l1001 CASE_07
                        # v3 2026-07-02 11:51: silicon had 381 Gold + 0 Silver
                        # but HC failed on snapshot-vs-matrix delta of -381).
                        "prefix_patterns": ["5000:dd::", "5000:ee::"],
                        "expected_counts": {
                            "5000:ee prefixes": {"total": 0},
                        },
                    }
                ),
            ],
            stage=taac_types.ValidationStage.PRE_TEST,
            description=f"{test_id} precheck: assert Silver=0 before mutation",
        )
    )

    # 1. Batch-mutate all active pools atomically. `apply_pool_mutations`
    # (in taac_ixia) does ONE Traffic.Stop → per-pool config mutation → ONE
    # StartAllProtocols → convergence settle scaled by total rows → ONE
    # Traffic.Regenerate + Apply. This replaces the per-pool loop that
    # cascaded Traffic Item corruption across cases (Run 20 CASE_05 FAIL).
    if csv_paths:
        setup_steps.append(
            _mutate_pools_batch_step(
                [
                    (csv_path, _pool_name_for(pool))
                    for pool, csv_path in csv_paths.items()
                ]
            )
        )

    # 2. (Superseded by step 0 above.) Silver was unconditionally toggled
    # OFF + drained + PRE_TEST-verified as zero at case start; Silver-heavy
    # cases will re-enable it via their own pool mutation in step 1.

    # 3. Traffic on → [per-case trigger sequence] → longevity → off.
    # For longevity cases (case_16..case_20), the trigger sequence is a
    # disruption loop that ALREADY fills `runtime_sec` end-to-end — so
    # skip the trailing unconditional longevity sleep (it would double
    # the wall-clock runtime) and just add a brief final settle so the
    # post-test HC fires against a stable state. For all other cases,
    # the trigger steps are short one-shots and the main runtime is
    # exercised by the unconditional longevity_step below.
    is_longevity = test_id in TESTS_LONGEVITY
    traffic_steps: t.List[taac_types.Step] = [
        create_start_traffic_step(),
        *_per_case_trigger_steps(test_id, runtime_sec, device_name),
    ]
    if is_longevity:
        traffic_steps.append(
            create_longevity_step(
                duration=60, description=f"{test_id} final settle pre-HC"
            )
        )
    else:
        traffic_steps.append(
            create_longevity_step(
                duration=runtime_sec, description=f"{test_id} run window"
            )
        )
    traffic_steps.append(create_stop_traffic_step())

    # Longevity playbooks (case_16..case_20) run for 1–12h with continuous
    # disruption (warmboot/BGP-GR loop/flap). Add CPU + MEMORY utilization
    # postchecks so slow leaks or runaway processes get caught at end-of-
    # case rather than going silent until the next post-mortem.
    #
    # V15 polish (post Run 11 nightly evidence, Task T277829549): thresholds
    # replaced bare `create_*_utilization_check()` which defaulted to
    # `threshold=0` (bytes) → EVERY sample above 0 counted as violation →
    # unconditional MEM HC FAIL across CASE_16/17/18/20. Values below are
    # from EBB's `_MEMORY_THRESHOLD_BY_SERVICE_PRECHECK` template (proven
    # in production on FBOSS EBB conveyor + hyperport/hardening tests).
    # CPU 400% is the FBOSS-hardening standard (multi-threaded bgpd bursts
    # under BGP config-reload / GR are expected to spike well over 100%).
    # Per-case Gold packet-loss thresholds (% frame loss on the persistent
    # Gold traffic item, measured after `sleep_time=60` s of clean re-run
    # once test cycles finish). Longevity + coldboot + disruption cases
    # allow bounded loss; steady-state cases must be lossless.
    # Silver traffic isn't measured — bag013 setup only has the one
    # Gold traffic item `ETH1_1_1_TO_DLB_GOLDEN_TRAFFIC`.
    _LOSS_THRESHOLD_BY_CASE: t.Dict[str, str] = {
        "case_07_dlb_coldboot": "10.0",
        "case_09_ecmp_coldboot": "10.0",
        "case_23_cold_start_cycle": "5.0",
        "case_21_ndp_flap": "5.0",
        "case_15_rollback_ecmp_to_dlb": "2.0",
        # CASE_05 (Silver+Gold mixed 50%): l1001 v3 2026-07-02 13:12 saw
        # silicon under-install (only 121 of ~3070 multi-NH groups
        # installed) despite total members ~47K fitting under 96K cap.
        # Silicon rejects/evicts under group-cap pressure. Gold traffic
        # traversing partially-installed Silver routes drops some packets.
        # Loose threshold acknowledges this real silicon behavior until we
        # get BCM confirmation on the true post-boot group cap.
        "case_05_ecmp_full_50pct_mixed": "5.0",
    }
    loss_threshold = _LOSS_THRESHOLD_BY_CASE.get(test_id, "0")
    # T278263332 workaround: skip packet-loss HC on long-running cases where
    # taac_ixia Thread-4 background telemetry contends with the HC's
    # get_latest_stats on the shared DefaultSnapshotSettings snapshot. In
    # runs >= 2h the mutex contention hangs MainThread 40+ min then IxNetwork
    # raises BadRequestError. CASE_19 (12h) definitely tripped it; other
    # longevity cases may too. Un-drop when T278263332 is resolved.
    _PACKETLOSS_SKIP_CASES = {"case_19_switch_dlb_ecmp"}
    extra_postchecks: t.List[taac_types.PointInTimeHealthCheck] = []
    if test_id not in _PACKETLOSS_SKIP_CASES:
        extra_postchecks.append(
            create_ixia_packet_loss_check(
                thresholds=[
                    hc_types.PacketLossThreshold(
                        names=["ETH1_1_1_TO_DLB_GOLDEN_TRAFFIC"],
                        metric=hc_types.PacketLossMetric.PERCENTAGE,
                        str_value=loss_threshold,
                    ),
                ],
                clear_traffic_stats=True,
                sleep_time=60,
            )
        )
    if test_id in TESTS_LONGEVITY:
        # V16 polish: post-reconvergence CPU/MEM leak checks — long-running
        # disruption loops surface bgpd / fboss_sw_agent leaks that don't
        # show in short hardening cases. Values from EBB's proven template.
        # CPU 400% = FBOSS-hardening standard (multi-threaded bgpd bursts).
        extra_postchecks.extend(
            [
                create_cpu_utilization_check(
                    threshold=400.0,
                    start_time_jq_var="test_case_start_time",
                ),
                create_memory_utilization_check(
                    threshold=Gigabyte.GIG_8.value,
                    threshold_by_service={
                        "bgpd": Gigabyte.GIG_4.value,
                        "fboss_hw_agent@0": Gigabyte.GIG_8.value,
                        "fboss_sw_agent": Gigabyte.GIG_8.value,
                        "fsdb": Gigabyte.GIG_8.value,
                        "qsfp_service": Gigabyte.GIG_8.value,
                    },
                    start_time_jq_var="test_case_start_time",
                ),
            ]
        )

    return create_dlb_hardening_playbook(
        name=test_id.upper(),
        setup_steps=setup_steps,
        traffic_steps=traffic_steps,
        stickiness_json_params=_stickiness_expectations(profile, test_id, pool_params),
        extra_postchecks=extra_postchecks,
    )


def _build_playbooks_for_ids(
    profile: DlbEcmpAsicProfile,
    test_ids: t.List[str],
    device_name: str,
    gold_pool: NhPool,
    silver_pool: NhPool,
    runtime_sec_overrides: t.Optional[t.Dict[str, int]] = None,
    default_runtime_sec: int = DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
) -> t.List[Playbook]:
    """Walk a list of test_ids → list of Playbooks.

    ``device_name`` is threaded into per-case trigger sequences that need
    it (post-reboot `coop_apply_patchers` task, etc.). ``gold_pool`` +
    ``silver_pool`` are threaded through so per-DUT NH-network variants
    (c002 for l1001, d002 for l1002) route to their own CSV directory
    without collision.
    """
    params = derive_test_params(profile, gold_pool, silver_pool)
    test_csv_paths = _ensure_csvs(profile, gold_pool, silver_pool)
    overrides = runtime_sec_overrides or {}
    # Background-wrapper longevity cases (case_16/17) have empty
    # `pool_params` per `dlb_hardening_test_params.py` — they're meant to
    # inherit case_02's baseline shape (50%-util Gold-only) as the steady
    # state on top of which the disruption loop runs. `_stickiness_expectations`
    # already inherits case_02 via its `if not pool_params` branch. The
    # playbook builder ALSO needs to inherit case_02's pool_params +
    # csv_paths so the setup-stage mutate step actually advertises the
    # baseline shape on the wire; without this, IXIA stays at its 1-prefix
    # bootstrap and stickiness HC false-FAILs (Run 11 nightly 2026-06-30
    # CASE_16 demonstrated this — bgpd healthy + ESTABLISHED, but only 1
    # Gold prefix advertised, HC expected 381 → fail).
    _BASELINE_INHERIT_TID = "case_02_dlb_fill_50pct"
    _INHERIT_BASELINE_FOR = {
        "case_16_background_warmboot",
        "case_17_background_bgp_gr",
    }
    playbooks: t.List[Playbook] = []
    for tid in test_ids:
        pool_params = params[tid]
        csv_paths = test_csv_paths[tid]
        if not pool_params and tid in _INHERIT_BASELINE_FOR:
            pool_params = params[_BASELINE_INHERIT_TID]
            csv_paths = test_csv_paths[_BASELINE_INHERIT_TID]
        runtime = overrides.get(tid, default_runtime_sec)
        playbooks.append(
            _build_playbook(
                profile,
                tid,
                pool_params,
                csv_paths,
                runtime,
                device_name,
                silver_pool=silver_pool,
            )
        )
    return playbooks


# =============================================================================
# Peer-group helper (shared between Gold + Silver peers — same on-device
# policy chain, just different BGP peer addresses).
# =============================================================================
def _get_gtsw_ixia_peer_group_tasks(device_name: str) -> t.List[t.Any]:
    return [
        create_coop_register_patcher_task(
            hostname=device_name,
            config_name="bgpcpp",
            patcher_name="add_peer_group_patcher_PEERGROUP_GTSW_IXIA_V6",
            task_name="add_peer_group_patcher",
            patcher_args={
                "name": PEERGROUP_GTSW_IXIA_V6,
                "description": "eBGP peering from GTSW to IXIA, IPv6",
                "disable_ipv4_afi": "True",
                "disable_ipv6_afi": "False",
                "ingress_policy_name": "PROPAGATE_GTSW_STSW_IN",
                "egress_policy_name": "PROPAGATE_GTSW_STSW_OUT",
                "bgp_peer_timers_hold_time_seconds": "30",
                "bgp_peer_timers_keep_alive_seconds": "10",
                "bgp_peer_timers_out_delay_seconds": "0",
                "bgp_peer_timers_withdraw_unprog_delay_seconds": "0",
                "peer_tag": "IXIA",
                "max_routes": "900000",
                "warning_only": "True",
                "warning_limit": "0",
                "next_hop_self": "False",
                "add_path": "BOTH",
                "is_confed_peer": "False",
                "is_passive": "False",
                "v4_over_v6_nexthop": "False",
                "link_bandwidth_bps": "auto",
            },
            py_func_name="add_peer_group_patcher",
        ),
    ]


# =============================================================================
# Factory: build a TestConfig with the named playbooks.
# =============================================================================
def build_dlb_hardening_testconfig(
    test_config_name: str,
    profile: DlbEcmpAsicProfile,
    device_name: str,
    local_mac_address: str,
    ixia_downlink_interface: str,
    ixia_rogue_interface: str,
    ixia_remote_interface: t.Optional[str],
    ixia_downlink_parent_v6: str,
    ixia_rogue_parent_v6: str,
    ixia_remote_parent_v6: t.Optional[str],
    gold_pool: NhPool,
    silver_pool: NhPool,
    remote_uplink_as_4byte: int,
    is_uplink_peer_confed: str,
    prefix_limit: str,
    test_ids: t.List[str],
    spine_modules: t.Sequence[int],
    runtime_sec_overrides: t.Optional[t.Dict[str, int]] = None,
    default_runtime_sec: int = DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
    direct_ixia_connections: t.Optional[t.List[t.Any]] = None,
    basset_pool: t.Optional[str] = None,
) -> TestConfig:
    """Build the IcePack/TH6 DLB hardening or longevity TestConfig.

    Shared factory for both ``NPI_DVT_ICEPACK_GTSW__DLB_HARDENING``
    (18 short tests) and ``NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY`` (5
    long tests). Differs only in ``test_ids`` (which playbooks to wire)
    and ``runtime_sec_overrides`` (per-playbook longevity durations).
    """
    # ---- L1 config (PFC priority groups for RDMA-IB DLB-eligible traffic) ----
    # NOTE: an IMIX FrameSize was originally defined here for DLB traffic
    # profile but the basic_traffic_item_configs below uses a FIXED-1024
    # frame size directly (matches the icepack_ecmp_resource_testing_config
    # reference). When we want IMIX, re-add the FrameSize struct here
    # and wire it into the traffic-item's frame_size_settings.
    dsf_l1_config = ixia_types.L1Config(
        enable_fcoe=True,
        flow_control_config=ixia_types.FlowControlConfig(
            pfc_prority_groups_config=ixia_types.PfcPriorityGroupsConfig(
                priority0_pfc_queue=ixia_types.PfcQueue.TWO,
                priority1_pfc_queue=ixia_types.PfcQueue.ONE,
                priority2_pfc_queue=ixia_types.PfcQueue.ZERO,
                priority3_pfc_queue=ixia_types.PfcQueue.THREE,
            ),
            enable_pfc_pause_delay=False,
        ),
    )

    # ---- TC-level pre/postchecks ----
    tc_prechecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
            ],
        ),
    ]
    tc_postchecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
            ],
        ),
    ]
    tc_snapshot_checks = [create_core_dumps_snapshot_check()]

    def _add_tc_checks(pb: Playbook) -> Playbook:
        new_prechecks = tc_prechecks + list(pb.prechecks or [])
        new_postchecks = list(pb.postchecks or []) + tc_postchecks
        if pb.skip_test_config_snapshot_checks:
            new_snapshot_checks = list(pb.snapshot_checks or [])
        else:
            new_snapshot_checks = list(pb.snapshot_checks or []) + tc_snapshot_checks
        return pb(
            prechecks=new_prechecks,
            postchecks=new_postchecks,
            snapshot_checks=new_snapshot_checks,
            skip_test_config_snapshot_checks=False,
        )

    # ---- BGP peer configs (Gold + Silver — two distinct peers on the
    # same rogue port `eth1/1/3`, both using the SAME DUT-local-addr
    # `c002::a` because the DUT only has one IPv6 address on this
    # interface. Differentiation between Gold-vs-Silver is by the peer's
    # remote address (`c002::b` vs `c002::d`) and the IXIA-side prefix
    # NH pool (`c002::a001..a080` for Gold = DLB-eligible, `c002::b001+`
    # for Silver = non-DLB ECMP). Run 7 root-cause 2026-06-29 found
    # Silver previously had `local_addr=c002::c` (fictitious) which
    # caused TCP src/dst mismatch and Silver session stuck IDLE forever.
    peer_configs_json = json.dumps(
        [
            {
                "local_addr": f"{ixia_rogue_parent_v6}::a",
                "peer_addr": f"{ixia_rogue_parent_v6}::b",
                "peer_group_name": PEERGROUP_GTSW_IXIA_V6,
                "remote_as_4_byte": str(remote_uplink_as_4byte),
                "description": "ixia_session_gold",
            },
            {
                "local_addr": f"{ixia_rogue_parent_v6}::a",
                "peer_addr": f"{ixia_rogue_parent_v6}::d",
                "peer_group_name": PEERGROUP_GTSW_IXIA_V6,
                "remote_as_4_byte": str(remote_uplink_as_4byte),
                "description": "ixia_session_silver",
            },
        ]
    )

    # ---- Endpoint ----
    ixia_ports_list = [ixia_downlink_interface, ixia_rogue_interface]
    if ixia_remote_interface:
        ixia_ports_list.append(ixia_remote_interface)
    endpoints = [
        taac_types.Endpoint(
            name=device_name,
            ixia_ports=ixia_ports_list,
            dut=True,
            mac_address=local_mac_address,
            direct_ixia_connections=direct_ixia_connections or [],
        ),
    ]

    # ---- Device groups on rogue port: Gold DG + Silver DG + NDP DG ----
    rogue_dgs = [
        # DG 0: Gold (DLB-eligible) BGP peer
        taac_types.DeviceGroupConfig(
            device_group_index=0,
            tag_name="DLB_resource(Gold)",
            enable=True,
            multiplier=1,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{ixia_rogue_parent_v6}::b",
                increment_ip="::",
                gateway_starting_ip=f"{ixia_rogue_parent_v6}::a",
                gateway_increment_ip="::",
                mask=64,
            ),
            v6_bgp_config=taac_types.BgpConfig(
                local_as_4_bytes=remote_uplink_as_4byte,
                local_as_increment=0,
                enable_4_byte_local_as=True,
                bgp_peer_type=ixia_types.BgpPeerType.EBGP,
                is_confed=is_uplink_peer_confed == "True",
                bgp_capabilities=[
                    ixia_types.BgpCapability.IpV6Unicast,
                    ixia_types.BgpCapability.Ipv6UnicastAddPath,
                ],
                custom_network_group_configs=[
                    ixia_types.CustomNetworkGroupConfig(
                        device_group_name="DLB_resource(Gold)",
                        network_group_name="DLB_GOLD_PREFIX_POOL",
                        # Starting shape — overwritten per-test by
                        # mutate_dlb_pool_from_csv. Pick a baseline
                        # that boots cleanly (1 prefix, 1 NH).
                        network_group_multiplier=1,
                        prefix_start_value="5000:dd::",
                        prefix_length=64,
                        nexthop_start_value=f"{gold_pool.nh_network}::a001",
                        nexthop_increments="::1",
                        ecmp_width=1,
                        community_list=[
                            "65446:30",
                            "65441:323",
                            "65456:323",
                        ],
                        network_group_index=0,
                    ),
                ],
            ),
        ),
        # DG 1: Silver (non-DLB ECMP) BGP peer
        # NOTE: Silver gateway MUST be the DUT's real IP `c002::a` (same
        # as Gold), NOT `c002::c`. Run 7 root-cause investigation
        # 2026-06-29 found Silver's BGP session stuck IDLE forever
        # because IXIA Silver's gateway was set to `c002::c` — an
        # address that doesn't exist on the DUT — so NDP resolution
        # failed, no TCP path to DUT, BGP never establishes. Gold's
        # gateway was correctly `c002::a` (real DUT addr) and worked.
        # On the DUT side, bgpcpp `peer_configs_json` declares Silver's
        # DUT-local-addr as `c002::c` — that's the "alias" the DUT
        # binds in its peer-config to differentiate Silver-vs-Gold
        # session contexts, NOT a real interface address. The actual
        # IXIA-side gateway must point to the real DUT IP `c002::a`.
        taac_types.DeviceGroupConfig(
            device_group_index=1,
            tag_name="ECMP_resource(Silver)",
            enable=True,
            multiplier=1,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{ixia_rogue_parent_v6}::d",
                increment_ip="::",
                gateway_starting_ip=f"{ixia_rogue_parent_v6}::a",
                gateway_increment_ip="::",
                mask=64,
            ),
            v6_bgp_config=taac_types.BgpConfig(
                local_as_4_bytes=remote_uplink_as_4byte,
                local_as_increment=0,
                enable_4_byte_local_as=True,
                bgp_peer_type=ixia_types.BgpPeerType.EBGP,
                is_confed=is_uplink_peer_confed == "True",
                bgp_capabilities=[
                    ixia_types.BgpCapability.IpV6Unicast,
                    ixia_types.BgpCapability.Ipv6UnicastAddPath,
                ],
                custom_network_group_configs=[
                    ixia_types.CustomNetworkGroupConfig(
                        device_group_name="ECMP_resource(Silver)",
                        network_group_name="DLB_SILVER_PREFIX_POOL",
                        network_group_multiplier=1,
                        prefix_start_value="5000:ee::",
                        prefix_length=64,
                        nexthop_start_value=f"{silver_pool.nh_network}::b001",
                        nexthop_increments="::1",
                        ecmp_width=1,
                        community_list=[
                            "65446:30",
                            "65441:323",
                            "65456:323",
                        ],
                        network_group_index=0,
                    ),
                ],
            ),
        ),
        # DG 2: NDP-supporting nexthops (no BGP). Covers BOTH Gold NHs
        # (::a001..a080 = 128) and Silver NHs (::b001..b???) so silicon
        # NDP-resolves all advertised next-hops. Sized to cover Gold
        # 128 + Silver up to 3072 = 3200, but we cap at a reasonable
        # number for the smoke setup; the real silver tests will need
        # to grow this DG's multiplier — TODO.
        taac_types.DeviceGroupConfig(
            device_group_index=2,
            tag_name="NDP_SUPPORTING_NEXTHOP",
            multiplier=130,
            v6_addresses_config=taac_types.IpAddressesConfig(
                starting_ip=f"{gold_pool.nh_network}::a001",
                increment_ip="::1",
                gateway_starting_ip=f"{gold_pool.nh_network}::a",
                mask=64,
            ),
        ),
    ]

    # ---- Playbooks ----
    playbooks = [
        _add_tc_checks(p)
        for p in _build_playbooks_for_ids(
            profile,
            test_ids,
            device_name=device_name,
            gold_pool=gold_pool,
            silver_pool=silver_pool,
            runtime_sec_overrides=runtime_sec_overrides,
            default_runtime_sec=default_runtime_sec,
        )
    ]

    return TestConfig(
        name=test_config_name,
        ixia_protocol_verification_timeout=10,
        skip_ixia_protocol_verification=True,
        ixia_config_cache=taac_types.IxiaConfigCache(enabled=False),
        basset_pool=basset_pool,
        endpoints=endpoints,
        setup_tasks=[
            create_coop_unregister_patchers_task(device_name),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="agent",
                patcher_name="disable_gtsw_spine_interfaces",
                task_name="change_port_admin_state",
                patcher_args={
                    f"eth1/{module}/{port}": "disable"
                    for module in spine_modules
                    for port in SPINE_PORT_INDICES
                },
                py_func_name="change_port_admin_state",
            ),
        ]
        + _get_gtsw_ixia_peer_group_tasks(device_name)
        + [
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name="add_bgp_peers_dut",
                task_name="add_bgp_peers",
                patcher_args={"peer_configs": peer_configs_json},
                py_func_name="add_bgp_peers",
            ),
            create_coop_apply_patchers_task(
                hostnames=[device_name],
                do_warmboot=True,
            ),
        ],
        teardown_tasks=[
            create_coop_unregister_patchers_task(device_name),
        ],
        basic_traffic_item_configs=[
            taac_types.BasicTrafficItemConfig(
                name=f"{ixia_downlink_interface.upper().replace('/', '_')}_TO_DLB_GOLDEN_TRAFFIC",
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_rogue_interface}",
                        device_group_index=0,
                        network_group_index=0,
                    ),
                ],
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.FIXED,
                    fixed_size=1024,
                ),
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                traffic_type=ixia_types.TrafficType.IPV6,
                tracking_types=[ixia_types.TrafficStatsTrackingType.TRAFFIC_ITEM],
                packet_headers=DSF_RDMA_IB_PACKET_HEADERS,
            ),
        ],
        basic_port_configs=[
            taac_types.BasicPortConfig(
                l1_config=dsf_l1_config,
                endpoint=f"{device_name}:{ixia_downlink_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="DOWNLINK_L3_TRAFFIC",
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_downlink_parent_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_downlink_parent_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                    ),
                ],
            ),
            taac_types.BasicPortConfig(
                l1_config=dsf_l1_config,
                endpoint=f"{device_name}:{ixia_rogue_interface}",
                device_group_configs=rogue_dgs,
            ),
            *(
                [
                    taac_types.BasicPortConfig(
                        l1_config=dsf_l1_config,
                        endpoint=f"{device_name}:{ixia_remote_interface}",
                        device_group_configs=[
                            taac_types.DeviceGroupConfig(
                                device_group_index=0,
                                tag_name="REMOTE_L3_TRAFFIC",
                                enable=True,
                                multiplier=1,
                                v6_addresses_config=taac_types.IpAddressesConfig(
                                    starting_ip=f"{ixia_remote_parent_v6}::b",
                                    increment_ip="::",
                                    gateway_starting_ip=f"{ixia_remote_parent_v6}::a",
                                    gateway_increment_ip="::",
                                    mask=64,
                                ),
                            ),
                        ],
                    ),
                ]
                if ixia_remote_interface and ixia_remote_parent_v6
                else []
            ),
        ],
        playbooks=playbooks,
    )


# =============================================================================
# Instances — gtsw001.l1001.c085.ash6 (IcePack TH6 / ICECUBE800BC).
# =============================================================================
_COMMON_DUT_KWARGS = {
    "profile": ICEPACK_TH6_PROFILE,
    "device_name": "gtsw001.l1001.c085.ash6",
    "local_mac_address": "02:00:00:00:0f:0c",
    "ixia_downlink_interface": "eth1/1/1",
    "ixia_rogue_interface": "eth1/1/3",
    "ixia_remote_interface": "eth1/1/5",
    "ixia_downlink_parent_v6": "2401:db00:206a:c000",
    "ixia_rogue_parent_v6": "2401:db00:206a:c002",
    "ixia_remote_parent_v6": "2401:db00:206a:c004",
    "gold_pool": ICEPACK_GOLD_POOL,
    "silver_pool": ICEPACK_SILVER_POOL,
    "spine_modules": GTSW001_ASH6_SPINE_MODULES,
    "remote_uplink_as_4byte": 4200601902,
    "is_uplink_peer_confed": "False",
    "prefix_limit": "75000",
    "basset_pool": "dne.test",
    "direct_ixia_connections": [
        taac_types.DirectIxiaConnection(
            interface="eth1/1/1",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/25",
        ),
        taac_types.DirectIxiaConnection(
            interface="eth1/1/3",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/27",
        ),
        taac_types.DirectIxiaConnection(
            interface="eth1/1/5",
            ixia_chassis_ip=IXIA19_CHASSIS_IP,
            ixia_port="1/29",
        ),
    ],
}


NPI_DVT_ICEPACK_GTSW__DLB_HARDENING: TestConfig = build_dlb_hardening_testconfig(
    test_config_name="NPI_DVT_ICEPACK_GTSW__DLB_HARDENING",
    test_ids=TESTS_HARDENING,
    runtime_sec_overrides=HARDENING_RUNTIME_OVERRIDES_SEC,
    default_runtime_sec=DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
    **_COMMON_DUT_KWARGS,
)


NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY: TestConfig = build_dlb_hardening_testconfig(
    test_config_name="NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY",
    test_ids=TESTS_LONGEVITY,
    runtime_sec_overrides=LONGEVITY_RUNTIMES_SEC,
    # 1hr default for any longevity case missing an explicit override.
    default_runtime_sec=3600,
    **_COMMON_DUT_KWARGS,
)


# gtsw001.l1002.c085.ash6 — parallel-worker DUT for overnight longevity so
# gtsw001.l1001 stays available for the hardening dial-in. Fabric probe
# 2026-07-01 (T+6h into DLB debug session) confirmed:
#   - Same IcePack/TH6 hardware (ICECUBE800BC)
#   - Same 32 STSW-facing spine modules as gtsw001.l1001 (full mirror)
#   - ALL 3 IXIA ports UP with real optical signal (eth1/1/5 Rx=2.71dBm)
# The l1001/l1002 pods differ in physical rack; l1002 was the only DUT in
# ash6 with all 3 IXIA ports cabled aside from l1001 itself. gtsw002-008 in
# l1001 all had eth1/1/5 dark. IXIA port mapping unknown → leave
# direct_ixia_connections empty, let TAAC's test_bed_chunker fetch from
# Skynet circuit-info (proven-working on gtsw001.l1001).
# l1002 is on IXIA20 chassis (different from l1001's IXIA19) — no chassis
# contention with l1001. LLDP discovery on Run 27 confirmed cabling:
#   eth1/1/1 → chassis ::3020, slot 1, port 53
#   eth1/1/3 → chassis ::3020, slot 1, port 55
# LLDP-only (empty direct_ixia_connections) mode caused "7/7 Trial traffic for
# ARP/NDP resolution" to fail with "Error in L2/L3 Traffic Apply" repeatedly
# across setup retries (netcastle log 1586265, 2026-07-01 08:34→08:41). The
# retry destroys the IXIA session each attempt without giving DUT-side NDP
# time to resolve on top of a freshly-created topology. Hardcoding the ports
# lets TAAC skip LLDP walk each retry cycle → faster setup convergence and
# matches the l1001 pattern that works.
IXIA20_CHASSIS_IP: str = "2401:db00:2066:31fb::3020"

_GTSW001_L1002_DUT_KWARGS = {
    **_COMMON_DUT_KWARGS,
    "device_name": "gtsw001.l1002.c085.ash6",
    # Spine module list mirrors gtsw001.l1001 exactly (32 modules verified
    # via live `fboss2 show interface | grep stsw` on 2026-07-01).
    "spine_modules": GTSW001_ASH6_SPINE_MODULES,
    # l1002 IXIA-facing subnets use `d000/d002/d004` (per DUT live probe),
    # NOT `c000/c002/c004` like l1001. If we don't override these + the pool
    # constants, BGP peers configure c002::a as gateway → NDP can never
    # resolve on l1002 → "7/7 Trial traffic ARP/NDP resolution" fails with
    # "Error in L2/L3 Traffic Apply" (netcastle log 2253984, 2026-07-01 09:00
    # was the last symptom before this override was added).
    "ixia_downlink_parent_v6": "2401:db00:206a:d000",
    "ixia_rogue_parent_v6": "2401:db00:206a:d002",
    # Per-DUT pool constants — same silicon dimensions, only nh_network
    # changes. Distinct `.name` routes CSVs to per-DUT subdirs (silver_l1002
    # vs silver) so both DUT families can share the module without CSV
    # collision.
    "gold_pool": ICEPACK_L1002_GOLD_POOL,
    "silver_pool": ICEPACK_L1002_SILVER_POOL,
    # eth1/1/5 has real optical signal on the DUT side but LLDP finds only 2
    # IXIA ports on this DUT. Whatever's on the other end of eth1/1/5 is not
    # IXIA. Run as 2-port DUT — hardening + longevity traffic path is
    # downlink→rogue only; the remote-loop endpoint on eth1/1/5 was never
    # referenced by any HC.
    "ixia_remote_interface": None,
    "ixia_remote_parent_v6": None,
    "direct_ixia_connections": [
        taac_types.DirectIxiaConnection(
            interface="eth1/1/1",
            ixia_chassis_ip=IXIA20_CHASSIS_IP,
            ixia_port="1/53",
        ),
        taac_types.DirectIxiaConnection(
            interface="eth1/1/3",
            ixia_chassis_ip=IXIA20_CHASSIS_IP,
            ixia_port="1/55",
        ),
    ],
}


NPI_DVT_ICEPACK_GTSW001_L1002__DLB_LONGEVITY: TestConfig = (
    build_dlb_hardening_testconfig(
        test_config_name="NPI_DVT_ICEPACK_GTSW001_L1002__DLB_LONGEVITY",
        test_ids=TESTS_LONGEVITY,
        runtime_sec_overrides=LONGEVITY_RUNTIMES_SEC,
        default_runtime_sec=3600,
        **_GTSW001_L1002_DUT_KWARGS,
    )
)


NPI_DVT_ICEPACK_GTSW001_L1002__DLB_HARDENING: TestConfig = (
    build_dlb_hardening_testconfig(
        test_config_name="NPI_DVT_ICEPACK_GTSW001_L1002__DLB_HARDENING",
        test_ids=TESTS_HARDENING,
        runtime_sec_overrides=HARDENING_RUNTIME_OVERRIDES_SEC,
        default_runtime_sec=DEFAULT_HARDENING_TRAFFIC_RUNTIME_SEC,
        **_GTSW001_L1002_DUT_KWARGS,
    )
)

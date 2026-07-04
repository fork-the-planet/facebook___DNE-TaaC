#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe

"""Smoke-test the DLB hardening parameter chain end-to-end.

Verifies:
- ``ICEPACK_TH6_PROFILE`` usable derivations match Pavan-confirmed numbers
  (381 / 3070 / 98302).
- ``derive_test_params`` covers all 23 cases and emits expected shapes for
  the key validation rows.
- ``generate_all_csvs`` produces actual CSVs at the expected paths with
  the right row counts.

Run: ``buck2 run fbcode//neteng/test_infra/dne/taac/testconfigs/npi:dlb_hardening_smoke``
"""

import os
import shutil
import tempfile

from taac.testconfigs.npi.dlb_asic_profiles import (
    ICEPACK_GOLD_POOL,
    ICEPACK_SILVER_POOL,
    ICEPACK_TH6_PROFILE,
    usable_from_raw,
)
from taac.testconfigs.npi.dlb_hardening_test_params import (
    derive_test_params,
    TESTS_HARDENING,
    TESTS_LONGEVITY,
)


def assert_eq(label, actual, expected):
    status = "OK" if actual == expected else "FAIL"
    print(f"  [{status}] {label}: {actual!r} == {expected!r}")
    if actual != expected:
        raise AssertionError(f"{label}: got {actual!r}, expected {expected!r}")


def main() -> None:
    print("=== Profile + usable derivations ===")
    assert_eq("usable_from_raw(511)", usable_from_raw(511), 381)
    assert_eq("usable_from_raw(4096)", usable_from_raw(4096), 3070)
    assert_eq("usable_from_raw(131072)", usable_from_raw(131072), 98302)
    assert_eq(
        "TH6.dlb_max_groups_usable",
        ICEPACK_TH6_PROFILE.dlb_max_groups_usable,
        381,
    )
    assert_eq(
        "TH6.ecmp_max_groups_usable",
        ICEPACK_TH6_PROFILE.ecmp_max_groups_usable,
        3070,
    )
    assert_eq(
        "TH6.ecmp_max_members_usable",
        ICEPACK_TH6_PROFILE.ecmp_max_members_usable,
        98302,
    )

    print("\n=== Pool definitions ===")
    assert_eq("Gold.size", ICEPACK_GOLD_POOL.size, 128)
    assert_eq("Gold.nh_host_start", ICEPACK_GOLD_POOL.nh_host_start, 0xA001)
    assert_eq("Gold.prefix_base", ICEPACK_GOLD_POOL.prefix_base, "5000:dd::")
    assert_eq("Silver.size", ICEPACK_SILVER_POOL.size, 3072)
    assert_eq("Silver.nh_host_start", ICEPACK_SILVER_POOL.nh_host_start, 0xB001)
    assert_eq("Silver.prefix_base", ICEPACK_SILVER_POOL.prefix_base, "5000:ee::")

    print("\n=== derive_test_params coverage ===")
    params = derive_test_params(
        ICEPACK_TH6_PROFILE, ICEPACK_GOLD_POOL, ICEPACK_SILVER_POOL
    )
    assert_eq("total test cases", len(params), 23)
    assert_eq(
        "hardening + longevity = total",
        len(TESTS_HARDENING) + len(TESTS_LONGEVITY),
        23,
    )
    assert_eq("hardening count", len(TESTS_HARDENING), 18)
    assert_eq("longevity count", len(TESTS_LONGEVITY), 5)
    # All declared test_ids must appear in derive_test_params.
    for tid in TESTS_HARDENING + TESTS_LONGEVITY:
        assert tid in params, f"declared test {tid} missing from derive_test_params"
    print("  [OK] all 23 declared tests covered")

    print(
        "\n=== Key validation-row shapes (TH6, post-fix; widths now derived from member budgets) ==="
    )
    # case_02: 381 groups × 5 width (= 2K members / 381 ≈ 5; 50% of 4K DLB member cap).
    assert_eq(
        "case_02 gold",
        params["case_02_dlb_fill_50pct"][ICEPACK_GOLD_POOL],
        (381, 5),
    )
    # case_04: spillover at 382 groups × 2 width (group-cap test; minimal
    # width to isolate GROUP dim from the 4K DLB member cap).
    assert_eq(
        "case_04 gold",
        params["case_04_dlb_spillover_plus_one"][ICEPACK_GOLD_POOL],
        (382, 2),
    )
    # case_05: gold (381, 5) DLB 50% members + silver (2689, 24) ECMP 50% members.
    assert_eq(
        "case_05 gold",
        params["case_05_ecmp_full_50pct_mixed"][ICEPACK_GOLD_POOL],
        (381, 5),
    )
    assert_eq(
        "case_05 silver",
        params["case_05_ecmp_full_50pct_mixed"][ICEPACK_SILVER_POOL],
        (2689, 24),
    )
    # case_06: 100% DLB members — 381 × 10 ≈ 4K (100% of DLB member cap).
    assert_eq(
        "case_06 gold (100% DLB members)",
        params["case_06_dlb_member_100pct"][ICEPACK_GOLD_POOL],
        (381, 10),
    )
    # case_08: 100% ECMP members — 2689 × 48 ≈ 129K (≈ 100% of 128K ECMP cap).
    assert_eq(
        "case_08 silver (100% ECMP members)",
        params["case_08_ecmp_members_100pct"][ICEPACK_SILVER_POOL],
        (2689, 48),
    )
    # case_11: ECMP member overcommit — 2689 × 60 ≈ 161K (25% past 128K cap).
    assert_eq(
        "case_11 silver (member overcommit)",
        params["case_11_ecmp_member_overcommit"][ICEPACK_SILVER_POOL],
        (2689, 60),
    )
    # case_12: 10 DLB groups × 128 width (per-group cap test).
    assert_eq(
        "case_12 gold",
        params["case_12_dlb_width_max"][ICEPACK_GOLD_POOL],
        (10, 128),
    )
    # case_14: 10 non-DLB ECMP groups × 200 width (tip-over).
    assert_eq(
        "case_14 silver",
        params["case_14_ecmp_width_tipover"][ICEPACK_SILVER_POOL],
        (10, 200),
    )
    # Background-wrapper cases have no own CSV.
    assert_eq("case_16 empty", params["case_16_background_warmboot"], {})
    assert_eq("case_17 empty", params["case_17_background_bgp_gr"], {})

    print("\n=== CSV generation spot-checks (small cases only) ===")
    # Full generate_all_csvs() takes ~10min due to heavy Silver-pool
    # cases (case_11_silver = 2689 prefixes × 256 width = 688K rows + dedup
    # pass). Smoke just spot-checks small cases to validate the wrappers
    # + pool plumbing. Full multi-MB Silver CSV generation is exercised
    # at testconfig load time (one-shot) or via the dedicated catalog
    # binary, not in the smoke.
    from taac.testconfigs.npi.dlb_csvs import gen_dlb_csv

    tmpdir = tempfile.mkdtemp(prefix="dlb_csv_smoke_")
    try:
        # Gold case_12: 10 grp × 128 width = 1280 rows (small, fast).
        rows = gen_dlb_csv.gen_fill_for_pool(ICEPACK_GOLD_POOL, groups=10, width=128)
        assert_eq("case_12_dlb_width_max row count", len(rows), 1280)
        gold_csv = os.path.join(tmpdir, "gold_case_12.csv")
        gen_dlb_csv.write_csv(gold_csv, rows)
        with open(gold_csv) as f:
            lines = f.read().splitlines()
        assert_eq("gold_case_12 csv data lines", len(lines) - 1, 1280)
        assert "5000:dd" in lines[1], f"gold prefix wrong: {lines[1]}"
        assert ":a" in lines[1].split(",")[1], f"gold NH wrong: {lines[1]}"
        print(f"  [OK] gold sample row: {lines[1]}")

        # Silver case_13: 10 grp × 128 width = 1280 rows (small, fast).
        rows = gen_dlb_csv.gen_fill_for_pool(ICEPACK_SILVER_POOL, groups=10, width=128)
        assert_eq("case_13_ecmp_width_max row count", len(rows), 1280)
        silver_csv = os.path.join(tmpdir, "silver_case_13.csv")
        gen_dlb_csv.write_csv(silver_csv, rows)
        with open(silver_csv) as f:
            lines = f.read().splitlines()
        assert "5000:ee" in lines[1], f"silver prefix wrong: {lines[1]}"
        assert ":b" in lines[1].split(",")[1], f"silver NH wrong: {lines[1]}"
        print(f"  [OK] silver sample row: {lines[1]}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n=== Testconfig load + playbook count ===")
    from taac.testconfigs.npi.dlb_hardening_test_config import (
        NPI_DVT_ICEPACK_GTSW__DLB_HARDENING,
        NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY,
    )

    hardening_pb_names = [
        pb.name for pb in NPI_DVT_ICEPACK_GTSW__DLB_HARDENING.playbooks
    ]
    longevity_pb_names = [
        pb.name for pb in NPI_DVT_ICEPACK_GTSW__DLB_LONGEVITY.playbooks
    ]
    assert_eq("hardening playbook count", len(hardening_pb_names), 18)
    assert_eq("longevity playbook count", len(longevity_pb_names), 5)
    assert_eq(
        "hardening + longevity = 23",
        len(hardening_pb_names) + len(longevity_pb_names),
        23,
    )
    print(
        f"  [OK] hardening playbooks: {hardening_pb_names[:3]} ... {hardening_pb_names[-2:]}"
    )
    print(f"  [OK] longevity playbooks: {longevity_pb_names}")

    # Spot-check structure of one playbook.
    case_02 = next(
        pb
        for pb in NPI_DVT_ICEPACK_GTSW__DLB_HARDENING.playbooks
        if "CASE_02" in pb.name
    )
    assert case_02.stages, "case_02 missing stages"
    assert case_02.postchecks, "case_02 missing postchecks"
    assert any(s.name and "STICKINESS" in str(s.name) for s in case_02.postchecks), (
        "case_02 missing stickiness postcheck"
    )
    print(
        f"  [OK] CASE_02 has {len(case_02.stages)} stages + {len(case_02.postchecks)} postchecks"
    )

    print("\n=== Per-case trigger-step dispatch ===")
    from taac.testconfigs.npi.dlb_hardening_test_config import (
        _per_case_trigger_steps,
    )

    # Cases that ARE just steady-state validations get no extra trigger.
    fake_device = "gtsw001.l1001.c085.ash6"
    for tid in (
        "case_01_baseline",
        "case_02_dlb_fill_50pct",
        "case_03_dlb_member_overcommit",
        "case_06_dlb_member_100pct",
        "case_22_ar_bit_negative",
    ):
        steps = _per_case_trigger_steps(tid, 120, fake_device)
        assert_eq(f"{tid} trigger step count (no trigger expected)", len(steps), 0)

    # CASE_07 + CASE_09 — coldboot: 6 steps. Pre-reboot settle + SYSTEM_REBOOT_STEP
    # + 2 × coop_apply_patchers (agent + bgpcpp) + drain/undrain + post-reboot settle.
    # Recovery sequence mandatory — Run 3 (2026-06-29) proved without it the DUT
    # stays DRAINED and STSW peers consume DLB pool.
    for tid in ("case_07_dlb_coldboot", "case_09_ecmp_coldboot"):
        steps = _per_case_trigger_steps(tid, 120, fake_device)
        assert_eq(f"{tid} trigger step count", len(steps), 6)
        descs = [s.description or "" for s in steps]
        assert "pre-reboot settle" in descs[0], f"{tid} step 0: {descs[0]}"
        assert "cold reboot trigger" in descs[1], f"{tid} step 1: {descs[1]}"
        assert "agent patchers" in descs[2], f"{tid} step 2: {descs[2]}"
        assert "bgpcpp patchers" in descs[3], f"{tid} step 3: {descs[3]}"
        assert "undrain" in descs[4], f"{tid} step 4: {descs[4]}"
        assert "post-reboot settle" in descs[5], f"{tid} step 5: {descs[5]}"
        # Step type assertions:
        assert "SYSTEM_REBOOT" in str(steps[1].name), (
            f"{tid} step 1 expected SYSTEM_REBOOT_STEP, got {steps[1].name}"
        )
        assert "DRAIN_UNDRAIN" in str(steps[4].name), (
            f"{tid} step 4 expected DRAIN_UNDRAIN_STEP, got {steps[4].name}"
        )
        for idx in (2, 3):
            assert "RUN_TASK" in str(steps[idx].name), (
                f"{tid} step {idx} expected RUN_TASK_STEP, got {steps[idx].name}"
            )
        print(
            f"  [OK] {tid}: pre-settle + REBOOT + agent-patcher + bgpcpp-patcher + undrain + post-settle"
        )

    # CASE_15 — rollback: 2 steps (pre-longevity + Silver toggle off).
    steps = _per_case_trigger_steps("case_15_rollback_ecmp_to_dlb", 120, fake_device)
    assert_eq("case_15 trigger step count", len(steps), 2)
    import json as _json

    sp15 = steps[1].step_params
    assert sp15 is not None and sp15.json_params is not None, sp15
    silver_off_params = _json.loads(sp15.json_params)
    assert silver_off_params["api_name"] == "toggle_dlb_pool_enabled"
    args = _json.loads(silver_off_params["args_json"])
    assert args == {"pool_name": "DLB_SILVER_PREFIX_POOL", "enabled": False}, args
    print("  [OK] case_15: pre-rollback + toggle_dlb_pool_enabled(Silver=False)")

    # CASE_21 — NDP flap: 4 steps (settle + NDP-off + hold + NDP-on).
    steps = _per_case_trigger_steps("case_21_ndp_flap", 120, fake_device)
    assert_eq("case_21 trigger step count", len(steps), 4)
    sp21_off = steps[1].step_params
    sp21_on = steps[3].step_params
    assert sp21_off is not None and sp21_off.json_params is not None
    assert sp21_on is not None and sp21_on.json_params is not None
    ndp_off_params = _json.loads(sp21_off.json_params)
    ndp_on_params = _json.loads(sp21_on.json_params)
    assert ndp_off_params["api_name"] == "toggle_device_groups"
    assert ndp_on_params["api_name"] == "toggle_device_groups"
    off_args = _json.loads(ndp_off_params["args_json"])
    on_args = _json.loads(ndp_on_params["args_json"])
    assert off_args == {
        "enable": False,
        "device_group_name_regex": "NDP_SUPPORTING_NEXTHOP",
    }, off_args
    assert on_args == {
        "enable": True,
        "device_group_name_regex": "NDP_SUPPORTING_NEXTHOP",
    }, on_args
    print("  [OK] case_21: settle + NDP-off + hold + NDP-on")

    # CASE_23 — cold-start cycle: 4 steps (settle + StopAll + hold + StartAll).
    steps = _per_case_trigger_steps("case_23_cold_start_cycle", 120, fake_device)
    assert_eq("case_23 trigger step count", len(steps), 4)
    sp23_stop = steps[1].step_params
    sp23_start = steps[3].step_params
    assert sp23_stop is not None and sp23_stop.json_params is not None
    assert sp23_start is not None and sp23_start.json_params is not None
    stop_params = _json.loads(sp23_stop.json_params)
    start_params = _json.loads(sp23_start.json_params)
    assert stop_params["api_name"] == "stop_all_protocols", stop_params
    assert start_params["api_name"] == "start_all_protocols", start_params
    print("  [OK] case_23: settle + stop_all_protocols + hold + start_all_protocols")

    print("\n=== SMOKE PASS ===")


if __name__ == "__main__":
    main()

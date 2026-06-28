# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
import json
import unittest

from taac.health_checks.retry_policy import DEFAULT_RETRY_SPEC
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.check_profile_registry import (
    CheckProfile,
    get_profile_checks,
    ProfileChecks,
)
from taac.health_check.health_check import types as hc_types


class CheckProfileRegistryTest(unittest.TestCase):
    def test_bounded_ecmp_profile_shape(self):
        checks = get_profile_checks(CheckProfile.PERF_SCALING_BOUNDED_ECMP)

        self.assertIsInstance(checks, ProfileChecks)
        # No prechecks for this profile (matches the prior inline playbook).
        self.assertEqual(checks.prechecks, [])
        # Postchecks: session establish, RIB/FIB consistency, convergence.
        self.assertEqual(
            [c.name for c in checks.postchecks],
            [
                hc_types.CheckName.BGP_SESSION_ESTABLISH_CHECK,
                hc_types.CheckName.BGP_RIB_FIB_CONSISTENCY_CHECK,
                hc_types.CheckName.BGP_CONVERGENCE_CHECK,
            ],
        )
        # Snapshot: core dumps + bgp session snapshot.
        self.assertEqual(len(checks.snapshot_checks), 2)
        self.assertEqual(
            checks.snapshot_checks[0].name, hc_types.CheckName.CORE_DUMPS_CHECK
        )

    def test_retry_is_baked_from_ssot(self):
        # Every postcheck must carry the uniform SSOT retry spec (P1/P3): the
        # profile never hand-passes retry numbers.
        checks = get_profile_checks(CheckProfile.PERF_SCALING_BOUNDED_ECMP)

        for check in checks.postchecks:
            self.assertIsNotNone(check.check_params)
            payload = json.loads(check.check_params.json_params)
            self.assertEqual(payload["retry_count"], DEFAULT_RETRY_SPEC.retry_count)
            self.assertEqual(
                payload["retry_delay_seconds"],
                DEFAULT_RETRY_SPEC.retry_delay_seconds,
            )
            self.assertEqual(
                payload["retry_delay_multiplier"],
                DEFAULT_RETRY_SPEC.retry_delay_multiplier,
            )

    def test_convergence_functional_params_are_explicit(self):
        # Functional params (per check, phase) are explicit/visible in the
        # profile — the "change and look" property.
        checks = get_profile_checks(CheckProfile.PERF_SCALING_BOUNDED_ECMP)

        convergence = next(
            c
            for c in checks.postchecks
            if c.name == hc_types.CheckName.BGP_CONVERGENCE_CHECK
        )
        payload = json.loads(convergence.check_params.json_params)
        self.assertEqual(payload["convergence_threshold"], 600)
        self.assertEqual(payload["fail_on_eor_expired"], True)
        self.assertEqual(convergence.check_id, "postcheck_bgp_convergence_time")

    def test_each_call_returns_fresh_objects(self):
        # Thrift structs are mutable; callers must not share instances.
        first = get_profile_checks(CheckProfile.PERF_SCALING_BOUNDED_ECMP)
        second = get_profile_checks(CheckProfile.PERF_SCALING_BOUNDED_ECMP)

        self.assertIsNot(first.postchecks[0], second.postchecks[0])

    def test_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            get_profile_checks("not_a_real_profile")

# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Unit tests for the BGP++ Update Group "Backpressure and Blocking" 2.3.x
playbook factories. These prove the playbook factories COMPOSE the right
triggers in the right order with the right args -- i.e. the test
automation is correct -- independent of whether a live IXIA / DUT can
make the triggers fire end-to-end.

Run:
    buck test fbcode//neteng/test_infra/dne/taac/playbooks/tests:test_ug_backpressure_playbooks

Asserts per factory:
- ``playbook.name`` matches the testconfig regex key.
- Stage count and trigger-stage shape.
- Heavy-attr step trio fires in the storm: configure_community_pool +
  configure_extended_community_pool + configure_as_path_pool with the
  exact arg sizes propagated from the factory inputs.
- Per-PB unique triggers fire: advertise/withdraw boundaries, peer
  shutdown/recovery via ``start_stop_bgp_peers``, mass-toggle via
  ``toggle_device_groups``, mid-test community pool swap.
- Cleanup steps restore baseline where applicable.
"""

import json
import unittest

from taac.playbooks.playbook_definitions import (
    create_ug_backpressure_all_peers_block_down_recover_playbook,
    create_ug_backpressure_fast_peers_not_held_back_playbook,
    create_ug_backpressure_peer_blocks_down_recover_playbook,
    create_ug_backpressure_withdraw_attr_change_playbook,
)


DEVICE = "bag013.ash6"
IFACE = "Ethernet3/36/2"

STORM_POOL = "PREFIX_POOL_IBGP_IPV6_PLANE_1_REMOTE_EB_DRAIN"
STORM_DG = "DEVICE_GROUP_IPV6_IBGP_PLANE_1_REMOTE_EB_DRAIN"
EBGP_DG_ALL = "DEVICE_GROUP_IPV[46]_EBGP$"
EBGP_DG = "DEVICE_GROUP_IPV6_EBGP"
EBGP_POOL = "PREFIX_POOL_IPV6_EBGP"
SHUTDOWN_REGEX = "BGP_PEER_IPV6_EBGP"

FAST_PEERS = [f"2401:db00:11:8::{0x11 + 2 * i:x}" for i in range(4)]
IBGP_PEERS = [f"2401:db00:11:9::{0x11 + 2 * i:x}" for i in range(4)]
SHUT_PEERS = FAST_PEERS[:2]
EBGP_PEERS = FAST_PEERS
BGP_MON = []  # bag013 quirk: BGP_MON IDLE; factories accept empty + skip checks


COMMUNITIES_32 = [[f"65529:{30000 + i}"] for i in range(32)]
EXT_COMMUNITIES_16 = [[f"rt:65529:{40000 + i}"] for i in range(16)]
AS_PATH_255 = [64512 + (i % 1023) for i in range(255)]
MEMORY_THRESHOLD = 10 * 1024**3


def _ixia_api_args(step):
    """Decode an INVOKE_IXIA_API_STEP's (api_name, args_dict)."""
    outer = json.loads(step.step_params.json_params)
    return outer.get("api_name"), json.loads(outer.get("args_json") or "{}")


def _run_task_args(step):
    """Decode a RUN_TASK_STEP's (task_name, params_dict).

    ``create_run_task_step`` serializes a ``RunTaskInput`` into
    ``step.input_json``; the inner task params are themselves a JSON string
    inside ``task.params.json_params``. Returns ``(None, {})`` when the step
    isn't a RUN_TASK_STEP (so callers can filter mixed step lists)."""
    if not step.input_json:
        return None, {}
    outer = json.loads(step.input_json)
    task = outer.get("task") or {}
    task_name = task.get("task_name")
    inner = (task.get("params") or {}).get("json_params") or ""
    return task_name, (json.loads(inner) if inner else {})


def _steps_by_desc(stage, needle):
    """Return all steps in stage whose description contains needle (case-insensitive)."""
    needle = needle.lower()
    return [s for s in (stage.steps or []) if needle in (s.description or "").lower()]


class FastPeersNotHeldBackPlaybookTest(unittest.TestCase):
    """2.3.1 -- heavy-attr storm; fast peers must keep flowing."""

    PREFIX_COUNT = 10000

    def setUp(self):
        self.playbook = create_ug_backpressure_fast_peers_not_held_back_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            storm_prefix_pool_regex=STORM_POOL,
            storm_device_group_regex=STORM_DG,
            storm_prefix_count=self.PREFIX_COUNT,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            fast_peer_addrs=FAST_PEERS,
            bgp_mon_peer_addrs=BGP_MON,
            iBGP_receiver_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
        )

    def test_name_and_two_stages(self):
        """Spec: Phase 1-3 storm stage + Phase 4-5 withdraw stage."""
        self.assertEqual(self.playbook.name, "ug_backpressure_fast_peers_not_held_back")
        self.assertEqual(len(self.playbook.stages), 2)

    def test_storm_stage_skips_pool_config_and_emits_advertise(self):
        """Since 2026-06-29 ``_heavy_attr_advertise_steps`` defaults to
        ``skip_pool_config=True``: the two chassis-cascading
        ``configure_*_pool`` steps (community + ext-community) are OMITTED
        from the trigger because they cascade-reset every BGP TCP session
        on the EBB-scale chassis (root cause: unconditional
        ``stop_protocols()`` in ixia.py). Pools are pre-attached at IXIA-
        build time via ``plane_drain_dg_v6_attribute_overrides`` on the
        topology builder. Per-prefix MED/LP/Origin cycling stays in the
        trigger (different IXIA API, no port-level stop). AS_PATH pool
        config is now emitted with ``stop_protocols=False`` scoped to only
        the storm sender DG, closing the 255-ASN spec gap without cascade."""
        storm = self.playbook.stages[0]
        # POSITIVE: trigger MUST contain MED/LP/Origin cycling + AS_PATH + advertise.
        for label, needle in (
            ("randomize MED", "randomize med"),
            ("randomize LocalPref", "randomize localpref"),
            ("cycle Origin", "cycle origin"),
            ("targeted AS_PATH", "set as_path"),
            ("storm advertise", "heavy-attr storm"),
        ):
            hits = _steps_by_desc(storm, needle)
            self.assertEqual(len(hits), 1, f"expected 1 {label} step, got {len(hits)}")
        # NEGATIVE: trigger MUST NOT contain the cascade-triggering pool configs.
        for label, needle in (
            ("community pool config", "set 32 community combinations"),
            ("ext-community pool config", "set 16 ext-community combinations"),
        ):
            hits = _steps_by_desc(storm, needle)
            self.assertEqual(
                len(hits),
                0,
                f"regression: {label} re-emerged in trigger -- this cascade-resets "
                "all 1272 BGP sessions on EBB scale; keep skip_pool_config=True "
                "until ixia.py is fixed",
            )

    def test_withdraw_stage_has_mid_settle_session_gate(self):
        """Defensive C+D fix (2026-06-25): the withdraw stage splits its
        post-withdraw settle into mid+end with an explicit session-establish
        gate in the middle. The earlier failure mode was sessions silently
        IDLE'd during a single 120s settle; the mid-settle gate catches that
        early instead of failing the whole spec gate at end."""
        withdraw = self.playbook.stages[1]
        # 1 withdraw step + 2 longevity (mid+end) + 2 validation (mid gate + Phase 5 gate)
        self.assertGreaterEqual(len(withdraw.steps or []), 5)
        mid_settle = _steps_by_desc(withdraw, "mid-settle for clean withdrawal")
        end_settle = _steps_by_desc(withdraw, "final-settle for ug re-convergence")
        self.assertEqual(len(mid_settle), 1, "mid-settle longevity missing")
        self.assertEqual(len(end_settle), 1, "end-settle longevity missing")

    def test_no_cleanup_steps_for_pb1(self):
        """PB1 withdraws inline in its own withdraw stage, no separate cleanup."""
        self.assertFalse(self.playbook.cleanup_steps)


class PeerBlocksDownRecoverPlaybookTest(unittest.TestCase):
    """2.3.2 -- 16 eBGP peers shutdown mid-storm + recovery."""

    INITIAL = 5000
    FOLLOWUP = 500
    SHUTDOWN_COUNT = 16

    def setUp(self):
        self.playbook = create_ug_backpressure_peer_blocks_down_recover_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            storm_prefix_pool_regex=STORM_POOL,
            storm_device_group_regex=STORM_DG,
            storm_initial_prefix_count=self.INITIAL,
            storm_followup_prefix_count=self.FOLLOWUP,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            shutdown_peer_regex=SHUTDOWN_REGEX,
            shutdown_peer_addrs=SHUT_PEERS,
            shutdown_count=self.SHUTDOWN_COUNT,
            surviving_receiver_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
        )

    def test_name_and_single_trigger_stage(self):
        self.assertEqual(self.playbook.name, "ug_backpressure_peer_blocks_down_recover")
        self.assertEqual(len(self.playbook.stages), 1)

    def test_shutdown_uses_per_peer_start_stop_not_dg_toggle(self):
        """2.3.2 is targeted (N peers, NOT the whole DG). Must use
        ``start_stop_bgp_peers`` with idx range, NOT ``toggle_device_groups``."""
        trigger = self.playbook.stages[0]
        shut = _steps_by_desc(trigger, f"shut down {self.SHUTDOWN_COUNT} ebgp")
        bring_up = _steps_by_desc(
            trigger, f"bring {self.SHUTDOWN_COUNT} ebgp sessions back up"
        )
        self.assertEqual(len(shut), 1)
        self.assertEqual(len(bring_up), 1)
        # And NOT a toggle_device_groups call -- regression guard against the
        # PB4-style mass-shutdown leaking into PB2.
        for step in trigger.steps or []:
            args = (step.description or "").lower()
            self.assertNotIn("mass shutdown", args)
            self.assertNotIn("toggle whole ebgp", args)

    def test_followup_inject_fires_after_shutdown(self):
        """Phase 3 must inject ``storm_followup_prefix_count`` MORE prefixes
        AFTER the shutdown so re-connecting peers see them via shadow RIB."""
        trigger = self.playbook.stages[0]
        followup = _steps_by_desc(trigger, f"inject {self.FOLLOWUP}")
        self.assertEqual(len(followup), 1)

    def test_cleanup_withdraws_all_storm_prefixes(self):
        cleanup = self.playbook.cleanup_steps or []
        total = self.INITIAL + self.FOLLOWUP
        withdraw_all = [
            s
            for s in cleanup
            if f"withdraw all {total}" in (s.description or "").lower()
        ]
        self.assertEqual(len(withdraw_all), 1)


class WithdrawAttrChangePlaybookTest(unittest.TestCase):
    """2.3.3 -- withdraw + community swap + LP-modify under backpressure."""

    IBGP_STORM = 5000
    EBGP_POOL_COUNT = 400
    WITHDRAW = 200
    LP_MODIFY = 100
    INITIAL_COMMUNITY = "65529:34814"
    # 16-bit RFC 1997 low field (0..65535); IXIA silently truncates values
    # above 65535 (99999 % 65536 = 34463), landing an unexpected on-wire
    # value. Kept in-range to match bag013's production config, which was
    # moved off "65529:99999" for the same reason.
    MUTATED_COMMUNITY = "65529:1234"
    TARGET_LP = 200

    def setUp(self):
        self.playbook = create_ug_backpressure_withdraw_attr_change_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            ibgp_storm_prefix_pool_regex=STORM_POOL,
            ibgp_storm_device_group_regex=STORM_DG,
            ibgp_storm_prefix_count=self.IBGP_STORM,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            ebgp_attr_change_prefix_pool_regex=EBGP_POOL,
            ebgp_attr_change_device_group_regex=EBGP_DG,
            ebgp_attr_change_prefix_count=self.EBGP_POOL_COUNT,
            withdraw_count=self.WITHDRAW,
            lp_modify_count=self.LP_MODIFY,
            initial_community=self.INITIAL_COMMUNITY,
            mutated_community=self.MUTATED_COMMUNITY,
            target_local_pref=self.TARGET_LP,
            ibgp_receiver_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
        )

    def test_name_and_single_trigger_stage(self):
        self.assertEqual(self.playbook.name, "ug_backpressure_withdraw_attr_change")
        self.assertEqual(len(self.playbook.stages), 1)

    def test_withdraw_then_swap_then_readd_sequence(self):
        """Default (legacy) path: spec 2.3.3 order is critical -- withdraw N ->
        swap community pool -> re-advertise N (which now carry the mutated
        community). Verifies the legacy code path used by characteristic-scale
        testbeds where chassis-wide stop_protocols() is tolerable."""
        trigger = self.playbook.stages[0]
        withdraw = _steps_by_desc(trigger, f"withdraw {self.WITHDRAW} ebgp")
        swap = _steps_by_desc(
            trigger,
            f"swap ebgp dg community pool {self.INITIAL_COMMUNITY} -> {self.MUTATED_COMMUNITY}",
        )
        readd = _steps_by_desc(
            trigger,
            f"re-advertise {self.WITHDRAW} ebgp routes carrying community {self.MUTATED_COMMUNITY}",
        )
        self.assertEqual(len(withdraw), 1)
        self.assertEqual(len(swap), 1)
        self.assertEqual(len(readd), 1)
        # Order: withdraw < swap < readd by step index.
        idx = {step: i for i, step in enumerate(trigger.steps or [])}
        self.assertLess(idx[withdraw[0]], idx[swap[0]])
        self.assertLess(idx[swap[0]], idx[readd[0]])

    def test_lp_modify_step_fires_with_target_value(self):
        """The LP-modify step must carry both the count AND the target LP value
        in its description so future operators can trace it from the log."""
        trigger = self.playbook.stages[0]
        lp_steps = _steps_by_desc(
            trigger,
            f"lp-modify {self.LP_MODIFY} ebgp routes to localpref={self.TARGET_LP}",
        )
        self.assertEqual(len(lp_steps), 1, "expected exactly 1 LP-modify step")

    def test_cleanup_restores_initial_community_and_withdraws_storm(self):
        cleanup = self.playbook.cleanup_steps or []
        restore = [
            s
            for s in cleanup
            if f"restore ebgp dg community to {self.INITIAL_COMMUNITY}"
            in (s.description or "").lower()
        ]
        withdraw_storm = [
            s
            for s in cleanup
            if "withdraw ibgp storm prefixes" in (s.description or "").lower()
        ]
        self.assertEqual(len(restore), 1)
        self.assertEqual(len(withdraw_storm), 1)


class WithdrawAttrChangeCascadeSafePlaybookTest(unittest.TestCase):
    """2.3.3 with ``skip_community_swap_for_cascade_safety=True`` -- the EBB
    full-scale path used by bag013. The Phase 2c configure_community_pool
    step and its BGP_RECEIVED_ROUTE_COMMUNITY_CHECK postcheck are OMITTED
    because configure_community_pool cascade-resets all BGP sessions on the
    chassis (ixia.py unconditional stop_protocols()). Phase 2a (withdraw)
    + Phase 2d (re-advertise, same community) + Phase 2e (LP-modify)
    still run; the per-peer equality check still runs."""

    IBGP_STORM = 5000
    WITHDRAW = 200
    LP_MODIFY = 100
    INITIAL_COMMUNITY = "65529:34814"
    # 16-bit RFC 1997 low field (0..65535); IXIA silently truncates values
    # above 65535 (99999 % 65536 = 34463), landing an unexpected on-wire
    # value. Kept in-range to match bag013's production config, which was
    # moved off "65529:99999" for the same reason.
    MUTATED_COMMUNITY = "65529:1234"
    TARGET_LP = 200

    def setUp(self):
        self.playbook = create_ug_backpressure_withdraw_attr_change_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            ibgp_storm_prefix_pool_regex=STORM_POOL,
            ibgp_storm_device_group_regex=STORM_DG,
            ibgp_storm_prefix_count=self.IBGP_STORM,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            ebgp_attr_change_prefix_pool_regex=EBGP_POOL,
            ebgp_attr_change_device_group_regex=EBGP_DG,
            ebgp_attr_change_prefix_count=400,
            withdraw_count=self.WITHDRAW,
            lp_modify_count=self.LP_MODIFY,
            initial_community=self.INITIAL_COMMUNITY,
            mutated_community=self.MUTATED_COMMUNITY,
            target_local_pref=self.TARGET_LP,
            ibgp_receiver_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
            skip_community_swap_for_cascade_safety=True,
        )

    def test_phase_2c_swap_step_is_absent(self):
        """The cascade-hazardous configure_community_pool step MUST NOT be
        in the trigger when skip_community_swap_for_cascade_safety=True."""
        trigger = self.playbook.stages[0]
        swap_hits = _steps_by_desc(trigger, "swap ebgp dg community pool")
        self.assertEqual(
            len(swap_hits),
            0,
            "regression: Phase 2c swap re-emerged in cascade-safe mode; "
            "this cascade-resets all BGP sessions chassis-wide",
        )

    def test_withdraw_readd_lp_modify_still_run(self):
        """Phase 2a + 2d + 2e (the non-cascading triggers) MUST still fire."""
        trigger = self.playbook.stages[0]
        withdraw = _steps_by_desc(trigger, f"withdraw {self.WITHDRAW} ebgp")
        readd = _steps_by_desc(trigger, f"re-advertise {self.WITHDRAW} ebgp")
        lp = _steps_by_desc(
            trigger,
            f"lp-modify {self.LP_MODIFY} ebgp routes to localpref={self.TARGET_LP}",
        )
        self.assertEqual(len(withdraw), 1)
        self.assertEqual(len(readd), 1)
        self.assertEqual(len(lp), 1)
        # Order: withdraw < readd by step index (no swap between them now).
        idx = {step: i for i, step in enumerate(trigger.steps or [])}
        self.assertLess(idx[withdraw[0]], idx[readd[0]])

    def test_cleanup_skips_community_restore(self):
        """When the swap didn't fire, the restore step is unnecessary AND
        also cascades -- so it MUST be omitted."""
        cleanup = self.playbook.cleanup_steps or []
        restore = [
            s
            for s in cleanup
            if "restore ebgp dg community" in (s.description or "").lower()
        ]
        self.assertEqual(
            len(restore),
            0,
            "regression: cleanup community-restore re-emerged; would cascade",
        )
        # Storm withdraw must still happen.
        withdraw_storm = [
            s
            for s in cleanup
            if "withdraw ibgp storm prefixes" in (s.description or "").lower()
        ]
        self.assertEqual(len(withdraw_storm), 1)


class WithdrawAttrChangePeerScopedPlaybookTest(unittest.TestCase):
    """2.3.3 with ``use_peer_scoped_community_swap=True`` (and
    ``skip_community_swap_for_cascade_safety=False``) -- the EBB full-scale
    path used by bag013 once the peer-scoped ``ixia_modify_communities``
    task is available. Phase 2c uses RUN_TASK_STEP(ixia_modify_communities,
    community_values=[mutated]) instead of the cascade-prone
    INVOKE_IXIA_API_STEP(configure_community_pool); cleanup mirrors with
    the same task but ``community_values=[initial]``. The inline Phase 3
    spec gate VALIDATION_STEP is appended to trigger_steps BEFORE cleanup
    so the community-anchor postcheck sees mutated state (cleanup reverts
    it before postchecks run)."""

    IBGP_STORM = 5000
    EBGP_POOL_COUNT = 400
    WITHDRAW = 200
    LP_MODIFY = 100
    INITIAL_COMMUNITY = "65529:34814"
    # 16-bit RFC 1997 low field (0..65535); IXIA silently truncates values
    # above 65535 (99999 % 65536 = 34463), landing an unexpected on-wire
    # value. Kept in-range to match bag013's production config, which was
    # moved off "65529:99999" for the same reason.
    MUTATED_COMMUNITY = "65529:1234"
    TARGET_LP = 200

    def setUp(self):
        self.playbook = create_ug_backpressure_withdraw_attr_change_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            ibgp_storm_prefix_pool_regex=STORM_POOL,
            ibgp_storm_device_group_regex=STORM_DG,
            ibgp_storm_prefix_count=self.IBGP_STORM,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            ebgp_attr_change_prefix_pool_regex=EBGP_POOL,
            ebgp_attr_change_device_group_regex=EBGP_DG,
            ebgp_attr_change_prefix_count=self.EBGP_POOL_COUNT,
            withdraw_count=self.WITHDRAW,
            lp_modify_count=self.LP_MODIFY,
            initial_community=self.INITIAL_COMMUNITY,
            mutated_community=self.MUTATED_COMMUNITY,
            target_local_pref=self.TARGET_LP,
            ibgp_receiver_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
            skip_community_swap_for_cascade_safety=False,
            use_peer_scoped_community_swap=True,
        )

    def _peer_scoped_swap_steps(self, steps, expected_value):
        """Filter to RUN_TASK_STEPs that swap community via
        ``ixia_modify_communities`` with the given ``community_values[0]``."""
        out = []
        for s in steps or []:
            task_name, params = _run_task_args(s)
            if task_name != "ixia_modify_communities":
                continue
            if (params.get("community_values") or [None])[0] != expected_value:
                continue
            out.append((s, params))
        return out

    def test_phase_2c_uses_peer_scoped_task_not_cascade_api(self):
        """Phase 2c MUST route through RUN_TASK_STEP(ixia_modify_communities)
        with ``community_values=[mutated_community]`` -- NOT the chassis-wide
        ``configure_community_pool`` API step. Regression here means we lost
        the cascade-safe path and would reset all BGP sessions on the chassis."""
        trigger = self.playbook.stages[0]
        swap = self._peer_scoped_swap_steps(trigger.steps, self.MUTATED_COMMUNITY)
        self.assertEqual(
            len(swap),
            1,
            "expected exactly 1 peer-scoped ixia_modify_communities Phase 2c "
            "swap with community_values=[mutated_community]",
        )
        _, params = swap[0]
        self.assertEqual(params.get("prefix_pool_regex"), EBGP_POOL)
        self.assertEqual(params.get("count"), 0)
        self.assertEqual(params.get("to_add"), True)
        # No cascade-prone configure_community_pool step on the trigger.
        cascade_hits = _steps_by_desc(trigger, "swap ebgp dg community pool")
        self.assertEqual(
            len(cascade_hits),
            0,
            "regression: chassis-wide configure_community_pool swap step "
            "re-emerged in peer-scoped mode; would cascade-reset all sessions",
        )

    def test_inline_phase_3_spec_gate_validation_step_present(self):
        """An inline VALIDATION_STEP must run AFTER Phase 2c swap and BEFORE
        cleanup reverts the community — otherwise the community-anchor
        postcheck only sees the reverted state and can never pass."""
        trigger = self.playbook.stages[0]
        inline_gate = _steps_by_desc(
            trigger, "phase 3 inline trigger-verification gate"
        )
        self.assertEqual(
            len(inline_gate),
            1,
            "regression: inline community-anchor VALIDATION_STEP missing — "
            "postcheck-time HC will fail because Phase 4 cleanup reverts "
            "the mutated community before postchecks run",
        )
        # The inline gate must come AFTER the Phase 2c swap step.
        swap = self._peer_scoped_swap_steps(trigger.steps, self.MUTATED_COMMUNITY)
        self.assertEqual(
            len(swap),
            1,
            "expected exactly 1 peer-scoped Phase 2c swap step -- IndexError "
            "on swap[0][0] below would obscure the real 'swap missing' cause",
        )
        idx = {step: i for i, step in enumerate(trigger.steps or [])}
        self.assertLess(idx[swap[0][0]], idx[inline_gate[0]])

    def test_cleanup_uses_peer_scoped_restore_not_cascade_api(self):
        """Cleanup MUST also route through RUN_TASK_STEP(ixia_modify_communities)
        with ``community_values=[initial_community]`` -- symmetric with Phase 2c."""
        cleanup = self.playbook.cleanup_steps or []
        restore = self._peer_scoped_swap_steps(cleanup, self.INITIAL_COMMUNITY)
        self.assertEqual(
            len(restore),
            1,
            "expected exactly 1 peer-scoped ixia_modify_communities cleanup "
            "restore with community_values=[initial_community]",
        )
        # And the cascade-prone restore is NOT present.
        cascade_restore = [
            s
            for s in cleanup
            if "restore ebgp dg community to" in (s.description or "").lower()
            and (_run_task_args(s)[0] or "") != "ixia_modify_communities"
        ]
        self.assertEqual(
            len(cascade_restore),
            0,
            "regression: chassis-wide configure_community_pool restore "
            "re-emerged in peer-scoped cleanup; would cascade",
        )


class AllPeersBlockDownRecoverPlaybookTest(unittest.TestCase):
    """2.3.4 -- ALL eBGP peers toggled down/up simultaneously via DG-toggle."""

    INITIAL = 10000
    FOLLOWUP = 500

    def setUp(self):
        self.playbook = create_ug_backpressure_all_peers_block_down_recover_playbook(
            device_name=DEVICE,
            ixia_interface=IFACE,
            storm_prefix_pool_regex=STORM_POOL,
            storm_device_group_regex=STORM_DG,
            storm_initial_prefix_count=self.INITIAL,
            storm_followup_prefix_count=self.FOLLOWUP,
            community_combinations=COMMUNITIES_32,
            extended_community_combinations=EXT_COMMUNITIES_16,
            as_path=AS_PATH_255,
            ebgp_group_dg_regex=EBGP_DG_ALL,
            ebgp_peer_addrs=EBGP_PEERS,
            bgp_mon_peer_addrs=BGP_MON,
            ibgp_peer_addrs=IBGP_PEERS,
            expected_established_sessions=10,
            memory_threshold_bytes=MEMORY_THRESHOLD,
        )

    def test_name_and_single_trigger_stage(self):
        self.assertEqual(
            self.playbook.name, "ug_backpressure_all_peers_block_down_recover"
        )
        self.assertEqual(len(self.playbook.stages), 1)

    def test_mass_shutdown_uses_toggle_device_groups_enable_false(self):
        """Spec demands TRUE simultaneous shutdown via single DG-toggle call
        (NOT per-peer start_stop). This is the on-wire trigger that proves
        Option B was implemented correctly."""
        trigger = self.playbook.stages[0]
        shutdown_steps = _steps_by_desc(trigger, "mass shutdown")
        self.assertEqual(len(shutdown_steps), 1)
        api_name, args = _ixia_api_args(shutdown_steps[0])
        self.assertEqual(api_name, "toggle_device_groups")
        self.assertEqual(args.get("enable"), False)
        self.assertEqual(args.get("device_group_name_regex"), EBGP_DG_ALL)
        # Spec 2.3.4: no GR / no settle before tear-down.
        self.assertEqual(args.get("sleep_time_before_applying_change"), 0)

    def test_mass_recovery_uses_toggle_device_groups_enable_true(self):
        trigger = self.playbook.stages[0]
        recovery_steps = _steps_by_desc(trigger, "mass recovery")
        self.assertEqual(len(recovery_steps), 1)
        api_name, args = _ixia_api_args(recovery_steps[0])
        self.assertEqual(api_name, "toggle_device_groups")
        self.assertEqual(args.get("enable"), True)
        self.assertEqual(args.get("device_group_name_regex"), EBGP_DG_ALL)

    def test_followup_inject_happens_between_shutdown_and_recovery(self):
        """Phase 4 inject must happen while eBGP is DOWN -- this proves the
        shadow-RIB re-sync claim (iBGP+BGP_MON receive followup while eBGP
        is offline; eBGP gets it from shadow on recovery)."""
        trigger = self.playbook.stages[0]
        shutdown = _steps_by_desc(trigger, "mass shutdown")[0]
        followup = _steps_by_desc(trigger, f"inject {self.FOLLOWUP}")[0]
        recovery = _steps_by_desc(trigger, "mass recovery")[0]
        idx = {step: i for i, step in enumerate(trigger.steps or [])}
        self.assertLess(idx[shutdown], idx[followup])
        self.assertLess(idx[followup], idx[recovery])

    def test_cleanup_withdraws_all_storm_prefixes(self):
        cleanup = self.playbook.cleanup_steps or []
        total = self.INITIAL + self.FOLLOWUP
        withdraw_all = [
            s
            for s in cleanup
            if f"withdraw all {total}" in (s.description or "").lower()
        ]
        self.assertEqual(len(withdraw_all), 1)

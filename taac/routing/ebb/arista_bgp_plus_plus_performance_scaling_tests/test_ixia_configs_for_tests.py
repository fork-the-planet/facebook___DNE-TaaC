# pyre-unsafe

import unittest

from ixia.ixia import types as ixia_types
from taac.routing.ebb.arista_bgp_plus_plus_performance_scaling_tests.ixia_configs_for_tests import (
    create_ebb_performance_scale_basic_port_configs,
)

_COMMON_KWARGS = {
    "device_name": "bag010.ash6",
    "ixia_interface_mimic_ebgp": "eth1",
    "ixia_interface_mimic_ibgp": "eth2",
    "ebgp_peer_count_v6": 1,
    "ebgp_peer_count_v4": 1,
    "ibgp_peer_count_v6": 1,
    "ibgp_peer_count_v4": 1,
    "ebgp_remote_as": 65334,
    "ibgp_remote_as": 64981,
    "ixia_ebgp_ic_parent_network_v6": "2401:db00:eef0:a00",
    "ixia_ebgp_ic_parent_network_v4": "10.163.28",
    "ixia_ibgp_ic_parent_network_v6": "2401:db00:eef0:a01",
    "ixia_ibgp_ic_parent_network_v4": "10.163.29",
}


def _ebgp_import_params(configs):
    params = []
    for port in configs:
        for dg in port.device_group_configs or []:
            if "EBGP" not in dg.device_group_name:
                continue
            for bgp_cfg in (dg.v4_bgp_config, dg.v6_bgp_config):
                if bgp_cfg is None:
                    continue
                params.extend(bgp_cfg.import_bgp_routes_params_list or [])
    return params


class EbgpNextHopSelfTest(unittest.TestCase):
    """The eBGP next-hop must be the connected tester IP so the DUT can resolve
    it. The route property NextHopType (SAME_AS_LOCAL_IP) is the authoritative
    knob (it otherwise defaults to MANUALLY and pins the next-hop to the CSV
    value); the import-time modification type stays PRESERVE_FROM_FILE."""

    def test_next_hop_self_sets_same_as_local_ip(self) -> None:
        params = _ebgp_import_params(
            create_ebb_performance_scale_basic_port_configs(
                ebgp_next_hop_self=True, **_COMMON_KWARGS
            )
        )
        self.assertEqual(len(params), 2)  # one v4, one v6 eBGP pool
        for p in params:
            self.assertEqual(
                p.set_next_hop_type,
                ixia_types.SetNextHopType.SAME_AS_LOCAL_IP,
            )
            # OVER_WRITE_TESTERS_ADDRESS was dropped as redundant -- NextHopType
            # does the work, so the modification type stays PRESERVE_FROM_FILE.
            self.assertEqual(
                p.bgp_next_hop_modification_type,
                ixia_types.BgpNextHopModificationType.PRESERVE_FROM_FILE,
            )

    def test_default_leaves_next_hop_type_unset(self) -> None:
        # Existing PRESERVE_FROM_FILE callers must stay byte-identical: the
        # field is left unset (runtime defaults it to MANUALLY).
        params = _ebgp_import_params(
            create_ebb_performance_scale_basic_port_configs(**_COMMON_KWARGS)
        )
        self.assertEqual(len(params), 2)
        for p in params:
            self.assertIsNone(p.set_next_hop_type)
            self.assertEqual(
                p.bgp_next_hop_modification_type,
                ixia_types.BgpNextHopModificationType.PRESERVE_FROM_FILE,
            )


def _ebgp_community_configs(configs):
    community_cfgs = []
    for p in _ebgp_import_params(configs):
        for attr in p.bgp_attribute_configs or []:
            if attr.attribute == ixia_types.BgpAttribute.COMMUNITIES:
                community_cfgs.append(attr)
    return community_cfgs


class EbgpFixedCommunitiesTest(unittest.TestCase):
    """Perf-scaling tags every eBGP route with a single clean community so it
    passes the DUT's EB-FA-IN inbound allowlist and avoids confusing
    named-community noise; other callers keep the CSV distribution."""

    def test_fixed_communities_use_inline_value_lists(self) -> None:
        cfgs = _ebgp_community_configs(
            create_ebb_performance_scale_basic_port_configs(
                ebgp_fixed_communities=["65529:39744"], **_COMMON_KWARGS
            )
        )
        self.assertEqual(len(cfgs), 2)  # v4 + v6 eBGP pools
        for c in cfgs:
            self.assertEqual(c.value_lists, [["65529:39744"]])
            self.assertIsNone(c.file_path)

    def test_default_uses_csv_distribution(self) -> None:
        cfgs = _ebgp_community_configs(
            create_ebb_performance_scale_basic_port_configs(**_COMMON_KWARGS)
        )
        self.assertEqual(len(cfgs), 2)
        for c in cfgs:
            self.assertIsNone(c.value_lists)
            self.assertIsNotNone(c.file_path)
            self.assertIn("communities", c.file_path)

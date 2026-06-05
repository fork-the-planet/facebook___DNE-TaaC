# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG — TestConfig.

Built from the centralized `create_dctypef_npi_cpu_queue_test_config` factory.
First-pass IcePack instantiation for `gtsw001.l1001.c085.ash6.tfbnw.net` (leaf
in a GTSW->STSW fabric; TH6 ASIC; netwhoami `hw=ICECUBE800BC=70`,
`chmodel=CHMODEL_ICEPACK_BCMTH6_GENERIC=3050`). Pavan-confirmed 2026-06-04:
TH6 (low, mid, high) = (0, 2, 9), same as Minipack3; per-packet queue mapping
is platform-agnostic; GTSW testing alone is sufficient (no STSW config needed).
"""

from taac.testconfigs.fboss_solution_tests.fboss_dctypef_51t_npi_cpu_queue_test_config import (
    create_dctypef_npi_cpu_queue_test_config,
)

NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG = create_dctypef_npi_cpu_queue_test_config(
    test_config_name="NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG",
    device_name="gtsw001.l1001.c085.ash6.tfbnw.net",
    local_mac_address="02:00:00:00:0f:0c",
    # IXIA ports: factory uses uplink as source of CPU-queue test traffic,
    # downlink as sink + BGP-flap target. Rogue is unused for CPU-queue
    # items but required by the factory signature.
    ixia_downlink_interface="eth1/13/1",
    ixia_uplink_interface="eth1/13/3",
    ixia_rogue_interface="eth1/13/5",
    # Uplink: real existing peer group toward the STSW spine.
    peergroup_uplink_mimic_v6="PEERGROUP_GTSW_STSW_V6",
    peergroup_uplink_mimic_v4="PEERGROUP_GTSW_STSW_V4",
    # Downlink (toward hosts): no native peer group on this leaf — the COOP
    # patcher creates these from scratch for IXIA simulation.
    peergroup_downlink_mimic_v6="PEERGROUP_GTSW_HOST_MIMIC_V6",
    peergroup_downlink_mimic_v4="PEERGROUP_GTSW_HOST_MIMIC_V4",
    # Rogue: mirror uplink (KO3 convention).
    peergroup_rogue_mimic_v6="PEERGROUP_GTSW_STSW_V6",
    peergroup_rogue_mimic_v4="PEERGROUP_GTSW_STSW_V4",
    # Uplink route maps: real names on this GTSW (confirmed from `fboss2 show bgp config`).
    # Downlink + rogue route maps: created from scratch by the COOP patcher (no
    # native host-facing or rogue policy exists on this leaf), so names are
    # arbitrary as long as they're unique.
    route_map_uplink_ingress="PROPAGATE_GTSW_STSW_IN",
    route_map_uplink_egress="PROPAGATE_GTSW_STSW_OUT",
    route_map_downlink_ingress="PROPAGATE_GTSW_HOST_IN",
    route_map_downlink_egress="PROPAGATE_GTSW_HOST_OUT",
    route_map_rogue_ingress="PROPAGATE_STSW_GTSW_IN",
    route_map_rogue_egress="PROPAGATE_STSW_GTSW_OUT",
    # IXIA-side parent networks: use the pre-configured BGP_MONITOR
    # placeholder ranges already present on the DUT
    # (v4 10.127.240.0/23, v6 2401:db00:1ff:c100::/56).
    ixia_downlink_ic_parent_network_v6="2401:db00:1ff:c108",
    ixia_uplink_ic_parent_network_v6="2401:db00:1ff:c109",
    ixia_rogue_ic_parent_network_v6="2401:db00:1ff:c10a",
    ixia_downlink_ic_parent_network_v4="10.127.240",
    ixia_uplink_ic_parent_network_v4="10.127.241",
    ixia_rogue_ic_parent_network_v4="10.127.242",
    unique_prefix_limit="73000",
    per_peer_max_route_limit="20000",
    downlink_peer_count=32,
    uplink_peer_count=32,
    rogue_peer_count=8,
    remote_uplink_as_4byte=4200601901,
    remote_downlink_as_4byte=65001,
    remote_as_4_byte_step=1,
    remote_rogue_as_4byte=2500,
    is_uplink_peer_confed="False",
    is_downlink_peer_confed="False",
    is_rogue_peer_confed="False",
    ixia_downlink_prefix_count_v6=5000,
    ixia_uplink_prefix_count_v6=5000,
    ixia_rogue_prefix_count_v6=7500,
    ixia_downlink_prefix_count_v4=5000,
    ixia_uplink_prefix_count_v4=5000,
    ixia_rogue_prefix_count_v4=7500,
    # Uplink: `65446:30` is the `LIVE` community required by the
    # `PROPAGATE_GTSW_STSW_IN` ingress filter on this GTSW; IXIA-mimic STSW
    # peers must tag advertised routes with it or BGP policy rejects them.
    # Downlink: host-facing peers have no policy attached, leave empty.
    ixia_downlink_communities=[],
    ixia_uplink_communities=["65446:30"],
    downlink_peer_tag="HOST",
    uplink_peer_tag="STSW",
    bgpd_restart_no_of_interations=5,
    wedge_agent_restart_no_of_interations=5,
    basset_pool="dne.test",
)

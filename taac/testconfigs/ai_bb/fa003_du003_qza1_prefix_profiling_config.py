# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe

"""
FA003-DU003.QZA1 Prefix Profiling Test Configuration.

Testbed: fa003-du003.qza1 (FADU role, QZA1 cluster)
IXIA chassis: ixia02.netcastle.ash6

Topology (4 ports on ixia02):
    - eth1/62/1 -> 1/3  (Contiguous prefix stresser)
    - eth1/62/5 -> 1/4  (Hybrid prefix stresser)
    - eth1/64/1 -> 1/16 (Non-contiguous prefix stresser)
    - eth1/64/5 -> 1/8  (Downlink - L3 traffic destination)
"""

from taac.testconfigs.ai_bb.mp3n_prefix_profiling_ixia_config import (
    create_device_test_configs,
)

_IXIA02_CHASSIS = "2401:db00:2066:3036::3002"

(
    FA003_DU003_QZA1_CONTIGUOUS_PREFIX_ALL,
    FA003_DU003_QZA1_HYBRID_PREFIX_ALL,
    FA003_DU003_QZA1_NON_CONTIGUOUS_PREFIX_ALL,
) = create_device_test_configs(
    device_name="fa003-du003.qza1",
    remote_as=4210205999,
    peer_group="PEERGROUP_FADU_IXIA_V6",
    contiguous=("eth1/62/1", "2401:db00:e60d:a000", _IXIA02_CHASSIS, "1/3"),
    hybrid=("eth1/62/5", "2401:db00:e60d:a002", _IXIA02_CHASSIS, "1/4"),
    non_contiguous=("eth1/64/1", "2401:db00:e60d:a006", _IXIA02_CHASSIS, "1/16"),
    downlink=("eth1/64/5", "2401:db00:e60d:a004", _IXIA02_CHASSIS, "1/8"),
    mac_address="4e:01:f7:35:a6:1c",
    ingress_policy="PROPAGATE_FADU_IXIA_PREFIX_PROFILING_IN",
    egress_policy="PROPAGATE_FADU_IXIA_PREFIX_PROFILING_OUT",
    patcher_suffix="fadu_ixia",
    config_name_prefix="FA003_DU003_QZA1_PREFIX_PROFILING_SCALE",
    basset_pool="dne.test",
    convergence_duration=300,
)

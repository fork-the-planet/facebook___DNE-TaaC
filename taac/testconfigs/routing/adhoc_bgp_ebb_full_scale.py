# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""BGP++ EBB full-scale mimic ad-hoc testconfigs (jsw002.m001.snc1 production EB).

Wave 5E.2 -- migrates the shared/generic mimic-full-scale wrapper
previously living at
``testconfigs/routing/ebb/arista_mimic_ebb_test_full_scale_test_config.py``
into this catalog. ``TestConfig.name`` preserved verbatim so the golden
manifest hash is byte-wise identical.

The 3 lab-box siblings (eb01/eb03/eb04) live in
``qual_bgp_ebb_full_scale.py`` since they target ``qual``-usage testbeds.

External consumers import via ``testconfigs.routing`` root; see README.md §7.
"""

from taac.testconfigs.routing.factories.bgp_ebb_full_scale_mimic import (
    create_bgp_ebb_full_scale_mimic_test_config,
)
from taac.testconfigs.routing.testbed import JSW002_M001_SNC1


# ─── ARISTA_MIMIC_EBB_TEST_FULL_SCALE (prod jsw002 EB, no Open/R) ─────────
# Legacy source declared no ``host_driver_args`` / ``oss_mock_device_data``
# / ``direct_ixia_connections`` / ``profile`` override (the underlying
# factory then defaults ``profile`` to ``BGP_PLUS_PLUS_WITHOUT_OPEN_R``).
# ``JSW002_M001_SNC1`` intentionally has an empty ``ixia_chassis_ip`` +
# no ``ixia_ports`` -- topology is discovered at runtime for this prod
# testbed -- so the mimic interface names come from ``testbed.extras``.
ARISTA_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG = (
    create_bgp_ebb_full_scale_mimic_test_config(
        JSW002_M001_SNC1,
        name="ARISTA_MIMIC_EBB_TEST_FULL_SCALE",
        ixia_interface_mimic_ebgp=JSW002_M001_SNC1.extras["dut_iface_ebgp"],
        ixia_interface_mimic_ibgp=JSW002_M001_SNC1.extras["dut_iface_ibgp"],
        ixia_interface_mimic_bgp_mon=JSW002_M001_SNC1.extras["dut_iface_bgp_mon"],
    )
)


__all__ = [
    "ARISTA_MIMIC_EBB_TEST_FULL_SCALE_TEST_CONFIG",
]

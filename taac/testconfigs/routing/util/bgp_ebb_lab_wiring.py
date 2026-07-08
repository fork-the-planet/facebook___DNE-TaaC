# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
"""Shared lab-device wiring helpers for EBB factories.

Extracted from ``factories/bgp_ebb_scaling.py`` in Wave 5-hotfix to break a
circular import: previously ``bgp_ebb_characteristic.py`` imported
``_lab_device_wiring`` from ``bgp_ebb_scaling.py``, but ``bgp_ebb_scaling.py``
also (indirectly) loads ``bgp_ebb_characteristic.py`` via
``ebb/case1_test_config.py`` → ``ebb/__init__.py`` → ``eb04_arista_*``
→ ``bgp_ebb_characteristic``. Hoisting to ``util/`` cuts the cycle.
"""

import json
import os
import typing as t

from taac.testconfigs.routing.testbed import Testbed
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection


def _lab_device_wiring(
    testbed: Testbed,
) -> tuple[dict[str, str] | None, dict[str, taac_types.MockDeviceInfo] | None]:
    """Return ``(host_driver_args, oss_mock_device_data)`` for ``testbed``.

    Lab boxes (EB02_LAB_ASH6 / EB03_LAB_ASH6 / EB04_LAB_ASH6 / EB_TEST_DEVICE)
    carry admin/password creds + MockDeviceInfo fields on ``testbed.extras``
    because ``svc-netcastle_bot`` is not authorized and ``netwhoami`` returns
    ``#INVALID#`` for them. Non-lab testbeds (bag012 / bag010 / etc.) leave
    ``extras`` empty of those keys; return ``(None, None)`` so the resulting
    ``TestConfig`` matches the legacy factory output for those DUTs.
    """
    if "lab_admin_username" not in testbed.extras:
        return None, None
    lab_password_env = (
        testbed.lab_device_password_env_var or "TAAC_EBB_LAB_DEVICE_PASSWORD"
    )
    lab_admin_username = testbed.extras["lab_admin_username"]
    lab_admin_password_default = testbed.extras.get(
        "lab_admin_password_default",
        "dnepit",  # pragma: allowlist secret
    )
    lab_password = os.environ.get(lab_password_env, lab_admin_password_default)
    device_name = testbed.device_name
    driver_kwargs: dict[str, t.Any] = {
        "username": lab_admin_username,
        "password": lab_password,
    }
    driver_kwargs.update(testbed.extras.get("host_driver_extra_kwargs", {}))
    host_driver_args = {device_name: json.dumps(driver_kwargs)}
    mock_kwargs: dict[str, t.Any] = {
        "name": device_name,
        "hardware": testbed.extras.get("mock_device_hardware", "ARISTA_7516"),
        "role": testbed.extras.get("mock_device_role", "EB"),
        "operating_system": "EOS",
        "dc": testbed.extras.get("mock_device_dc", "ash6"),
        "region": testbed.extras.get("mock_device_region", "ash"),
        "asset_id": testbed.extras.get("mock_device_asset_id", 12345),
        "asic": testbed.extras.get("mock_device_asic", "JERICHO"),
        "routing_protocol": "BGP",
        "dc_type": "ONE",
        "network_area": testbed.extras.get("mock_device_network_area", "BACKBONE"),
        "network_area_type": "BACKBONE",
    }
    if "mock_device_network_type" in testbed.extras:
        mock_kwargs["network_type"] = testbed.extras["mock_device_network_type"]
    oss_mock_device_data = {device_name: taac_types.MockDeviceInfo(**mock_kwargs)}
    return host_driver_args, oss_mock_device_data


def _direct_ixia_conns_two_port(testbed: Testbed) -> list[DirectIxiaConnection]:
    """Two ``DirectIxiaConnection`` entries (eBGP + iBGP) derived from testbed.

    Matches the layout the case1/3/4/6/9 legacy factories use: only the first
    two ``testbed.ixia_ports`` entries are wired (BGP-MON is unused).
    """
    ebgp_iface, ebgp_port = testbed.ixia_ports[0]
    ibgp_iface, ibgp_port = testbed.ixia_ports[1]
    return [
        DirectIxiaConnection(
            interface=ebgp_iface,
            ixia_chassis_ip=testbed.ixia_chassis_ip,
            ixia_port=ebgp_port,
        ),
        DirectIxiaConnection(
            interface=ibgp_iface,
            ixia_chassis_ip=testbed.ixia_chassis_ip,
            ixia_port=ibgp_port,
        ),
    ]

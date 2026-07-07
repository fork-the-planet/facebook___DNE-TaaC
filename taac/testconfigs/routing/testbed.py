# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Routing test DUT baseline definitions.

Home of the ``Testbed`` dataclass + all Testbed instances used by
routing testconfig factories under ``testconfigs/routing/``. Per-role
config bundles (peer group names, route maps, communities) live in
the sibling ``role_defaults.py``.

See ``README.md`` §2 for the framework rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taac.testconfigs.routing.role_defaults import ebb_peer_groups


@dataclass(frozen=True)
class Testbed:
    """DUT baseline for a routing test. Fits all usecases (EBB / DC / FA verify / feature).

    Physical identity fields stay flat; anything varying by testbed-family
    (BGP peer-group names, communities, route maps, etc.) goes into
    role-keyed dicts. Factories look up what they need by role key.
    """

    # ─── Physical identity (always required) ──────────────────────────────
    device_name: str
    ixia_chassis_ip: str
    # ``ixia_ports`` items are ``(dut_iface, chassis_port)`` tuples. The
    # chassis-port string is IXIA's ``"<card>/<port>"`` shorthand (e.g. ``"8/2"``
    # = card 8, port 2 on the IXIA chassis at ``ixia_chassis_ip``). Order is
    # load-bearing for factories that hard-index the list: ``[0]`` = eBGP,
    # ``[1]`` = iBGP, ``[2]`` = BGP-MON (when present).
    ixia_ports: list = field(default_factory=list)

    # ─── DUT identity properties (optional, flat) ─────────────────────────
    mac_address: str | None = None
    speed: str = "100g-2"
    router_id: str | None = None
    dut_bgp_as: int | None = None  # DUT's own local BGP AS

    # ─── Configerator paths for full-config deployment ────────────────────
    bgpcpp_configerator_path: str | None = None
    openr_configerator_path: str | None = None
    fboss_agent_configerator_path: str | None = None

    # ─── Lab auth ─────────────────────────────────────────────────────────
    lab_device_password_env_var: str | None = None

    # ─── Named parameter maps — BGP topology ──────────────────────────────
    peer_groups: dict = field(default_factory=dict)
    as_numbers: dict = field(default_factory=dict)
    route_maps: dict = field(default_factory=dict)
    communities: dict = field(default_factory=dict)
    parent_networks: dict = field(default_factory=dict)

    # ─── FBOSS baseline attributes (patcher-applied at setup) ─────────────
    fboss_attributes: dict = field(default_factory=dict)

    # ─── Escape hatch ─────────────────────────────────────────────────────
    extras: dict = field(default_factory=dict)


# ─── Shared private constants ─────────────────────────────────────────────

_EBB_BGPCPP_PATH = "taac/ebb_ci_cd_configs/ebb_full_scale_bgpcpp_config"
_ASH6_IXIA_CHASSIS = "2401:db00:2066:303b::3001"


# ─── BAG conveyor testbeds ────────────────────────────────────────────────

BAG002_SNC1 = Testbed(
    device_name="bag002.snc1",
    ixia_chassis_ip="ares1-my24520014",
    ixia_ports=[
        ("Ethernet3/25/1", "1/17"),  # eBGP
        ("Ethernet3/26/1", "1/18"),  # iBGP
        ("Ethernet3/27/1", "1/19"),  # BGP-MON
    ],
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    peer_groups=ebb_peer_groups(),
)

BAG010_ASH6 = Testbed(
    device_name="bag010.ash6",
    ixia_chassis_ip=_ASH6_IXIA_CHASSIS,
    ixia_ports=[
        ("Ethernet3/36/1", "7/1"),  # eBGP
        ("Ethernet3/36/2", "7/2"),  # iBGP
        ("Ethernet3/36/3", "7/3"),  # BGP-MON
    ],
    dut_bgp_as=65010,
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    openr_configerator_path="taac/ebb_ci_cd_configs/bag010_ash6_openr_config",
    peer_groups=ebb_peer_groups(),
    extras={
        # OpenR link-config knobs consumed by
        # ``conveyor_common_tasks.get_common_setup_tasks`` for the bag010.ash6
        # DUT. Kept in ``extras`` because they are OpenR-specific baseline
        # attributes and do not fit the generic Testbed fields.
        "openr_port_channel_member": "Ethernet3/6/1",
        "openr_port_channel_ipv4": "10.131.97.238/31",
        "openr_port_channel_link_local": "fe80::eba:a7f:fd02/64",
        "openr_local_link": {
            "ipv4": "10.131.97.238",
            "ipv6": "fe80::eba:a7f:fd02",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
        "openr_other_link": {
            "ipv4": "10.131.97.239",
            "ipv6": "fe80::eba:a7f:fd03",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
    },
)

BAG011_ASH6 = Testbed(
    device_name="bag011.ash6",
    ixia_chassis_ip=_ASH6_IXIA_CHASSIS,
    ixia_ports=[
        ("Ethernet3/36/1", "7/4"),  # eBGP
        ("Ethernet3/36/2", "7/5"),  # iBGP
        ("Ethernet3/36/3", "7/6"),  # BGP-MON
    ],
    # NOTE: preserved verbatim from the legacy bag011_ash6_test_config.py
    # which stored the DUT's local BGP AS in a variable named
    # ``BAG012_EOS_BGP_AS = 65011``. The literal 65011 is bag011's AS; the
    # legacy variable name was a copy-paste artifact.
    dut_bgp_as=65011,
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    openr_configerator_path="taac/ebb_ci_cd_configs/bag011_ash6_openr_config",
    peer_groups=ebb_peer_groups(),
    extras={
        # OpenR link-config knobs consumed by
        # ``conveyor_common_tasks.get_common_setup_tasks`` for the bag011.ash6
        # DUT. Kept in ``extras`` because they are OpenR-specific baseline
        # attributes and do not fit the generic Testbed fields.
        "openr_port_channel_member": "Ethernet3/9/1",
        "openr_port_channel_ipv4": "10.131.97.236/31",
        "openr_port_channel_link_local": "fe80::eba:a7f:fd00/64",
        # bag011 uses the shared ``OPENR_LOCAL_LINK`` / ``OPENR_OTHER_LINK``
        # constants from ``conveyor_constants.py`` verbatim (unlike bag010
        # which has DUT-specific overrides).
        "openr_local_link": {
            "ipv4": "10.131.97.236",
            "ipv6": "fe80::eba:a7f:fd00",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
        "openr_other_link": {
            "ipv4": "10.131.97.237",
            "ipv6": "fe80::eba:a7f:fd01",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
    },
)

BAG012_ASH6 = Testbed(
    device_name="bag012.ash6",
    ixia_chassis_ip=_ASH6_IXIA_CHASSIS,
    ixia_ports=[
        ("Ethernet3/36/1", "7/7"),  # eBGP
        ("Ethernet3/36/2", "7/8"),  # iBGP
        # bag012 has NO BGP-MON port
    ],
    dut_bgp_as=65012,
    # bag012 is the only bag testbed that pins ``router_id`` explicitly
    # (bag010/bag011/bag013 all rely on the device-default BGP router-id).
    # Preserved verbatim from the legacy bag012 config for golden-manifest identity.
    router_id="10.163.28.11",
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    peer_groups=ebb_peer_groups(),
)

BAG013_ASH6 = Testbed(
    device_name="bag013.ash6",
    ixia_chassis_ip=_ASH6_IXIA_CHASSIS,
    ixia_ports=[
        ("Ethernet3/36/1", "8/2"),  # eBGP
        ("Ethernet3/36/2", "8/3"),  # iBGP
        ("Ethernet3/36/3", "8/4"),  # BGP-MON
    ],
    dut_bgp_as=65013,
    # No ``router_id`` — device-default (same as bag010/bag011; see BAG012_ASH6 note).
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    openr_configerator_path="taac/ebb_ci_cd_configs/bag013_ash6_openr_config",
    peer_groups=ebb_peer_groups(),
    extras={
        # OpenR link-config knobs consumed by
        # ``conveyor_common_tasks.get_common_setup_tasks`` for the bag013.ash6
        # DUT. Kept in ``extras`` because they are OpenR-specific baseline
        # attributes and do not fit the generic Testbed fields.
        "openr_port_channel_member": "Ethernet3/9/1",
        "openr_port_channel_ipv4": "10.131.97.232/31",
        "openr_port_channel_link_local": "fe80::eba:a7f:fcfc/64",
        "openr_local_link": {
            "ipv4": "10.131.97.232",
            "ipv6": "fe80::eba:a7f:fcfc",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
        "openr_other_link": {
            "ipv4": "10.131.97.233",
            "ipv6": "fe80::eba:a7f:fcfd",
            "ifName": "po100211",
            "weight": 0,
            "metric": 10,
        },
    },
)


# ─── EB03 lab testbed (Arista lab box in ASH6) ────────────────────────────
# eb03.lab.ash6 is a lab device with admin/password auth (svc-netcastle_bot
# not authorized). extras carries lab-specific credentials + MockDeviceInfo
# fields (netwhoami returns #INVALID# for this device).
EB03_LAB_ASH6 = Testbed(
    device_name="eb03.lab.ash6",
    ixia_chassis_ip=_ASH6_IXIA_CHASSIS,
    ixia_ports=[
        ("Ethernet3/1/3", "6/5"),  # eBGP
        ("Ethernet3/1/5", "6/6"),  # iBGP
        ("Ethernet3/36/1", "2/8"),  # BGP-MON
    ],
    dut_bgp_as=64981,
    bgpcpp_configerator_path=_EBB_BGPCPP_PATH,
    lab_device_password_env_var="TAAC_EBB_LAB_DEVICE_PASSWORD",
    peer_groups=ebb_peer_groups(),
    extras={
        "lab_admin_username": "admin",
        "lab_admin_password_default": "dnepit",  # pragma: allowlist secret
        "mock_device_hardware": "ARISTA_7516",
        "mock_device_role": "EB",
        "mock_device_asic": "JERICHO",
        "mock_device_dc": "ash6",
        "mock_device_region": "ash",
        "mock_device_asset_id": 12345,
        "mock_device_network_area": "BACKBONE",
        "mock_device_network_type": "EBB",
    },
)

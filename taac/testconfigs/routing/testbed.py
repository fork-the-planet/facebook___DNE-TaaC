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
)

# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
import random
import typing as t

from taac.constants import TestDevice
from taac.utils.json_thrift_utils import try_json_to_thrift
from taac.utils.oss_taac_lib_utils import (
    ConsoleFileLogger,
    get_root_logger,
)
from taac.test_as_a_config import types as taac_types

LOGGER: ConsoleFileLogger = get_root_logger()


def lookup_transformation_function(select_name: str):
    return {
        "SELECT_SWITCH_INTERFACES": select_switch_interfaces,
        "SELECT_INTERFACES_BY_SLICING": select_interfaces_by_slicing,
        "SELECT_SAMPLE": select_sample,
        "SELECT_INTERFACES_BY_NEIGHBORS": select_interfaces_by_neighbors,
        "SELECT_SNAKE_CIRCUIT_A_ENDS": select_snake_circuit_a_ends,
    }.get(select_name, None)


def _port_sort_key(interface_name: str) -> t.Tuple[int, ...]:
    """Deterministic ordering key for an interface name like ``eth1/34/5``.

    Returns the tuple of integer components (``(1, 34, 5)``) so ports compare
    by unit, then module, then lane. Non-numeric names fall back to a tuple
    that sorts them last but stably.
    """
    parts = []
    for token in interface_name.replace("eth", "").split("/"):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _transceiver_key(interface_name: str) -> t.Tuple[int, ...]:
    """Group key identifying the physical transceiver of an interface.

    On gearbox optics (e.g. montblanc) all sub-port lanes of a module share ONE
    transceiver, so ``eth1/2/1``, ``eth1/2/3``, ``eth1/2/5``, ``eth1/2/7`` all map
    to the same key ``(1, 2)`` (unit, module -- the lane component is dropped).
    Admin-disabling any one lane downs the whole transceiver, so parity grouping
    MUST be done at this granularity, never per-lane.
    """
    return _port_sort_key(interface_name)[:-1]


def select_snake_circuit_a_ends(
    val: t.Any, params: t.Dict[str, t.Any]
) -> t.List[taac_types.TestInterface]:
    """Return the A-ends of the even- or odd-indexed snake-circuit TRANSCEIVERS.

    A *snake circuit* is a pair of interfaces on the SAME device cabled to each
    other (a loopback jumper). For each circuit the **A-end** is the
    deterministically-lower interface (by unit/module/lane, see
    ``_port_sort_key``); the other end is the Z-end.

    Parity is assigned at **transceiver granularity**, NOT per circuit. We group
    circuits by their A-end transceiver (``_transceiver_key``), order the groups,
    and assign whole groups alternately: ``params["parity"] == "even"`` selects
    transceiver groups 0, 2, 4, ...; ``"odd"`` selects groups 1, 3, 5, .... All
    A-ends of the selected groups are returned (flattened, circuit-ordered).

    Why transceiver granularity: on gearbox optics every sub-port lane of a module
    shares one transceiver, so disabling one lane downs the whole transceiver (all
    its lanes) and their jumper partners. If two lanes of the same transceiver
    landed in opposite parity groups, disabling the "even" lane would down the
    "odd" sibling that the MID_TEST check expects UP -- a guaranteed false failure
    (exactly the gearbox bug seen on fboss159). Keeping a transceiver's circuits in
    one parity group means disabling an even group downs ONLY even transceivers
    (and their partner ends), leaving every odd transceiver fully up.

    Only A-ends are returned, so a caller disables one lane per selected circuit
    (which downs the whole transceiver anyway). Each returned ``TestInterface``
    keeps its ``neighbor_*`` fields, so a downstream PORT_STATE/LLDP check expands
    it to BOTH ends of the circuit and expects the whole circuit down. The
    selection is deterministic and cache-free: the same parity always yields the
    same set, so re-enable steps just re-derive it instead of reading a cache.
    """
    parity = params["parity"]
    if parity not in ("even", "odd"):
        raise ValueError(f"parity must be 'even' or 'odd', got {parity!r}")

    interfaces: t.List[taac_types.TestInterface] = [  # pyre-ignore
        try_json_to_thrift(interface, taac_types.TestInterface) for interface in val
    ]
    by_name: t.Dict[str, taac_types.TestInterface] = {
        iface.interface_name: iface for iface in interfaces
    }

    # Build the set of unique circuits, each represented by its A-end interface.
    seen: t.Set[t.FrozenSet[str]] = set()
    circuits: t.List[taac_types.TestInterface] = []
    for iface in interfaces:
        local = iface.interface_name
        neighbor = iface.neighbor_interface_name
        if not neighbor:
            continue
        key = frozenset({local, neighbor})
        if key in seen:
            continue
        seen.add(key)
        a_name, _z_name = sorted([local, neighbor], key=_port_sort_key)
        circuits.append(by_name.get(a_name, iface))

    circuits.sort(key=lambda iface: _port_sort_key(iface.interface_name))

    # Group circuits by A-end transceiver, preserving circuit order within a group.
    groups: t.Dict[t.Tuple[int, ...], t.List[taac_types.TestInterface]] = {}
    for circuit in circuits:
        groups.setdefault(_transceiver_key(circuit.interface_name), []).append(circuit)

    # Select whole transceiver groups by index parity, then flatten.
    ordered_keys = sorted(groups.keys())
    start = 0 if parity == "even" else 1
    selected: t.List[taac_types.TestInterface] = []
    for group_key in ordered_keys[start::2]:
        selected.extend(groups[group_key])
    return selected


def select_switch_interfaces(
    val: t.Any, params: t.Dict[str, t.Any]
) -> t.List[taac_types.TestInterface]:
    test_device: TestDevice = val
    return test_device.interfaces


def select_interfaces_by_slicing(
    val: t.Any, params: t.Dict[str, t.Any]
) -> t.List[taac_types.TestInterface]:
    interfaces: t.List[taac_types.TestInterface] = val
    slicing_expression = params["slicing_expression"]
    slice_obj = slice(
        *map(lambda x: int(x) if x else None, slicing_expression.split(":"))
    )
    selected_interfaces = interfaces[slice_obj]
    return selected_interfaces


def select_interfaces_by_neighbors(
    val: t.Any, params: t.Dict[str, t.Any]
) -> t.List[taac_types.TestInterface]:
    interfaces: t.List[taac_types.TestInterface] = [  # pyre-ignore
        try_json_to_thrift(interface, taac_types.TestInterface) for interface in val
    ]
    neighbors = params["neighbors"]
    selected_interfaces = []
    for interface in interfaces:
        if interface.neighbor_switch_name in neighbors:
            selected_interfaces.append(interface)
    return selected_interfaces


def select_sample(val: t.List[t.Any], params: t.Dict[str, t.Any]) -> t.List[t.Any]:
    return random.sample(val, params["sample_size"])

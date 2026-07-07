# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""Per-role DUT-config helpers (peer_groups, route_maps, communities).

Testbed instances in ``testbed.py`` call these helpers to populate
their role-keyed dicts. Factory code does NOT branch on DUT role —
it just reads standard role keys (uplink_v6, downlink_v6, ibgp_v6,
ebgp_v6, ...) from the Testbed dicts.

See ``README.md`` §2 "DUT roles and role-defaults helpers".

Skeleton — populated as Wave 1 migration diffs land.
"""

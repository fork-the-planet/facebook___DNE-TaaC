# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
"""The bgpcpp_config peer-rewrite merge must write as root (sudo).

/mnt/flash/bgpcpp_config is root-owned on some EOS boxes (e.g. bag010); the base
config is deployed with privilege, so the in-shell peer merge must run under
``sudo`` too — otherwise ``open('w')`` raises PermissionError and the device
silently keeps the full-scale config (1274 peers) instead of the sweep set.
Guards both splice paths.
"""

import unittest

from taac.testconfigs.routing.util.bgp_ebb_setup_tasks import (
    build_bgpcpp_peers_patch_shell_cmds,
)
from taac.testconfigs.routing.util.bgpcpp_peers_modification import (
    _generate_bgpcpp_peers_modification_tasks,
)

_CONFIG_PATH = "/mnt/flash/bgpcpp_config"


class PeerRewriteSudoTest(unittest.TestCase):
    def test_per_iteration_merge_writes_as_root(self) -> None:
        # build_bgpcpp_peers_patch_shell_cmds — per-stage rescale path.
        merge = build_bgpcpp_peers_patch_shell_cmds(peers=[], router_id="10.0.0.1")[-1]
        self.assertIn("sudo python3", merge)
        self.assertIn(_CONFIG_PATH, merge)

    def test_setup_merge_writes_as_root(self) -> None:
        # _generate_bgpcpp_peers_modification_tasks — setup path.
        tasks = _generate_bgpcpp_peers_modification_tasks(
            bgpcpp_device="bag010.ash6", router_id="10.0.0.1", peers=[]
        )
        blob = str(tasks)
        self.assertIn("sudo python3", blob)
        self.assertIn(_CONFIG_PATH, blob)

# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
"""Helper to generate bgpcpp_config peer-replacement tasks.

Hoisted from ``testconfigs/routing/ebb/case1_test_config.py`` so that
factories under ``testconfigs/routing/factories/`` can consume it
without triggering the ``ebb/__init__.py`` force-import chain (which
loads every wrapper module and creates a cycle back through
``bgp_ebb_characteristic``).
"""

import base64 as _b64_mod
import json
import typing as t

from taac.routing.ebb.ebb_bgp_plus_plus_test_config.tcp_socket_experiment.constants import (
    BGPCPP_CONFIG_PATH,
)
from taac.task_definitions import (
    create_run_commands_on_shell_task,
)
from taac.test_as_a_config.types import Task


def _generate_bgpcpp_peers_modification_tasks(
    bgpcpp_device: str,
    router_id: t.Optional[str],
    peers: t.List[t.Dict[str, t.Any]],
    config_path: str = BGPCPP_CONFIG_PATH,
    local_as_4_byte: t.Optional[int] = None,
) -> t.List[Task]:
    """
    Generate tasks to modify the deployed bgpcpp_config.

    The base bgpcpp_config is first deployed from configerator (with all
    peer_groups, policies, communities, localprefs, etc.). These tasks
    replace ONLY the 'peers' and 'router_id' fields, preserving
    everything else (including local_as_4_byte from the base config,
    unless local_as_4_byte is explicitly provided for iBGP scenarios).

    Uses base64 encoding to avoid shell command length limits — the 282
    peers JSON is ~50KB which exceeds EOS shell limits when passed inline.
    """
    peers_json = json.dumps(peers)
    peers_b64 = _b64_mod.b64encode(peers_json.encode()).decode()

    # Chunk the base64 string into 20KB pieces to avoid EOS shell limits
    chunk_size = 20000
    chunks = [
        peers_b64[i : i + chunk_size] for i in range(0, len(peers_b64), chunk_size)
    ]

    tasks = []

    # Step 1: Write base64-encoded peers in chunks to a temp file
    chunk_cmds = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            chunk_cmds.append(f"bash echo '{chunk}' > /tmp/peers.b64")
        else:
            chunk_cmds.append(f"bash echo '{chunk}' >> /tmp/peers.b64")
    # Decode the base64 file to JSON
    chunk_cmds.append("bash base64 -d /tmp/peers.b64 > /tmp/experiment_peers.json")
    chunk_cmds.append("bash rm -f /tmp/peers.b64")

    tasks.append(
        create_run_commands_on_shell_task(
            hostname=bgpcpp_device,
            cmds=chunk_cmds,
            ixia_needed=True,
        )
    )

    # Step 2: Short python3 script reads peers from temp file and merges
    local_as_line = ""
    if local_as_4_byte is not None:
        local_as_line = f"c['local_as_4_byte']={local_as_4_byte}; "
    # router_id is optional: when None we preserve the deployed config's
    # router_id (matching the legacy in-shell peer-replace behavior, which
    # only swapped the 'peers' field and never touched router_id).
    router_id_line = ""
    if router_id is not None:
        router_id_line = f"c['router_id']='{router_id}'; "
    # sudo: /mnt/flash/bgpcpp_config is root-owned on some EOS boxes (e.g.
    # bag010); the base config is deployed with privilege, so this merge must
    # write as root too — otherwise open('w') raises PermissionError and the
    # device silently keeps the full-scale config.
    merge_script = (
        f'sudo python3 -c "'
        f"import json; "
        f"f=open('{config_path}'); c=json.load(f); f.close(); "
        f"p=open('/tmp/experiment_peers.json'); "
        f"c['peers']=json.load(p); p.close(); "
        f"{router_id_line}"
        f"{local_as_line}"
        f"f=open('{config_path}','w'); "
        f"json.dump(c,f,indent=2); f.close(); "
        f"print('Updated peers:',len(c['peers']),"
        f"'router_id:',c['router_id'],"
        f"'local_as_4_byte:',c.get('local_as_4_byte'))"
        f'"'
    )
    tasks.append(
        create_run_commands_on_shell_task(
            hostname=bgpcpp_device,
            cmds=[f"bash {merge_script}"],
            ixia_needed=True,
        )
    )

    return tasks

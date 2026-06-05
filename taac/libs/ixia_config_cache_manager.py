# pyre-strict
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

"""
Cache manager for IxNetwork topology configurations (ixncfg files).

Today's TAAC runs spend 226s (BAG012) to 40+ min (BAG010/011 production scale)
in `create_basic_setup` calling per-API REST setup for the IXIA topology. This
manager replaces that with a `LoadConfig` of a pre-built ixncfg on the API
server — ~10-20s on cache hit.

Cache key shape: `{test_config_name}__{chassis_id}__{config_hash}.ixncfg`
  - test_config_name: different tests need different topologies
  - chassis_id: ixncfg embeds vport↔chassis-port bindings; cross-chassis breaks
  - config_hash: 12-char prefix of sha256(_CACHE_VERSION + IxiaConfig Thrift bytes).
    The hash rolls (and invalidates stale caches) when EITHER the IxiaConfig
    struct content changes OR `_CACHE_VERSION` is bumped. Bump _CACHE_VERSION
    when Python setup logic (`create_basic_setup`, etc.) changes in a way that
    affects the resulting topology even if the IxiaConfig struct is unchanged.

Tier 1 (chassis-local) is implemented. Tier 2 (Manifold) is reserved for a
follow-up — the `manifold_bucket` field on `IxiaConfigCache` is wired through
but not yet consumed here.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ixia.ixia import types as ixia_types
from taac.ixia.taac_ixia import TaacIxia
from taac.utils.oss_taac_lib_utils import (
    ConsoleFileLogger,
    none_throws,
)
from taac.test_as_a_config import types as taac_types


# Chars allowed in sanitized key fragments. Dots are NOT allowed — they get
# replaced with `_` (hostnames like `ixia11.ash6` become `ixia11_ash6`). The
# `.ixncfg` suffix is appended verbatim AFTER sanitization, not preserved
# through it.
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_-]")

# Cache version: bump when Python topology-generation logic changes in a way
# that would affect the saved `.ixncfg` (e.g. new DG/peer/prefix wiring in
# `create_basic_setup`, change in port-config builder, etc.). Bumping
# invalidates ALL existing cached ixncfg files across all testbeds — they'll be
# re-created on the next cold run.
#
# v2 (2026-06-05): dropped IxiaConfig content from the hash. The built
# IxiaConfig embeds runtime chassis-queried state (e.g. logical port numbers
# resolved via `async_get_ixia_logical_port`) that varies run-to-run even for
# an identical TestConfig — observed on bag012.ash6 cold→warm where two
# back-to-back runs of the same TestConfig produced different hashes
# (7ca5ecc43fa6 vs adc161447418), causing warm cache to never hit. Cache is
# now keyed purely by (test_config_name, chassis_id, _CACHE_VERSION), which
# is stable per testbed. The trade-off: cache will NOT auto-invalidate when a
# TestConfig's declarative content (port map, BGP peers) changes — the
# engineer must bump _CACHE_VERSION manually. A follow-up should hash a
# canonical subset of the SOURCE TestConfig (basic_port_configs etc.) to get
# the best of both: stable per run, auto-invalidating per declarative drift.
_CACHE_VERSION = "v2"


def _sanitize(s: str) -> str:
    """Replace any non-alphanumeric/dash/underscore char with `_`."""
    return _SAFE_KEY_RE.sub("_", s)


def compute_cache_key(
    test_config_name: str,
    chassis_id: str,
    ixia_config: ixia_types.IxiaConfig,  # accepted for API back-compat, NOT hashed
) -> str:
    """Stable cache key for a `(test_config_name, chassis_id, _CACHE_VERSION)` triple.

    `ixia_config` is accepted for API back-compat with v1 callers but is NOT
    included in the key — see the docstring on `_CACHE_VERSION` for why.
    """
    # Suppress unused-arg warning while keeping the back-compat signature.
    _ = ixia_config
    return (
        f"{_sanitize(test_config_name)}__"
        f"{_sanitize(chassis_id)}__{_CACHE_VERSION}.ixncfg"
    )


class IxiaConfigCacheManager:
    """3-tier cache manager (Tier 1 chassis-local; Tier 2 Manifold deferred).

    Usage:
        mgr = IxiaConfigCacheManager(ixia, cache_config, logger)
        key = mgr.compute_key(test_config_name, ixia_config)
        if mgr.try_load_from_chassis(key):
            ...skip create_basic_setup, go straight to start_and_verify_protocols
        else:
            ...run create_basic_setup
            mgr.save_to_chassis(key)  # warm cache for next run
    """

    def __init__(
        self,
        ixia: TaacIxia,
        cache_config: taac_types.IxiaConfigCache,
        logger: ConsoleFileLogger,
    ) -> None:
        self._ixia = ixia
        self._cfg = cache_config
        self._logger = logger

    def compute_key(
        self,
        test_config_name: str,
        ixia_config: ixia_types.IxiaConfig,
    ) -> str:
        """Compute cache key including chassis identity (from self._ixia).

        `primary_chassis_ip` is typed as Optional, but at this point in the
        runner flow the IXIA session is established so it must be set; fail
        fast via none_throws if it isn't.
        """
        return compute_cache_key(
            test_config_name,
            none_throws(self._ixia.primary_chassis_ip),
            ixia_config,
        )

    def chassis_path(self, key: str) -> str:
        """Full path of the cache file on the IxNetwork API server."""
        return f"{self._cfg.chassis_local_dir.rstrip('/')}/{key}"

    def try_load_from_chassis(self, key: str) -> bool:
        """Tier 1: try LoadConfig from chassis-local path.

        Delegates to TaacIxia.load_config_from_chassis which already handles
        exceptions, returns bool, and calls start_and_verify_protocols on success.
        Returns True on hit (caller skips create_basic_setup), False on miss.
        """
        path = self.chassis_path(key)
        self._logger.info(f"ixia cache: Tier 1 lookup — trying {path}")
        t0 = time.monotonic()
        loaded = self._ixia.load_config_from_chassis(path)
        elapsed = time.monotonic() - t0
        if loaded:
            self._logger.info(
                f"ixia cache: Tier 1 HIT — loaded in {elapsed:.1f}s "
                f"(would have been ~226s+ via create_basic_setup)"
            )
        else:
            self._logger.info(f"ixia cache: Tier 1 miss after {elapsed:.1f}s")
        return loaded

    def save_to_chassis(self, key: str) -> None:
        """Save current session state to chassis-local cache for next run.

        Delegates to TaacIxia.save_config_to_chassis which handles exceptions
        and returns bool. NEVER raises — cache warming is best-effort.
        """
        path = self.chassis_path(key)
        self._logger.info(f"ixia cache: warming Tier 1 — {path}")
        ok = self._ixia.save_config_to_chassis(path)
        if ok:
            self._logger.info(f"ixia cache: Tier 1 warmed at {path}")
        else:
            self._logger.error(
                "ixia cache: Tier 1 warm-up FAILED. Next run pays cold cost again."
            )

    def _placeholder_manifold(self) -> Any:
        """Reserved for Tier 2 — see `manifold_bucket` field on IxiaConfigCache.

        Not implemented in this diff. Follow-up will add ManifoldClient.get/put
        plus a Files(local_file=True) hop to push downloaded ixncfg to API server.
        """
        raise NotImplementedError("Tier 2 (Manifold) deferred to follow-up diff")

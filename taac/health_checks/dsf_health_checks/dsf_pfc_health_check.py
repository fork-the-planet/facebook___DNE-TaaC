# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
import asyncio
import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.utils.common import async_everpaste_str
from taac.utils.health_check_utils import get_fb303_client
from taac.health_check.health_check import types as hc_types


class DsfPfcHealthCheck(AbstractDeviceHealthCheck[hc_types.DsfPfcHealthCheckIn]):
    CHECK_NAME: hc_types.CheckName = hc_types.CheckName.DSF_PFC_CHECK

    # Class-level snapshot store keyed by (device, interface, priority) → (out_pfc, in_pfc)
    # of the monotonic .sum counters. Populated when the HC runs with
    # check_params["mode"] == "snapshot" (typically in prechecks) and consumed as
    # the pretest baseline when the HC runs with mode == "check" (postchecks).
    # Bypasses the fb303 hw_agent .sum.60 windowed-counter aggregation race that
    # transiently returns 0 mid-cycle.
    _snapshots: t.Dict[t.Tuple[str, str, int], t.Tuple[int, int]] = {}

    async def _run(
        self,
        obj: TestDevice,
        input: hc_types.DsfPfcHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        operating_system = obj.attributes.operating_system
        match operating_system:
            case "FBOSS":
                return await self._run_fboss_pfc_health_check(obj, input, check_params)
            case "EOS":
                return await self._run_eos_pfc_health_check(obj, input, check_params)
            case _:
                return hc_types.HealthCheckResult(
                    status=hc_types.HealthCheckStatus.FAIL,
                    message=f"Unsupported operating system: {operating_system}",
                )

    async def _run_fboss_pfc_health_check(
        self,
        obj: TestDevice,
        input: hc_types.DsfPfcHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        # mode controls how PFC counters are sampled:
        #   "windowed_60" (default): read `.sum.60` — matches legacy behavior,
        #     but on fboss_hw_agent this counter races with the aggregation
        #     writer and can transiently return 0 mid-cycle.
        #   "snapshot": read monotonic `.sum` and store as pretest baseline
        #     keyed by (device, interface, priority). Always returns PASS.
        #   "check": read monotonic `.sum` and compare (current - snapshot)
        #     against threshold. Bypasses the windowed-counter race entirely.
        mode = check_params.get("mode", "windowed_60")
        if mode == "windowed_60":
            return await self._run_fboss_pfc_windowed(input)
        if mode not in ("snapshot", "check"):
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=f"Unsupported DsfPfcHealthCheck mode: {mode}",
            )
        for threshold in input.thresholds:
            for endpoint in threshold.interfaces:
                device, interface = endpoint.split(":")
                # AbstractDeviceHealthCheck is invoked once per DUT. Only run
                # this endpoint's read when the current DUT (`obj.name`) owns
                # it — otherwise we redundantly poll the same counter from
                # multiple DUT contexts, and each redundant read is a fresh
                # chance to trip fboss_hw_agent's fb303 aggregation race. The
                # non-owning DUT's HC becomes a no-op that returns PASS.
                if device != obj.name:
                    continue
                priority = int(threshold.priority)
                # fboss_hw_agent's fb303 counter reads race with the counter
                # aggregation writer; individual reads occasionally return 0
                # for counters that are actually non-zero. The race window can
                # span >1s (we've seen 15 consecutive back-to-back reads all
                # return 0 from a second HC invocation). Defense in depth:
                #   1. Take max across 3 back-to-back reads (kills brief blips)
                #   2. In check mode: if max still < prior snapshot (impossible
                #      for a truly monotonic counter), retry with 200ms sleep
                #      to let the race window pass. Up to 5 attempts.
                out_key = f"{interface}.out_pfc_frames.priority{priority}.sum"
                in_key = f"{interface}.in_pfc_frames.priority{priority}.sum"
                key = (device, interface, priority)
                baseline = self._snapshots.get(key, (0, 0))
                out_pfc_sum = 0
                in_pfc_sum = 0
                try:
                    async with await get_fb303_client(device) as client:
                        for attempt in range(5):
                            burst: list[t.Tuple[int, int]] = []
                            for _ in range(3):
                                c = await client.getSelectedCounters([out_key, in_key])
                                burst.append((c.get(out_key, 0), c.get(in_key, 0)))
                            out_pfc_sum = max(out_pfc_sum, max(r[0] for r in burst))
                            in_pfc_sum = max(in_pfc_sum, max(r[1] for r in burst))
                            # Race detection: monotonic counters can't decrease.
                            # If we've seen the baseline already, current sum
                            # must be >= baseline. If not, keep polling.
                            if mode != "check" or (
                                out_pfc_sum >= baseline[0] and in_pfc_sum >= baseline[1]
                            ):
                                break
                            self.logger.warning(
                                f"Racy zero suspected at {endpoint} priority{priority} "
                                f"(attempt {attempt + 1}/5): current out_sum={out_pfc_sum} < baseline={baseline[0]}"
                            )
                            await asyncio.sleep(0.2)
                except Exception as e:
                    return hc_types.HealthCheckResult(
                        status=hc_types.HealthCheckStatus.FAIL,
                        message=f"Failed to fetch priority{priority} monotonic counters for {device} {interface}: {str(e)}",
                    )

                if mode == "snapshot":
                    # Snapshot is idempotent per key: keep the higher of any
                    # prior snapshot vs. current read. Guards against a racy
                    # zero from a later snapshot invocation (same test, another
                    # DUT context) overwriting a valid earlier snapshot.
                    prior = self._snapshots.get(key)
                    if prior is not None:
                        out_pfc_sum = max(out_pfc_sum, prior[0])
                        in_pfc_sum = max(in_pfc_sum, prior[1])
                    self._snapshots[key] = (out_pfc_sum, in_pfc_sum)
                    self.logger.info(
                        f"Snapshotted {endpoint} priority{priority} - in_pfc_sum: {in_pfc_sum}, out_pfc_sum: {out_pfc_sum}"
                    )
                    continue

                if key not in self._snapshots:
                    return hc_types.HealthCheckResult(
                        status=hc_types.HealthCheckStatus.FAIL,
                        message=(
                            f"DsfPfcHealthCheck mode=check requires a prior snapshot for "
                            f"{device} {interface} priority{priority}; wire a mode=snapshot precheck first."
                        ),
                    )
                baseline_out, baseline_in = self._snapshots[key]
                out_pfc = max(0, out_pfc_sum - baseline_out)
                in_pfc = max(0, in_pfc_sum - baseline_in)
                self.logger.info(
                    f"At {endpoint} priority{priority} observed - in_pfc: {in_pfc}, out_pfc: {out_pfc} "
                    f"(delta from snapshot: in_sum {baseline_in}→{in_pfc_sum}, out_sum {baseline_out}→{out_pfc_sum})"
                )

                # Check out_pfc if threshold is provided
                if threshold.out_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, out_pfc, threshold.out_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "out_pfc",
                            out_pfc,
                            threshold.out_pfc,
                            threshold.comparison,
                            priority,
                        )

                # Check in_pfc if threshold is provided
                if threshold.in_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, in_pfc, threshold.in_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "in_pfc",
                            in_pfc,
                            threshold.in_pfc,
                            threshold.comparison,
                            priority,
                        )

        # Return PASS if no failures
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
        )

    async def _run_fboss_pfc_windowed(
        self,
        input: hc_types.DsfPfcHealthCheckIn,
    ) -> hc_types.HealthCheckResult:
        """Legacy windowed `.sum.60` path — preserved for backward compatibility
        with existing callers that do not opt into snapshot mode."""
        for threshold in input.thresholds:
            for endpoint in threshold.interfaces:
                device, interface = endpoint.split(":")
                priority = int(threshold.priority)
                try:
                    async with await get_fb303_client(device) as client:
                        counter = await client.getSelectedCounters(
                            [
                                f"{interface}.out_pfc_frames.priority{priority}.sum.60",
                                f"{interface}.in_pfc_frames.priority{priority}.sum.60",
                            ]
                        )
                    out_pfc = counter.get(
                        f"{interface}.out_pfc_frames.priority{priority}.sum.60", 0
                    )
                    in_pfc = counter.get(
                        f"{interface}.in_pfc_frames.priority{priority}.sum.60", 0
                    )
                    self.logger.info(
                        f"At {endpoint} priority{priority} observed - in_pfc: {in_pfc}, out_pfc: {out_pfc}"
                    )
                except Exception as e:
                    return hc_types.HealthCheckResult(
                        status=hc_types.HealthCheckStatus.FAIL,
                        message=f"Failed to fetch priority{priority} counters for {device} {interface}: {str(e)}",
                    )
                if threshold.out_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, out_pfc, threshold.out_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "out_pfc",
                            out_pfc,
                            threshold.out_pfc,
                            threshold.comparison,
                            priority,
                        )
                if threshold.in_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, in_pfc, threshold.in_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "in_pfc",
                            in_pfc,
                            threshold.in_pfc,
                            threshold.comparison,
                            priority,
                        )
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
        )

    async def _run_eos_pfc_health_check(
        self,
        obj: TestDevice,
        input: hc_types.DsfPfcHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        for threshold in input.thresholds:
            for endpoint in threshold.interfaces:
                device, interface = endpoint.split(":")
                priority = int(threshold.priority)
                try:
                    counters = await self._get_eos_pfc_counters(interface, priority)
                    out_pfc = counters["txFrames"]
                    in_pfc = counters["rxFrames"]
                    self.logger.info(
                        f"At {endpoint} priority{priority} observed - in_pfc: {in_pfc}, out_pfc: {out_pfc}"
                    )
                except Exception as e:
                    return hc_types.HealthCheckResult(
                        status=hc_types.HealthCheckStatus.FAIL,
                        message=f"Failed to fetch priority{priority} counters for {device} {interface}: {str(e)}",
                    )

                # Check out_pfc if threshold is provided
                if threshold.out_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, out_pfc, threshold.out_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "out_pfc",
                            out_pfc,
                            threshold.out_pfc,
                            threshold.comparison,
                            priority,
                        )

                # Check in_pfc if threshold is provided
                if threshold.in_pfc is not None:
                    if await self._compare_pfc(
                        threshold.comparison, in_pfc, threshold.in_pfc
                    ):
                        return await self.create_failure_result(
                            device,
                            interface,
                            "in_pfc",
                            in_pfc,
                            threshold.in_pfc,
                            threshold.comparison,
                            priority,
                        )

        # Return PASS if no failures
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
        )

    async def _get_eos_pfc_counters(
        self,
        interface: str,
        priority: int,
    ) -> t.Dict[str, int]:
        cmd = f"show interface {interface} priority-flow-control counters detail | json"
        # pyrefly: ignore [missing-attribute]
        response = await self.driver.async_execute_show_json_on_shell(cmd)
        return response["interfaces"][interface]["priorities"][str(priority)]

    async def create_failure_result(
        self,
        device: str,
        interface: str,
        pfc_type,
        observed_pfc,
        threshold_value,
        threshold_comparison,
        priority: int,
    ):
        # Use the Everpaste URL directly; it is already a clickable internalfb.com
        # link, so the throttled fburl tier (createFBUrl) is unnecessary here.
        everpaste_url = await async_everpaste_str(f"{pfc_type}: {observed_pfc}")
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.FAIL,
            message=f"Traffic on {device} {interface} for {pfc_type} (priority {priority}) exceeds the threshold of {threshold_value}. "
            f"Observed {pfc_type}: {observed_pfc}. Failure report: {everpaste_url}",
        )

    async def _compare_pfc(
        self,
        comparison: hc_types.ComparisonType,
        observed_pfc: int,
        threshold_value: int = 0,
    ) -> bool:
        """
        Helper function to compare the observed PFC value with the threshold based on the comparison type.
        """
        if comparison == hc_types.ComparisonType.LESS_THAN:
            return observed_pfc >= threshold_value
        elif comparison == hc_types.ComparisonType.GREATER_THAN:
            return observed_pfc <= threshold_value
        elif comparison == hc_types.ComparisonType.EQUAL_TO:
            return observed_pfc != threshold_value
        return False

    async def skip_check(self, obj: TestDevice) -> t.Tuple[bool, str | None]:
        supported_roles = ["RDSW", "FDSW", "EDSW", "DTSW", "RTSW", "SUSW", "BAG"]
        if obj.attributes.role not in supported_roles:
            return True, f"{obj.name}'s device role is not in {supported_roles}"
        return False, None

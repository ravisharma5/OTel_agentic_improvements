"""Multi-device parallel command execution via thread pool."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass

from mcp_telecom.connection import DeviceManager
from mcp_telecom.safety import validate_command
from mcp_telecom.vendors.mappings import get_command

logger = logging.getLogger("mcp_telecom.parallel")


def _future_timeout_seconds(device_timeout: int) -> float:
    """Budget for connect + read + margin (seconds)."""
    return float(max(60, device_timeout * 3 + 30))


@dataclass(frozen=True)
class DeviceResult:
    """Outcome of a single-device operation in a parallel batch."""

    device: str
    output: str
    success: bool
    elapsed_ms: float
    error: str | None


def format_parallel_results(results: dict[str, DeviceResult]) -> str:
    """Format parallel batch results for display."""
    if not results:
        return "No devices in batch."

    lines: list[str] = []
    lines.append("Parallel execution summary")
    lines.append("=" * 72)

    for name in sorted(results.keys()):
        r = results[name]
        status = "OK" if r.success else "FAILED"
        lines.append(f"\n[{name}] {status} — {r.elapsed_ms:.2f} ms")
        if r.error:
            lines.append(f"  Error: {r.error}")
        elif r.output:
            out = r.output.rstrip()
            if len(out) > 4000:
                out = out[:4000] + "\n  ... (truncated)"
            for part in out.splitlines():
                lines.append(f"  {part}")
        else:
            lines.append("  (no output)")

    ok = sum(1 for r in results.values() if r.success)
    lines.append("\n" + "-" * 72)
    lines.append(f"Total: {len(results)} device(s), {ok} succeeded, {len(results) - ok} failed.")
    return "\n".join(lines)


class ParallelExecutor:
    """Run commands or mapped operations across many devices in parallel."""

    def __init__(self, manager: DeviceManager) -> None:
        self._manager = manager

    def _resolve_devices(self, devices: list[str] | None) -> list[str]:
        if devices is None:
            return [d.name for d in self._manager.list_devices()]
        return list(devices)

    def _run_command_on_device(self, device_name: str, command: str) -> DeviceResult:
        start = time.perf_counter()
        try:
            config = self._manager.get_device(device_name)
            read_timeout = max(1, int(config.timeout))
            with self._manager.connect(device_name) as conn:
                raw = conn.send_command(command, read_timeout=read_timeout)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return DeviceResult(
                device=device_name,
                output=(raw or "").strip(),
                success=True,
                elapsed_ms=round(elapsed_ms, 2),
                error=None,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.warning("Parallel command failed on %s: %s", device_name, e)
            return DeviceResult(
                device=device_name,
                output="",
                success=False,
                elapsed_ms=round(elapsed_ms, 2),
                error=str(e),
            )

    def _execute_parallel(
        self,
        targets: list[str],
        build_command: str | dict[str, str],
        max_workers: int,
    ) -> dict[str, DeviceResult]:
        """Run per-device work in parallel threads."""
        if not targets:
            return {}

        cmd_by_device: dict[str, str]
        if isinstance(build_command, str):
            cmd_by_device = {n: build_command for n in targets}
        else:
            cmd_by_device = build_command

        results: dict[str, DeviceResult] = {}
        workers = max(1, min(max_workers, len(targets)))

        def task(name: str) -> DeviceResult:
            return self._run_command_on_device(name, cmd_by_device[name])

        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(task, name): name for name in targets}
            for fut, name in future_map.items():
                try:
                    cfg = self._manager.get_device(name)
                    budget = _future_timeout_seconds(cfg.timeout)
                    results[name] = fut.result(timeout=budget)
                except FuturesTimeoutError:
                    logger.error("Device %s exceeded time budget (%.1fs)", name, budget)
                    results[name] = DeviceResult(
                        device=name,
                        output="",
                        success=False,
                        elapsed_ms=round(budget * 1000, 2),
                        error=f"Execution timed out after {budget:.0f}s",
                    )
                except Exception as e:
                    results[name] = DeviceResult(
                        device=name,
                        output="",
                        success=False,
                        elapsed_ms=0.0,
                        error=str(e),
                    )

        return results

    def run_on_all(
        self,
        command: str,
        devices: list[str] | None = None,
        max_workers: int = 10,
    ) -> dict[str, str]:
        """Run a raw CLI command on all or selected devices in parallel."""
        targets = self._resolve_devices(devices)
        err = validate_command(command)
        if err is not None:
            return {name: err for name in targets}

        detailed = self._execute_parallel(targets, command.strip(), max_workers)
        return {
            name: (r.output if r.success else (r.error or "Unknown error"))
            for name, r in detailed.items()
        }

    def run_operation_on_all(
        self,
        operation: str,
        devices: list[str] | None = None,
        max_workers: int = 10,
    ) -> dict[str, str]:
        """Run a vendor-mapped operation on each device (command resolved per vendor)."""
        targets = self._resolve_devices(devices)
        cmd_map: dict[str, str] = {}
        per_device_error: dict[str, str] = {}

        for name in targets:
            try:
                cfg = self._manager.get_device(name)
                cmd = get_command(cfg.device_type, operation)
                v_err = validate_command(cmd)
                if v_err is not None:
                    per_device_error[name] = v_err
                else:
                    cmd_map[name] = cmd
            except Exception as e:
                per_device_error[name] = str(e)

        if not cmd_map and per_device_error:
            return dict(per_device_error)
        if not cmd_map:
            return {}

        results_struct = self._execute_parallel(list(cmd_map.keys()), cmd_map, max_workers)
        out: dict[str, str] = dict(per_device_error)
        for name, r in results_struct.items():
            out[name] = r.output if r.success else (r.error or "Unknown error")
        return out

    def compare_across_devices(
        self,
        operation: str,
        devices: list[str] | None = None,
        max_workers: int = 10,
    ) -> str:
        """Run a mapped operation on multiple devices and summarize similarities and differences."""
        targets = self._resolve_devices(devices)
        if not targets:
            return "No devices to compare."

        cmd_map: dict[str, str] = {}
        lines: list[str] = [f"Comparison report: operation={operation!r}", "=" * 72]

        for name in targets:
            try:
                cfg = self._manager.get_device(name)
                cmd = get_command(cfg.device_type, operation)
                v_err = validate_command(cmd)
                if v_err is not None:
                    lines.append(f"\n[{name}] skipped: {v_err}")
                else:
                    cmd_map[name] = cmd
            except Exception as e:
                lines.append(f"\n[{name}] skipped: {e}")

        if not cmd_map:
            return "\n".join(lines)

        results = self._execute_parallel(list(cmd_map.keys()), cmd_map, max_workers)

        successes = {k: v for k, v in results.items() if v.success}
        normalized = {k: " ".join(v.output.split()) for k, v in successes.items()}
        unique_outputs: dict[str, list[str]] = {}
        for dev, norm in normalized.items():
            unique_outputs.setdefault(norm, []).append(dev)

        lines.append(f"\nDevices queried: {', '.join(sorted(cmd_map.keys()))}")
        lines.append(f"Succeeded: {len(successes)} / {len(cmd_map)}")

        if len(unique_outputs) == 1 and successes:
            lines.append("\nAll successful devices returned identical normalized output.")
        elif len(unique_outputs) > 1:
            lines.append(
                f"\nFound {len(unique_outputs)} distinct output "
                f"pattern(s) (whitespace-normalized)."
            )

        for name in sorted(results.keys()):
            r = results[name]
            lines.append(f"\n--- {name} ({r.elapsed_ms:.2f} ms) ---")
            if not r.success:
                lines.append(f"FAILED: {r.error}")
                continue
            preview = r.output.strip()
            if len(preview) > 3500:
                preview = preview[:3500] + "\n... (truncated)"
            lines.append(preview or "(empty)")

        return "\n".join(lines)

    def _health_on_device(self, device_name: str) -> DeviceResult:
        start = time.perf_counter()
        try:
            status = self._manager.check_health(device_name)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if status.reachable:
                return DeviceResult(
                    device=device_name,
                    output=f"reachable, response_time_ms={status.response_time_ms}",
                    success=True,
                    elapsed_ms=round(elapsed_ms, 2),
                    error=None,
                )
            return DeviceResult(
                device=device_name,
                output="",
                success=False,
                elapsed_ms=round(elapsed_ms, 2),
                error=status.error or "unreachable",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return DeviceResult(
                device=device_name,
                output="",
                success=False,
                elapsed_ms=round(elapsed_ms, 2),
                error=str(e),
            )

    def batch_health_check(
        self,
        devices: list[str] | None = None,
        max_workers: int = 10,
    ) -> str:
        """Run health checks in parallel and return a summary string."""
        targets = self._resolve_devices(devices)
        if not targets:
            return "No devices configured for health check."

        workers = max(1, min(max_workers, len(targets)))
        results: dict[str, DeviceResult] = {}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self._health_on_device, name): name for name in targets}
            for fut, name in futures.items():
                try:
                    cfg = self._manager.get_device(name)
                    budget = _future_timeout_seconds(cfg.timeout)
                    results[name] = fut.result(timeout=budget)
                except FuturesTimeoutError:
                    results[name] = DeviceResult(
                        device=name,
                        output="",
                        success=False,
                        elapsed_ms=round(budget * 1000, 2),
                        error=f"Health check timed out after {budget:.0f}s",
                    )
                except Exception as e:
                    results[name] = DeviceResult(
                        device=name,
                        output="",
                        success=False,
                        elapsed_ms=0.0,
                        error=str(e),
                    )

        ok = sum(1 for r in results.values() if r.success)
        header = (
            f"Batch health check: {ok}/{len(results)} reachable\n"
            f"Total wall-clock batch (max per-device time shown below; parallelized)\n"
            + "-" * 72
        )
        body = format_parallel_results(results)
        return header + "\n" + body

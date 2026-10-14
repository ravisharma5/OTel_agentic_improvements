"""Tests for parallel multi-device execution."""

from __future__ import annotations

from unittest.mock import MagicMock

from mcp_telecom.parallel import DeviceResult, ParallelExecutor, format_parallel_results


class TestDeviceResult:
    def test_dataclass_fields(self):
        r = DeviceResult(
            device="r1",
            output="ok",
            success=True,
            elapsed_ms=12.5,
            error=None,
        )
        assert r.device == "r1"
        assert r.output == "ok"
        assert r.success is True
        assert r.elapsed_ms == 12.5
        assert r.error is None


class TestFormatParallelResults:
    def test_mixed_success_and_failure(self):
        results = {
            "b": DeviceResult("b", "out", True, 10.0, None),
            "a": DeviceResult("a", "", False, 5.0, "boom"),
        }
        text = format_parallel_results(results)
        assert "Parallel execution summary" in text
        assert "[a] FAILED" in text
        assert "Error: boom" in text
        assert "[b] OK" in text
        assert "out" in text
        assert "1 succeeded" in text
        assert "1 failed" in text


class TestParallelExecutor:
    def test_rejects_unsafe_command_without_connecting(self):
        manager = MagicMock()
        ex = ParallelExecutor(manager)
        out = ex.run_on_all("configure terminal", devices=["d1"])
        assert "d1" in out
        assert isinstance(out["d1"], DeviceResult)
        assert out["d1"].success is False
        assert out["d1"].error
        manager.connect.assert_not_called()
        manager.get_device.assert_not_called()

    def test_empty_devices_returns_empty(self):
        manager = MagicMock()
        ex = ParallelExecutor(manager)
        assert ex.run_on_all("show version", devices=[]) == {}

    def test_run_operation_on_all_output_is_directly_usable_by_format_parallel_results(self):
        """Same regression as run_on_all's, for run_operation_on_all -- this is
        the method server.py's parallel_operation tool actually calls (the one
        confirmed crashing live, 213 times). Had zero test coverage before this."""
        manager = MagicMock()
        device_cfg = MagicMock()
        device_cfg.device_type = "unsupported-vendor-for-this-test"
        manager.get_device.return_value = device_cfg
        ex = ParallelExecutor(manager)

        results = ex.run_operation_on_all("bgp_summary", devices=["d1", "d2"])
        text = format_parallel_results(results)  # must not raise

        assert "Parallel execution summary" in text
        assert "[d1] FAILED" in text
        assert "[d2] FAILED" in text
        assert all(isinstance(r, DeviceResult) for r in results.values())

    def test_run_on_all_output_is_directly_usable_by_format_parallel_results(self):
        """2026-10-14 regression: run_on_all used to return dict[str, str],
        but format_parallel_results() -- the only thing server.py's
        parallel_command/parallel_operation tools ever do with this return
        value -- requires dict[str, DeviceResult] (it reads .success/.error/
        .elapsed_ms off each value). That mismatch caused a deterministic
        AttributeError on every single call to both tools, confirmed live:
        213 occurrences over 9+ hours, traced to a real memory leak (each
        failed call still opened fresh SSH sessions to every device that
        never got cleaned up, since the crash happened after the device
        calls completed, before any connection teardown in the formatting
        path). This must not raise."""
        manager = MagicMock()
        ex = ParallelExecutor(manager)
        results = ex.run_on_all("configure terminal", devices=["d1", "d2"])
        text = format_parallel_results(results)  # must not raise
        assert "Parallel execution summary" in text
        assert "[d1] FAILED" in text
        assert "[d2] FAILED" in text

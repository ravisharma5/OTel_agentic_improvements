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
        assert out["d1"]
        manager.connect.assert_not_called()
        manager.get_device.assert_not_called()

    def test_empty_devices_returns_empty(self):
        manager = MagicMock()
        ex = ParallelExecutor(manager)
        assert ex.run_on_all("show version", devices=[]) == {}

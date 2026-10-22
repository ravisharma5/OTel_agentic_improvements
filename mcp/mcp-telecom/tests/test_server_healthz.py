"""Tests for mcp_telecom.server.memory_pressure_ok, the graceful-recycle
health check added after the 2026-10-22 OOM incident (see server.py's
module-level comment above memory_pressure_ok for the full writeup)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcp_telecom.server import MEMORY_HEALTHY_FRACTION, memory_pressure_ok


def _write_cgroup_files(tmp_path: Path, current: str, max_: str) -> tuple[str, str]:
    current_path = tmp_path / "memory.current"
    max_path = tmp_path / "memory.max"
    current_path.write_text(current)
    max_path.write_text(max_)
    return str(current_path), str(max_path)


class TestMemoryPressureOk:
    def test_healthy_well_under_limit(self, tmp_path):
        current_path, max_path = _write_cgroup_files(tmp_path, "100000000", "1000000000")
        assert memory_pressure_ok(current_path, max_path) is True

    def test_unhealthy_over_threshold(self, tmp_path):
        # 80% of a 1,000,000,000 limit, above the 75% threshold
        current_path, max_path = _write_cgroup_files(tmp_path, "800000000", "1000000000")
        assert memory_pressure_ok(current_path, max_path) is False

    def test_exactly_at_threshold_boundary(self, tmp_path):
        limit = 1_000_000_000
        at_threshold = int(limit * MEMORY_HEALTHY_FRACTION)
        # Strictly less-than: exactly at the threshold is still unhealthy
        current_path, max_path = _write_cgroup_files(tmp_path, str(at_threshold), str(limit))
        assert memory_pressure_ok(current_path, max_path) is False
        # One byte under is healthy
        current_path, max_path = _write_cgroup_files(tmp_path, str(at_threshold - 1), str(limit))
        assert memory_pressure_ok(current_path, max_path) is True

    def test_unlimited_cgroup_is_always_healthy(self, tmp_path):
        current_path, max_path = _write_cgroup_files(tmp_path, "999999999999", "max")
        assert memory_pressure_ok(current_path, max_path) is True

    def test_missing_files_fail_open(self, tmp_path):
        missing_current = str(tmp_path / "does-not-exist-current")
        missing_max = str(tmp_path / "does-not-exist-max")
        assert memory_pressure_ok(missing_current, missing_max) is True

    def test_malformed_content_fails_open(self, tmp_path):
        current_path, max_path = _write_cgroup_files(tmp_path, "not-a-number", "1000000000")
        assert memory_pressure_ok(current_path, max_path) is True

    def test_default_paths_do_not_raise(self):
        # On a real cgroup v2 host this reads the real values; in CI/dev
        # without that path it must still fail open rather than raise.
        assert memory_pressure_ok() in (True, False)

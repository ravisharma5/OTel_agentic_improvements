"""Tests for Prometheus metrics exporter."""

from __future__ import annotations

import pytest

try:
    import prometheus_client  # noqa: F401

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


class TestMetricsExporter:
    def test_can_instantiate(self):
        import mcp_telecom.metrics as m

        assert isinstance(m.metrics_exporter, m.MetricsExporter)

    def test_module_imports_cleanly(self):
        import mcp_telecom.metrics as m

        assert hasattr(m, "MetricsExporter")
        assert hasattr(m, "metrics_exporter")

    @pytest.mark.skipif(not _HAS_PROMETHEUS, reason="prometheus_client not installed")
    def test_register_device_metrics_idempotent(self):
        import mcp_telecom.metrics as m

        m.metrics_exporter.register_device_metrics()
        m.metrics_exporter.register_device_metrics()
        assert m.metrics_exporter._registered is True

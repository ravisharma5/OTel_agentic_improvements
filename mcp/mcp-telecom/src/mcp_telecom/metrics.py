"""Prometheus metrics exporter for MCP-Telecom.

Optional dependency: install ``prometheus_client`` to enable metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram

try:
    from prometheus_client import (
        Counter as _Counter,
    )
    from prometheus_client import (
        Gauge as _Gauge,
    )
    from prometheus_client import (
        Histogram as _Histogram,
    )
    from prometheus_client import (
        generate_latest,
    )
    from prometheus_client import (
        start_http_server as _start_http_server,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _Counter = _Gauge = _Histogram = None  # type: ignore[misc, assignment]
    generate_latest = None  # type: ignore[assignment]
    _start_http_server = None  # type: ignore[assignment]
    _PROMETHEUS_AVAILABLE = False


def _require_prometheus() -> None:
    if not _PROMETHEUS_AVAILABLE:
        raise RuntimeError(
            "prometheus_client is not installed. Install with: pip install prometheus_client"
        )


class MetricsExporter:
    """Registers and updates Prometheus metrics for MCP-Telecom."""

    def __init__(self) -> None:
        self._registered = False
        self._device_up: Gauge | None = None
        self._response_ms: Gauge | None = None
        self._commands_total: Counter | None = None
        self._command_duration: Histogram | None = None
        self._devices_total: Gauge | None = None
        self._active_connections: Gauge | None = None
        self._snmp_polls_total: Counter | None = None
        self._compliance_score: Gauge | None = None
        self._seen_devices: set[str] = set()
        if _PROMETHEUS_AVAILABLE:
            self.register_device_metrics()

    def register_device_metrics(self) -> None:
        """Register Prometheus gauge, counter, and histogram metrics."""
        _require_prometheus()
        if self._registered:
            return

        self._device_up = _Gauge(
            "mcp_telecom_device_up",
            "Whether the device is reachable (1) or not (0).",
            ["device", "vendor", "host"],
        )
        self._response_ms = _Gauge(
            "mcp_telecom_device_response_ms",
            "Last observed health check response time in milliseconds.",
            ["device"],
        )
        self._commands_total = _Counter(
            "mcp_telecom_commands_total",
            "Total MCP tool command invocations per device.",
            ["device", "tool", "status"],
        )
        self._command_duration = _Histogram(
            "mcp_telecom_command_duration_seconds",
            "Command execution duration in seconds.",
            ["device", "tool"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        )
        self._devices_total = _Gauge(
            "mcp_telecom_devices_total",
            "Number of distinct devices that have reported status.",
        )
        self._active_connections = _Gauge(
            "mcp_telecom_active_connections",
            "Active connection indicator per device (1 if last health check succeeded).",
            ["device"],
        )
        self._snmp_polls_total = _Counter(
            "mcp_telecom_snmp_polls_total",
            "Total SNMP poll operations.",
            ["device", "oid"],
        )
        self._compliance_score = _Gauge(
            "mcp_telecom_compliance_score",
            "Last recorded compliance score per device (0-100).",
            ["device"],
        )
        self._registered = True

    def update_device_status(
        self,
        device: str,
        vendor: str,
        host: str,
        reachable: bool,
        response_ms: float | None,
    ) -> None:
        _require_prometheus()
        assert self._device_up is not None
        self._device_up.labels(device=device, vendor=vendor, host=host).set(1 if reachable else 0)
        assert self._response_ms is not None
        self._response_ms.labels(device=device).set(float(response_ms or 0.0))
        assert self._active_connections is not None
        self._active_connections.labels(device=device).set(1 if reachable else 0)
        self._seen_devices.add(device)
        assert self._devices_total is not None
        self._devices_total.set(len(self._seen_devices))

    def record_command(
        self,
        device: str,
        tool: str,
        success: bool,
        duration_seconds: float,
    ) -> None:
        _require_prometheus()
        status = "success" if success else "failure"
        assert self._commands_total is not None
        self._commands_total.labels(device=device, tool=tool, status=status).inc()
        assert self._command_duration is not None
        self._command_duration.labels(device=device, tool=tool).observe(max(0.0, duration_seconds))

    def update_compliance_score(self, device: str, score: float) -> None:
        _require_prometheus()
        assert self._compliance_score is not None
        self._compliance_score.labels(device=device).set(float(score))

    def get_metrics_text(self) -> str:
        """Return metrics in Prometheus text exposition format."""
        _require_prometheus()
        assert generate_latest is not None
        return generate_latest().decode("utf-8")

    def start_http_server(self, port: int = 9090) -> None:
        """Start a background HTTP server exposing ``/metrics``."""
        _require_prometheus()
        assert _start_http_server is not None
        _start_http_server(port)


metrics_exporter = MetricsExporter()

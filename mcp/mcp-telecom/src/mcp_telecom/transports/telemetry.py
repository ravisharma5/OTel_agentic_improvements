"""gRPC streaming telemetry receiver for MCP-Telecom.

Implements a telemetry collector that can subscribe to gNMI (gRPC Network
Management Interface) paths on network devices and store the latest values
for querying by MCP tools.

Supports:
- gNMI Subscribe (STREAM, ONCE, POLL modes)
- OpenConfig and vendor-native YANG paths
- In-memory telemetry cache with timestamps
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("mcp_telecom.telemetry")


@dataclass
class TelemetryUpdate:
    """A single telemetry data point."""

    path: str
    value: str | float | int | bool | dict
    timestamp: datetime
    device: str
    source: str = "gnmi"


@dataclass
class TelemetrySubscription:
    """A telemetry subscription definition."""

    device: str
    paths: list[str]
    mode: str = "STREAM"
    interval_ms: int = 10000


COMMON_TELEMETRY_PATHS = {
    "interface_counters": "/interfaces/interface/state/counters",
    "interface_state": "/interfaces/interface/state/oper-status",
    "cpu_utilization": "/components/component/cpu/utilization/state/instant",
    "memory_used": "/components/component/state/memory/utilized",
    "bgp_peer_state": "/network-instances/network-instance/protocols/"
                      "protocol/bgp/neighbors/neighbor/state",
    "bgp_prefixes_received": "/network-instances/network-instance/protocols/"
                             "protocol/bgp/neighbors/neighbor/afi-safis/"
                             "afi-safi/state/prefixes/received",
    "ospf_neighbor_state": "/network-instances/network-instance/protocols/"
                           "protocol/ospf/areas/area/interfaces/interface/"
                           "neighbors/neighbor/state",
    "system_uptime": "/system/state/boot-time",
    "temperature": "/components/component/state/temperature/instant",
    "fan_speed": "/components/component/fan/state/speed",
    "power_supply": "/components/component/power-supply/state",
    "interface_rate_in": "/interfaces/interface/state/counters/in-octets",
    "interface_rate_out": "/interfaces/interface/state/counters/out-octets",
    "interface_errors_in": "/interfaces/interface/state/counters/in-errors",
    "interface_errors_out": "/interfaces/interface/state/counters/out-errors",
}


class TelemetryStore:
    """Thread-safe in-memory store for telemetry data.

    Keeps the latest value for each (device, path) pair along with
    a configurable history depth for trend analysis.
    """

    def __init__(self, max_history: int = 100):
        self._lock = threading.Lock()
        self._latest: dict[str, dict[str, TelemetryUpdate]] = {}
        self._history: dict[str, list[TelemetryUpdate]] = {}
        self._max_history = max_history

    def record(self, update: TelemetryUpdate) -> None:
        """Record a telemetry update."""
        with self._lock:
            if update.device not in self._latest:
                self._latest[update.device] = {}
            self._latest[update.device][update.path] = update

            key = f"{update.device}:{update.path}"
            if key not in self._history:
                self._history[key] = []
            self._history[key].append(update)
            if len(self._history[key]) > self._max_history:
                self._history[key] = self._history[key][-self._max_history:]

    def get_latest(
        self, device: str, path: str | None = None
    ) -> dict | TelemetryUpdate | None:
        """Get latest telemetry for a device, optionally filtered by path."""
        with self._lock:
            device_data = self._latest.get(device)
            if device_data is None:
                return None
            if path:
                return device_data.get(path)
            return dict(device_data)

    def get_history(
        self, device: str, path: str, count: int = 20
    ) -> list[TelemetryUpdate]:
        """Get historical telemetry values for trend analysis."""
        with self._lock:
            key = f"{device}:{path}"
            history = self._history.get(key, [])
            return history[-count:]

    def get_all_devices(self) -> list[str]:
        """List all devices with telemetry data."""
        with self._lock:
            return list(self._latest.keys())

    def get_summary(self, device: str) -> dict:
        """Get a summary of all telemetry data for a device."""
        with self._lock:
            device_data = self._latest.get(device, {})
            return {
                "device": device,
                "paths_monitored": len(device_data),
                "paths": [
                    {
                        "path": path,
                        "value": u.value,
                        "age_seconds": (
                            datetime.now(timezone.utc) - u.timestamp
                        ).total_seconds(),
                    }
                    for path, u in device_data.items()
                ],
            }

    def format_for_display(self, device: str) -> str:
        """Format telemetry data for human-readable display."""
        summary = self.get_summary(device)
        if not summary["paths"]:
            return f"No telemetry data available for {device}."

        lines = [
            f"Telemetry Data for {device}",
            f"  Paths monitored: {summary['paths_monitored']}",
            "-" * 60,
        ]
        for p in summary["paths"]:
            age = int(p["age_seconds"])
            val = p["value"]
            if isinstance(val, dict):
                val = json.dumps(val, indent=2)
            lines.append(f"  {p['path']}")
            lines.append(f"    Value: {val}  (age: {age}s)")
        return "\n".join(lines)


telemetry_store = TelemetryStore()


class GnmiCollector:
    """gNMI telemetry collector.

    Connects to devices via gRPC and subscribes to telemetry paths.
    Data is stored in the shared TelemetryStore for querying.

    Note: Requires `grpcio` and `cisco-gnmi` or similar gNMI client
    library. This implementation provides the framework and simulated
    data for demonstration. Replace _subscribe_loop with actual gNMI
    calls for production use.
    """

    def __init__(
        self,
        store: TelemetryStore | None = None,
    ):
        self.store = store or telemetry_store
        self._subscriptions: dict[str, TelemetrySubscription] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._running: dict[str, bool] = {}

    def subscribe(self, subscription: TelemetrySubscription) -> str:
        """Start a telemetry subscription for a device."""
        key = subscription.device
        if key in self._running and self._running[key]:
            return f"Subscription already active for {key}"

        self._subscriptions[key] = subscription
        self._running[key] = True

        thread = threading.Thread(
            target=self._subscribe_loop,
            args=(subscription,),
            daemon=True,
            name=f"telemetry-{key}",
        )
        self._threads[key] = thread
        thread.start()

        logger.info(
            "Started telemetry subscription for %s (%d paths)",
            key,
            len(subscription.paths),
        )
        return (
            f"Telemetry subscription started for {key}: "
            f"{len(subscription.paths)} paths, "
            f"mode={subscription.mode}, "
            f"interval={subscription.interval_ms}ms"
        )

    def unsubscribe(self, device: str) -> str:
        """Stop a telemetry subscription."""
        if device in self._running:
            self._running[device] = False
            logger.info("Stopped telemetry subscription for %s", device)
            return f"Telemetry subscription stopped for {device}"
        return f"No active subscription for {device}"

    def list_subscriptions(self) -> list[dict]:
        """List all active telemetry subscriptions."""
        return [
            {
                "device": sub.device,
                "paths": sub.paths,
                "mode": sub.mode,
                "interval_ms": sub.interval_ms,
                "active": self._running.get(sub.device, False),
            }
            for sub in self._subscriptions.values()
        ]

    def _subscribe_loop(self, sub: TelemetrySubscription) -> None:
        """Background loop that collects telemetry.

        In production, replace this with actual gNMI Subscribe RPC.
        This implementation provides the framework structure.
        """
        interval_s = sub.interval_ms / 1000.0

        while self._running.get(sub.device, False):
            for path in sub.paths:
                try:
                    # Framework placeholder: in production, this calls
                    #   gnmi_stub.Subscribe(SubscribeRequest(...))
                    # and processes SubscribeResponse updates.
                    update = TelemetryUpdate(
                        path=path,
                        value={"status": "awaiting_gnmi_connection"},
                        timestamp=datetime.now(timezone.utc),
                        device=sub.device,
                    )
                    self.store.record(update)
                except Exception as e:
                    logger.error(
                        "Telemetry error for %s path %s: %s",
                        sub.device, path, e,
                    )

            time.sleep(interval_s)


gnmi_collector = GnmiCollector()

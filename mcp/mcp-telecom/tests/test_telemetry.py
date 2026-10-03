"""Tests for streaming telemetry components."""

from datetime import datetime, timezone

from mcp_telecom.transports.telemetry import (
    COMMON_TELEMETRY_PATHS,
    TelemetryStore,
    TelemetrySubscription,
    TelemetryUpdate,
)


class TestTelemetryStore:
    def test_record_and_get_latest(self):
        store = TelemetryStore()
        update = TelemetryUpdate(
            path="/interfaces/interface/state/counters",
            value={"in_octets": 1000},
            timestamp=datetime.now(timezone.utc),
            device="router1",
        )
        store.record(update)
        latest = store.get_latest("router1", update.path)
        assert latest is not None
        assert latest.value == {"in_octets": 1000}

    def test_get_latest_all_paths(self):
        store = TelemetryStore()
        for i in range(3):
            store.record(TelemetryUpdate(
                path=f"/path/{i}",
                value=i,
                timestamp=datetime.now(timezone.utc),
                device="r1",
            ))
        result = store.get_latest("r1")
        assert isinstance(result, dict)
        assert len(result) == 3

    def test_get_latest_unknown_device(self):
        store = TelemetryStore()
        assert store.get_latest("nonexistent") is None

    def test_history(self):
        store = TelemetryStore()
        for i in range(5):
            store.record(TelemetryUpdate(
                path="/test", value=i,
                timestamp=datetime.now(timezone.utc),
                device="r1",
            ))
        history = store.get_history("r1", "/test", 3)
        assert len(history) == 3
        assert history[0].value == 2

    def test_history_max_cap(self):
        store = TelemetryStore(max_history=10)
        for i in range(20):
            store.record(TelemetryUpdate(
                path="/cap", value=i,
                timestamp=datetime.now(timezone.utc),
                device="r1",
            ))
        history = store.get_history("r1", "/cap", 100)
        assert len(history) == 10

    def test_get_all_devices(self):
        store = TelemetryStore()
        for dev in ["r1", "r2", "r3"]:
            store.record(TelemetryUpdate(
                path="/test", value=0,
                timestamp=datetime.now(timezone.utc),
                device=dev,
            ))
        assert sorted(store.get_all_devices()) == ["r1", "r2", "r3"]

    def test_get_summary(self):
        store = TelemetryStore()
        store.record(TelemetryUpdate(
            path="/test", value=42,
            timestamp=datetime.now(timezone.utc),
            device="r1",
        ))
        summary = store.get_summary("r1")
        assert summary["device"] == "r1"
        assert summary["paths_monitored"] == 1

    def test_format_for_display(self):
        store = TelemetryStore()
        store.record(TelemetryUpdate(
            path="/cpu", value=55.2,
            timestamp=datetime.now(timezone.utc),
            device="r1",
        ))
        text = store.format_for_display("r1")
        assert "r1" in text
        assert "55.2" in text

    def test_format_empty_device(self):
        store = TelemetryStore()
        text = store.format_for_display("unknown")
        assert "No telemetry data" in text


class TestTelemetrySubscription:
    def test_create_subscription(self):
        sub = TelemetrySubscription(
            device="r1",
            paths=["/interfaces", "/bgp"],
            interval_ms=5000,
        )
        assert sub.device == "r1"
        assert len(sub.paths) == 2
        assert sub.mode == "STREAM"


class TestCommonPaths:
    def test_paths_exist(self):
        assert "interface_counters" in COMMON_TELEMETRY_PATHS
        assert "cpu_utilization" in COMMON_TELEMETRY_PATHS
        assert "bgp_peer_state" in COMMON_TELEMETRY_PATHS

    def test_paths_are_openconfig_format(self):
        for name, path in COMMON_TELEMETRY_PATHS.items():
            assert path.startswith("/"), f"{name} path should start with /"

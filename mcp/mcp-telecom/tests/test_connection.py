"""Tests for the connection manager."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from mcp_telecom.connection import DeviceManager
from mcp_telecom.models import DeviceConfig, VendorType


class TestDeviceManager:
    def test_empty_manager(self):
        dm = DeviceManager()
        assert dm.list_devices() == []

    def test_add_device(self):
        dm = DeviceManager()
        config = DeviceConfig(
            device_type=VendorType.NOKIA_SROS,
            host="192.168.1.1",
            username="testuser",
            password="testpass",  # noqa: S106
        )
        dm.add_device("test-router", config)
        devices = dm.list_devices()
        assert len(devices) == 1
        assert devices[0].name == "test-router"

    def test_remove_device(self):
        dm = DeviceManager()
        config = DeviceConfig(
            device_type=VendorType.NOKIA_SROS,
            host="192.168.1.1",
            username="testuser",
            password="testpass",  # noqa: S106
        )
        dm.add_device("test-router", config)
        assert dm.remove_device("test-router") is True
        assert dm.list_devices() == []

    def test_remove_nonexistent_device(self):
        dm = DeviceManager()
        assert dm.remove_device("nonexistent") is False

    def test_get_device(self):
        dm = DeviceManager()
        config = DeviceConfig(
            device_type=VendorType.CISCO_IOS,
            host="10.0.0.1",
            username="testuser",
            password="testpass",  # noqa: S106
        )
        dm.add_device("switch1", config)
        retrieved = dm.get_device("switch1")
        assert retrieved.host == "10.0.0.1"

    def test_get_unknown_device_raises(self):
        dm = DeviceManager()
        with pytest.raises(ValueError, match="Unknown device"):
            dm.get_device("nonexistent")

    def test_load_config_from_yaml(self):
        yaml_content = """
router1:
  device_type: nokia_sros
  host: 192.168.1.1
  username: testuser
  password: testpass
  port: 22
router2:
  device_type: cisco_ios
  host: 192.168.2.1
  username: testuser
  password: testpass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            tmp_path = f.name

        try:
            dm = DeviceManager(tmp_path)
            devices = dm.list_devices()
            assert len(devices) == 2
            names = [d.name for d in devices]
            assert "router1" in names
            assert "router2" in names
        finally:
            os.unlink(tmp_path)

    def test_load_missing_config(self):
        dm = DeviceManager("/nonexistent/path.yaml")
        assert dm.list_devices() == []

    def test_list_devices_sorted(self):
        dm = DeviceManager()
        for name in ["zebra", "alpha", "middle"]:
            dm.add_device(
                name,
                DeviceConfig(
                    device_type=VendorType.NOKIA_SROS,
                    host="1.1.1.1",
                    username="testuser",
                    password="testpass",  # noqa: S106
                ),
            )
        names = [d.name for d in dm.list_devices()]
        assert names == sorted(names)


class TestConnectReuse:
    """Regression tests for #(connection-pooling fix): connect() used to open
    a fresh ConnectHandler and disconnect it on every single call -- the
    ConnectionPool it now checks out from (and returns to) exists precisely
    so a second call to the same device doesn't pay that cost again."""

    def _manager_with_device(self) -> DeviceManager:
        dm = DeviceManager()
        dm.add_device(
            "r1",
            DeviceConfig(
                device_type=VendorType.NOKIA_SROS,
                host="192.168.1.1",
                username="testuser",
                password="testpass",  # noqa: S106
            ),
        )
        return dm

    def test_second_call_reuses_pooled_connection(self):
        dm = self._manager_with_device()
        fake_conn = MagicMock()
        fake_conn.is_alive.return_value = True
        with patch("mcp_telecom.pool.ConnectHandler", return_value=fake_conn) as mock_handler:
            with dm.connect("r1") as conn1:
                conn1.send_command("show version")
            with dm.connect("r1") as conn2:
                conn2.send_command("show version")
        # One real ConnectHandler() call for both uses -- the second checked
        # the same connection back out of the pool instead of opening a new one.
        assert mock_handler.call_count == 1
        assert conn1 is conn2

    def test_failed_connection_is_not_pooled(self):
        dm = self._manager_with_device()
        with patch("mcp_telecom.pool.ConnectHandler", side_effect=RuntimeError("boom")):
            with pytest.raises(ConnectionError):
                with dm.connect("r1"):
                    pass
        stats = dm.pool.get_stats()
        assert stats["total_connections"] == 0

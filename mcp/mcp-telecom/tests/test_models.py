"""Tests for data models."""


from mcp_telecom.models import (
    CommandResult,
    DeviceConfig,
    HealthStatus,
    VendorType,
)


class TestVendorType:
    def test_nokia_sros(self):
        assert VendorType.NOKIA_SROS.value == "nokia_sros"

    def test_cisco_iosxr(self):
        assert VendorType.CISCO_IOSXR.value == "cisco_xr"

    def test_juniper_junos(self):
        assert VendorType.JUNIPER_JUNOS.value == "juniper_junos"

    def test_all_vendors_have_values(self):
        for vendor in VendorType:
            assert vendor.value is not None
            assert len(vendor.value) > 0


class TestDeviceConfig:
    def test_basic_config(self):
        config = DeviceConfig(
            device_type=VendorType.NOKIA_SROS,
            host="192.168.1.1",
            username="admin",
            password="testpass",  # noqa: S106
        )
        assert config.host == "192.168.1.1"
        assert config.port == 22
        assert config.timeout == 30

    def test_custom_port(self):
        config = DeviceConfig(
            device_type=VendorType.CISCO_IOS,
            host="10.0.0.1",
            username="admin",
            password="testpass",  # noqa: S106
            port=2222,
        )
        assert config.port == 2222

    def test_password_not_in_repr(self):
        config = DeviceConfig(
            device_type=VendorType.NOKIA_SROS,
            host="192.168.1.1",
            username="admin",
            password="testpass_hidden",  # noqa: S106
        )
        assert "testpass_hidden" not in repr(config)


class TestCommandResult:
    def test_success_result(self):
        result = CommandResult(
            device="router1",
            command="show version",
            output="Nokia SR OS 22.10",
            vendor=VendorType.NOKIA_SROS,
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = CommandResult(
            device="router1",
            command="show version",
            output="",
            vendor=VendorType.NOKIA_SROS,
            success=False,
            error="Connection timeout",
        )
        assert result.success is False
        assert "timeout" in result.error.lower()


class TestHealthStatus:
    def test_healthy(self):
        status = HealthStatus(
            device="router1",
            reachable=True,
            response_time_ms=42.5,
        )
        assert status.reachable is True

    def test_unreachable(self):
        status = HealthStatus(
            device="router1",
            reachable=False,
            error="Connection refused",
        )
        assert status.reachable is False

"""Shared test fixtures for MCP-Telecom tests."""

import pytest

from mcp_telecom.connection import DeviceManager
from mcp_telecom.models import DeviceConfig, VendorType


@pytest.fixture
def device_manager():
    """Create a DeviceManager with test devices (no real connections)."""
    dm = DeviceManager()
    dm.add_device(
        "test-nokia",
        DeviceConfig(
            device_type=VendorType.NOKIA_SROS,
            host="192.168.1.1",
            username="testuser",
            password="testpass",  # noqa: S106
        ),
    )
    dm.add_device(
        "test-cisco",
        DeviceConfig(
            device_type=VendorType.CISCO_IOS,
            host="192.168.2.1",
            username="testuser",
            password="testpass",  # noqa: S106
        ),
    )
    dm.add_device(
        "test-juniper",
        DeviceConfig(
            device_type=VendorType.JUNIPER_JUNOS,
            host="192.168.3.1",
            username="testuser",
            password="testpass",  # noqa: S106
        ),
    )
    return dm

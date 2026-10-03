"""Tests for vendor command mappings."""

import pytest

from mcp_telecom.models import VendorType
from mcp_telecom.vendors.mappings import (
    VENDOR_COMMANDS,
    get_command,
    list_operations,
)


class TestGetCommand:
    def test_nokia_bgp_summary(self):
        cmd = get_command(VendorType.NOKIA_SROS, "bgp_summary")
        assert cmd == "show router bgp summary"

    def test_cisco_bgp_summary(self):
        cmd = get_command(VendorType.CISCO_IOS, "bgp_summary")
        assert cmd == "show ip bgp summary"

    def test_cisco_xr_bgp_summary(self):
        cmd = get_command(VendorType.CISCO_IOSXR, "bgp_summary")
        assert cmd == "show bgp summary"

    def test_juniper_bgp_summary(self):
        cmd = get_command(VendorType.JUNIPER_JUNOS, "bgp_summary")
        assert cmd == "show bgp summary"

    def test_arista_bgp_summary(self):
        cmd = get_command(VendorType.ARISTA_EOS, "bgp_summary")
        assert cmd == "show ip bgp summary"

    def test_interface_detail_with_param(self):
        cmd = get_command(VendorType.CISCO_IOS, "interface_detail", interface="Gi0/0/0")
        assert "Gi0/0/0" in cmd

    def test_nokia_interface_detail_with_param(self):
        cmd = get_command(VendorType.NOKIA_SROS, "interface_detail", interface="1/1/1")
        assert "1/1/1" in cmd

    def test_unknown_operation_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            get_command(VendorType.NOKIA_SROS, "nonexistent_operation")

    def test_all_vendors_have_bgp_summary(self):
        for vendor in VendorType:
            cmds = VENDOR_COMMANDS.get(vendor, {})
            if cmds:
                assert "bgp_summary" in cmds, f"{vendor} missing bgp_summary"


class TestListOperations:
    def test_nokia_operations(self):
        ops = list_operations(VendorType.NOKIA_SROS)
        assert "bgp_summary" in ops
        assert "interfaces" in ops
        assert "alarms" in ops

    def test_cisco_operations(self):
        ops = list_operations(VendorType.CISCO_IOS)
        assert "bgp_summary" in ops
        assert "vlan_brief" in ops

    def test_juniper_operations(self):
        ops = list_operations(VendorType.JUNIPER_JUNOS)
        assert "bgp_summary" in ops
        assert "firewall_filters" in ops

    def test_operations_are_sorted(self):
        for vendor in VendorType:
            ops = list_operations(vendor)
            assert ops == sorted(ops)


class TestVendorCoverage:
    """Ensure all vendors have a minimum set of common operations."""

    COMMON_OPERATIONS = [
        "bgp_summary",
        "interfaces",
        "interface_detail",
        "system_info",
        "version",
        "routing_table",
        "config_running",
        "log_events",
        "arp_table",
    ]

    @pytest.mark.parametrize("vendor", [v for v in VendorType if v != VendorType.NOKIA_SROS_TELNET])
    def test_common_operations_exist(self, vendor):
        ops = list_operations(vendor)
        for op in self.COMMON_OPERATIONS:
            assert op in ops, f"{vendor.value} missing common operation: {op}"

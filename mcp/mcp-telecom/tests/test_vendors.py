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


# 2026-10-14: NOKIA_SRLINUX excluded alongside NOKIA_SROS_TELNET -- SR
# Linux's confirmed top-level `show` command tree (verified live against a
# real device) has no config_running equivalent at all. Its real
# running-config mechanism is a separate `info` CLI verb, not a `show`
# command, which this project's show/display/ping/traceroute-only safety
# model doesn't support. See mappings.py's NOKIA_SRLINUX entry for the full
# reasoning -- faking this mapping would be actively wrong, not just
# incomplete. Module-level (not a class attribute) because pytest.mark.
# parametrize's decorator expression can't see other names in its own
# enclosing class body.
_VENDORS_WITHOUT_FULL_COMMON_COVERAGE = {VendorType.NOKIA_SROS_TELNET, VendorType.NOKIA_SRLINUX}


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

    @pytest.mark.parametrize(
        "vendor", [v for v in VendorType if v not in _VENDORS_WITHOUT_FULL_COMMON_COVERAGE]
    )
    def test_common_operations_exist(self, vendor):
        ops = list_operations(vendor)
        for op in self.COMMON_OPERATIONS:
            assert op in ops, f"{vendor.value} missing common operation: {op}"


class TestNokiaSrLinuxMapping:
    """2026-10-14: devices.yaml's r1/r2/r3 were configured as nokia_sros but
    are actually running SR Linux -- a different Nokia NOS with incompatible
    CLI syntax (confirmed live: SR Linux rejects "show router bgp summary",
    SR OS's command, with "Unknown token 'router'"). These tests pin the
    commands that were verified live against a real device (2026-10-14) so a
    future refactor can't silently drift back to SR OS-style syntax."""

    def test_bgp_summary_uses_network_instance_syntax_not_sros_syntax(self):
        cmd = get_command(VendorType.NOKIA_SRLINUX, "bgp_summary")
        assert cmd == "show network-instance default protocols bgp summary"
        assert cmd != get_command(VendorType.NOKIA_SROS, "bgp_summary")

    def test_system_info_and_uptime_both_use_show_version(self):
        # SR Linux has no "show system information" (confirmed live: SR
        # Linux's "system" subtree doesn't include "information" as a
        # child) or dedicated uptime command -- show version covers both.
        assert get_command(VendorType.NOKIA_SRLINUX, "system_info") == "show version"
        assert get_command(VendorType.NOKIA_SRLINUX, "uptime") == "show version"

    def test_interface_detail_with_param(self):
        cmd = get_command(VendorType.NOKIA_SRLINUX, "interface_detail", interface="ethernet-1/1")
        assert "ethernet-1/1" in cmd

    def test_config_running_not_mapped(self):
        """Must raise, not silently return a wrong/empty command -- SR
        Linux's real config-display mechanism isn't a `show` command at all."""
        with pytest.raises(ValueError, match="not supported"):
            get_command(VendorType.NOKIA_SRLINUX, "config_running")

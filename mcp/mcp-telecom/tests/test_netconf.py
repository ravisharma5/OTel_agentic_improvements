"""Tests for NETCONF transport (unit tests without real devices)."""


from mcp_telecom.transports.netconf import (
    VENDOR_DEVICE_TYPE_MAP,
    YANG_FILTERS,
    xml_to_text,
)


class TestXmlToText:
    def test_valid_xml(self):
        xml = "<root><child>value</child></root>"
        result = xml_to_text(xml)
        assert "<root>" in result
        assert "value" in result

    def test_invalid_xml_passthrough(self):
        bad = "not xml at all"
        assert xml_to_text(bad) == bad

    def test_nested_xml(self):
        xml = "<a><b><c>deep</c></b></a>"
        result = xml_to_text(xml)
        assert "deep" in result


class TestVendorMappings:
    def test_all_vendors_mapped(self):
        expected = [
            "nokia_sros", "cisco_xr", "cisco_ios",
            "juniper_junos",
        ]
        for vendor in expected:
            assert vendor in VENDOR_DEVICE_TYPE_MAP

    def test_ncclient_types_valid(self):
        valid_types = {
            "alu", "iosxr", "csr", "nexus", "junos", "default",
        }
        for vendor, ncc_type in VENDOR_DEVICE_TYPE_MAP.items():
            assert ncc_type in valid_types, (
                f"{vendor} maps to unknown ncclient type: {ncc_type}"
            )


class TestYangFilters:
    def test_system_info_filters_exist(self):
        assert "system_info" in YANG_FILTERS
        filters = YANG_FILTERS["system_info"]
        assert "nokia_sros" in filters or "openconfig" in filters

    def test_interfaces_filters_exist(self):
        assert "interfaces" in YANG_FILTERS

    def test_bgp_filters_exist(self):
        assert "bgp_summary" in YANG_FILTERS

    def test_filters_are_xml(self):
        for operation, filters in YANG_FILTERS.items():
            for vendor, xml in filters.items():
                assert "<" in xml, (
                    f"{operation}/{vendor} filter not valid XML"
                )

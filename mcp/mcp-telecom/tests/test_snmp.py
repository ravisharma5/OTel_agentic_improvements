"""Tests for SNMP transport helpers."""

from __future__ import annotations

import pytest

import mcp_telecom.transports.snmp as snmp_module
from mcp_telecom.transports.snmp import format_snmp_results, get_device_mibs


def _oid_constant_names() -> list[str]:
    return [
        n
        for n in dir(snmp_module)
        if n.isupper() and not n.startswith("_") and n not in ("PYSNMP_AVAILABLE",)
    ]


class TestSnmpOids:
    def test_oid_constants_are_strings_starting_with_private_enterprise_tree(self):
        for name in _oid_constant_names():
            val = getattr(snmp_module, name)
            if not isinstance(val, str):
                continue
            assert val.startswith("1.3.6"), f"{name}={val!r}"


class TestFormatSnmpResults:
    def test_tuple_rows(self):
        text = format_snmp_results([("1.3.6.1.2.1.1.1.0", "Router")])
        assert "1.3.6.1.2.1.1.1.0 = Router" in text

    def test_mapping_rows(self):
        text = format_snmp_results([{"oid": "1.3.6.1.2.1.1.5.0", "value": "r1"}])
        assert "1.3.6.1.2.1.1.5.0 = r1" in text


class TestGetDeviceMibs:
    @pytest.mark.parametrize(
        "device_type",
        ["cisco_ios", "juniper_junos", "nokia_sros"],
    )
    def test_known_vendors_return_non_empty_lists(self, device_type: str):
        mibs = get_device_mibs(device_type)
        assert isinstance(mibs, list)
        assert len(mibs) > 0
        assert all(isinstance(x, str) for x in mibs)


class TestSnmpModuleImport:
    def test_import_cleanly(self):
        import mcp_telecom.transports.snmp  # noqa: F401

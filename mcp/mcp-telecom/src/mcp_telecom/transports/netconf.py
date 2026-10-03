"""NETCONF/YANG transport for MCP-Telecom.

Provides structured data retrieval from network devices using NETCONF
protocol with YANG data models. This is a programmatic alternative to
screen-scraping CLI output via SSH.

Supports:
- Nokia SR OS (YANG models)
- Cisco IOS-XR (native + OpenConfig YANG)
- Juniper Junos (native YANG)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger("mcp_telecom.netconf")

NETCONF_PORT_MAP = {
    "nokia_sros": 830,
    "cisco_xr": 830,
    "cisco_ios": 830,
    "juniper_junos": 830,
    "arista_eos": 830,
}

VENDOR_DEVICE_TYPE_MAP = {
    "nokia_sros": "alu",
    "nokia_sros_telnet": "alu",
    "cisco_xr": "iosxr",
    "cisco_ios": "csr",
    "cisco_nxos": "nexus",
    "juniper_junos": "junos",
    "arista_eos": "default",
}

YANG_FILTERS: dict[str, dict[str, str]] = {
    "system_info": {
        "nokia_sros": """
            <state xmlns="urn:nokia.com:sros:ns:yang:sr:state">
                <system><oper-name/><version/><up-time/></system>
            </state>""",
        "cisco_xr": """
            <system-time xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-shellutil-oper"/>
        """,
        "juniper_junos": """
            <system-information xmlns="http://yang.juniper.net/junos/rpc"/>
        """,
        "openconfig": """
            <system xmlns="http://openconfig.net/yang/system">
                <state/>
            </system>""",
    },
    "interfaces": {
        "openconfig": """
            <interfaces xmlns="http://openconfig.net/yang/interfaces">
                <interface><name/><state/></interface>
            </interfaces>""",
        "nokia_sros": """
            <state xmlns="urn:nokia.com:sros:ns:yang:sr:state">
                <port/>
            </state>""",
        "cisco_xr": """
            <interfaces xmlns="http://openconfig.net/yang/interfaces"/>
        """,
        "juniper_junos": """
            <interfaces-state xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>
        """,
    },
    "bgp_summary": {
        "openconfig": """
            <bgp xmlns="http://openconfig.net/yang/bgp">
                <neighbors><neighbor><state/></neighbor></neighbors>
            </bgp>""",
        "nokia_sros": """
            <state xmlns="urn:nokia.com:sros:ns:yang:sr:state">
                <router><bgp><neighbor/></bgp></router>
            </state>""",
        "cisco_xr": """
            <bgp xmlns="http://openconfig.net/yang/bgp"/>
        """,
    },
    "routing_table": {
        "cisco_xr": """
            <rib xmlns="http://openconfig.net/yang/rib/bgp"/>
        """,
        "juniper_junos": """
            <route-information xmlns="http://yang.juniper.net/junos/rpc"/>
        """,
    },
}


def _try_import_ncclient():
    """Lazy import ncclient so it's optional."""
    try:
        from ncclient import manager
        return manager
    except ImportError:
        raise ImportError(
            "ncclient is required for NETCONF support. "
            "Install it with: pip install ncclient"
        )


class NetconfTransport:
    """NETCONF transport for structured device data retrieval."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        device_type: str,
        port: int | None = None,
        timeout: int = 30,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.device_type = device_type
        self.port = port or NETCONF_PORT_MAP.get(device_type, 830)
        self.timeout = timeout
        self._ncclient_type = VENDOR_DEVICE_TYPE_MAP.get(
            device_type, "default"
        )

    @contextmanager
    def session(self) -> Generator:
        """Open a NETCONF session as a context manager."""
        manager = _try_import_ncclient()
        conn = None
        try:
            conn = manager.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                device_params={"name": self._ncclient_type},
                timeout=self.timeout,
                hostkey_verify=False,
            )
            logger.debug("NETCONF session opened to %s", self.host)
            yield conn
        finally:
            if conn:
                conn.close_session()
                logger.debug("NETCONF session closed to %s", self.host)

    def get_config(
        self, source: str = "running", filter_xml: str | None = None
    ) -> str:
        """Retrieve configuration via NETCONF <get-config>."""
        with self.session() as conn:
            if filter_xml:
                result = conn.get_config(
                    source=source,
                    filter=("subtree", filter_xml),
                )
            else:
                result = conn.get_config(source=source)
            return result.xml

    def get_operational(self, filter_xml: str) -> str:
        """Retrieve operational state via NETCONF <get>."""
        with self.session() as conn:
            result = conn.get(filter=("subtree", filter_xml))
            return result.xml

    def get_capabilities(self) -> list[str]:
        """List NETCONF server capabilities (YANG modules supported)."""
        with self.session() as conn:
            return list(conn.server_capabilities)

    def get_yang_data(self, operation: str) -> str:
        """Retrieve data using a pre-defined YANG filter for the vendor.

        Falls back to OpenConfig filters if vendor-specific is unavailable.
        """
        filters = YANG_FILTERS.get(operation, {})
        filter_xml = filters.get(self.device_type) or filters.get(
            "openconfig"
        )

        if not filter_xml:
            return (
                f"No YANG filter defined for operation '{operation}' "
                f"on {self.device_type}"
            )

        return self.get_operational(filter_xml.strip())

    def rpc(self, rpc_xml: str) -> str:
        """Execute a raw NETCONF RPC."""
        with self.session() as conn:
            result = conn.dispatch(ET.fromstring(rpc_xml))
            return result.xml


def xml_to_text(xml_string: str, indent: int = 2) -> str:
    """Pretty-print XML for human-readable output."""
    try:
        root = ET.fromstring(xml_string)
        ET.indent(root, space=" " * indent)
        return ET.tostring(root, encoding="unicode")
    except ET.ParseError:
        return xml_string

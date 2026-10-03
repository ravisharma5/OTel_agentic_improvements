"""Vendor-specific command mappings.

Each vendor has different CLI syntax. This module normalizes common operations
into a unified interface so tools can work across Nokia, Cisco, and Juniper
without the AI needing to know vendor-specific syntax.
"""

from __future__ import annotations

from mcp_telecom.models import VendorType

VENDOR_COMMANDS: dict[str, dict[str, str]] = {
    # ── Nokia SR OS ──────────────────────────────────────────────
    VendorType.NOKIA_SROS: {
        "bgp_summary": "show router bgp summary",
        "bgp_neighbors": "show router bgp neighbor",
        "bgp_routes": "show router bgp routes",
        "interfaces": "show port",
        "interface_detail": "show port {interface} detail",
        "system_info": "show system information",
        "uptime": "show uptime",
        "version": "show version",
        "routing_table": "show router route-table",
        "ospf_neighbors": "show router ospf neighbor",
        "ospf_database": "show router ospf database",
        "isis_adjacency": "show router isis adjacency",
        "mpls_lsp": "show router mpls lsp",
        "mpls_path": "show router mpls path",
        "ldp_session": "show router ldp session",
        "vprn_service": "show service vprn",
        "vpls_service": "show service vpls",
        "sap_status": "show service sap-using",
        "chassis": "show chassis",
        "card_status": "show card",
        "mda_status": "show mda",
        "alarms": "show system alarms",
        "log_events": "show log log-id 99",
        "ntp_status": "show system ntp all",
        "config_running": "admin display-config",
        "environment": "show chassis environment",
        "memory": "show system memory-pools",
        "cpu": "show system cpu",
        "lag_status": "show lag",
        "vrrp_status": "show router vrrp instance",
        "pim_neighbors": "show router pim neighbor",
        "igmp_groups": "show router igmp group",
        "lldp_neighbors": "show system lldp neighbor",
        "arp_table": "show router arp",
        "mac_table": "show service fdb-mac",
    },
    VendorType.NOKIA_SROS_TELNET: {},  # same commands, inherits from SROS

    # ── Cisco IOS / IOS-XE ──────────────────────────────────────
    VendorType.CISCO_IOS: {
        "bgp_summary": "show ip bgp summary",
        "bgp_neighbors": "show ip bgp neighbors",
        "bgp_routes": "show ip bgp",
        "interfaces": "show ip interface brief",
        "interface_detail": "show interface {interface}",
        "system_info": "show version",
        "uptime": "show version | include uptime",
        "version": "show version",
        "routing_table": "show ip route",
        "ospf_neighbors": "show ip ospf neighbor",
        "ospf_database": "show ip ospf database",
        "isis_adjacency": "show isis neighbors",
        "mpls_lsp": "show mpls traffic-eng tunnels brief",
        "mpls_path": "show mpls traffic-eng topology path",
        "ldp_session": "show mpls ldp neighbor",
        "chassis": "show inventory",
        "card_status": "show module",
        "alarms": "show facility-alarm status",
        "log_events": "show logging",
        "ntp_status": "show ntp status",
        "config_running": "show running-config",
        "environment": "show environment all",
        "memory": "show memory statistics",
        "cpu": "show processes cpu sorted",
        "lag_status": "show etherchannel summary",
        "vrrp_status": "show vrrp brief",
        "pim_neighbors": "show ip pim neighbor",
        "igmp_groups": "show ip igmp groups",
        "lldp_neighbors": "show lldp neighbors detail",
        "arp_table": "show arp",
        "mac_table": "show mac address-table",
        "spanning_tree": "show spanning-tree brief",
        "vlan_brief": "show vlan brief",
        "cdp_neighbors": "show cdp neighbors detail",
        "access_lists": "show access-lists",
    },

    # ── Cisco IOS-XR ────────────────────────────────────────────
    VendorType.CISCO_IOSXR: {
        "bgp_summary": "show bgp summary",
        "bgp_neighbors": "show bgp neighbors",
        "bgp_routes": "show bgp",
        "interfaces": "show ip interface brief",
        "interface_detail": "show interface {interface}",
        "system_info": "show version",
        "uptime": "show version | include uptime",
        "version": "show version",
        "routing_table": "show route",
        "ospf_neighbors": "show ospf neighbor",
        "ospf_database": "show ospf database",
        "isis_adjacency": "show isis neighbors",
        "mpls_lsp": "show mpls traffic-eng tunnels brief",
        "ldp_session": "show mpls ldp neighbor brief",
        "chassis": "show inventory",
        "card_status": "show platform",
        "alarms": "show alarms brief",
        "log_events": "show logging",
        "ntp_status": "show ntp status",
        "config_running": "show running-config",
        "environment": "show environment",
        "memory": "show memory summary",
        "cpu": "show processes cpu",
        "lag_status": "show bundle all",
        "lldp_neighbors": "show lldp neighbors detail",
        "arp_table": "show arp",
    },

    # ── Cisco NX-OS ─────────────────────────────────────────────
    VendorType.CISCO_NXOS: {
        "bgp_summary": "show ip bgp summary",
        "bgp_neighbors": "show ip bgp neighbors",
        "interfaces": "show interface brief",
        "interface_detail": "show interface {interface}",
        "system_info": "show version",
        "version": "show version",
        "routing_table": "show ip route",
        "ospf_neighbors": "show ip ospf neighbors",
        "config_running": "show running-config",
        "vlan_brief": "show vlan brief",
        "mac_table": "show mac address-table",
        "log_events": "show logging last 50",
        "cpu": "show processes cpu sort",
        "memory": "show system resources",
        "lldp_neighbors": "show lldp neighbors detail",
        "arp_table": "show ip arp",
    },

    # ── Juniper Junos ───────────────────────────────────────────
    VendorType.JUNIPER_JUNOS: {
        "bgp_summary": "show bgp summary",
        "bgp_neighbors": "show bgp neighbor",
        "bgp_routes": "show route protocol bgp",
        "interfaces": "show interfaces terse",
        "interface_detail": "show interfaces {interface} extensive",
        "system_info": "show system information",
        "uptime": "show system uptime",
        "version": "show version",
        "routing_table": "show route",
        "ospf_neighbors": "show ospf neighbor",
        "ospf_database": "show ospf database",
        "isis_adjacency": "show isis adjacency",
        "mpls_lsp": "show mpls lsp",
        "mpls_path": "show mpls path",
        "ldp_session": "show ldp session",
        "chassis": "show chassis hardware",
        "card_status": "show chassis fpc",
        "alarms": "show system alarms",
        "log_events": "show log messages | last 50",
        "ntp_status": "show ntp associations",
        "config_running": "show configuration",
        "environment": "show chassis environment",
        "memory": "show system memory",
        "cpu": "show system processes extensive",
        "lag_status": "show lacp interfaces",
        "vrrp_status": "show vrrp summary",
        "pim_neighbors": "show pim neighbors",
        "igmp_groups": "show igmp group",
        "lldp_neighbors": "show lldp neighbors",
        "arp_table": "show arp no-resolve",
        "mac_table": "show ethernet-switching table",
        "firewall_filters": "show firewall",
    },

    # ── Arista EOS ──────────────────────────────────────────────
    VendorType.ARISTA_EOS: {
        "bgp_summary": "show ip bgp summary",
        "bgp_neighbors": "show ip bgp neighbors",
        "interfaces": "show ip interface brief",
        "interface_detail": "show interface {interface}",
        "system_info": "show version",
        "version": "show version",
        "routing_table": "show ip route",
        "ospf_neighbors": "show ip ospf neighbor",
        "config_running": "show running-config",
        "vlan_brief": "show vlan brief",
        "mac_table": "show mac address-table",
        "log_events": "show logging last 50",
        "lldp_neighbors": "show lldp neighbors detail",
        "arp_table": "show arp",
        "mlag_status": "show mlag detail",
        "cpu": "show processes top once",
        "environment": "show environment all",
    },
}

# Nokia SROS telnet uses the same commands as SSH
VENDOR_COMMANDS[VendorType.NOKIA_SROS_TELNET] = VENDOR_COMMANDS[VendorType.NOKIA_SROS].copy()


def get_command(
    vendor: VendorType,
    operation: str,
    **kwargs: str,
) -> str:
    """Get the vendor-specific command for a given operation.

    Args:
        vendor: The device vendor type.
        operation: The normalized operation name (e.g. 'bgp_summary').
        **kwargs: Format parameters (e.g. interface='Gi0/0/0').

    Returns:
        The vendor-specific CLI command string.

    Raises:
        ValueError: If the operation is not supported for the vendor.
    """
    commands = VENDOR_COMMANDS.get(vendor)
    if commands is None:
        raise ValueError(f"Unsupported vendor: {vendor}")

    template = commands.get(operation)
    if template is None:
        supported = ", ".join(sorted(commands.keys()))
        raise ValueError(
            f"Operation '{operation}' not supported for {vendor.value}. "
            f"Supported: {supported}"
        )

    return template.format(**kwargs) if kwargs else template


def list_operations(vendor: VendorType) -> list[str]:
    """List all supported operations for a vendor."""
    commands = VENDOR_COMMANDS.get(vendor)
    if commands is None:
        raise ValueError(f"Unsupported vendor: {vendor}")
    return sorted(commands.keys())

"""Routing protocol tools for MCP-Telecom.

Tools for inspecting BGP, OSPF, IS-IS, and MPLS state on network devices.
"""

from __future__ import annotations

from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.vendors.mappings import get_command


def show_bgp_summary(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show BGP neighbor summary on a network device."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "bgp_summary")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_bgp_summary", True, len(output))
    return output


def show_bgp_neighbors(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show detailed BGP neighbor information."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "bgp_neighbors")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_bgp_neighbors", True, len(output))
    return output


def show_routing_table(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show the IP routing table."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "routing_table")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_routing_table", True, len(output))
    return output


def show_ospf_neighbors(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show OSPF neighbor adjacencies."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "ospf_neighbors")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_ospf_neighbors", True, len(output))
    return output


def show_mpls_lsp(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show MPLS Label Switched Paths."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "mpls_lsp")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_mpls_lsp", True, len(output))
    return output

"""Interface monitoring tools for MCP-Telecom.

Tools for inspecting interface status, statistics, and Layer 2 details.
"""

from __future__ import annotations

from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.vendors.mappings import get_command


def show_interfaces(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show interface summary status on a network device."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "interfaces")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_interfaces", True, len(output))
    return output


def show_interface_detail(
    device_manager: DeviceManager,
    audit: AuditLogger,
    device: str,
    interface: str,
) -> str:
    """Show detailed statistics for a specific interface."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "interface_detail", interface=interface)
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_interface_detail", True, len(output))
    return output


def show_lldp_neighbors(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show LLDP neighbor discovery information."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "lldp_neighbors")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_lldp_neighbors", True, len(output))
    return output


def show_lag_status(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show Link Aggregation Group (LAG/Port-Channel) status."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "lag_status")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_lag_status", True, len(output))
    return output

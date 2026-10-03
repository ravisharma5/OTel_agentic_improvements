"""System monitoring tools for MCP-Telecom.

Tools for checking system health, alarms, NTP, environment, and resources.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.vendors.mappings import get_command


def show_system_info(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show system information including version and uptime."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "system_info")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_system_info", True, len(output))
    return output


def show_alarms(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show active alarms/alerts on the device."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "alarms")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_alarms", True, len(output))
    return output


def show_ntp_status(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show NTP synchronization status."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "ntp_status")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_ntp_status", True, len(output))
    return output


def show_cpu(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show CPU utilization."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "cpu")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_cpu", True, len(output))
    return output


def show_memory(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show memory utilization."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "memory")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_memory", True, len(output))
    return output


def show_environment(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show environmental monitoring (power, fans, temperature)."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "environment")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_environment", True, len(output))
    return output


def show_log_events(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Show recent log/event messages from the device."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "log_events")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_log_events", True, len(output))
    return output


def backup_config(device_manager: DeviceManager, audit: AuditLogger, device: str) -> str:
    """Backup the running configuration of a device.

    Returns the full running config and saves a timestamped copy locally.
    """
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "config_running")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd, read_timeout=60)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backups/{device}_{timestamp}.cfg"

    import os
    os.makedirs("backups", exist_ok=True)
    with open(filename, "w") as f:
        f.write(output)

    audit.log_command(device, cmd, "backup_config", True, len(output))
    return f"Configuration backed up to {filename}\n\n{output}"


def health_check_all(device_manager: DeviceManager) -> str:
    """Run health checks on all configured devices."""
    devices = device_manager.list_devices()
    if not devices:
        return "No devices configured."

    results = []
    for dev in devices:
        status = device_manager.check_health(dev.name)
        emoji = "UP" if status.reachable else "DOWN"
        line = f"  {emoji} {dev.name} ({dev.host}) - {dev.vendor.value}"
        if status.reachable:
            line += f" - {status.response_time_ms}ms"
        else:
            line += f" - Error: {status.error}"
        results.append(line)

    return "Device Health Check Results:\n" + "\n".join(results)

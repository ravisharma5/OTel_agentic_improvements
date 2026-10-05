"""MCP-Telecom Server — The first MCP server for network equipment.

Exposes network device operations as MCP tools, resources, and prompts
so AI agents (Claude, GPT, etc.) can interact with Nokia SR OS, Cisco IOS-XR,
Juniper Junos, and other network equipment through natural language.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.safety import validate_command
from mcp_telecom.vendors.mappings import get_command, list_operations

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("MCP_TELECOM_LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_telecom")

# CR-03: Containment directory for backup file reads
BACKUPS_DIR = Path("backups").resolve()

# ── Initialize core components ──────────────────────────────────────────────

mcp = FastMCP(
    "MCP-Telecom",
    instructions=(
        "The first MCP server for network equipment. "
        "Interact with Nokia SR OS, Cisco IOS-XR, Juniper Junos, "
        "Arista EOS, and Cisco NX-OS routers through AI agents."
    ),
)

config_path = os.getenv("MCP_TELECOM_DEVICES_FILE", "devices.yaml")
device_manager = DeviceManager(config_path)
audit = AuditLogger()


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Network Operations
# ═══════════════════════════════════════════════════════════════════════════


# ── Routing Protocol Tools ──────────────────────────────────────────────────

@mcp.tool()
def show_bgp_summary(device: str) -> str:
    """Show BGP neighbor summary on a network device.

    Returns the BGP peering table with neighbor states, prefixes received,
    and session uptime. Works across all supported vendors.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "bgp_summary")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_bgp_summary", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_bgp_summary", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_bgp_neighbors(device: str) -> str:
    """Show detailed BGP neighbor information on a network device.

    Returns per-neighbor details including state, AS number, messages
    sent/received, and hold time.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "bgp_neighbors")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_bgp_neighbors", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_bgp_neighbors", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_routing_table(device: str) -> str:
    """Show the IP routing table on a network device.

    Returns all routes with protocol, next-hop, metric, and preference.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "routing_table")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_routing_table", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_routing_table", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_ospf_neighbors(device: str) -> str:
    """Show OSPF neighbor adjacencies on a network device.

    Returns OSPF neighbor states, interface associations, and dead intervals.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "ospf_neighbors")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_ospf_neighbors", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_ospf_neighbors", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_mpls_lsp(device: str) -> str:
    """Show MPLS Label Switched Paths on a network device.

    Returns LSP status, tunnel endpoints, and label bindings.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "mpls_lsp")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_mpls_lsp", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_mpls_lsp", False, error=str(e))
        return f"Error: {e}"


# ── Interface Tools ─────────────────────────────────────────────────────────

@mcp.tool()
def show_interfaces(device: str) -> str:
    """Show interface status summary on a network device.

    Returns all interfaces with admin/operational status, speed, and description.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "interfaces")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_interfaces", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_interfaces", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_interface_detail(device: str, interface: str) -> str:
    """Show detailed statistics for a specific interface.

    Returns counters, errors, CRC, drops, utilization, MTU, and speed
    for the specified interface.

    Args:
        device: Name of the device as defined in devices.yaml
        interface: Interface name (e.g., 'Gi0/0/0', '1/1/1', 'ge-0/0/0')
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "interface_detail", interface=interface)
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_interface_detail", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_interface_detail", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_lldp_neighbors(device: str) -> str:
    """Show LLDP neighbor discovery information.

    Returns connected neighbors with their system name, port ID,
    and capabilities — useful for topology discovery.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "lldp_neighbors")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_lldp_neighbors", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_lldp_neighbors", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_lag_status(device: str) -> str:
    """Show Link Aggregation Group (LAG/Port-Channel/Bundle) status.

    Returns LAG member ports, their states, and aggregate bandwidth.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "lag_status")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_lag_status", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_lag_status", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_arp_table(device: str) -> str:
    """Show the ARP table on a network device.

    Returns IP-to-MAC address mappings for all entries in the ARP cache.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "arp_table")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_arp_table", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_arp_table", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_mac_table(device: str) -> str:
    """Show the MAC address table on a network device.

    Returns MAC addresses, VLANs, and associated interfaces.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "mac_table")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_mac_table", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_mac_table", False, error=str(e))
        return f"Error: {e}"


# ── System Monitoring Tools ─────────────────────────────────────────────────

@mcp.tool()
def show_system_info(device: str) -> str:
    """Show system information including version, uptime, and hardware.

    Returns device platform, software version, uptime, serial number,
    and hardware details.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "system_info")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_system_info", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_system_info", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_alarms(device: str) -> str:
    """Show active alarms and alerts on a network device.

    Returns current alarm conditions including severity, timestamp, and description.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "alarms")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_alarms", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_alarms", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_ntp_status(device: str) -> str:
    """Show NTP synchronization status on a network device.

    Returns NTP peers, stratum, offset, and synchronization state.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "ntp_status")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_ntp_status", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_ntp_status", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_cpu(device: str) -> str:
    """Show CPU utilization on a network device.

    Returns CPU usage per core/process to identify resource bottlenecks.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "cpu")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_cpu", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_cpu", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_memory(device: str) -> str:
    """Show memory utilization on a network device.

    Returns memory pool usage, free/used/total memory statistics.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "memory")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_memory", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_memory", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_environment(device: str) -> str:
    """Show environmental monitoring on a network device.

    Returns power supply, fan, and temperature sensor readings.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "environment")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_environment", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_environment", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def show_log_events(device: str) -> str:
    """Show recent log/syslog messages from a network device.

    Returns the most recent event log entries for troubleshooting.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "log_events")
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, "show_log_events", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", "show_log_events", False, error=str(e))
        return f"Error: {e}"


# ── Configuration & Backup Tools ────────────────────────────────────────────

@mcp.tool()
def backup_config(device: str) -> str:
    """Backup the running configuration of a network device.

    Fetches the full running config and saves a timestamped copy locally.
    Returns the configuration content and the backup file path.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        from mcp_telecom.tools.system import backup_config as _backup
        return _backup(device_manager, audit, device)
    except Exception as e:
        audit.log_command(device, "", "backup_config", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def compare_configs(device: str, backup_file: str) -> str:
    """Compare the current running config with a previous backup.

    Performs a diff between the live running configuration and a saved
    backup file, highlighting additions and removals.

    Args:
        device: Name of the device as defined in devices.yaml
        backup_file: Path to the backup file to compare against
    """
    try:
        import difflib

        # CR-03: Contain backup_file reads to the BACKUPS_DIR.
        # Resolve the RAW joined path (NOT .name-stripped) so traversal
        # components like "../" resolve to their actual filesystem target.
        candidate = (BACKUPS_DIR / backup_file).resolve()
        if not candidate.is_relative_to(BACKUPS_DIR.resolve()):
            return "Error: backup_file must be within the backups/ directory"

        if not candidate.exists():
            return f"Error: Backup file not found: {backup_file}"

        previous = candidate.read_text()

        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "config_running")
        with device_manager.connect(device) as conn:
            current = conn.send_command(cmd, read_timeout=60)

        diff = difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"backup ({backup_file})",
            tofile=f"running ({device})",
            lineterm="",
        )
        diff_text = "\n".join(diff)

        audit.log_command(device, cmd, "compare_configs", True, len(diff_text))
        return diff_text if diff_text else "No differences found — configs are identical."
    except Exception as e:
        audit.log_command(device, "", "compare_configs", False, error=str(e))
        return f"Error: {e}"


# ── Generic Command Execution ───────────────────────────────────────────────

@mcp.tool()
def run_command(device: str, command: str) -> str:
    """Run any read-only (show) command on a network device.

    For safety, only read-only commands are permitted. Configuration commands
    are blocked. Use this when you need a specific command not covered by
    the dedicated tools.

    Args:
        device: Name of the device as defined in devices.yaml
        command: The CLI command to execute
            (must start with 'show', 'display', 'ping', or 'traceroute')
    """
    error = validate_command(command)
    if error:
        audit.log_command(device, command, "run_command", False, error=error)
        return f"Error: {error}"

    try:
        with device_manager.connect(device) as conn:
            output = conn.send_command(command)
        audit.log_command(device, command, "run_command", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, command, "run_command", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def run_vendor_operation(device: str, operation: str) -> str:
    """Run a named operation using the vendor-specific command mapping.

    This automatically translates the operation name to the correct CLI
    command for the device's vendor. Use 'list_device_capabilities' to see
    available operations.

    Args:
        device: Name of the device as defined in devices.yaml
        operation: Operation name (e.g., 'bgp_summary', 'interfaces', 'alarms')
    """
    try:
        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, operation)
        with device_manager.connect(device) as conn:
            output = conn.send_command(cmd)
        audit.log_command(device, cmd, f"run_vendor_operation:{operation}", True, len(output))
        return output
    except Exception as e:
        audit.log_command(device, "", f"run_vendor_operation:{operation}", False, error=str(e))
        return f"Error: {e}"


# ── Device Management Tools ─────────────────────────────────────────────────

@mcp.tool()
def list_devices() -> str:
    """List all configured network devices.

    Returns the names, hosts, vendors, and ports of all devices
    available for interaction.
    """
    devices = device_manager.list_devices()
    if not devices:
        return "No devices configured. Add devices to devices.yaml."

    lines = ["Configured Devices:", "=" * 60]
    for d in devices:
        lines.append(f"  {d.name:20s}  {d.host:15s}  {d.vendor.value:15s}  port:{d.port}")
    return "\n".join(lines)


@mcp.tool()
def list_device_capabilities(device: str) -> str:
    """List all supported operations for a specific device.

    Shows what commands are available for this device based on its vendor type.
    Use the operation names with the 'run_vendor_operation' tool.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        config = device_manager.get_device(device)
        ops = list_operations(config.device_type)
        lines = [
            f"Capabilities for '{device}' ({config.device_type.value}):",
            "-" * 50,
        ]
        for op in ops:
            cmd = get_command(config.device_type, op)
            lines.append(f"  {op:25s} → {cmd}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def health_check(device: str | None = None) -> str:
    """Check reachability and response time for devices.

    Tests SSH connectivity and measures response time. If no device is
    specified, checks all configured devices.

    Args:
        device: Optional device name. If omitted, checks all devices.
    """
    if device:
        status = device_manager.check_health(device)
        state = "REACHABLE" if status.reachable else "UNREACHABLE"
        result = f"{device}: {state}"
        if status.reachable:
            result += f" (response: {status.response_time_ms}ms)"
        else:
            result += f" (error: {status.error})"
        return result

    from mcp_telecom.tools.system import health_check_all
    return health_check_all(device_manager)


@mcp.tool()
def get_audit_log(count: int = 25) -> str:
    """Retrieve recent entries from the command audit log.

    Shows what commands have been executed, when, on which device,
    and whether they succeeded.

    Args:
        count: Number of recent entries to retrieve (default: 25)
    """
    entries = audit.get_recent_entries(count)
    if not entries:
        return "No audit log entries found."

    lines = ["Recent Audit Log:", "=" * 80]
    for entry in entries:
        ts = entry.get("timestamp", "?")[:19]
        dev = entry.get("device", "?")
        cmd = entry.get("command", "?")
        ok = "OK" if entry.get("success") else "FAIL"
        lines.append(f"  [{ts}] {ok:4s} {dev:15s} {cmd}")
    return "\n".join(lines)


# ── Nokia SR OS Specific Tools ──────────────────────────────────────────────

@mcp.tool()
def show_nokia_services(device: str) -> str:
    """Show Nokia SR OS service summary (VPRN, VPLS, SAP).

    Nokia-specific tool for viewing all configured services.
    Only works on Nokia SR OS devices.

    Args:
        device: Name of a Nokia SR OS device
    """
    try:
        config = device_manager.get_device(device)
        if "nokia" not in config.device_type.value:
            return "Error: This tool only works on Nokia SR OS devices."

        results = []
        with device_manager.connect(device) as conn:
            for op in ["vprn_service", "vpls_service", "sap_status"]:
                try:
                    cmd = get_command(config.device_type, op)
                    output = conn.send_command(cmd)
                    results.append(f"--- {op} ---\n{output}")
                except ValueError:
                    pass

        combined = "\n\n".join(results)
        audit.log_command(device, "show services", "show_nokia_services", True, len(combined))
        return combined
    except Exception as e:
        audit.log_command(device, "", "show_nokia_services", False, error=str(e))
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  MCP RESOURCES — Device Information
# ═══════════════════════════════════════════════════════════════════════════

@mcp.resource("telecom://devices")
def resource_device_inventory() -> str:
    """Full inventory of all configured network devices."""
    devices = device_manager.list_devices()
    inventory = [
        {
            "name": d.name,
            "host": d.host,
            "vendor": d.vendor.value,
            "port": d.port,
        }
        for d in devices
    ]
    return json.dumps(inventory, indent=2)


@mcp.resource("telecom://devices/{device_name}/info")
def resource_device_info(device_name: str) -> str:
    """Configuration metadata for a specific device (no secrets)."""
    try:
        config = device_manager.get_device(device_name)
        info = {
            "name": device_name,
            "host": config.host,
            "vendor": config.device_type.value,
            "port": config.port,
            "timeout": config.timeout,
            "supported_operations": list_operations(config.device_type),
        }
        return json.dumps(info, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("telecom://vendors")
def resource_supported_vendors() -> str:
    """List of all supported network equipment vendors."""
    from mcp_telecom.models import VendorType
    vendors = [
        {
            "type": v.value,
            "operations_count": len(list_operations(v)),
        }
        for v in VendorType
    ]
    return json.dumps(vendors, indent=2)


@mcp.resource("telecom://audit-log")
def resource_audit_log() -> str:
    """Recent command audit log entries."""
    entries = audit.get_recent_entries(100)
    return json.dumps(entries, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP PROMPTS — Troubleshooting Templates
# ═══════════════════════════════════════════════════════════════════════════

@mcp.prompt()
def troubleshoot_bgp(device: str) -> str:
    """Step-by-step BGP troubleshooting workflow for a device."""
    return f"""You are a senior network engineer troubleshooting BGP on device '{device}'.

Follow this systematic approach:

1. **Check BGP Summary** — Use show_bgp_summary('{device}') to see all BGP peers.
   - Look for peers in non-Established states
   - Check if prefix counts look normal

2. **Examine Specific Neighbors** — Use show_bgp_neighbors('{device}') for detailed neighbor info.
   - Check hold-time and keepalive timers
   - Look for notification messages

3. **Verify Routing Table** — Use show_routing_table('{device}') to check if expected routes exist.
   - Confirm next-hop reachability
   - Check for missing prefixes

4. **Check Interfaces** — Use show_interfaces('{device}') to verify the peering interface is up.
   - Confirm IP addressing
   - Check for errors/drops

5. **Review Logs** — Use show_log_events('{device}') for recent BGP-related events.

6. **System Resources** — Use show_cpu('{device}') and show_memory('{device}')
   to rule out resource issues.

Provide a diagnosis with:
- Root cause analysis
- Impact assessment
- Recommended remediation steps
"""


@mcp.prompt()
def troubleshoot_interface(device: str, interface: str) -> str:
    """Step-by-step interface troubleshooting workflow."""
    return f"""You are a senior network engineer troubleshooting \
interface '{interface}' on device '{device}'.

Follow this systematic approach:

1. **Interface Status** — Use show_interface_detail('{device}', '{interface}') for detailed stats.
   - Check admin/oper status
   - Look for errors, CRC, drops
   - Verify speed/duplex

2. **Interface Summary** — Use show_interfaces('{device}') to see this interface in context.

3. **LLDP Neighbors** — Use show_lldp_neighbors('{device}') to check physical connectivity.
   - Verify the expected neighbor is connected

4. **ARP Table** — Use show_arp_table('{device}') to check Layer 3 reachability.

5. **Log Events** — Use show_log_events('{device}') for interface-related events.
   - Look for flap events
   - Check for error messages

Provide a diagnosis with:
- Current interface state summary
- Identified issues
- Recommended actions
"""


@mcp.prompt()
def network_health_audit(device: str) -> str:
    """Comprehensive network device health audit."""
    return f"""You are performing a comprehensive health audit on device '{device}'.

Execute these checks systematically:

1. **System Overview**
   - show_system_info('{device}') — Version, uptime, hardware
   - show_environment('{device}') — Power, fans, temperature

2. **Resource Utilization**
   - show_cpu('{device}') — CPU usage
   - show_memory('{device}') — Memory usage

3. **Active Alarms**
   - show_alarms('{device}') — Any active alarms

4. **Network State**
   - show_interfaces('{device}') — Interface health
   - show_bgp_summary('{device}') — BGP peering state
   - show_ospf_neighbors('{device}') — OSPF adjacencies
   - show_routing_table('{device}') — Route count and sources

5. **Time Sync**
   - show_ntp_status('{device}') — NTP synchronization

6. **Recent Activity**
   - show_log_events('{device}') — Recent logs

Generate a health report with:
- Overall health score (Critical / Warning / Healthy)
- Summary of findings per category
- List of issues found (sorted by severity)
- Recommended actions
"""


@mcp.prompt()
def compare_device_pair(device_a: str, device_b: str) -> str:
    """Compare two devices side-by-side for consistency checks."""
    return f"""You are comparing devices '{device_a}' and '{device_b}' for consistency.

Collect data from both devices:

1. **System Info** — show_system_info for both devices
   - Compare software versions
   - Compare uptime

2. **Interfaces** — show_interfaces for both devices
   - Compare interface states
   - Identify mismatches

3. **BGP State** — show_bgp_summary for both devices
   - Compare peer counts
   - Check if they peer with each other

4. **Routing** — show_routing_table for both devices
   - Compare route counts
   - Look for asymmetric routes

Generate a comparison report highlighting:
- Matching configurations
- Discrepancies found
- Potential issues
- Recommendations for alignment
"""


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — NETCONF / YANG
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def netconf_get_config(device: str, source: str = "running") -> str:
    """Retrieve device configuration via NETCONF (structured XML/YANG).

    Uses NETCONF protocol instead of SSH CLI scraping. Returns structured
    XML data. Requires ncclient: pip install mcp-telecom[netconf]

    Args:
        device: Name of the device as defined in devices.yaml
        source: Config datastore — 'running', 'candidate', or 'startup'
    """
    try:
        from mcp_telecom.transports.netconf import (
            NetconfTransport,
            xml_to_text,
        )

        config = device_manager.get_device(device)
        nc = NetconfTransport(
            host=config.host,
            username=config.username,
            password=config.password,
            device_type=config.device_type.value,
            timeout=config.timeout,
        )
        result = nc.get_config(source=source)
        audit.log_command(
            device, f"netconf:get-config:{source}",
            "netconf_get_config", True, len(result),
        )
        return xml_to_text(result)
    except ImportError:
        return (
            "NETCONF support not installed. "
            "Run: pip install mcp-telecom[netconf]"
        )
    except Exception as e:
        audit.log_command(
            device, "", "netconf_get_config", False, error=str(e),
        )
        return f"Error: {e}"


@mcp.tool()
def netconf_get_operational(
    device: str, operation: str
) -> str:
    """Retrieve operational state via NETCONF using YANG models.

    Uses pre-defined YANG filters for common operations. Supported
    operations: system_info, interfaces, bgp_summary, routing_table.

    Args:
        device: Name of the device as defined in devices.yaml
        operation: YANG operation (e.g. 'system_info', 'interfaces')
    """
    try:
        from mcp_telecom.transports.netconf import (
            NetconfTransport,
            xml_to_text,
        )

        config = device_manager.get_device(device)
        nc = NetconfTransport(
            host=config.host,
            username=config.username,
            password=config.password,
            device_type=config.device_type.value,
            timeout=config.timeout,
        )
        result = nc.get_yang_data(operation)
        audit.log_command(
            device, f"netconf:get:{operation}",
            "netconf_get_operational", True, len(result),
        )
        return xml_to_text(result)
    except ImportError:
        return (
            "NETCONF support not installed. "
            "Run: pip install mcp-telecom[netconf]"
        )
    except Exception as e:
        audit.log_command(
            device, "", "netconf_get_operational", False, error=str(e),
        )
        return f"Error: {e}"


@mcp.tool()
def netconf_capabilities(device: str) -> str:
    """List NETCONF/YANG capabilities advertised by a device.

    Shows all YANG modules the device supports, useful for understanding
    what structured data you can retrieve.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        from mcp_telecom.transports.netconf import NetconfTransport

        config = device_manager.get_device(device)
        nc = NetconfTransport(
            host=config.host,
            username=config.username,
            password=config.password,
            device_type=config.device_type.value,
            timeout=config.timeout,
        )
        caps = nc.get_capabilities()
        lines = [
            f"NETCONF Capabilities for {device}:",
            f"  Total: {len(caps)} YANG modules",
            "-" * 60,
        ]
        for cap in sorted(caps):
            lines.append(f"  {cap}")
        return "\n".join(lines)
    except ImportError:
        return (
            "NETCONF support not installed. "
            "Run: pip install mcp-telecom[netconf]"
        )
    except Exception as e:
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Streaming Telemetry (gNMI)
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def telemetry_subscribe(
    device: str,
    paths: str = "interface_counters,bgp_peer_state,cpu_utilization",
    interval_ms: int = 10000,
) -> str:
    """Start a gNMI streaming telemetry subscription for a device.

    Subscribes to OpenConfig telemetry paths and caches the latest
    values for querying. Use telemetry_query to read collected data.

    Args:
        device: Name of the device as defined in devices.yaml
        paths: Comma-separated telemetry path names or OpenConfig paths
        interval_ms: Collection interval in milliseconds (default: 10000)
    """
    from mcp_telecom.transports.telemetry import (
        COMMON_TELEMETRY_PATHS,
        TelemetrySubscription,
        gnmi_collector,
    )

    resolved_paths = []
    for p in paths.split(","):
        p = p.strip()
        resolved_paths.append(COMMON_TELEMETRY_PATHS.get(p, p))

    sub = TelemetrySubscription(
        device=device,
        paths=resolved_paths,
        mode="STREAM",
        interval_ms=interval_ms,
    )
    result = gnmi_collector.subscribe(sub)
    audit.log_command(
        device, f"telemetry:subscribe:{paths}",
        "telemetry_subscribe", True, len(result),
    )
    return result


@mcp.tool()
def telemetry_query(device: str) -> str:
    """Query the latest telemetry data collected for a device.

    Returns the most recent values for all subscribed telemetry paths.
    Start a subscription first with telemetry_subscribe.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    from mcp_telecom.transports.telemetry import telemetry_store

    return telemetry_store.format_for_display(device)


@mcp.tool()
def telemetry_history(
    device: str, path: str, count: int = 20
) -> str:
    """Get historical telemetry values for trend analysis.

    Returns time-series data for a specific telemetry path on a device.

    Args:
        device: Name of the device as defined in devices.yaml
        path: Telemetry path name (e.g. 'interface_counters')
        count: Number of historical data points (default: 20)
    """
    from mcp_telecom.transports.telemetry import (
        COMMON_TELEMETRY_PATHS,
        telemetry_store,
    )

    resolved = COMMON_TELEMETRY_PATHS.get(path, path)
    history = telemetry_store.get_history(device, resolved, count)
    if not history:
        return f"No telemetry history for {device} path '{path}'."

    lines = [f"Telemetry History: {device} / {path}", "-" * 50]
    for entry in history:
        ts = entry.timestamp.strftime("%H:%M:%S")
        lines.append(f"  [{ts}] {entry.value}")
    return "\n".join(lines)


@mcp.tool()
def telemetry_list_subscriptions() -> str:
    """List all active telemetry subscriptions."""
    from mcp_telecom.transports.telemetry import gnmi_collector

    subs = gnmi_collector.list_subscriptions()
    if not subs:
        return "No active telemetry subscriptions."

    lines = ["Active Telemetry Subscriptions:", "=" * 60]
    for s in subs:
        status = "ACTIVE" if s["active"] else "STOPPED"
        lines.append(
            f"  {s['device']:20s} {status:8s} "
            f"{len(s['paths'])} paths, {s['interval_ms']}ms"
        )
    return "\n".join(lines)


@mcp.tool()
def telemetry_unsubscribe(device: str) -> str:
    """Stop a telemetry subscription for a device.

    Args:
        device: Name of the device to stop collecting from
    """
    from mcp_telecom.transports.telemetry import gnmi_collector

    return gnmi_collector.unsubscribe(device)


@mcp.tool()
def telemetry_list_paths() -> str:
    """List all pre-defined telemetry path shortcuts.

    Shows the available shortcut names and their corresponding
    OpenConfig YANG paths for use with telemetry_subscribe.
    """
    from mcp_telecom.transports.telemetry import COMMON_TELEMETRY_PATHS

    lines = [
        "Available Telemetry Paths:",
        "=" * 70,
    ]
    for name, path in sorted(COMMON_TELEMETRY_PATHS.items()):
        lines.append(f"  {name:30s} {path}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Topology Discovery
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def discover_topology(devices: str = "") -> str:
    """Discover network topology by collecting LLDP data from all devices.

    Connects to each configured device (or specified subset), collects
    LLDP neighbor information, and builds a topology map showing how
    devices are interconnected.

    Args:
        devices: Comma-separated device names. Empty = all devices.
    """
    from mcp_telecom.topology import (
        TopoNode,
        parse_lldp_output,
        topology_db,
    )

    device_list = device_manager.list_devices()
    if devices:
        names = {d.strip() for d in devices.split(",")}
        device_list = [d for d in device_list if d.name in names]

    if not device_list:
        return "No devices to discover. Check devices.yaml."

    results = []
    for dev in device_list:
        topology_db.add_node(TopoNode(
            name=dev.name, host=dev.host, vendor=dev.vendor.value,
        ))

        try:
            config = device_manager.get_device(dev.name)
            cmd = get_command(config.device_type, "lldp_neighbors")
            with device_manager.connect(dev.name) as conn:
                output = conn.send_command(cmd)

            links = parse_lldp_output(
                dev.name, output, config.device_type.value,
            )
            for link in links:
                topology_db.add_link(link)

            results.append(
                f"  {dev.name}: discovered {len(links)} neighbors"
            )
            audit.log_command(
                dev.name, cmd, "discover_topology", True, len(output),
            )
        except Exception as e:
            results.append(f"  {dev.name}: error — {e}")
            audit.log_command(
                dev.name, "", "discover_topology", False, error=str(e),
            )

    header = "Topology Discovery Results:\n" + "\n".join(results)
    return header + "\n\n" + topology_db.to_ascii()


@mcp.tool()
def show_topology() -> str:
    """Show the discovered network topology as an ASCII diagram.

    Displays all discovered devices and their interconnections.
    Run discover_topology first to collect data.
    """
    from mcp_telecom.topology import topology_db
    return topology_db.to_ascii()


@mcp.tool()
def show_topology_json() -> str:
    """Export the network topology as JSON.

    Returns the topology in structured JSON format for programmatic
    use or integration with visualization tools.
    """
    from mcp_telecom.topology import topology_db
    return topology_db.to_json()


@mcp.tool()
def show_topology_mermaid() -> str:
    """Export the network topology as a Mermaid diagram.

    Returns Mermaid-formatted graph that can be rendered in Markdown,
    GitHub, or documentation tools.
    """
    from mcp_telecom.topology import topology_db
    return topology_db.to_mermaid()


@mcp.tool()
def find_path(source: str, target: str) -> str:
    """Find the shortest path between two devices in the topology.

    Uses BFS on the LLDP-discovered topology to find the shortest
    path between two network devices.

    Args:
        source: Source device name
        target: Target device name
    """
    from mcp_telecom.topology import topology_db

    path = topology_db.find_path(source, target)
    if path is None:
        return (
            f"No path found between '{source}' and '{target}'. "
            "Ensure topology has been discovered with discover_topology."
        )
    return " → ".join(path) + f"  ({len(path) - 1} hops)"


@mcp.tool()
def show_device_neighbors(device: str) -> str:
    """Show all discovered neighbors for a specific device.

    Lists every direct connection found via LLDP/CDP for the device.

    Args:
        device: Name of the device
    """
    from mcp_telecom.topology import topology_db

    links = topology_db.get_neighbors(device)
    if not links:
        return (
            f"No neighbors discovered for '{device}'. "
            "Run discover_topology first."
        )

    lines = [
        f"Neighbors of {device} ({len(links)} links):",
        "-" * 50,
    ]
    for link in links:
        if link.local_device == device:
            lines.append(
                f"  {link.local_port:20s} ↔ "
                f"{link.remote_device} ({link.remote_port})"
            )
        else:
            lines.append(
                f"  {link.remote_port:20s} ↔ "
                f"{link.local_device} ({link.local_port})"
            )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — SNMP MIB Polling
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def snmp_get(
    device: str,
    oids: str = "sysDescr,sysUpTime,sysName",
    community: str = "public",
) -> str:
    """Poll SNMP OIDs from a network device.

    Retrieves specific SNMP MIB values. Accepts OID names or dotted
    notation. Requires pysnmp: pip install mcp-telecom[snmp]

    Args:
        device: Name of the device as defined in devices.yaml
        oids: Comma-separated OID names or numbers
        community: SNMPv2c community string (default: public)
    """
    try:
        from mcp_telecom.transports.snmp import (
            SnmpPoller,
            format_snmp_results,
        )

        config = device_manager.get_device(device)
        poller = SnmpPoller(host=config.host, community=community)
        oid_list = [o.strip() for o in oids.split(",")]
        results = poller.get(oid_list)
        audit.log_command(
            device, f"snmp:get:{oids}", "snmp_get", True, len(results),
        )
        return format_snmp_results(results)
    except ImportError:
        return "SNMP support not installed. Run: pip install mcp-telecom[snmp]"
    except Exception as e:
        audit.log_command(device, "", "snmp_get", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def snmp_walk(
    device: str,
    base_oid: str = "1.3.6.1.2.1.2.2.1",
    community: str = "public",
) -> str:
    """Walk an SNMP MIB subtree on a network device.

    Retrieves all OIDs under the specified base OID. Useful for
    interface tables, routing tables, etc.

    Args:
        device: Name of the device as defined in devices.yaml
        base_oid: Base OID to walk (default: IF-MIB ifTable)
        community: SNMPv2c community string
    """
    try:
        from mcp_telecom.transports.snmp import (
            SnmpPoller,
            format_snmp_results,
        )

        config = device_manager.get_device(device)
        poller = SnmpPoller(host=config.host, community=community)
        results = poller.walk(base_oid)
        audit.log_command(
            device, f"snmp:walk:{base_oid}", "snmp_walk", True, len(results),
        )
        return format_snmp_results(results)
    except ImportError:
        return "SNMP support not installed. Run: pip install mcp-telecom[snmp]"
    except Exception as e:
        audit.log_command(device, "", "snmp_walk", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def snmp_device_overview(
    device: str, community: str = "public"
) -> str:
    """Get a quick SNMP-based overview of a device.

    Polls system MIB, interface counts, and uptime in a single request.

    Args:
        device: Name of the device as defined in devices.yaml
        community: SNMPv2c community string
    """
    try:
        from mcp_telecom.transports.snmp import (
            SYS_CONTACT,
            SYS_DESCR,
            SYS_LOCATION,
            SYS_NAME,
            SYS_UPTIME,
            SnmpPoller,
            format_snmp_results,
        )

        config = device_manager.get_device(device)
        poller = SnmpPoller(host=config.host, community=community)
        results = poller.get([
            SYS_DESCR, SYS_UPTIME, SYS_NAME, SYS_LOCATION, SYS_CONTACT,
        ])
        audit.log_command(
            device, "snmp:device_overview",
            "snmp_device_overview", True, len(results),
        )
        return format_snmp_results(results)
    except ImportError:
        return "SNMP support not installed. Run: pip install mcp-telecom[snmp]"
    except Exception as e:
        audit.log_command(device, "", "snmp_device_overview", False, error=str(e))
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Multi-Device Parallel Queries
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def parallel_command(
    command: str, devices: str = "", max_workers: int = 10
) -> str:
    """Run a read-only command on multiple devices simultaneously.

    Executes the same CLI command across all (or specified) devices in
    parallel using a thread pool. Much faster than querying one-by-one.

    Args:
        command: CLI command to run (must be read-only)
        devices: Comma-separated device names. Empty = all devices.
        max_workers: Max concurrent threads (default: 10)
    """
    from mcp_telecom.parallel import ParallelExecutor, format_parallel_results

    executor = ParallelExecutor(device_manager)
    device_list = (
        [d.strip() for d in devices.split(",") if d.strip()] if devices else None
    )
    results = executor.run_on_all(command, device_list, max_workers)
    audit.log_command(
        "ALL", command, "parallel_command", True, len(results),
    )
    return format_parallel_results(results)


@mcp.tool()
def parallel_operation(
    operation: str, devices: str = "", max_workers: int = 10
) -> str:
    """Run a vendor-mapped operation on multiple devices simultaneously.

    Translates the operation name to the correct vendor CLI command for
    each device and runs them all in parallel.

    Args:
        operation: Operation name (e.g. 'bgp_summary', 'interfaces')
        devices: Comma-separated device names. Empty = all devices.
        max_workers: Max concurrent threads (default: 10)
    """
    from mcp_telecom.parallel import ParallelExecutor, format_parallel_results

    executor = ParallelExecutor(device_manager)
    device_list = (
        [d.strip() for d in devices.split(",") if d.strip()] if devices else None
    )
    results = executor.run_operation_on_all(operation, device_list, max_workers)
    audit.log_command(
        "ALL", f"op:{operation}", "parallel_operation", True, len(results),
    )
    return format_parallel_results(results)


@mcp.tool()
def compare_devices(
    operation: str, devices: str = ""
) -> str:
    """Compare command output across multiple devices.

    Runs the same operation on multiple devices and highlights differences.
    Useful for finding configuration drift or inconsistencies.

    Args:
        operation: Operation name (e.g. 'system_info', 'ntp_status')
        devices: Comma-separated device names. Empty = all devices.
    """
    from mcp_telecom.parallel import ParallelExecutor

    executor = ParallelExecutor(device_manager)
    device_list = (
        [d.strip() for d in devices.split(",") if d.strip()] if devices else None
    )
    return executor.compare_across_devices(operation, device_list)


@mcp.tool()
def parallel_health_check(devices: str = "") -> str:
    """Health-check multiple devices in parallel.

    Tests SSH reachability and response time for all specified devices
    simultaneously. Much faster than sequential health checks.

    Args:
        devices: Comma-separated device names. Empty = all devices.
    """
    from mcp_telecom.parallel import ParallelExecutor

    executor = ParallelExecutor(device_manager)
    device_list = (
        [d.strip() for d in devices.split(",") if d.strip()] if devices else None
    )
    return executor.batch_health_check(device_list)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Config Compliance
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def compliance_check(device: str) -> str:
    """Check a device's running config against security best practices.

    Evaluates the running configuration against 20+ compliance rules
    covering NTP, SSH, SNMP, AAA, passwords, and more. Returns a
    scored report with pass/fail per rule and remediation advice.

    Args:
        device: Name of the device as defined in devices.yaml
    """
    try:
        from mcp_telecom.compliance import DEFAULT_RULES, ComplianceChecker

        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "config_running")
        with device_manager.connect(device) as conn:
            running_config = conn.send_command(cmd, read_timeout=60)

        checker = ComplianceChecker()
        checker.load_rules_from_dict([r.model_dump() for r in DEFAULT_RULES])
        results = checker.check_config(
            device, running_config, config.device_type.value,
        )
        report = checker.generate_report(results)
        score = checker.get_score(results)
        audit.log_command(
            device, "compliance_check", "compliance_check",
            True, len(report),
        )
        return f"Compliance Score: {score:.0%}\n\n{report}"
    except Exception as e:
        audit.log_command(device, "", "compliance_check", False, error=str(e))
        return f"Error: {e}"


@mcp.tool()
def compliance_check_rule(
    device: str, rule_name: str
) -> str:
    """Check a specific compliance rule against a device.

    Args:
        device: Name of the device as defined in devices.yaml
        rule_name: Name of the compliance rule to check
    """
    try:
        from mcp_telecom.compliance import DEFAULT_RULES, ComplianceChecker

        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "config_running")
        with device_manager.connect(device) as conn:
            running_config = conn.send_command(cmd, read_timeout=60)

        matching = [r for r in DEFAULT_RULES if r.name == rule_name]
        if not matching:
            names = ", ".join(r.name for r in DEFAULT_RULES)
            return f"Unknown rule: '{rule_name}'. Available: {names}"

        checker = ComplianceChecker()
        checker.load_rules_from_dict([r.model_dump() for r in matching])
        results = checker.check_config(
            device, running_config, config.device_type.value,
        )
        return checker.generate_report(results)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def compliance_list_rules() -> str:
    """List all available compliance rules and their descriptions."""
    from mcp_telecom.compliance import DEFAULT_RULES

    lines = ["Compliance Rules:", "=" * 70]
    for rule in DEFAULT_RULES:
        vendor = rule.vendor or "all"
        lines.append(
            f"  [{rule.severity:8s}] {rule.name:30s} "
            f"({vendor}) — {rule.description}"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Connection Pool Management
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def pool_stats() -> str:
    """Show connection pool statistics.

    Returns counts of active, idle, and total persistent SSH connections
    per device. Useful for monitoring connection reuse.
    """
    from mcp_telecom.pool import ConnectionPool

    pool = ConnectionPool()
    stats = pool.get_stats()
    lines = [
        "Connection Pool Stats:",
        f"  Total connections: {stats['total_connections']}",
        "-" * 50,
    ]
    for dev, info in stats.get("devices", {}).items():
        lines.append(
            f"  {dev:20s}  active={info['active']}  "
            f"idle={info['idle']}  total={info['total']}"
        )
    if not stats.get("devices"):
        lines.append("  No active connections in pool.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Containerlab Integration
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def clab_generate(
    scenario: str = "basic",
) -> str:
    """Generate a Containerlab topology for lab testing.

    Creates a containerlab YAML topology file that mirrors your production
    device inventory, or uses a pre-built test scenario.

    Args:
        scenario: Test scenario — 'basic', 'mpls_core', 'datacenter',
            'isp_edge', or 'inventory' (uses your devices.yaml)
    """
    from mcp_telecom.containerlab import ContainerlabManager

    clab = ContainerlabManager()

    if scenario == "inventory":
        devices = device_manager.list_devices()
        content = clab.generate_topology(devices)
    else:
        content = clab.generate_test_scenario(scenario)

    path = clab.save_topology(content)
    commands = clab.get_deploy_commands(path)

    return f"Generated topology: {path}\n\n{content}\n\nDeploy commands:\n{commands}"


@mcp.tool()
def clab_devices_yaml(
    scenario: str = "basic",
) -> str:
    """Generate a devices.yaml for a Containerlab lab.

    Creates a MCP-Telecom devices.yaml that connects to the management
    IPs of a containerlab deployment, so you can instantly start using
    MCP-Telecom against your lab.

    Args:
        scenario: Which lab scenario to generate for
    """
    import yaml as _yaml

    from mcp_telecom.containerlab import ContainerlabManager

    clab = ContainerlabManager()
    topo_content = clab.generate_test_scenario(scenario)
    topo_data = _yaml.safe_load(topo_content)
    devices_yaml = clab.generate_devices_yaml("mcp-telecom", topo_data)
    return f"devices.yaml for '{scenario}' lab:\n\n{devices_yaml}"


@mcp.tool()
def clab_scenarios() -> str:
    """List available Containerlab test scenarios.

    Shows pre-built lab topologies you can deploy for testing
    MCP-Telecom without production network access.
    """
    scenarios = {
        "basic": "3-router triangle (Nokia SR Linux)",
        "mpls_core": "MPLS PE-P-PE with Nokia + Cisco XR",
        "datacenter": "Spine-leaf with Arista + Cisco NX-OS",
        "isp_edge": "Internet edge with BGP peering (multi-vendor)",
        "inventory": "Mirror your current devices.yaml inventory",
    }
    lines = ["Containerlab Scenarios:", "=" * 60]
    for name, desc in scenarios.items():
        lines.append(f"  {name:15s} — {desc}")
    lines.append("\nUse clab_generate(scenario='...') to create a topology.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Dashboard & Metrics
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool()
def start_dashboard(port: int = 8080) -> str:
    """Get instructions to start the web dashboard.

    The dashboard provides a real-time view of all device statuses with
    auto-refreshing device cards. Requires: pip install mcp-telecom[dashboard]

    Args:
        port: HTTP port for the dashboard (default: 8080)
    """
    return (
        f"To start the MCP-Telecom web dashboard:\n\n"
        f"  pip install fastapi uvicorn\n"
        f"  python -c \"\n"
        f"from mcp_telecom.dashboard import DashboardApp\n"
        f"from mcp_telecom.connection import DeviceManager\n"
        f"dm = DeviceManager('devices.yaml')\n"
        f"app = DashboardApp(dm)\n"
        f"app.start(port={port})\n"
        f"\"\n\n"
        f"Then open http://localhost:{port} in your browser.\n"
        f"The dashboard shows device status cards with auto-refresh."
    )


@mcp.tool()
def start_metrics_endpoint(port: int = 9090) -> str:
    """Get instructions to start the Prometheus metrics exporter.

    Exposes /metrics endpoint for Grafana dashboards. Tracks device
    reachability, command execution counts, and compliance scores.
    Requires: pip install mcp-telecom[metrics]

    Args:
        port: HTTP port for Prometheus metrics (default: 9090)
    """
    return (
        f"To start the Prometheus metrics exporter:\n\n"
        f"  pip install prometheus_client\n"
        f"  python -c \"\n"
        f"from mcp_telecom.metrics import metrics_exporter\n"
        f"metrics_exporter.start_http_server(port={port})\n"
        f"\"\n\n"
        f"Then add to your Prometheus config:\n"
        f"  scrape_configs:\n"
        f"    - job_name: mcp-telecom\n"
        f"      static_configs:\n"
        f"        - targets: ['localhost:{port}']\n\n"
        f"Available metrics:\n"
        f"  mcp_telecom_device_up\n"
        f"  mcp_telecom_device_response_ms\n"
        f"  mcp_telecom_commands_total\n"
        f"  mcp_telecom_command_duration_seconds\n"
        f"  mcp_telecom_devices_total\n"
        f"  mcp_telecom_compliance_score"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Additional MCP Resources
# ═══════════════════════════════════════════════════════════════════════════


@mcp.resource("telecom://topology")
def resource_topology() -> str:
    """Current network topology in JSON format."""
    from mcp_telecom.topology import topology_db
    return topology_db.to_json()


@mcp.resource("telecom://telemetry/{device_name}")
def resource_telemetry(device_name: str) -> str:
    """Latest telemetry data for a device."""
    from mcp_telecom.transports.telemetry import telemetry_store
    summary = telemetry_store.get_summary(device_name)
    return json.dumps(summary, indent=2, default=str)


@mcp.resource("telecom://compliance-rules")
def resource_compliance_rules() -> str:
    """Available compliance rules in JSON format."""
    from mcp_telecom.compliance import DEFAULT_RULES
    return json.dumps([r.model_dump() for r in DEFAULT_RULES], indent=2)


@mcp.resource("telecom://pool-stats")
def resource_pool_stats() -> str:
    """Connection pool statistics."""
    from mcp_telecom.pool import ConnectionPool
    pool = ConnectionPool()
    return json.dumps(pool.get_stats(), indent=2)


# ═══════════════════════════════════════════════════════════════════════════
#  Server Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def create_app():
    """Create the ASGI app with custom routes (e.g. /healthz)."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    app = mcp.http_app()
    # Add /healthz route for readiness probe (D-20)
    # StarletteWithLifespan uses .router.routes, not .route() decorator
    app.router.routes.append(Route("/healthz", healthz))

    return app


def main():
    """Run the MCP-Telecom server over Streamable HTTP."""
    import uvicorn

    logger.info("Starting MCP-Telecom server v0.2.0 (HTTP transport)")
    logger.info("Loaded %d devices", len(device_manager.list_devices()))

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

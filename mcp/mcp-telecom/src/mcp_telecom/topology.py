"""Network topology discovery for MCP-Telecom.

Builds a network topology graph from LLDP/CDP neighbor data collected
across multiple devices. Provides adjacency maps, path analysis, and
text-based topology visualization.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("mcp_telecom.topology")


@dataclass
class TopoNode:
    """A node (device) in the network topology."""

    name: str
    host: str
    vendor: str
    system_description: str = ""
    management_ip: str = ""


@dataclass
class TopoLink:
    """A link (connection) between two nodes."""

    local_device: str
    local_port: str
    remote_device: str
    remote_port: str
    remote_system: str = ""
    capabilities: str = ""


@dataclass
class NetworkTopology:
    """Complete network topology built from discovery data."""

    nodes: dict[str, TopoNode] = field(default_factory=dict)
    links: list[TopoLink] = field(default_factory=list)

    def add_node(self, node: TopoNode) -> None:
        self.nodes[node.name] = node

    def add_link(self, link: TopoLink) -> None:
        for existing in self.links:
            if (
                existing.local_device == link.remote_device
                and existing.local_port == link.remote_port
                and existing.remote_device == link.local_device
                and existing.remote_port == link.local_port
            ):
                return
        self.links.append(link)

    def get_neighbors(self, device: str) -> list[TopoLink]:
        """Get all links for a specific device."""
        return [
            link
            for link in self.links
            if link.local_device == device or link.remote_device == device
        ]

    def get_adjacency_map(self) -> dict[str, list[str]]:
        """Build an adjacency map of device-to-device connections."""
        adj: dict[str, set[str]] = {}
        for link in self.links:
            adj.setdefault(link.local_device, set()).add(link.remote_device)
            adj.setdefault(link.remote_device, set()).add(link.local_device)
        return {k: sorted(v) for k, v in sorted(adj.items())}

    def find_path(self, source: str, target: str) -> list[str] | None:
        """Find the shortest path between two devices (BFS)."""
        if source == target:
            return [source]

        adj = self.get_adjacency_map()
        visited = {source}
        queue: list[list[str]] = [[source]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            for neighbor in adj.get(current, []):
                if neighbor == target:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    def to_ascii(self) -> str:
        """Generate an ASCII topology diagram."""
        if not self.nodes:
            return "No topology data available."

        adj = self.get_adjacency_map()
        lines = [
            "Network Topology (discovered via LLDP/CDP)",
            "=" * 55,
            "",
        ]

        for device in sorted(self.nodes.keys()):
            node = self.nodes[device]
            vendor_tag = f" [{node.vendor}]" if node.vendor else ""
            lines.append(f"  [{device}]{vendor_tag}")

            neighbors = adj.get(device, [])
            for i, neighbor in enumerate(neighbors):
                connector = "└──" if i == len(neighbors) - 1 else "├──"
                link = self._find_link(device, neighbor)
                port_info = ""
                if link:
                    port_info = (
                        f" ({link.local_port} ↔ {link.remote_port})"
                    )
                lines.append(f"    {connector} {neighbor}{port_info}")

            lines.append("")

        lines.append(f"Nodes: {len(self.nodes)}  Links: {len(self.links)}")
        return "\n".join(lines)

    def _find_link(
        self, device_a: str, device_b: str
    ) -> TopoLink | None:
        for link in self.links:
            if (
                link.local_device == device_a
                and link.remote_device == device_b
            ):
                return link
            if (
                link.local_device == device_b
                and link.remote_device == device_a
            ):
                return TopoLink(
                    local_device=device_b,
                    local_port=link.local_port,
                    remote_device=device_a,
                    remote_port=link.remote_port,
                )
        return None

    def to_json(self) -> str:
        """Export topology as JSON for programmatic use."""
        return json.dumps(
            {
                "nodes": [
                    {
                        "name": n.name,
                        "host": n.host,
                        "vendor": n.vendor,
                    }
                    for n in self.nodes.values()
                ],
                "links": [
                    {
                        "source": link.local_device,
                        "source_port": link.local_port,
                        "target": link.remote_device,
                        "target_port": link.remote_port,
                    }
                    for link in self.links
                ],
            },
            indent=2,
        )

    def to_mermaid(self) -> str:
        """Export topology as a Mermaid diagram for docs/wikis."""
        lines = ["graph LR"]
        seen = set()
        for link in self.links:
            key = tuple(sorted([link.local_device, link.remote_device]))
            if key in seen:
                continue
            seen.add(key)
            lp = link.local_port.replace("/", "_")
            rp = link.remote_port.replace("/", "_")
            lines.append(
                f"    {link.local_device}"
                f' -- "{lp} ↔ {rp}" --- '
                f"{link.remote_device}"
            )
        return "\n".join(lines)


def parse_lldp_output(
    device_name: str, raw_output: str, vendor: str
) -> list[TopoLink]:
    """Parse LLDP neighbor output into topology links.

    Handles output from Nokia, Cisco, Juniper, and Arista CLI formats.
    """
    links = []

    if vendor in ("nokia_sros", "nokia_sros_telnet"):
        links = _parse_nokia_lldp(device_name, raw_output)
    elif vendor in ("cisco_ios", "cisco_xr", "cisco_nxos"):
        links = _parse_cisco_lldp(device_name, raw_output)
    elif vendor == "juniper_junos":
        links = _parse_juniper_lldp(device_name, raw_output)
    elif vendor == "arista_eos":
        links = _parse_cisco_lldp(device_name, raw_output)
    else:
        logger.warning(
            "No LLDP parser for vendor %s on %s", vendor, device_name
        )

    return links


def _parse_nokia_lldp(device: str, output: str) -> list[TopoLink]:
    """Parse Nokia SR OS LLDP output."""
    links = []
    current_port = ""

    for line in output.splitlines():
        line = line.strip()
        port_match = re.match(r'^(\d+/\d+/\d+)', line)
        if port_match:
            current_port = port_match.group(1)

        sys_match = re.search(r'System Name\s*:\s*(\S+)', line)
        if sys_match and current_port:
            remote = sys_match.group(1)
            links.append(TopoLink(
                local_device=device,
                local_port=current_port,
                remote_device=remote,
                remote_port="",
            ))

        port_id_match = re.search(
            r'Port Description\s*:\s*(.+)', line
        )
        if port_id_match and links:
            links[-1].remote_port = port_id_match.group(1).strip()

    return links


def _parse_cisco_lldp(device: str, output: str) -> list[TopoLink]:
    """Parse Cisco/Arista LLDP output.

    Cisco 'show lldp neighbors detail' groups entries separated by
    dashed lines. Each block contains System Name, Port id, and
    Local Intf fields in varying order.
    """
    links = []
    blocks = re.split(r'-{5,}', output)

    for block in blocks:
        local_match = re.search(r'Local Intf:\s*(\S+)', block)
        sys_match = re.search(r'System Name:\s*(\S+)', block)
        port_match = re.search(r'Port id:\s*(\S+)', block)

        if local_match and sys_match:
            links.append(TopoLink(
                local_device=device,
                local_port=local_match.group(1),
                remote_device=sys_match.group(1),
                remote_port=port_match.group(1) if port_match else "",
            ))

    return links


def _parse_juniper_lldp(device: str, output: str) -> list[TopoLink]:
    """Parse Juniper Junos LLDP output."""
    links = []

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and re.match(r'^[a-z]', parts[0]):
            local_port = parts[0]
            remote_system = parts[-2] if len(parts) >= 5 else parts[-1]
            remote_port = parts[-1]

            if not remote_system.startswith('-'):
                links.append(TopoLink(
                    local_device=device,
                    local_port=local_port,
                    remote_device=remote_system,
                    remote_port=remote_port,
                ))

    return links


topology_db = NetworkTopology()

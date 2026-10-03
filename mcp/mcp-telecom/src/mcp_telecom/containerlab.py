"""Containerlab topology generation for MCP-Telecom lab testing."""

from __future__ import annotations

import ipaddress
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from mcp_telecom.models import DeviceInfo, VendorType

VENDOR_TO_CLAB_KIND: dict[VendorType, str] = {
    VendorType.NOKIA_SROS: "nokia_srlinux",
    VendorType.NOKIA_SROS_TELNET: "nokia_srlinux",
    VendorType.CISCO_IOSXR: "cisco_xrd",
    VendorType.CISCO_IOS: "cisco_iosxe",
    VendorType.CISCO_NXOS: "cisco_nxos",
    VendorType.JUNIPER_JUNOS: "juniper_crpd",
    VendorType.ARISTA_EOS: "arista_ceos",
}

CLAB_DEFAULT_IMAGES: dict[VendorType, str] = {
    VendorType.NOKIA_SROS: "ghcr.io/nokia/srlinux:latest",
    VendorType.NOKIA_SROS_TELNET: "ghcr.io/nokia/srlinux:latest",
    VendorType.CISCO_IOSXR: "cisco/xrd-router:latest",
    VendorType.CISCO_IOS: "cisco/ios-xe:latest",
    VendorType.CISCO_NXOS: "cisco/nexus9300v:latest",
    VendorType.JUNIPER_JUNOS: "juniper/crpd:latest",
    VendorType.ARISTA_EOS: "ceosimage:latest",
}

CLAB_KIND_TO_DEVICE_TYPE: dict[str, str] = {
    "nokia_srlinux": "nokia_sros",
    "vr-nokia_sros": "nokia_sros",
    "cisco_xrd": "cisco_xr",
    "vr-cisco_xrv9k": "cisco_xr",
    "cisco_iosxe": "cisco_ios",
    "vr-cisco_csr1000v": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "vr-cisco_n9kv": "cisco_nxos",
    "juniper_crpd": "juniper_junos",
    "vr-juniper_vmx": "juniper_junos",
    "arista_ceos": "arista_eos",
    "ceosimage": "arista_eos",
}

DEFAULT_MGMT_SUBNET = "172.20.20.0/24"
DEFAULT_LAB_NAME = "mcp-telecom"


def _clab_node_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name.strip()).strip("-_.")
    return s or "node"


def _next_eth(allocator: dict[str, int], node: str) -> str:
    n = allocator[node]
    allocator[node] = n + 1
    return f"eth{n}"


def _split_endpoint(ep: str) -> tuple[str, str]:
    if ":" in ep:
        n, i = ep.split(":", 1)
        return n, i
    return ep, "eth1"


def _resolve_clab_name(node: str, name_map: dict[str, str]) -> str | None:
    if node in name_map.values():
        return node
    return name_map.get(node)


def _coerce_links(
    name_map: dict[str, str],
    links: Sequence[Mapping[str, Any] | tuple[str, str] | list[str]] | None,
) -> list[dict[str, list[str]]]:
    if not links:
        return []
    out: list[dict[str, list[str]]] = []
    for item in links:
        if isinstance(item, tuple) and len(item) == 2:
            a, b = str(item[0]), str(item[1])
            out.append({"endpoints": [a, b]})
        elif isinstance(item, list) and len(item) == 2:
            out.append({"endpoints": [str(item[0]), str(item[1])]})
        elif isinstance(item, Mapping):
            ep = item.get("endpoints")
            if isinstance(ep, (list, tuple)) and len(ep) == 2:
                out.append({"endpoints": [str(ep[0]), str(ep[1])]})
        else:
            continue
    filtered: list[dict[str, list[str]]] = []
    for link in out:
        ea, eb = link["endpoints"]
        na, ia = _split_endpoint(ea)
        nb, ib = _split_endpoint(eb)
        ra = _resolve_clab_name(na, name_map)
        rb = _resolve_clab_name(nb, name_map)
        if ra is not None and rb is not None:
            filtered.append({"endpoints": [f"{ra}:{ia}", f"{rb}:{ib}"]})
    return filtered


def _default_chain_links(devices: list[DeviceInfo]) -> list[dict[str, list[str]]]:
    if len(devices) < 2:
        return []
    alloc: dict[str, int] = defaultdict(lambda: 1)
    clab_names = [_clab_node_name(d.name) for d in devices]
    links: list[dict[str, list[str]]] = []
    for i in range(len(clab_names) - 1):
        a, b = clab_names[i], clab_names[i + 1]
        links.append(
            {"endpoints": [f"{a}:{_next_eth(alloc, a)}", f"{b}:{_next_eth(alloc, b)}"]}
        )
    return links


class ContainerlabManager:
    """Build Containerlab topologies and MCP-Telecom devices.yaml from inventory."""

    def __init__(self, lab_name: str = DEFAULT_LAB_NAME) -> None:
        self.lab_name = lab_name

    def generate_topology(
        self,
        devices: list[DeviceInfo],
        links: list[Mapping[str, Any] | tuple[str, str] | list[str]] | None = None,
    ) -> str:
        if not devices:
            raise ValueError("At least one device is required to generate a topology")

        name_map = {d.name: _clab_node_name(d.name) for d in devices}
        nodes: dict[str, dict[str, Any]] = {}

        for d in devices:
            cn = name_map[d.name]
            kind = VENDOR_TO_CLAB_KIND[d.vendor]
            image = CLAB_DEFAULT_IMAGES[d.vendor]
            nodes[cn] = {
                "kind": kind,
                "image": image,
                "startup-config": f"configs/{cn}.cfg",
            }

        if links is not None:
            link_list = _coerce_links(name_map, links)
        else:
            link_list = _default_chain_links(devices)

        doc: dict[str, Any] = {
            "name": self.lab_name,
            "mgmt": {"network": "clab", "ipv4-subnet": DEFAULT_MGMT_SUBNET},
            "topology": {"nodes": nodes, "links": link_list},
        }

        return yaml.dump(
            doc,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    def save_topology(self, content: str, path: str = "clab-mcp-telecom.yml") -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p.resolve())

    def generate_devices_yaml(self, lab_name: str, topology_data: dict[str, Any]) -> str:
        topo = topology_data.get("topology") or {}
        nodes = topo.get("nodes") or {}
        if not isinstance(nodes, dict):
            raise ValueError("topology_data must contain topology.nodes as a mapping")

        mgmt = topology_data.get("mgmt") or {}
        subnet = str(mgmt.get("ipv4-subnet") or DEFAULT_MGMT_SUBNET)
        net = ipaddress.ip_network(subnet, strict=False)
        hosts = list(net.hosts())
        if len(hosts) > 1:
            hosts = hosts[1:]
        if len(hosts) < len(nodes):
            raise ValueError("Management subnet has fewer usable host addresses than nodes")

        sorted_names = sorted(nodes.keys())
        devices_out: dict[str, dict[str, Any]] = {}

        for idx, node_name in enumerate(sorted_names):
            spec = nodes[node_name]
            if not isinstance(spec, Mapping):
                continue
            kind = str(spec.get("kind") or "")
            device_type = CLAB_KIND_TO_DEVICE_TYPE.get(kind, "nokia_sros")
            host_ip = str(hosts[idx])
            devices_out[node_name] = {
                "device_type": device_type,
                "host": host_ip,
                "username": "admin",
                "password": "${CLAB_DEVICE_PASSWORD}",
                "port": 22,
                "timeout": 60,
            }

        header = (
            f"# MCP-Telecom devices for Containerlab lab: {lab_name}\n"
            f"# Deploy the lab first; management IPs follow {subnet} assignment order.\n\n"
        )
        return header + yaml.dump(
            devices_out,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )

    def get_deploy_commands(self, topology_file: str = "clab-mcp-telecom.yml") -> str:
        t = topology_file
        return (
            f"sudo containerlab deploy -t {t}\n"
            f"sudo containerlab inspect -t {t}\n"
            f"sudo containerlab destroy -t {t}\n"
        )

    def generate_test_scenario(self, scenario: str = "basic") -> str:
        key = scenario.lower().strip()
        builders = {
            "basic": _scenario_basic,
            "mpls_core": _scenario_mpls_core,
            "datacenter": _scenario_datacenter,
            "isp_edge": _scenario_isp_edge,
        }
        if key not in builders:
            raise ValueError(
                f"Unknown scenario '{scenario}'. Choose from: {', '.join(sorted(builders))}"
            )
        doc = builders[key]()
        return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _scenario_basic() -> dict[str, Any]:
    return {
        "name": "mcp-telecom-basic",
        "mgmt": {"network": "clab", "ipv4-subnet": DEFAULT_MGMT_SUBNET},
        "topology": {
            "nodes": {
                "r1": {
                    "kind": "nokia_srlinux",
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/r1.cfg",
                },
                "r2": {
                    "kind": "nokia_srlinux",
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/r2.cfg",
                },
                "r3": {
                    "kind": "nokia_srlinux",
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/r3.cfg",
                },
            },
            "links": [
                {"endpoints": ["r1:eth1", "r2:eth1"]},
                {"endpoints": ["r2:eth2", "r3:eth1"]},
                {"endpoints": ["r3:eth2", "r1:eth2"]},
            ],
        },
    }


def _scenario_mpls_core() -> dict[str, Any]:
    return {
        "name": "mcp-telecom-mpls-core",
        "mgmt": {"network": "clab", "ipv4-subnet": DEFAULT_MGMT_SUBNET},
        "topology": {
            "nodes": {
                "pe-nokia-a": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.NOKIA_SROS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/pe-nokia-a.cfg",
                },
                "p-cisco": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_IOSXR],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_IOSXR],
                    "startup-config": "configs/p-cisco.cfg",
                },
                "pe-nokia-b": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.NOKIA_SROS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/pe-nokia-b.cfg",
                },
            },
            "links": [
                {"endpoints": ["pe-nokia-a:eth1", "p-cisco:eth1"]},
                {"endpoints": ["p-cisco:eth2", "pe-nokia-b:eth1"]},
            ],
        },
    }


def _scenario_datacenter() -> dict[str, Any]:
    return {
        "name": "mcp-telecom-dc",
        "mgmt": {"network": "clab", "ipv4-subnet": DEFAULT_MGMT_SUBNET},
        "topology": {
            "nodes": {
                "spine1": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.ARISTA_EOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.ARISTA_EOS],
                    "startup-config": "configs/spine1.cfg",
                },
                "spine2": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.ARISTA_EOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.ARISTA_EOS],
                    "startup-config": "configs/spine2.cfg",
                },
                "leaf1": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_NXOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_NXOS],
                    "startup-config": "configs/leaf1.cfg",
                },
                "leaf2": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_NXOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_NXOS],
                    "startup-config": "configs/leaf2.cfg",
                },
                "leaf3": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_NXOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_NXOS],
                    "startup-config": "configs/leaf3.cfg",
                },
            },
            "links": [
                {"endpoints": ["leaf1:eth1", "spine1:eth1"]},
                {"endpoints": ["leaf1:eth2", "spine2:eth1"]},
                {"endpoints": ["leaf2:eth1", "spine1:eth2"]},
                {"endpoints": ["leaf2:eth2", "spine2:eth2"]},
                {"endpoints": ["leaf3:eth1", "spine1:eth3"]},
                {"endpoints": ["leaf3:eth2", "spine2:eth3"]},
            ],
        },
    }


def _scenario_isp_edge() -> dict[str, Any]:
    return {
        "name": "mcp-telecom-isp-edge",
        "mgmt": {"network": "clab", "ipv4-subnet": DEFAULT_MGMT_SUBNET},
        "topology": {
            "nodes": {
                "upstream": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_IOSXR],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_IOSXR],
                    "startup-config": "configs/upstream.cfg",
                },
                "isp-edge": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.NOKIA_SROS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.NOKIA_SROS],
                    "startup-config": "configs/isp-edge.cfg",
                },
                "peer-isp": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.JUNIPER_JUNOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.JUNIPER_JUNOS],
                    "startup-config": "configs/peer-isp.cfg",
                },
                "ce-site": {
                    "kind": VENDOR_TO_CLAB_KIND[VendorType.CISCO_IOS],
                    "image": CLAB_DEFAULT_IMAGES[VendorType.CISCO_IOS],
                    "startup-config": "configs/ce-site.cfg",
                },
            },
            "links": [
                {"endpoints": ["upstream:eth1", "isp-edge:eth1"]},
                {"endpoints": ["isp-edge:eth2", "peer-isp:eth1"]},
                {"endpoints": ["isp-edge:eth3", "ce-site:eth1"]},
            ],
        },
    }

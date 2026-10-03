"""Tests for network topology discovery."""

from mcp_telecom.topology import (
    NetworkTopology,
    TopoLink,
    TopoNode,
    parse_lldp_output,
)


class TestNetworkTopology:
    def test_add_node(self):
        topo = NetworkTopology()
        topo.add_node(TopoNode(name="r1", host="1.1.1.1", vendor="nokia_sros"))
        assert "r1" in topo.nodes

    def test_add_link(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink(
            local_device="r1", local_port="1/1/1",
            remote_device="r2", remote_port="1/1/2",
        ))
        assert len(topo.links) == 1

    def test_no_duplicate_links(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink(
            local_device="r1", local_port="1/1/1",
            remote_device="r2", remote_port="1/1/2",
        ))
        topo.add_link(TopoLink(
            local_device="r2", local_port="1/1/2",
            remote_device="r1", remote_port="1/1/1",
        ))
        assert len(topo.links) == 1

    def test_adjacency_map(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        topo.add_link(TopoLink("r2", "e3", "r3", "e4"))
        adj = topo.get_adjacency_map()
        assert "r2" in adj["r1"]
        assert "r1" in adj["r2"]
        assert "r3" in adj["r2"]

    def test_find_path_direct(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        path = topo.find_path("r1", "r2")
        assert path == ["r1", "r2"]

    def test_find_path_multihop(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        topo.add_link(TopoLink("r2", "e3", "r3", "e4"))
        topo.add_link(TopoLink("r3", "e5", "r4", "e6"))
        path = topo.find_path("r1", "r4")
        assert path == ["r1", "r2", "r3", "r4"]

    def test_find_path_same_device(self):
        topo = NetworkTopology()
        assert topo.find_path("r1", "r1") == ["r1"]

    def test_find_path_unreachable(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        assert topo.find_path("r1", "r99") is None

    def test_to_ascii(self):
        topo = NetworkTopology()
        topo.add_node(TopoNode("r1", "1.1.1.1", "nokia_sros"))
        topo.add_node(TopoNode("r2", "2.2.2.2", "cisco_xr"))
        topo.add_link(TopoLink("r1", "1/1/1", "r2", "Gi0/0/0"))
        text = topo.to_ascii()
        assert "r1" in text
        assert "r2" in text

    def test_to_json(self):
        topo = NetworkTopology()
        topo.add_node(TopoNode("r1", "1.1.1.1", "nokia_sros"))
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        data = topo.to_json()
        assert '"r1"' in data
        assert '"links"' in data

    def test_to_mermaid(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        mermaid = topo.to_mermaid()
        assert "graph LR" in mermaid
        assert "r1" in mermaid

    def test_empty_topology(self):
        topo = NetworkTopology()
        assert "No topology data" in topo.to_ascii()

    def test_get_neighbors(self):
        topo = NetworkTopology()
        topo.add_link(TopoLink("r1", "e1", "r2", "e2"))
        topo.add_link(TopoLink("r1", "e3", "r3", "e4"))
        neighbors = topo.get_neighbors("r1")
        assert len(neighbors) == 2


class TestLldpParsing:
    def test_cisco_lldp_parse(self):
        output = """----------------------------------------
Chassis id: 001e.1234.5678
Port id: Gi0/0/1
System Name: router-b

Local Intf: Gi0/0/0
----------------------------------------
Chassis id: 001e.abcd.ef01
Port id: Eth1/1
System Name: switch-a

Local Intf: Gi0/0/1
"""
        links = parse_lldp_output("router-a", output, "cisco_ios")
        assert len(links) == 2
        remote_names = {link.remote_device for link in links}
        assert "router-b" in remote_names
        assert "switch-a" in remote_names

    def test_unknown_vendor_returns_empty(self):
        links = parse_lldp_output("r1", "some output", "unknown_vendor")
        assert links == []

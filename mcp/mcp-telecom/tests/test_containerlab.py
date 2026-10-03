"""Tests for Containerlab topology helpers."""

from __future__ import annotations

import pytest
import yaml

from mcp_telecom.containerlab import (
    VENDOR_TO_CLAB_KIND,
    ContainerlabManager,
)
from mcp_telecom.models import VendorType


class TestVendorToClabKind:
    def test_covers_all_vendor_types(self):
        for v in VendorType:
            assert v in VENDOR_TO_CLAB_KIND
            assert isinstance(VENDOR_TO_CLAB_KIND[v], str)
            assert VENDOR_TO_CLAB_KIND[v]


class TestContainerlabManager:
    def test_generate_test_scenario_basic_valid_yaml(self):
        mgr = ContainerlabManager()
        raw = mgr.generate_test_scenario("basic")
        data = yaml.safe_load(raw)
        assert data["name"] == "mcp-telecom-basic"
        assert "topology" in data
        assert "nodes" in data["topology"]
        assert "links" in data["topology"]

    @pytest.mark.parametrize(
        "scenario",
        ["basic", "mpls_core", "datacenter", "isp_edge"],
    )
    def test_generate_test_scenario_all_scenarios(self, scenario: str):
        mgr = ContainerlabManager()
        raw = mgr.generate_test_scenario(scenario)
        data = yaml.safe_load(raw)
        assert isinstance(data, dict)
        assert "name" in data
        assert data.get("topology", {}).get("nodes")

    def test_get_deploy_commands(self):
        mgr = ContainerlabManager()
        cmds = mgr.get_deploy_commands("my-topo.yml")
        assert "sudo containerlab deploy -t my-topo.yml" in cmds
        assert "sudo containerlab inspect -t my-topo.yml" in cmds
        assert "sudo containerlab destroy -t my-topo.yml" in cmds

    def test_generate_devices_yaml_valid(self):
        mgr = ContainerlabManager()
        topo_raw = mgr.generate_test_scenario("basic")
        topo = yaml.safe_load(topo_raw)
        assert topo is not None
        out = mgr.generate_devices_yaml("mcp-telecom-basic", topo)
        parsed = yaml.safe_load(out)
        assert isinstance(parsed, dict)
        for _node, spec in parsed.items():
            assert "device_type" in spec
            assert "host" in spec

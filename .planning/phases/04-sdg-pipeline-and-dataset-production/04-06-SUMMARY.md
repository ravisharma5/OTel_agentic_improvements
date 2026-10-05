---
phase: 04-sdg-pipeline-and-dataset-production
plan: 06
subsystem: mcp-telecom-device-backend
status: checkpoint-blocked
tags: [containerlab, device-inventory, command-allowlist, nokia-srl]
dependency_graph:
  requires: [04-01]
  provides: [containerlab-topology, device-inventory, command-allowlist]
  affects: [mcp-telecom, sdg-pipeline]
tech_stack:
  added: [containerlab, nokia-srlinux]
  patterns: [dict-keyed-device-config, deny-by-default-allowlist]
key_files:
  created:
    - mcp/mcp-telecom/containerlab-topology.yaml
    - mcp/mcp-telecom/devices.yaml
  modified:
    - mcp/mcp-telecom/devices.yaml.example
    - mcp/mcp-telecom/command_allowlist.yaml
decisions:
  - "Used ContainerlabManager.generate_test_scenario('basic') to generate topology matching _scenario_basic() output (r1, r2, r3 nodes)"
  - "Nokia SRL default credentials (admin/NokiaSrl1!) used for local testing; documented Secret pattern for OpenShift deployment"
  - "32 command prefixes in allowlist covering Nokia, Cisco, Juniper, Arista show/display families plus diagnostics"
  - "Fixed devices.yaml.example from incompatible list-style to correct dict-keyed format matching DeviceManager.load_config() contract"
metrics:
  duration: "2 minutes"
  completed_date: null
  tasks_completed: 1
  tasks_total: 2
  checkpoint_task: 2
---

# Phase 4 Plan 06: Containerlab Topology and Device Config Summary

Containerlab 3-node Nokia SRL ring topology generated; device inventory and command allowlist populated for SDG device-layer tool coverage. Blocked at checkpoint awaiting human deployment and SSH verification.

## Completed Tasks

### Task 1: Generate Containerlab topology, fix devices.yaml.example, and populate device config files

**Commit:** `e07ddb4`

**What was done:**

1. **containerlab-topology.yaml** -- Generated using `ContainerlabManager.generate_test_scenario("basic")`. Produces a 3-node Nokia SR Linux ring with nodes named r1, r2, r3 (confirmed against `_scenario_basic()` at line 244 of containerlab.py). Management subnet 172.20.20.0/24. Ring links: r1:eth1-r2:eth1, r2:eth2-r3:eth1, r3:eth2-r1:eth2.

2. **devices.yaml** -- Populated in dict-keyed format matching `DeviceManager.load_config()` contract (confirmed: `for name, cfg in raw.items()` at line 45 of connection.py). Three devices (r1, r2, r3) with management IPs 172.20.20.2/.3/.4, device_type nokia_sros, port 22, Nokia SRL default credentials. Includes comments documenting Kubernetes service name pattern for Clabernetes deployment.

3. **devices.yaml.example** -- Fixed from incompatible list-style format (`devices: [{hostname: ..., platform: ...}]`) to correct dict-keyed format that `DeviceManager.load_config()` actually expects. Added 3 example entries (cisco_ios, arista_eos, nokia_sros) showing the correct pattern with env-var credential references.

4. **command_allowlist.yaml** -- Populated with 32 permitted command prefixes covering MCP-Telecom's 58 device-layer tools. Includes: show bgp/routing/interfaces/mpls/lldp/lag/system/version/chassis/port/router/service/network-instance families, display equivalents for Nokia SR OS classic CLI, and diagnostic commands (ping, traceroute). These are consumed by `safety.py`'s `validate_command()` Gate 2 (CR-01).

**Verification results:**
- Topology: 3 nodes (r1, r2, r3) with nokia_srlinux kind, 3 ring links, 172.20.20.0/24 mgmt
- devices.yaml: dict-keyed with r1/r2/r3, loadable by DeviceManager.load_config()
- command_allowlist.yaml: 32 entries, includes show/display families + ping/traceroute
- devices.yaml.example: dict-keyed format, no list-style `devices:` key

## Checkpoint: Task 2 -- Deploy Containerlab and verify device reachability

**Status:** Blocked -- requires human action (infrastructure deployment)

**What needs to happen:**
1. Deploy Clabernetes on existing OpenShift cluster (or Containerlab on a VM)
2. Apply the topology via clabverter
3. Verify 3 SRL pods (r1, r2, r3) reach Running state
4. Test SSH connectivity from MCP-Telecom pod to each device
5. Update devices.yaml hosts to Kubernetes service names if using Clabernetes
6. Run ConfigMap sync script

See Task 2 in 04-06-PLAN.md for detailed verification steps.

## Deviations from Plan

None -- plan executed exactly as written for Task 1.

## Self-Check: PASSED

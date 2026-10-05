---
phase: 04-sdg-pipeline-and-dataset-production
plan: 06
subsystem: mcp-telecom-device-backend
status: complete
tags: [containerlab, clabernetes, device-inventory, command-allowlist, nokia-srl]
dependency_graph:
  requires: [04-01]
  provides: [containerlab-topology, device-inventory, command-allowlist, live-device-backend]
  affects: [mcp-telecom, sdg-pipeline]
tech_stack:
  added: [containerlab, nokia-srlinux, clabernetes]
  patterns: [dict-keyed-device-config, deny-by-default-allowlist]
key_files:
  created:
    - mcp/mcp-telecom/containerlab-topology.yaml
    - mcp/mcp-telecom/devices.yaml
    - mcp/openshift/clabernetes-topology-cr.yaml
  modified:
    - mcp/mcp-telecom/devices.yaml.example
    - mcp/mcp-telecom/command_allowlist.yaml
decisions:
  - "Used ContainerlabManager.generate_test_scenario('basic') to generate topology matching _scenario_basic() output (r1, r2, r3 nodes)"
  - "Nokia SRL default credentials (admin/NokiaSrl1!) used for local testing; documented Secret pattern for OpenShift deployment"
  - "32 command prefixes in allowlist covering Nokia, Cisco, Juniper, Arista show/display families plus diagnostics"
  - "Fixed devices.yaml.example from incompatible list-style to correct dict-keyed format matching DeviceManager.load_config() contract"
  - "Deployed via Clabernetes on OpenShift namespace c9s, constructing the Topology CR directly (spec.definition.containerlab as a raw string) since clabverter was unavailable in the deployment environment -- the CRD accepts the same containerlab YAML clabverter would have wrapped"
  - "Removed startup-config: configs/r*.cfg references from the topology -- those files were never generated anywhere in the repo; Nokia SRL boots fine on factory defaults"
  - "Renamed link endpoints from generic eth1/eth2 to Nokia SR Linux's native e1-1/e1-2 format -- containerlab 0.74.3 does not auto-translate generic ethN names for the nokia_srlinux kind and rejects them outright"
  - "Granted anyuid SCC to clabernetes-manager/clabernetes-service-account (controller pods failed under default restricted-v2 due to a webhook cert file owned by a fixed UID) and privileged SCC to clabernetes-launcher-service-account (per-node launcher pods require runAsUser:0 + privileged:true for docker-in-docker)"
  - "Updated devices.yaml hosts to Clabernetes' per-node Service DNS names (mcp-telecom-basic-r{1,2,3}.c9s.svc.cluster.local) -- ClusterIP is reachable cluster-wide even though the Service's EXTERNAL-IP stays <pending> on this sandbox cluster (no cloud LB provisioner)"
metrics:
  duration: "2 minutes (Task 1) + ~45 minutes (Task 2, including SCC/interface-naming troubleshooting)"
  completed_date: "2026-10-05"
  tasks_completed: 2
  tasks_total: 2
  checkpoint_task: 2
---

# Phase 4 Plan 06: Containerlab Topology and Device Config Summary

Containerlab 3-node Nokia SRL ring topology generated, deployed live to OpenShift via Clabernetes (namespace c9s), and verified reachable from the MCP-Telecom pod over SSH with a real `show version` response. Device inventory and command allowlist are populated and pointed at the live deployment.

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

### Task 2: Deploy Containerlab and verify device reachability

**Status:** Complete

**What was done:**

1. **Clabernetes installed** via Helm into new namespace `c9s`: `helm upgrade --install --create-namespace --namespace c9s clabernetes oci://ghcr.io/srl-labs/clabernetes/clabernetes` (chart v0.6.0, image v0.6.0).

2. **SCC troubleshooting (3 rounds):**
   - Initial `oc adm policy add-scc-to-user privileged -n c9s -z clabernetes-manager` targeted the wrong SA name; the actual manager pods run as `clabernetes-service-account`.
   - Granting `privileged` to the correct SA still left pods under `restricted-v2` (assigns a random non-root UID) -- manager pods crashed with `permission denied` opening a webhook TLS cert owned by a fixed UID. Fixed by granting `anyuid` SCC instead (to both `clabernetes-service-account` and `clabernetes-manager`), which lets the pod run as its image's intended UID rather than a randomized one.
   - Manager/UI pods then ran stably (3/3 Running, 0 restarts).

3. **Topology CR applied directly** (clabverter was not installed and podman machine was not running in the deployment environment, so the clabverter conversion step was skipped): constructed a `clabernetes.containerlab.dev/v1alpha1` `Topology` CR with `spec.definition.containerlab` holding the raw containerlab YAML as a string -- this is exactly what clabverter itself would have produced, since the Topology CRD accepts raw containerlab topology YAML natively. See `mcp/openshift/clabernetes-topology-cr.yaml`.

4. **Two real topology bugs found and fixed during deployment** (not present until an actual deploy was attempted):
   - `startup-config: configs/r{1,2,3}.cfg` referenced files that don't exist anywhere in the repo -- containerlab errored trying to load them. Removed; Nokia SR Linux boots on factory defaults.
   - Generic `eth1`/`eth2` link endpoint names are rejected by containerlab 0.74.3 for the `nokia_srlinux` kind (`"eth1" doesn't match the required pattern: ethernet-L/P ... or eL-P"`). Renamed to the native `e1-1`/`e1-2` format. This is a latent gap in `containerlab.py`'s generic `_next_eth()` helper (line 60-63), which emits plain `ethN` for every vendor kind regardless of what that kind's CLI actually expects -- flagged in both the topology file's header comment and here for whoever next touches scenario generation for a kind other than the Linux-native ones.

5. **Launcher pods also needed a separate, stronger SCC grant:** after the Topology CR deployed, the per-node launcher Deployments (`mcp-telecom-basic-r1/r2/r3`) failed with `ReplicaFailure: FailedCreate` -- their pod spec requests `securityContext.privileged: true` + `runAsUser: 0` (needed for the docker-in-docker that runs containerlab inside each launcher pod), which no non-privileged SCC permits. Granted `privileged` SCC to `clabernetes-launcher-service-account` specifically (separate from the controller SA). All 3 launcher pods reached `Running` immediately after.

6. **End-to-end verification performed** (not just TCP reachability):
   - `oc get topology -n c9s` shows `STATE: running`, `READY: true`.
   - Raw SSH banner exchange succeeded from the `mcp-telecom` pod (namespace `otel25-mcp`) to all three devices via their Clabernetes Service DNS names (`mcp-telecom-basic-r{1,2,3}.c9s.svc.cluster.local:22`).
   - Full authenticated login + command execution via the MCP-Telecom pod's own `netmiko` library (`/app/.venv/bin/python3`, `device_type: nokia_sros`, `admin`/`NokiaSrl1!`) against `r1`, running `show version` and receiving real device output: `Hostname: r1`, `Chassis Type: 7220 IXR-D2L`, `System HW MAC Address: 1A:05:00:FF:00:00`. This is the exact tool-call path MCP-Telecom's `run_command`/`show_interface_detail` tools use in production, not a synthetic test.
7. **`devices.yaml` updated** from the placeholder `172.20.20.x` Containerlab-internal management IPs (unreachable from other pods/namespaces) to the actual Clabernetes Service DNS names that the live reachability test above confirms work cross-namespace.
8. **ConfigMap sync script run:** `scripts/sync-backend-routing.sh` -- `otel25-backends/backend-routing` synced to `otel25-mcp/backend-routing` (6/6 keys verified, no drift found; unrelated to this specific device deployment but is the Task's documented final step per the plan).

**Verification results:**
- `oc get pods -n c9s`: `clabernetes-manager` 3/3 Running, `clabernetes-ui` 3/3 Running, `mcp-telecom-basic-r1/r2/r3` 1/1 Running, 0 restarts after fix
- `oc get topology -n c9s`: `mcp-telecom-basic` STATE=running, READY=true
- SSH banner from all 3 devices: `SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4`
- Authenticated `show version` via netmiko against r1: real Nokia SR Linux output returned
- `scripts/sync-backend-routing.sh`: PASS (4/4 checks)

## Deviations from Plan

- Task 2's documented steps assumed `clabverter` would be available; it was not installed, and the podman machine needed to run it via container was not started. Worked around by hand-constructing the Clabernetes `Topology` CR directly (the CRD's `spec.definition.containerlab` field is exactly what clabverter populates from the same input), avoiding the dependency entirely rather than installing new tooling.
- Task 2's plan assumed the manager SA name was `clabernetes-manager`; discovered via live deployment that the actual controller SA Helm creates is `clabernetes-service-account` (both exist, but the pods run as the latter) -- both are now granted appropriate SCCs for completeness.
- `privileged` alone was insufficient for the controller pods (needed `anyuid` instead) and insufficient for a different reason than expected for the launcher pods (which did need `privileged`, but to a third, separate service account not mentioned in the original plan's verification steps: `clabernetes-launcher-service-account`). Documented in `mcp/openshift/clabernetes-topology-cr.yaml`'s header comment for reproducibility.
- The topology YAML itself had two latent bugs (nonexistent startup-config files, incorrect generic interface naming for the nokia_srlinux kind) that only surfaced once a real deployment was attempted -- both fixed in the committed `containerlab-topology.yaml`.

## Self-Check: PASSED

# MCP telco toolkit audit

Audited 2026-09-26. The original mcp-telco-toolkit (rohitsalesforce132) is gone — repo and user account both return 404. This audit covers what exists now.

## Available MCP servers for telecom

### 1. MCP-Telecom (Avinash-Amudala/MCP-Telecom)

The strongest existing toolkit. Network equipment focused, not API/BSS focused.

| Field | Detail |
|---|---|
| **URL** | github.com/Avinash-Amudala/MCP-Telecom |
| **Language** | Python 3.10+ |
| **Framework** | FastMCP (Python MCP SDK) |
| **License** | MIT |
| **Tools** | 60+ |
| **Deployment** | Docker, Docker Compose, or direct Python. Dockerfile included. |
| **Tests** | 157 tests |
| **Transport** | stdio (standard MCP) |

**What it covers:**

- **Routing & protocols (5 tools):** BGP summary/neighbors, routing table, OSPF neighbors, MPLS LSP
- **Interfaces & L2 (6 tools):** interface status/detail, LLDP neighbors, LAG, ARP, MAC table
- **System monitoring (7 tools):** system info, alarms, NTP, CPU, memory, environment, syslog
- **Config & ops (9 tools):** config backup/compare, safe CLI command execution, vendor-translated ops, device listing, health check, audit log
- **NETCONF/YANG (3 tools):** get config, get operational state, list capabilities
- **gNMI telemetry (6 tools):** subscribe, query, history, list subscriptions, unsubscribe, list paths
- **Topology (6 tools):** LLDP/CDP discovery, ASCII/JSON/Mermaid export, shortest path, device neighbors
- **SNMP (3 tools):** get, walk, device overview
- **Parallel queries (4 tools):** multi-device command, operation, comparison, health check
- **Compliance (3 tools):** score against 20+ rules, check single rule, list rules
- **Containerlab (3 tools):** generate topology, devices.yaml, list scenarios
- **Dashboard & metrics (3 tools):** web dashboard, Prometheus exporter, connection pool stats

**Supported vendors:** Nokia SR OS, Cisco IOS/IOS-XE/IOS-XR/NX-OS, Juniper JunOS, Arista EOS

**Safety model:** Read-only. Blocks configure/delete/commit/reload/shutdown/write/clear/reset/debug. All commands logged in JSONL.

**How tools are defined:** Python functions decorated with `@mcp.tool()` in `src/mcp_telecom/tools/`. Adding a new tool = write a function, add decorator, import in main. Pattern is straightforward.

**Backends:** Connects to real network devices via SSH (Netmiko), NETCONF (ncclient), gNMI, SNMP. Also generates containerlab topologies for lab testing. No mock mode.

**OpenShift:** Not specifically designed for it, but has Dockerfile and docker-compose.yml. Python app, runs anywhere containers run. Straightforward to deploy on OpenShift.

**Relevance to fault prediction:** High. The `show_alarms`, `show_log_events`, `show_interfaces`, `show_cpu`, `show_memory`, `show_environment`, SNMP polling, and gNMI telemetry tools directly support fault detection on physical/virtual network equipment. However, this is the **infrastructure layer** — it talks to routers and switches, not to BSS/OSS APIs (TMF642, TMF628) or 5G core APIs (NWDAF).

### 2. mcp-camara-demo (kimagliardi/mcp-camara-demo)

Minimal demo. Proof of concept only.

| Field | Detail |
|---|---|
| **URL** | github.com/kimagliardi/mcp-camara-demo |
| **Language** | Python |
| **Framework** | MCP Python SDK |
| **License** | None specified |
| **Tools** | 3 |

**Tools:**

1. `load_openapi_spec` — loads the CAMARA NetworkSliceBooking OpenAPI YAML
2. `call_sessions_api` — POST to /sessions on localhost:9000
3. `interpret_natural_language` — extracts network slicing params from text, maps to API call

**Relevance:** Shows the pattern for wrapping CAMARA APIs as MCP tools. Only covers Network Slice Booking. Too thin to use directly, but the approach (load OpenAPI spec → expose as tool) is exactly what we'd do at scale.

### 3. telco-mcp-server (rashad-malik/telco-mcp-server)

Customer churn prediction demo. 4 tools (plot, correlate, query, predict churn). Educational only. Not relevant to fault prediction MCP work.

## Summary: what we have vs what we need

| Need | What exists | Gap |
|---|---|---|
| **TMF642 Alarm Management** | Nothing | Build from OpenAPI spec |
| **TMF628 Performance Management** | Nothing | Build from OpenAPI spec |
| **NWDAF analytics (TS 29.520)** | Nothing as MCP; NextGCore exposes the API | Build MCP wrapper for NextGCore NWDAF |
| **CAMARA Device Status** | Nothing (mcp-camara-demo only covers Network Slicing) | Build from OpenAPI spec |
| **TMF621 Trouble Ticket** | Nothing | Build from OpenAPI spec |
| **Network equipment alarms/metrics** | MCP-Telecom (60+ tools, MIT) | Exists. Can use directly. |
| **CAMARA subscriber APIs** | mcp-camara-demo (3 tools, demo only) | Need to build properly |

## Recommendation

The original mcp-telco-toolkit is gone, but MCP-Telecom is a better starting point for the infrastructure layer. For the BSS/OSS layer (TMF642, TMF628, TMF621) and the 5G core layer (NWDAF), we need to build new MCP tools.

**Two-track approach:**

1. **Infrastructure layer:** Use MCP-Telecom as-is for device-level fault data (alarms, metrics, telemetry). MIT license, 60+ tools, Docker-ready.
2. **BSS/OSS + 5G core layer:** Build a new MCP server (or extend mcp-camara-demo's pattern) wrapping TMF642, TMF628, TMF621, NWDAF (TS 29.520), and CAMARA Device Status. Use OpenAPI-to-MCP conversion. Target: ~20 new tools for the fault prediction use case.

Both feed into the SDG pipeline for training data generation.

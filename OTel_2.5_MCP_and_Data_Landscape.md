# OTel 2.5 — Telco MCP servers and training data

Author: Ravi Sharma

Answering two questions that came up during review of the OTel 2.5 tool-calling proposal:

1. Do we have training data for long-horizon telecom tasks (multi-step agentic workflows)? If not, how do we generate it?
2. What MCP servers and tool schemas can we build on?

This document answers both. Single-turn and multi-turn formats are both in scope, since operators use the model both ways.

---

## Part 1: Telecom MCP servers

### What exists


| MCP Server / Toolkit            | Tools                                                              | Source APIs                                                                          | Status                               | Link                                                                                                                                    |
| ------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| **MCP-Telecom**                 | 60+ tools (routing, interfaces, system monitoring, config, NETCONF, gNMI, SNMP, topology, compliance) | Nokia SR OS, Cisco IOS/IOS-XE/IOS-XR/NX-OS, Juniper JunOS, Arista EOS | Working, MIT license, Docker-ready | [github.com/Avinash-Amudala/MCP-Telecom](https://github.com/Avinash-Amudala/MCP-Telecom) |
| **mcp-camara-demo**             | 3 tools (load spec, call sessions API, NL-to-API)                  | CAMARA Network Slice Booking                                                         | Demo / proof of concept              | [github.com/kimagliardi/mcp-camara-demo](https://github.com/kimagliardi/mcp-camara-demo) |
| **CAMARA MCP (white paper)**    | Architectural pattern, not a shipped server                        | QoD, Device Location, Edge Discovery, Carrier Billing, etc.                          | White paper only (Jan 2026)          | [camaraproject.org](https://camaraproject.org/2026/01/12/camara-charts-a-path-for-network-aware-ai-applications-with-mcp/)              |
| **Telco-AIX AutoNet**           | MCP Proxy Server for diagnostic, planning, and validation agents   | Internal telco ops APIs                                                              | In development (Fatih Nar / Red Hat) | Published via [Medium](https://medium.com/enterpriseai/episode-xxvii-lessons-learned-from-a-telco-mcp-backend-experiments-bf14d90b1e6a) |
| **TM Forum Agentic Innovation** | Agents for fault resolution, 5G dynamic slice management, security | TM Forum Open APIs                                                                   | Demonstrated at DTW Ignite 2026      | [tmforum.org](https://www.tmforum.org/member-projects/innovation-hubs/projects/genai-llm)                                               |

Note: The previously referenced mcp-telco-toolkit (rohitsalesforce132) is no longer available — both the repo and the GitHub account return 404 as of September 2026.




### API schemas available for conversion to MCP tools

These aren't MCP servers yet, but they're OpenAPI 3.0 specs that can be converted to MCP tool definitions and used for SDG. Conversion tooling exists ([@samchon/openapi](https://dev.to/samchon/i-made-openapi-and-llm-schema-definitions-1mn0) does OpenAPI-to-LLM-function-schema).


| Source                                                                              | Scale               | What it covers                                                                                                                                                                                                | License       |
| ----------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| **CAMARA APIs** ([github.com/camaraproject](https://github.com/camaraproject))      | 60+ APIs            | Subscriber-facing: QoD, Device Location, SIM Swap, Number Verification, Device Status, Edge Discovery, Carrier Billing, Call Forwarding, Click-to-Dial, KYC/Age Verification                                  | Apache 2.0    |
| **TM Forum Open APIs** ([github.com/tmforum-apis](https://github.com/tmforum-apis)) | 96 repos, 100+ APIs | Network management: product catalog, ordering, inventory, service activation, fault management (TMF642), performance management (TMF628), billing, SLA management. Gen5 APIs support intent-based automation. | Apache 2.0    |
| **IETF Network Management Agent (NMA) draft**                                       | ~12 API groups      | Infrastructure ops: service configuration, alarm monitoring, performance monitoring, network optimization, topology management                                                                                | IETF license  |
| **ONAP APIs**                                                                       | Large, complex      | Service orchestration (SO), inventory (A&AI), configuration (CPS), policy, analytics                                                                                                                          | Apache 2.0    |
| **3GPP NF APIs (TS 29.5xx series)**                                                 | ~20 NF APIs         | Core network: NRF discovery (TS 29.510), NWDAF analytics (TS 29.520), PCF policy (TS 29.507), AMF/SMF session management                                                                                      | Standard spec |


### Coverage by telecom domain


| Domain                         | CAMARA        | TM Forum        | IETF NMA | 3GPP NF              | ONAP    |
| ------------------------------ | ------------- | --------------- | -------- | -------------------- | ------- |
| Subscriber operations          | Strong        | Partial         | —        | —                    | —       |
| Service assurance / fault mgmt | —             | Strong (TMF642) | Strong   | Partial (NWDAF)      | Strong  |
| Performance monitoring         | —             | Strong (TMF628) | Strong   | Partial (NWDAF)      | Partial |
| Network configuration          | —             | Partial         | Strong   | Strong (PCF, SMF)    | Strong  |
| Billing / revenue              | Partial       | Strong          | —        | —                    | —       |
| Slice management               | Partial (QoD) | —               | —        | Strong (NSSF, NSACF) | Partial |
| Security                       | —             | —               | Partial  | Partial (AUSF)       | —       |
| Intent / autonomous ops        | —             | Gen5 APIs       | —        | —                    | Policy  |


No single source covers everything. Combining CAMARA + TM Forum + 3GPP NF gets the widest coverage.

### Recommended MCP build plan

Two tracks. MCP-Telecom already covers the infrastructure/device layer (60+ tools for routers, switches, transport equipment). What's missing is the BSS/OSS and 5G core layer. Build that in three waves:

**Track A (infrastructure layer): Use MCP-Telecom as-is.** 60+ tools for device-level alarms, metrics, telemetry via SSH/NETCONF/gNMI/SNMP. MIT license, Docker-ready, read-only safety model. No build work needed.

**Track B (BSS/OSS + 5G core): Build new MCP tools from OpenAPI specs.**

1. **Wave 1 (fault prediction):** TMF642 alarm management (6 tools), TMF628 performance monitoring (5 tools), NWDAF analytics TS 29.520 (3 tools), TMF621 trouble ticket (4 tools), CAMARA Device Location (2 tools). Target: ~20 new tools. Use mcp-camara-demo's pattern (load OpenAPI spec, expose as MCP tool) as the starting template.
2. **Wave 2 (subscriber + billing):** Add CAMARA APIs (Device Status, QoD, SIM Swap, Number Verification, Edge Discovery, Carrier Billing) and TM Forum product/billing APIs (TMF620, TMF622, TMF637). Target: ~40 new tools total.
3. **Wave 3 (core network + intent):** Add 3GPP NF APIs — NRF discovery (TS 29.510), PCF policy (TS 29.507), AMF/SMF session management. These are the APIs NextGCore exposes as working endpoints. Target: ~55 new tools total.

Each wave produces both a working MCP server (for execution-verified SDG) and normalized function-calling schemas (for training data generation). Combined with MCP-Telecom's 60+ tools, this gives 115+ tools across both tracks.

---

## Part 2: Training data for tool calling

### Single-turn tool-calling data

Generating single-turn data (one query, one or more tool calls) is the easier problem. The SDG pipeline:

1. Take normalized tool schemas from the MCP build
2. Use a frontier model as teacher to generate query-to-function-call pairs
3. Verify through format check, execution check (against mock servers), and semantic judge
4. Output as training JSONL

Complexity tiers (matching ZTE-AIM/TFCE for eval comparability):

- **Simple:** Single tool call from a clear query
- **Multiple:** Sequential tool calls where output of one informs the next
- **Parallel:** Independent tool calls that can execute simultaneously
- **Parallel-multiple:** Combination of parallel and sequential chains

The harder question is multi-step and multi-turn.

### Long-horizon / multi-step training data

Without training data in multi-step format, the model won't perform on agentic workflows. No one has published a ready-to-use, English-language, multi-step telecom tool-calling training dataset built on CAMARA/TM Forum/3GPP schemas. That's the gap OTel 2.5 needs to fill. But proven pipelines exist for generating it:

**6GAgentGym** ([arXiv 2603.29656](https://arxiv.org/abs/2603.29656), March 2026)

Closest methodological match. Provides:

- 42 typed tools (read-only observation + state-mutating configuration) for network management
- **6G-Forge**: a data synthesis pipeline that bootstraps closed-loop training trajectories from NS-3 simulation seeds, with execution verification against a learned Experiment Model
- Agentic SFT + RL training: supervised fine-tuning on verified trajectories, then reinforcement learning with online closed-loop interaction
- An 8B model trained this way achieves comparable overall success to GPT-5 and stronger performance on long-horizon tasks specifically
- Limitation: 42 tools cover network slicing and UAV control but not radio-level ops (beamforming, power control)

**Availability:** No public code, GitHub repo, or dataset has been released as of September 2026. The methodology is well-documented in the paper and reproducible, but artifacts would need to be reimplemented. The 6G-Forge approach can be adapted to generate trajectories over our CAMARA/TM Forum tool schemas instead of their 42 tools.

**NVIDIA + Tech Mahindra NOC Reasoning Pipeline** (MWC 2026)

The most ready-to-use option. Generates multi-step NOC incident resolution data:

- Generates synthetic NOC incident data with structured fields (region, domain, priority, cause, engineer notes, resolution)
- A teacher model generates multi-step tool-calling action sequences per incident
- A second pass adds per-step reasoning traces ("why this step, what signals, how it influences next decision")
- Traces are converted to multi-turn tool-calling format simulating realistic agent interaction
- Curriculum learning from simple single-tool incidents to complex multi-step cases
- Fine-tuned Qwen3-32B went from ~20% to ~60% accuracy on incident summary prediction
- Open-source guide and code: [NeMo Skills tutorial](https://nvidia-nemo.github.io/Skills/tutorials/2026/02/27/teaching-a-model-to-reason-over-telecom-network-incidents/) with all scripts under `recipes/noc-reasoning-agent` in the [NVIDIA-NeMo/Skills repo](https://github.com/NVIDIA-NeMo/Skills) (Apache 2.0). See also the [NVIDIA Developer Blog writeup](https://developer.nvidia.com/blog/building-telco-reasoning-models-for-autonomous-networks-with-nvidia-nemo/).

**TelAgentBench** (SK Telecom, EMNLP 2025) — structural reference only

- 1,700+ instances across 5 agentic capabilities
- 757 tool-calling scenarios spanning up to 23 BSS APIs with multi-step and multi-turn configurations
- Available on HuggingFace (`skt/TelAgentBench`)
- Queries are Korean-language, so not directly usable for English training or eval. However, the function signatures and API schemas are in English, making it useful as a structural reference for how to organize multi-step telecom tool-calling scenarios.

**Telco-GAIA** (arXiv 2607.20510, July 2026)

- Bilingual benchmark addressing TelAgentBench's limitations (Korean-only, no multimodal)
- Multi-step agentic evaluation

**General multi-step tool-calling approaches (not telecom-specific but applicable):**


| Framework                           | What it does                                                                                                                                                            | Scale                   |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| **ToolBench / ToolLLM** (ICLR 2024) | 16,464 real-world APIs, 120,000+ instruction-API pairs. Three-stage pipeline: API collection, instruction generation, solution path annotation with depth-first search. | 16K APIs, 120K examples |
| **APIGen** (2024)                   | Automated pipeline for generating verifiable function-calling datasets. Referenced by 6GAgentGym as a foundation.                                                       | Pipeline, not dataset   |
| **BFCL V3/V4** (Berkeley)           | V3 evaluates multi-turn multi-step function calling with state-based evaluation. V4 Agentic adds web search with multi-hop reasoning and error recovery.                | Eval benchmark          |
| **StableToolBench** (2024)          | ToolBench + virtualized API execution for reproducibility                                                                                                               | 16K APIs                |


### Proposal on how to generate the data we need for OTel 2.5

Combining the best elements from the three proven pipelines:

**Step 1: Define incident/task templates** (from NVIDIA NeMo approach)

Create 50-100 telecom task templates spanning the 5 WG use cases:

- Fault diagnosis: "subscriber reports dropped calls in sector X"
- Churn risk: "high-value customer with repeated service complaints"
- Revenue anomaly: "billing discrepancy on roaming CDRs"
- Energy: "traffic dropped below threshold on cells A, B, C overnight"
- Closed-loop: "latency SLA breach on network slice SST=1"

Each template specifies: initial observation, relevant tools from the MCP server, expected resolution path, success criteria.

**Step 2: Generate trajectories with execution verification** (from 6G-Forge approach)

For each template:

1. Teacher model generates a multi-step plan: which tools to call, in what order, what to do with each result
2. Execute each tool call against a backend to get realistic responses. Three tiers of backends are available:
  - **Live 5G core:** NextGCore exposes 12+ real SBI endpoints (NRF TS 29.510, NWDAF TS 29.520, PCF TS 29.507, AMF TS 29.518, UDR TS 29.504) over HTTP/2. Deploy via Docker Compose, run nextgsim to register UEs and establish PDU sessions, and tool calls get real responses from a running 5G core.
  - **Operator developer sandboxes:** Several operators expose CAMARA-compliant sandbox APIs with realistic responses. [GSMA Open Gateway Sandbox](https://open-gateway.gsma.com/sandbox) (SIM Swap, Number Verification, QoD, Device Location, Device Status), [Vodafone CAMARA Sandbox](https://developer.vodafone.com/camara-sandbox), [BT API Developer Portal](https://developer.bt.com/camara), Telefonica Open Gateway, Deutsche Telekom developer portal, and [Microsoft Azure Programmable Connectivity](https://learn.microsoft.com/en-us/azure/programmable-connectivity/) (aggregates multiple operators behind a single SDK). Rate-limited, may require registration.
  - **Auto-generated mock servers:** [Prism](https://stoplight.io/open-source/prism) takes any OpenAPI 3.0 spec and auto-generates a mock server with dynamic, schema-valid responses. No code required. This is the fastest path for the 100+ TM Forum and IETF NMA specs that don't have live backends. WireMock and MockServer are alternatives with more configurability.
  - The combination of all three tiers means every MCP tool call has a backend to respond to it — some from real systems, some from operator sandboxes, some from spec-driven mocks.
3. Teacher model generates the next step based on actual tool output (not hallucinated responses)
4. Verify the trajectory reaches the correct resolution
5. Reject trajectories that loop, hallucinate tool names, or reach wrong conclusions

The result is execution-verified trajectories. The model trains on tool calls that actually ran, not fabricated outputs.

**Step 3: Add reasoning traces** (from NVIDIA NeMo approach)

For each verified trajectory, a second teacher pass adds per-step reasoning:

- Why this tool was chosen over alternatives
- What the tool output means in telecom context
- How the output informs the next decision
- When to escalate vs continue autonomously

**Step 4: Format as both single-turn and multi-turn**

Each trajectory produces training examples in two formats:

- **Single-turn:** The full task description + all tool calls as one response (for batch/planning use)
- **Multi-turn:** Each tool call is a separate turn, with the operator (or system) providing tool results between turns (for interactive use)

Both formats go into the training mix.

**Step 5: Curriculum ordering**

Order the training data from simple to complex (from NVIDIA approach):

1. Single-tool, single-turn
2. Multi-tool parallel (independent calls)
3. Multi-tool sequential (output of one feeds the next)
4. Multi-turn with operator refinement
5. Full closed-loop (observe, decide, act, verify)

### Target dataset size, subject to quality check


| Tier                      | Examples         | Source                                     |
| ------------------------- | ---------------- | ------------------------------------------ |
| Single-turn simple        | 3,000-5,000      | SDG from tool schemas                      |
| Single-turn multi-tool    | 2,000-3,000      | SDG from tool schemas                      |
| Multi-step trajectories   | 2,000-3,000      | SDG with execution verification            |
| Multi-turn conversational | 1,000-2,000      | SDG from trajectory reformatting           |
| Adversarial / refusal     | 500-1,000        | SDG (queries that shouldn't trigger tools) |
| **Total**                 | **8,500-14,000** |                                            |


After multi-stage verification and filtering, expect 50-70% survival rate, yielding 5,000-10,000 high-quality training examples.

---

## Part 3: Eval benchmarks (No training on these)


| Benchmark                                                                                                     | What it measures                                                                            | Scale                              | Format                |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------- | --------------------- |
| **ZTE-AIM/TFCE** ([HuggingFace](https://huggingface.co/datasets/ZTE-AIM/Telecom-Function-Calling-Evaluation)) | Telecom function calling across 4 complexity tiers                                          | 1,800+ functions, 917 problems     | English, tool-calling |
| **GSMA Open Telco Benchmarks** ([HuggingFace](https://huggingface.co/GSMA))                                   | Standards knowledge (TeleQnA), config generation (TeleYAML), root-cause analysis (TeleLogs) | 16,866 samples across 7 benchmarks | English, mixed        |
| **TelAgentBench** ([HuggingFace](https://huggingface.co/datasets/skt/TelAgentBench))                          | Agentic capabilities across BSS APIs                                                        | 1,700+ instances, 757 tool-calling | Korean (caveat)       |
| **Telco-GAIA**                                                                                                | Multi-step agentic, bilingual                                                               | In development                     | Bilingual             |
| **BFCL V4 Agentic** (Berkeley)                                                                                | General multi-step tool calling with error recovery                                         | Benchmark                          | English               |


Measure OTel 2.0 vs 2.5 on all of these. ZTE-AIM/TFCE and GSMA benchmarks are the primary gates. TelAgentBench is secondary (language mismatch). BFCL V4 catches general tool-calling regression.

---

## Part 4: Sandbox environments for execution-verified SDG

Running tool calls against a live system (rather than just checking format) avoids hallucinated examples. Available sandboxes:


| Sandbox                                                                                   | What it is                                                                                                       | Observability                                                                                      | OpenShift?                                                                                                                                                                                                      | License               |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| **fenar/cnvopen5gcore** ([github](https://github.com/fenar/cnvopen5gcore))                | Open5GS + UERANSIM on OpenShift with Service Mesh, Helm + ArgoCD                                                 | Basic (no native NWDAF)                                                                            | **Yes, built for it.** Helm charts, ArgoCD, SCTP MachineConfig, Istio. Actively maintained by Fatih Nar.                                                                                                        | AGPL-3.0 (Open5GS)    |
| **NextGCore** ([github](https://github.com/NextgCoreLab/nextgcore))                       | Full 5G SA core in Rust, 17 NFs including NWDAF with ONNX backend, intent-driven policy loop, slice SLA observer | Built-in: NWDAF analytics APIs (TS 29.520), Prometheus metrics, structured observe-decide-act logs | Partial. Has `k8s/` directory but no OpenShift-specific work. Needs adaptation (SCCs, SCTP).                                                                                                                    | AGPL-3.0              |
| **Open5GS + UERANSIM** ([open5gs.org](https://open5gs.org/))                              | Mature 5G core + UE/gNB simulator                                                                                | Basic: no native NWDAF, needs external monitoring                                                  | Yes, via [kindk8s-open5gs](https://github.com/jnunyez/kindk8s-open5gs) (Kustomize + MongoDB operator, confirmed with `oc` CLI) or [Gradiant Helm charts](https://github.com/gradiant/openverso-charts).         | AGPL-3.0              |
| **Free5GC** ([free5gc.org](https://free5gc.org/))                                         | 5G core in Go, multiple community NWDAF add-ons                                                                  | Community NWDAF implementations (3+ published, including LLM-enabled NWDAF, Jun 2026)              | Yes, via [towards5gs-helm](https://github.com/Orange-OpenSource/towards5gs-helm) (Orange, one chart per NF). Also [free5gc-openshift](https://github.com/tele0x/free5gc-openshift) exists but is stale (~2021). | Apache 2.0            |
| **GSMA Labs 5gs-sandbox** ([github](https://github.com/gsma-labs/5gs-sandbox))            | Docker Compose packaging of Open5GS + UERANSIM (15 containers) with `inspect-kathara` agent evaluation framework | Same as Open5GS. GSMA's contribution is the packaging and agent eval framework.                    | No. Docker Compose only.                                                                                                                                                                                        | AGPL-3.0 (underlying) |
| **MCP-Telecom** ([github](https://github.com/Avinash-Amudala/MCP-Telecom))               | 60+ MCP tools for network equipment (Nokia, Cisco, Juniper, Arista) via SSH/NETCONF/gNMI/SNMP                    | Device-level: alarms, syslog, CPU/memory, gNMI telemetry, interface stats                          | Runs anywhere (Python/Docker)                                                                                                                                                                                   | MIT                   |


**Recommendation for OpenShift:** Use **fenar/cnvopen5gcore** as the primary OpenShift deployment — it's built for it, has Helm + ArgoCD, and is maintained by the WG's Vice Chair (Fatih Nar). Supplement with **NextGCore** (via Docker Compose on a dev machine or adapted K8s manifests) when NWDAF analytics APIs and the intent-driven policy loop are needed for execution-verified SDG.

**Recommendation for SDG backends:** NextGCore is the strongest sandbox for generating multi-step training data because of its built-in NWDAF and intent loop. Use MCP-Telecom for device-layer fault data (alarms, metrics, telemetry from network equipment). Use operator sandboxes (GSMA Open Gateway, Vodafone, BT) for CAMARA API responses, and Prism for auto-mocking TM Forum/IETF NMA specs that don't have live backends.

Note on the GSMA 5G Sandbox: it's a useful packaging of Open5GS + UERANSIM, but the underlying components are independent open-source projects, not GSMA-developed. GSMA's contribution is the Docker Compose integration and the `inspect-kathara` agent eval framework.

---

## OTel 2.0 gap analysis (from the [model card](https://huggingface.co/farbodtavakkoli/OTel-2.0-LLM-31B-IT))

OTel 2.0 trained on ~440B tokens of telecom standards (3GPP, ETSI, ITU, GSMA, CAMARA, O-RAN, TM Forum). It knows the standards well. What it has never seen is how those standards show up in operations. The gaps below are all documented or implied by the model card. We address them one at a time, starting with the narrowest.

| # | Gap | What's missing | Impact on fault prediction use case | Status |
|---|-----|---------------|-------------------------------------|--------|
| 1 | **Telecom tool calling** | No telecom MCP tools, no telecom function schemas, no agentic workflow examples in training | Can't call TMF642/TMF628/NWDAF APIs to pull alarms or metrics | **First — active** |
| 2 | **Operational data types** | Never seen live telemetry, KPIs, alarms, RF measurements, vendor CLI output, CDRs, network event logs | Can't interpret tool call responses that contain real operational data | Queued |
| 3 | **Vendor CLI / NOS docs** | Cisco IOS-XR, Juniper JUNOS, Nokia, Arista documentation excluded from training | If a fault workflow returns CLI output, model can't parse it | Queued |
| 4 | **IETF RFCs** | Routing, MPLS, BGP, transport/IP protocol specs absent | Fault diagnosis at transport layer hits a blind spot | Queued |
| 5 | **OSS/BSS workflow data** | TM Forum frameworks are in training, but actual ticketing, fault consoles, change-approval flows are not | Knows the standard, hasn't seen how it's used operationally | Queued |
| 6 | **Autonomous task completion** | No evaluation for closed-loop tasks (SLA extraction, 5G config, fault diagnosis, network defense) | Can't chain tools to complete an end-to-end fault resolution | Queued (partially addressed by gap 1) |
| 7 | **MOP validation** | Command sequencing, expected outputs, rollback steps untested | Can't validate or generate safe operational procedures | Queued |
| 8 | **Network security ops** | DDoS detection, firewall/eBPF construction, anomaly analysis absent | Out of scope for fault prediction, relevant for later use cases | Queued |
| 9 | **Vision tower** | No telecom image training — can't read network diagrams, spectrum plots, equipment photos | Not blocking for tool-calling workflows | Queued |

**Published benchmarks:** The model card reports only an internal comparison (92% on 1,700 rows, text-only vs multimodal). No ZTE-AIM/TFCE scores, no GSMA benchmark scores. Comprehensive evaluation via MLCommons is listed as future work. This means we don't have a public OTel 2.0 baseline to compare against — we should run ZTE-AIM/TFCE and GSMA benchmarks on OTel 2.0 before training 2.5, so we can measure improvement.

**Approach:** Tackle gap 1 (tool calling) first via the MCP build + SDG pipeline described in Parts 1-2. Flag gaps 2-4 to Farbod as likely candidates for the OSFT training mix — vendor CLI docs and IETF RFCs could be added alongside tool-calling data in the same training cycle without much extra pipeline work.

---

## Summary of available resources


| Category                      | Resource                                                                        | Ready to use?                                                                                                                                              | OpenShift?                          |
| ----------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **MCP server (infra layer)**  | MCP-Telecom (60+ tools, Nokia/Cisco/Juniper/Arista)                             | Yes (MIT, Docker-ready)                                                                                                                                    | Runs anywhere                       |
| **MCP architecture**          | CAMARA white paper on MCP integration                                           | Reference only                                                                                                                                             | —                                   |
| **MCP in development**        | Telco-AIX AutoNet (Fatih Nar)                                                   | In progress                                                                                                                                                | OpenShift AI                        |
| **Tool schemas for SDG**      | CAMARA (60+), TM Forum (100+), IETF NMA (~12), 3GPP NF (~20)                    | Need conversion to function-calling format                                                                                                                 | —                                   |
| **Multi-step SDG pipeline**   | 6G-Forge (6GAgentGym)                                                           | Methodology only, no public code/data                                                                                                                      | —                                   |
| **NOC reasoning pipeline**    | NVIDIA + Tech Mahindra via [NeMo Skills](https://github.com/NVIDIA-NeMo/Skills) | Yes, fully reproducible ([tutorial](https://nvidia-nemo.github.io/Skills/tutorials/2026/02/27/teaching-a-model-to-reason-over-telecom-network-incidents/)) | —                                   |
| **Telecom tool-calling eval** | ZTE-AIM/TFCE (917 problems)                                                     | Ready                                                                                                                                                      | —                                   |
| **Standards knowledge eval**  | GSMA Open Telco Benchmarks (16,866 samples)                                     | Ready                                                                                                                                                      | —                                   |
| **Agentic eval**              | TelAgentBench (757 scenarios, Korean)                                           | Structural reference only                                                                                                                                  | —                                   |
| **Execution sandbox**         | fenar/cnvopen5gcore (Open5GS on OpenShift)                                      | Ready                                                                                                                                                      | **Yes, built for it**               |
| **Execution sandbox**         | NextGCore (17 NFs, NWDAF, intent loop)                                          | Ready (Docker Compose)                                                                                                                                     | K8s manifests, needs OCP adaptation |
| **Execution sandbox**         | Free5GC + community NWDAF                                                       | Ready                                                                                                                                                      | Yes (Helm)                          |
| **CAMARA API backends**       | GSMA Open Gateway, Vodafone, BT, Telefonica sandboxes                           | Ready (rate-limited, registration)                                                                                                                         | —                                   |
| **Mock API generation**       | Prism (auto-mock from OpenAPI specs)                                            | Ready                                                                                                                                                      | Runs anywhere                       |



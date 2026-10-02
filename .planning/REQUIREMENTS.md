# Requirements: OTel 2.5 Telecom Tool-Calling Training

**Defined:** 2026-09-26
**Core Value:** OTel 2.5 can correctly call telecom tools to complete fault prediction workflows — measured by Farbod's team after OSFT training on our dataset.

## v1 Requirements

### MCP Tools

- [ ] **MCP-01**: Build 6 curated TMF642 alarm management MCP tools (list, get, acknowledge, clear, comment, subscribe)
- [ ] **MCP-02**: Build 5 curated TMF628 performance management MCP tools (list jobs, create on-demand collection, get status, list/get tracking records)
- [ ] **MCP-03**: Build 4 curated TMF621 trouble ticket MCP tools (create, update, get, list)
- [ ] **MCP-04**: Build 3 curated NWDAF TS 29.520 analytics MCP tools (get analytics, subscribe events, unsubscribe)
- [ ] **MCP-05**: Build 2 curated CAMARA Device Location MCP tools (verify location, retrieve location)
- [ ] **MCP-06**: Deploy MCP-Telecom (60+ device-layer tools) on OpenShift for infrastructure fault data
- [ ] **MCP-07**: Build reusable OpenAPI-to-MCP conversion tooling for future API waves
- [ ] **MCP-08**: Compose all MCP servers behind Kuadrant MCP Gateway on OpenShift with tool namespacing

### Backends

- [x] **BACK-01**: Deploy Prism mock backends on OpenShift for TMF642, TMF628, TMF621, and CAMARA APIs from their OpenAPI specs
- [x] **BACK-02**: Deploy NextGCore on OpenShift with working NWDAF endpoints for execution-verified analytics tool calls
- [x] **BACK-03**: Configure backend routing via ConfigMap (swap between Prism mocks and live backends without code changes)

### SDG Pipeline

- [ ] **SDG-01**: Configure and run sdg_hub MCP distillation flow against our MCP servers (question generation, execution verification, quality filtering)
- [ ] **SDG-02**: Implement curriculum ordering in sdg_hub (simple single-tool → parallel → sequential → multi-turn → closed-loop)
- [ ] **SDG-03**: Output training data in both single-turn and multi-turn trajectory formats
- [ ] **SDG-04**: Produce 8,500-14,000 raw examples, filter to 5,000-10,000 high-quality verified examples
- [ ] **SDG-05**: Deliver filtered dataset to Farbod's team for OSFT training

### Industry Gaps Document

- [ ] **GAPS-01**: Draft industry gaps document covering: MCP conformance testing framework, standard telco API simulators, agent deployment reference architecture on OpenShift
- [ ] **GAPS-02**: Identify frameworks and standards that help operators deploy AI agents with Red Hat tools and platforms

## v2 Requirements

### Additional Use Cases

- **UC-01**: Extend MCP tools for churn prediction use case (subscriber history, billing, complaint APIs)
- **UC-02**: Extend MCP tools for revenue recovery use case (billing, CDR, roaming APIs)
- **UC-03**: Extend MCP tools for energy optimization use case (RAN metrics, traffic patterns, power control)
- **UC-04**: Extend MCP tools for closed-loop demo use case (full observe-decide-act cycle, sub-200ms)

### Model Gaps 2-9

- **GAP-02**: Operational data types training data
- **GAP-03**: Vendor CLI / NOS documentation training data
- **GAP-04**: IETF RFC training data
- **GAP-05**: OSS/BSS workflow training data
- **GAP-06**: Autonomous task completion training data
- **GAP-07**: MOP validation training data
- **GAP-08**: Network security ops training data
- **GAP-09**: Vision tower telecom image training data

### Operator Sandbox Integration

- **SAND-01**: Integrate GSMA Open Gateway, Vodafone, BT CAMARA sandbox APIs as additional backend tier

## Out of Scope

| Feature | Reason |
|---------|--------|
| Running OSFT training | Farbod's team owns training. We deliver data + pipeline. |
| OTel 2.0 baseline benchmarks | Farbod's team owns eval. They already have model baselines. |
| BFCL / TFCE regression checking | Eval responsibility belongs to training team. |
| Production deployment of OTel 2.5 | WG produces the model recipe, operators deploy. |
| Building a new 5G core | We use existing open-source cores as sandboxes. |
| Formal MCP certification program | Too heavy. Conformance test suite is the achievable v1 (in gaps doc). |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MCP-01 | Phase 3 | Pending |
| MCP-02 | Phase 3 | Pending |
| MCP-03 | Phase 3 | Pending |
| MCP-04 | Phase 3 | Pending |
| MCP-05 | Phase 3 | Pending |
| MCP-06 | Phase 2 | Pending |
| MCP-07 | Phase 2 | Pending |
| MCP-08 | Phase 3 | Pending |
| BACK-01 | Phase 1 | Complete |
| BACK-02 | Phase 1 | Complete |
| BACK-03 | Phase 1 | Complete |
| SDG-01 | Phase 4 | Pending |
| SDG-02 | Phase 4 | Pending |
| SDG-03 | Phase 4 | Pending |
| SDG-04 | Phase 4 | Pending |
| SDG-05 | Phase 4 | Pending |
| GAPS-01 | Phase 5 | Pending |
| GAPS-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-09-26*
*Last updated: 2026-09-26 after roadmap phase mapping*

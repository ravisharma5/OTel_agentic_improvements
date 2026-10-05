# Roadmap: OTel 2.5 Telecom Tool-Calling Training

## Overview

This project builds the infrastructure and pipeline to produce telecom-specific tool-calling training data for fine-tuning OTel 2.0 into OTel 2.5. The work flows through four horizontal layers -- backend infrastructure, MCP tooling foundation, domain tool servers with gateway composition, and the SDG pipeline that produces the final dataset -- plus a parallel industry gaps document. Each layer gates the next: backends must exist before tools can be tested, tools must be composable before the pipeline can generate data, and the pipeline must run before the dataset can be delivered.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Backend Infrastructure** - Deploy Prism mocks, NextGCore NWDAF, and configurable routing on OpenShift (completed 2026-10-02)
- [x] **Phase 2: MCP Tooling Foundation** - Build OpenAPI-to-MCP conversion tooling and deploy MCP-Telecom device-layer toolkit (completed 2026-10-04)
- [x] **Phase 3: MCP Domain Servers and Gateway** - Build 20 fault-prediction MCP tools and compose behind Kuadrant MCP Gateway (completed 2026-10-05)
- [ ] **Phase 4: SDG Pipeline and Dataset Production** - Run sdg_hub distillation, produce 5K-10K verified training examples, deliver to Farbod's team
- [ ] **Phase 5: Industry Gaps Document** - Draft gaps document covering MCP conformance, telco API simulators, and agent deployment architecture

## Phase Details

### Phase 1: Backend Infrastructure

**Goal**: Mock and live backends are deployed on OpenShift and return valid API responses for all fault-prediction APIs
**Depends on**: Nothing (first phase)
**Requirements**: BACK-01, BACK-02, BACK-03
**Success Criteria** (what must be TRUE):

  1. Prism mock servers for TMF642, TMF628, TMF621, and CAMARA APIs return valid HTTP responses matching their OpenAPI spec schemas
  2. NextGCore is running on OpenShift with NWDAF endpoints responding to TS 29.520 analytics requests
  3. Backend routing ConfigMap allows switching any MCP tool between Prism mock and live backend without redeploying services

**Plans:** 4/4 plans complete

Plans:
**Wave 1**

- [x] 01-01-PLAN.md -- Vendor OpenAPI specs, create Prism Dockerfile and validation scripts
- [x] 01-02-PLAN.md -- NextGCore NWDAF local validation with Podman (go/no-go decision)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-03-PLAN.md -- OpenShift cluster setup and Prism mock deployment

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md -- NextGCore/NWDAF deployment, ConfigMap routing, final verification

### Phase 2: MCP Tooling Foundation

**Goal**: Reusable conversion tooling and existing device-layer toolkit are operational on OpenShift, ready for domain tool building
**Depends on**: Phase 1
**Requirements**: MCP-06, MCP-07
**Success Criteria** (what must be TRUE):

  1. OpenAPI-to-MCP conversion tooling can generate a curated FastMCP server from a TMF or CAMARA OpenAPI spec, selecting specific operations rather than exposing the entire API surface
  2. MCP-Telecom's 60+ device-layer tools are deployed on OpenShift and individually callable via MCP protocol

**Plans:** 3/3 plans complete

Plans:
**Wave 1**

- [x] 02-01-PLAN.md -- Package verification, MCP-Telecom vendor/patch, config scaffolds

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md -- MCP-Telecom containerization and OpenShift deployment
- [x] 02-03-PLAN.md -- OpenAPI-to-MCP conversion CLI and CAMARA smoke test

### Phase 3: MCP Domain Servers and Gateway

**Goal**: All 20 fault-prediction MCP tools are built, tested against backends, and composable through a unified gateway endpoint
**Depends on**: Phase 2
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04, MCP-05, MCP-08
**Success Criteria** (what must be TRUE):

  1. 20 curated MCP tools across TMF642 (6), TMF628 (5), TMF621 (4), NWDAF (3), and CAMARA (2) are individually callable and return valid responses from their backends
  2. Kuadrant MCP Gateway on OpenShift composes all domain MCP servers and MCP-Telecom with tool namespacing, presenting a single endpoint
  3. An MCP client calling any tool through the gateway receives the correct backend response -- Prism mock or live NextGCore depending on routing configuration

**Plans:** 6/6 plans complete

Plans:
**Wave 1**

- [x] 03-01-PLAN.md -- Package legitimacy verification and verification scripts (verify-domain-tools.sh, verify-gateway.sh)
- [x] 03-04-PLAN.md -- Gateway + auth infrastructure (OSSM 3.3+, cert-manager, Keycloak, RHCL MCP Gateway Operator)

**Wave 2** *(blocked on Wave 1 Plan 01)*

- [x] 03-02-PLAN.md -- TMF single-spec domain servers: TMF642 (6 tools), TMF628 (5 tools), TMF621 (4 tools)
- [x] 03-03-PLAN.md -- Multi-spec domain servers: NWDAF (3 tools), CAMARA (2 tools)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-05-PLAN.md -- Domain server containerization, OpenShift deployment, 20-tool individual verification

**Wave 4** *(blocked on Wave 3 + Wave 1 Plan 04)*

- [x] 03-06-PLAN.md -- Backend registration (MCPServerRegistration), virtual servers, AuthPolicy, end-to-end gateway verification

### Phase 4: SDG Pipeline and Dataset Production

**Goal**: Execution-verified, quality-filtered training dataset is produced and delivered to Farbod's team for OSFT training
**Depends on**: Phase 3
**Requirements**: SDG-01, SDG-02, SDG-03, SDG-04, SDG-05
**Success Criteria** (what must be TRUE):

  1. sdg_hub MCP distillation flow generates tool-calling training examples from MCP server schemas with three-stage verification (format, execution, semantic) against live backends
  2. Training examples follow curriculum ordering (single-tool, parallel, sequential, multi-turn, closed-loop) and are output in both single-turn and multi-turn trajectory formats
  3. 5,000-10,000 high-quality verified examples are produced from an initial 8,500-14,000 raw generation run, with quality metrics and coverage statistics
  4. Filtered dataset is delivered to Farbod's team in their required OSFT-compatible JSONL format, validated by the training team

**Plans**: TBD

Plans:

- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Industry Gaps Document

**Goal**: Industry gaps document identifies critical missing infrastructure for deploying telecom AI agents at scale
**Depends on**: Nothing (parallel track)
**Requirements**: GAPS-01, GAPS-02
**Success Criteria** (what must be TRUE):

  1. Document covers three gap areas: MCP conformance testing framework, standard telco API simulators, and agent deployment reference architecture on OpenShift
  2. Document identifies specific frameworks, standards, and Red Hat tools/platforms that help operators deploy AI agents in production

**Plans**: TBD

Plans:

- [ ] 05-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4. Phase 5 runs in parallel.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend Infrastructure | 4/4 | Complete    | 2026-10-02 |
| 2. MCP Tooling Foundation | 3/3 | Complete    | 2026-10-04 |
| 3. MCP Domain Servers and Gateway | 6/6 | Complete   | 2026-10-05 |
| 4. SDG Pipeline and Dataset Production | 0/3 | Not started | - |
| 5. Industry Gaps Document | 0/1 | Not started | - |

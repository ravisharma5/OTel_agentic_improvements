# Domain Pitfalls

**Domain:** Telecom MCP tool-calling training data generation (SDG pipeline, MCP tools wrapping TMF/NWDAF/CAMARA APIs, OSFT fine-tuning dataset for OTel 2.5)
**Researched:** 2026-09-26

## Critical Pitfalls

Mistakes that cause rewrites, blown timelines, or useless training data.

### Pitfall 1: Teacher model hallucinating tool schemas and parameter values

**What goes wrong:** The teacher model (used in SDG) invents tool names, fabricates parameter formats, or generates argument values that do not exist in the actual API schema. In telecom, this is particularly dangerous because TMF APIs use non-obvious enumeration values -- for example, TMF628 expects `g_5mn` for 5-minute granularity, not `PT5M` (ISO 8601). A teacher model will confidently generate ISO 8601 because its general training says that format is "more correct." The generated training example looks plausible but teaches the fine-tuned model to produce calls that will always fail validation.

Evidence: AI agents benchmarked on TMF628 consistently overrode TMF-specific enumeration values with ISO 8601 equivalents (source: [I Gave AI Agents a Telecom Job Interview](https://dev.to/mattercoder/i-gave-ai-agents-a-telecom-job-interview-most-failed-without-a-cheat-sheet-ddj)). EdgeGen found that TaskBench and FuncBenchGen systematically generated hallucinated identifiers (user IDs not matching database format, fabricated reservation IDs reused across samples) and garbled parameter values where natural language fragments appeared in API argument fields (source: [EdgeGen](https://arxiv.org/html/2609.24115)).

**Why it happens:** Teacher models have strong priors from general training data. TMF enumeration values, 3GPP-specific formats, and NWDAF analytics event IDs (`ABNORMAL_BEHAVIOUR`, `LOAD_LEVEL_INFORMATION`) are domain-specific tokens absent from or rare in pretraining corpora. The model substitutes its best guess.

**Consequences:** Training data teaches incorrect API usage. Fine-tuned model generates plausible-looking but non-functional tool calls. Detected only at eval time (or worse, never -- if eval also uses mocks that don't validate enums).

**Prevention:**
- Execute every generated tool call against a real or validating backend. Reject any trajectory that produces schema-validation error, 400, or tool-not-found.
- Inject the full OpenAPI spec (including enum constraints, pattern regexes, and examples) into the teacher prompt context window, not just tool name/description summaries.
- Use APIGen's three-stage verification: format check, function execution, semantic verification. Do not skip the execution stage.
- Build a telecom-specific enum registry (all TMF granularity values, alarm severity values, NWDAF event IDs, CAMARA status codes) and validate every generated parameter against it.

**Detection:** Run generated examples against Prism in validation-proxy mode (not just mock mode). Any 422/400 response is a hallucinated parameter. Track hallucination rate per tool per generation batch.

**Phase:** SDG pipeline design (must be architected before generation begins).

---

### Pitfall 2: Mode collapse in generated training examples

**What goes wrong:** The SDG pipeline produces thousands of examples, but they all follow 2-3 patterns. For fault prediction, this looks like: every example starts with `tmf642_list_alarms`, then calls `tmf628_get_tracking_records`, then creates a ticket. Real NOC workflows are far more varied -- sometimes you start from a performance anomaly, sometimes from a subscriber complaint, sometimes from an NWDAF prediction. The fine-tuned model learns to always follow the same sequence regardless of the presenting symptom.

Evidence: Shumailov et al. (Nature, 2024) demonstrated that successive generations of models trained on synthetic data progressively lose distribution tails, converging toward a near-delta-function output (source: [Model Collapse via Synthetic Training Data](https://www.emergentmind.com/topics/model-collapse-through-synthetic-training-data)). Google's Simula framework addresses this by decomposing generation into Global Diversification (taxonomies), Local Diversification (1-of-N meta-prompting), and Complexification (source: [Google Research blog](https://research.google/blog/designing-synthetic-datasets-for-the-real-world-mechanism-design-and-reasoning-from-first-principles/)).

**Why it happens:** Single teacher model with homogeneous prompts. Low temperature settings. Prompt templates that anchor on the same entry point. No explicit coverage tracking across the tool-call space.

**Consequences:** Fine-tuned model has narrow behavioral repertoire. Fails on workflows that deviate from the dominant pattern. Poor performance on held-out eval scenarios that test alternative entry points or tool orderings.

**Prevention:**
- Define a fault-prediction scenario taxonomy before generation: at least 8-10 distinct entry points (alarm-triggered, performance-degradation-triggered, NWDAF-prediction-triggered, subscriber-complaint-triggered, topology-change-triggered, etc.).
- Use diverse prompt templates (minimum 15-20 distinct templates per workflow type).
- Vary generation parameters: temperature 0.7-1.0, multiple top-p values, pool results across runs.
- Track tool-call n-gram distribution across generated corpus. Flag any tool sequence that appears in more than 5% of examples.
- Implement NVIDIA Data Designer's "quality as a first-class stage" pattern -- validators and judges run as pipeline stages, not afterthoughts.

**Detection:** Compute n-gram entropy over tool-call sequences in the generated corpus. Plot tool-call frequency distribution -- it should be roughly uniform across the 20 tools, not heavily skewed. If the top-3 tools account for more than 40% of all calls, diversity is insufficient.

**Phase:** SDG pipeline design and execution. Must be monitored continuously during generation, not just checked post-hoc.

---

### Pitfall 3: Prism mocks producing unrealistic responses that poison training data

**What goes wrong:** Prism generates responses from OpenAPI schema definitions using json-schema-faker. For TMF642 alarms, this means you get syntactically valid JSON with random strings for alarm types, meaningless severity values, and timestamps from the year 2000. The teacher model reasons over these fake responses and produces "correct" tool-call chains that would be nonsensical against a real TMF642 backend. The training data teaches the model to expect and work with unrealistic alarm patterns.

Evidence: Prism's documentation states that sparse schemas with few constraints produce low-quality generated data, and there is no way to inject custom business logic or stateful behavior (source: [Stoplight Prism docs](https://docs.stoplight.io/docs/prism/83dbbd75532cf-http-mocking)). TMF APIs specifically suffer from the "characteristic pattern" which uses generic, loosely-typed payloads that Prism cannot meaningfully populate (source: [Amartus TMF integration guide](https://amartus.com/how-to-effectively-design-integration-interfaces-that-are-based-on-tmf-open-api-specifications/)).

**Why it happens:** TMF OpenAPI specs are intentionally generic -- they use the characteristic pattern (name-value pair bags) rather than concrete schemas. Prism has no domain knowledge, no statefulness, no business logic. `oneOf`/`anyOf` discriminators and deeply nested `$ref` chains in 3GPP specs compound the problem.

**Consequences:** Training examples that "work" against mocks but fail against real APIs. Model learns wrong response patterns. Entire training data batches may need to be discarded when validated against real backends.

**Prevention:**
- Enrich OpenAPI specs with realistic `example` values before feeding to Prism. TMF specs ship examples in their user guides -- extract and embed them.
- For TMF642/628/621: build custom mock servers (or use TMF reference implementations from the GitHub repos) instead of relying on generic Prism mocking. The TMF repos include reference implementation mock servers.
- For NWDAF: use NextGCore's actual NWDAF implementation (ONNX-backed analytics) rather than mocking. This is the single strongest data quality lever in the project.
- Layer Prism in validation-proxy mode (request validation only) on top of custom mocks, so you get schema validation without fake responses.
- Tag every training example with its backend tier (live/sandbox/mock). Weight live and sandbox examples higher in training.

**Detection:** Sample 50 generated examples from each backend tier. Have a telecom domain expert review response realism. If mock-generated responses contain obviously synthetic data (random UUIDs as alarm types, zero-value KPIs, timestamps from wrong decades), the mock layer needs enrichment.

**Phase:** Backend deployment (before SDG begins). Mock enrichment must be complete before first SDG batch.

---

### Pitfall 4: TMF API version and spec ambiguity creating inconsistent tool definitions

**What goes wrong:** TMF642 has both v4.0.0 (Swagger 2.0) and v5.0.1 (OAS 3.0) specs. TMF628 has only Swagger 2.0. The v4 and v5 specs differ in resource models, endpoint paths, and attribute names. If you build MCP tools from v5 specs but your mock server runs v4 reference implementations, every tool call will fail. Worse: different tools built by different contributors may target different spec versions, creating an internally inconsistent toolkit.

Evidence: The Amartus analysis found that TMF APIs "won't just work together" even between conformant implementations, that entity attribute definitions are "very generic, leaving a lot of room for customization," and that there are "bugs and inconsistencies in spec documents" (source: [Amartus TMF integration guide](https://amartus.com/how-to-effectively-design-integration-interfaces-that-are-based-on-tmf-open-api-specifications/)). TMF Forum's own conformance profile acknowledges that "even full compliance does not guarantee out-of-the-box interoperability."

**Why it happens:** TMF APIs evolve across major versions with breaking changes. The OpenAPI specs in GitHub repos do not always match the normative PDFs. Swagger 2.0 and OAS 3.0 have different schema capabilities ($ref handling, discriminators, nullable fields).

**Consequences:** MCP tools that generate valid requests for one spec version get rejected by backends expecting another. Training data inconsistency across tools. Integration debugging absorbs weeks of timeline.

**Prevention:**
- Pin a single spec version per API at project start: TMF642 v5.0.1 (OAS 3.0), TMF628 v4.0.0 (Swagger 2.0, convert to OAS 3.0 with @samchon/openapi), TMF621 v5.0.1 (OAS 3.0). Document the pin in the project manifest.
- Validate every MCP tool definition against the pinned spec using an OpenAPI linter before any SDG.
- Build mock backends from the same pinned spec used for tool definitions. Never mix spec versions between tool and backend.
- When operator sandboxes expose different TMF versions, build an adapter layer rather than changing tool definitions.

**Detection:** Run a spec-version audit script that extracts the `info.version` from every OpenAPI file used in the project and flags any mismatches between tool definitions and backend specs.

**Phase:** MCP tool development (first task before building any tools).

---

### Pitfall 5: Training data format incompatible with OSFT expectations

**What goes wrong:** You generate 10,000 beautiful tool-calling examples, deliver them to Farbod's team, and discover the JSONL format does not match what Training Hub's OSFT algorithm expects. OSFT (via mini-trainer backend) requires a specific `messages` array structure with `role`/`content` fields. Tool-calling turns need to encode `tool_calls` with `id`, `type`, `function` (name + arguments), and subsequent `tool` role messages with matching IDs. If the SDG pipeline outputs a different schema (e.g., OpenAI function-calling format, or a flat list of tool invocations without conversation structure), the entire dataset needs reformatting -- or worse, the reformatting introduces subtle errors.

Evidence: Red Hat's OSFT training examples require JSONL with messages format (source: [Red Hat AI Examples - OSFT](https://github.com/red-hat-data-services/red-hat-ai-examples/tree/main/examples/fine-tuning/osft)). HuggingFace TRL 0.19.0 introduced native tool-calling support with a specific conversation turn structure (user -> assistant tool_call -> tool result -> assistant response). Loss masking during training should be computed only on tool-call tokens, which requires the format to mark these boundaries explicitly.

**Why it happens:** OSFT is a relatively new algorithm (Nayak et al., 2025). Documentation is sparse. The SDG pipeline team and the training team may not coordinate on format until late in the project.

**Consequences:** Days to weeks of reformatting work. Possible data loss during conversion (tool-call IDs, multi-turn threading, system prompts). Training team cannot start until format is resolved, compressing the already tight timeline.

**Prevention:**
- Get a sample OSFT-format JSONL file from Farbod's team in week 1. Build the SDG pipeline's output serializer to produce exactly that format from day 1.
- Include a format validation step in the SDG pipeline that checks every generated example against the OSFT schema before writing to the output file.
- Generate 10 examples early (week 2-3), deliver to Farbod's team for a dry-run training pass. Fix format issues immediately.
- Ensure multi-turn tool-calling conversations maintain consistent `tool_call_id` references between assistant `tool_calls` and `tool` role responses.

**Detection:** Automated schema validation on every batch output. Any example that fails to parse as valid OSFT format is rejected and logged.

**Phase:** Pipeline design (must be resolved before first SDG batch). Dry-run validation with training team no later than week 3.

---

### Pitfall 6: NextGCore NWDAF is configured but not exercised, breaking live backend assumptions

**What goes wrong:** The project plan assumes NextGCore provides a live NWDAF backend for execution-verified SDG. In reality, NextGCore's NWDAF is "configured but not exercised" in Docker E2E overlays. NWDAF analytics subscriptions are memory-only with no durable store -- a container restart silently drops all subscriptions with no termination signal to consumers. The NWDAF daemon also had identity-pinning issues in the OAuth2 overlay. You deploy it expecting a working NWDAF analytics endpoint, discover it returns stubs or crashes, and fall back to Prism mocks for 100% of NWDAF tool calls -- defeating the purpose of the three-tier backend strategy.

Evidence: NextGCore issue #192 documents that NWDAF subscriptions are memory-only with no durable store; a restart drops them silently (source: [NextGCore issue #192](https://github.com/NextgCoreLab/nextgcore/issues/192)). The Docker E2E overlay exercises only 10 of 14 configured NFs, with NWDAF among those not exercised (source: NextGCore CI/overlay documentation).

**Why it happens:** NextGCore is a research/interop implementation, not a production-certified core. NWDAF is the newest and least mature NF. The project's research says "NextGCore implements TS 29.520 with ONNX-backed analytics" -- but "implements" and "reliably serves API requests in a containerized deployment" are different claims.

**Consequences:** Three-tier backend strategy collapses to two tiers (operator sandboxes + mocks). NWDAF tool-calling examples are all mock-backed, reducing training data quality for the most novel and valuable tools in the kit.

**Prevention:**
- Week 1-2: Deploy NextGCore, run the NWDAF AnalyticsInfo endpoint manually (curl). Verify it returns real analytics data, not stubs. File issues for any blockers.
- If NextGCore NWDAF is not production-ready, evaluate the IIITV NWDAF implementation (Open5GS + UERANSIM-based) or M-Baraa-Mardini's modular NWDAF as alternative backends.
- Build enriched NWDAF mocks as a fallback: populate them with realistic analytics event payloads (load level information, abnormal behavior detection results) based on 3GPP examples from TS 29.520.
- Accept that NWDAF live-backend may take 2-3 weeks to stabilize and plan SDG batches accordingly -- generate TMF-backed examples first, NWDAF examples last.

**Detection:** Automated health check: curl the NWDAF AnalyticsInfo endpoint daily. If it returns errors or stubs, alert immediately. Track the percentage of NWDAF examples from live vs. mock backends.

**Phase:** Backend deployment (must be validated before NWDAF SDG begins). Critical path item.

## Moderate Pitfalls

### Pitfall 7: Eval benchmarks not measuring what matters

**What goes wrong:** You baseline OTel 2.0 on ZTE-AIM/TFCE (917 problems) and GSMA benchmarks (16,866 samples), train to improve those scores, and declare success. But ZTE-AIM/TFCE was designed for linguistic tasks (intent recognition, entity extraction) where models already score over 90%. The "Execution Wall" -- procedural execution tasks like solution generation -- is where models collapse to approximately 30% accuracy. If your eval weights linguistic tasks equally with execution tasks, you can show a big score improvement without actually improving tool-calling capability.

Evidence: TeleCom-Bench (ZTE-AICloud) found a 66-point gap between linguistic and procedural execution tasks: Qwen3-235B scores 71% in Root Cause Diagnosis but collapses to 5% in Solution Generation (source: [TeleCom-Bench](https://arxiv.org/html/2605.18025v1)). A BFCL v4 validity audit found an 18.5% misalignment rate between evaluator scores and human judgments across 496 expert-reviewed tasks (source: BFCL v4 cross-benchmark audit).

**Why it happens:** Benchmark optimization bias. Teams naturally focus on metrics that improve most easily. Linguistic tasks are easier to train for, so they improve first, inflating aggregate scores. Meanwhile, the procedural execution tasks that actually represent tool-calling competence stay flat.

**Consequences:** False positive on model improvement. OTel 2.5 "improves" on benchmarks but fails in real NOC scenarios. The WG delivers a model that looks good on paper but doesn't meaningfully advance telecom tool-calling.

**Prevention:**
- Create a custom eval suite specifically for fault-prediction tool-calling: 50-100 scenarios requiring multi-step tool call chains (alarm retrieval -> performance correlation -> NWDAF analytics -> ticket creation). Score on tool-call correctness (right tool, right parameters, right sequence), not just final-answer accuracy.
- Weight procedural execution tasks at least 3x higher than linguistic tasks in your aggregate score.
- Hold out 20% of generated scenarios from training as a private eval set. Never train on these.
- Include "negative" eval scenarios: cases where the correct action is to not call a tool, to request clarification, or to refuse an action.

**Detection:** If your aggregate benchmark score improves more than 10 points but your tool-call-specific score improves less than 3 points, you are optimizing for the wrong thing.

**Phase:** Eval framework design (must be designed before training begins, validated with Farbod's team).

---

### Pitfall 8: OpenShift deployment blocks burning weeks on SCTP, SCCs, and networking

**What goes wrong:** 5G core NFs (particularly AMF) require SCTP protocol support. OpenShift's default `restricted-v2` SCC blocks the capabilities 5G NFs need (specific UIDs, network privileges). SCTP must be explicitly enabled via MachineConfig. Docker Compose networking (separate bridges without routing) does not translate to OpenShift pod networking. You lose 2-3 weeks debugging SCCs, SCTP MachineConfig, and service exposure instead of building tools and generating data.

Evidence: Deploying Open5GS on OpenShift requires eliminating privileged pods while satisfying SCC requirements, and AMF must be exposed via SCTP NodePort (source: [Open5GS on OpenShift](https://medium.com/@anil.sonmez/open5gs-on-openshift-container-platform-c92e72dd4738)). Red Hat documentation warns never to modify default SCCs (they reset on upgrade) and to create custom SCCs instead (source: [OpenShift SCC docs](https://docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html)).

**Why it happens:** NextGCore has a `k8s/` directory but no OpenShift-specific manifests. fenar/cnvopen5gcore is OpenShift-native but has no NWDAF. The gap between "runs in Docker Compose" and "runs on OpenShift" is larger than most teams estimate.

**Consequences:** 2-3 weeks of timeline consumed by platform engineering instead of data generation. If unresolved, the entire three-tier backend strategy (which depends on OpenShift-deployed backends) is at risk.

**Prevention:**
- Use fenar/cnvopen5gcore for general 5G core context (it is already OpenShift-native). Reserve NextGCore for NWDAF-specific endpoints, potentially running it alongside on OpenShift with custom SCCs.
- Create custom SCCs (never modify defaults) with the minimum capabilities needed: `NET_BIND_SERVICE`, specific UID ranges, SCTP protocol allowance.
- Enable SCTP at the cluster level via MachineConfig before attempting any 5G NF deployment.
- Budget 1 full week for OpenShift platform setup in the project plan. Front-load this work to week 1-2.
- MCP servers (Node.js/Python) and Prism mocks do not need SCTP or special SCCs -- deploy these first while sorting out 5G core deployment.

**Detection:** Create a deployment smoke test: can the AMF register, can a gNB connect via SCTP, can the NWDAF endpoint respond? Run this daily during the deployment phase.

**Phase:** Infrastructure setup (week 1-2, must be resolved before backend-dependent SDG begins).

---

### Pitfall 9: Happy-path-only training data producing a model that cannot handle errors or edge cases

**What goes wrong:** Every generated training example shows a clean workflow: alarms are found, performance data is retrieved, analytics return results, tickets are created successfully. The model never sees what happens when an alarm query returns empty results, when the NWDAF endpoint is down, when a ticket creation fails due to missing required fields, or when the user's request is ambiguous. In production, these edge cases are the majority of interactions.

Evidence: EdgeGen found that existing synthetic generation methods "predominantly generate happy-path interactions" and fail to test denial scenarios, policy violations, or error states. Training on happy-path-only data "can be actively harmful" -- models fine-tuned on it regressed on 3-4 out of 6 tested models in policy-dense domains (source: [EdgeGen](https://arxiv.org/html/2609.24115)). ToolBench showed 84% error rate in generated examples, largely from missing edge case coverage (source: [Quality Matters](https://arxiv.org/html/2409.16341v2)).

**Why it happens:** It is easier to generate successful examples than failure scenarios. Mocks return 200 by default. Teacher models prefer to show completion rather than error handling.

**Consequences:** Model does not know how to handle API errors, empty results, or ambiguous requests. In real NOC scenarios, it hallucinates data rather than reporting "no alarms found" or asking for clarification.

**Prevention:**
- Explicitly design error scenarios into the SDG prompt taxonomy: empty alarm lists, NWDAF timeout, partial performance data, conflicting alarm states, invalid user requests.
- Target 20-30% of training examples as error-handling or edge-case scenarios.
- Configure Prism to return error responses (4xx, 5xx) for a percentage of requests. Use Prism's `--errors` flag or inject fault scenarios.
- Include "tool not needed" examples where the correct response is to answer directly without calling any tools.
- Include "clarification needed" examples where the user request is under-specified.

**Detection:** Categorize generated examples by outcome type (success/error/clarification/refusal). If more than 85% are success scenarios, diversity is insufficient.

**Phase:** SDG prompt design (must be built into prompt taxonomy before generation begins).

---

### Pitfall 10: Oct 15 deadline with external dependency on operator sandboxes

**What goes wrong:** The three-tier backend strategy depends on operator sandboxes (GSMA Open Gateway, Vodafone, BT) for CAMARA API execution verification. Operator sandbox access requires onboarding (application, approval, credential provisioning). GSMA Open Gateway launched a sandbox but individual operator sandbox availability varies by market and API. If sandbox access takes 4-6 weeks to provision, you lose a quarter of the 7-week timeline before the Oct 15 deadline.

Evidence: GSMA Open Gateway has 237 certified API assets across 85 networks in 50 markets, but historically "proprietary interfaces, inconsistent security protocols, and custom data models" led to "higher integration expenses, longer onboarding times, and constraints on scalability" (source: [GSMA Open Gateway](https://www.gsma.com/solutions-and-impact/gsma-open-gateway/)). An independent analysis found GSMA "operates no callable API, publishes no OpenAPI under its own name, and runs no self-serve developer portal with keys" -- developers reach endpoints through aggregators and channel partners (source: [API Evangelist Open Gateway analysis](https://github.com/api-evangelist/open-gateway)).

**Why it happens:** Operator sandbox access is not under the project's control. Approval timelines vary by operator. Some sandboxes may be limited to specific CAMARA APIs (SIM Swap, Number Verification) and not cover Device Status or Device Location.

**Consequences:** CAMARA tool-calling examples are mock-only, reducing training data quality. If operator sandbox access arrives late, there is no time to regenerate or validate examples. The timeline has no slack.

**Prevention:**
- Apply for all operator sandboxes immediately (week 1). Do not wait until the SDG phase.
- Treat operator sandboxes as "bonus" data quality, not a dependency. Design the pipeline to produce viable training data using only NextGCore + Prism mocks. Operator sandbox data is an enrichment layer.
- Use the GSMA Open Gateway sandbox (centralized, CAMARA-compliant) as the primary CAMARA source -- it is the fastest to onboard.
- Build enriched CAMARA mocks with realistic response payloads as a guaranteed fallback.
- If any sandbox produces data by week 4, re-run the SDG pipeline for those specific tools to upgrade from mock-backed to sandbox-backed examples.

**Detection:** Track sandbox access status weekly: applied/pending/approved/active for each operator. If no sandbox is active by week 3, escalate and commit to the mock-only plan.

**Phase:** Project kickoff (sandbox applications must go out in the first week).

## Minor Pitfalls

### Pitfall 11: MCP-Telecom (60+ tools) schema inconsistency with new BSS/OSS tools

**What goes wrong:** MCP-Telecom uses FastMCP (Python) with `@mcp.tool()` decorators. The new BSS/OSS tools may use a different MCP SDK (e.g., TypeScript MCP SDK), different naming conventions, or different error-handling patterns. During SDG, the teacher model sees two inconsistent tool-calling styles in the same context window, reducing training signal quality.

**Prevention:**
- Adopt a single tool-definition convention across all MCP servers. If MCP-Telecom uses Python FastMCP, either build new tools in the same framework or create a unified tool-schema export format.
- Normalize all tool names to a consistent pattern: `{api}_{operation}` (e.g., `tmf642_list_alarms`, `mcp_telecom_show_alarms`).
- Generate a unified tool catalog document that the teacher model consumes, abstracting away implementation differences.

**Phase:** MCP tool development (must be resolved before SDG consumes tool definitions).

---

### Pitfall 12: Token count exceeding context window with full tool catalog

**What goes wrong:** 20 new tools + 60+ MCP-Telecom tools = 80+ tool definitions. Each tool definition includes name, description, parameter schema, and examples. At 200-500 tokens per tool, the full catalog consumes 16,000-40,000 tokens before any conversation begins. This may exceed the context budget for both the teacher model (during SDG) and the fine-tuned model (at inference time).

**Prevention:**
- For SDG: provide only the fault-prediction-relevant subset (approximately 20-25 tools) in the teacher prompt, not the full 80+ tool catalog.
- For training data: each example should include only the tools relevant to that scenario (5-8 tools typically), not the full catalog.
- Track average token count per training example. Target under 4,096 tokens per example for efficient OSFT training. Flag any example exceeding 8,192 tokens.

**Phase:** SDG pipeline design (tool catalog subsetting logic must be built into the pipeline).

---

### Pitfall 13: NWDAF release mismatch between spec and implementation

**What goes wrong:** The project references Rel-18 NWDAF OpenAPI specs, but NextGCore (and most open-source 5G cores) implement Rel-16 or early Rel-17 at best. Rel-18 added 6 new NWDAF use cases, ML model training/monitoring APIs, and roaming data APIs that no open-source implementation supports. MCP tools built from Rel-18 specs will reference endpoints and analytics events that NextGCore does not serve.

Evidence: NWDAF went from 1 use case in Rel-15 to 21 use cases in Rel-18. Open-source implementations consistently lag the spec by 2-3 releases (source: [Enhanced Open-Source NWDAF](https://arxiv.org/html/2601.01838v1)).

**Prevention:**
- Audit which NWDAF analytics events NextGCore actually supports (likely: LOAD_LEVEL_INFORMATION, possibly ABNORMAL_BEHAVIOUR). Build MCP tools only for supported events.
- Use Rel-16 OpenAPI specs for the MCP tool definitions, not Rel-18. This matches what NextGCore can serve.
- Document the release gap explicitly. Future phases can expand when implementations catch up.

**Phase:** MCP tool development (must audit NextGCore capabilities before writing NWDAF tool definitions).

---

### Pitfall 14: Multi-turn conversation threading breaks in SDG output

**What goes wrong:** Fault prediction workflows are multi-turn: 4-6 tool calls across 8-12 conversation turns. If the SDG pipeline does not correctly thread `tool_call_id` references, or drops intermediate turns, the training example teaches the model a broken conversation flow. OSFT training with broken threading produces a model that loses track of context mid-workflow.

Evidence: ToolMind found that most existing multi-turn synthesis methods "validate correctness only at the trajectory level, which may overlook turn-level errors that can propagate during training and degrade model performance" (source: [ToolMind](https://arxiv.org/html/2511.15718v2)).

**Prevention:**
- Validate every multi-turn example end-to-end: each `tool_call_id` in an assistant turn must have a corresponding `tool` role response. No orphaned calls, no missing responses.
- Build a turn-level validator (not just trajectory-level) into the SDG pipeline.
- Limit maximum turns per example to 12-16 to avoid context-length issues during training.

**Phase:** SDG pipeline design (turn-level validation must be a pipeline stage).

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| MCP tool development | TMF spec version mismatch between tools and backends (#4) | Pin spec versions in week 1, validate with linter |
| MCP tool development | Schema inconsistency across MCP-Telecom and new tools (#11) | Adopt single naming/schema convention |
| MCP tool development | NWDAF release mismatch (#13) | Audit NextGCore capabilities before writing tool defs |
| Backend deployment | NextGCore NWDAF not actually functional (#6) | Validate with curl in week 1-2, have fallback plan |
| Backend deployment | OpenShift SCTP/SCC blocks (#8) | Budget 1 week, front-load to week 1-2 |
| Backend deployment | Operator sandbox access delays (#10) | Apply week 1, treat as bonus not dependency |
| SDG pipeline design | Training data format mismatch with OSFT (#5) | Get sample format from training team in week 1 |
| SDG pipeline design | Token count bloat from full tool catalog (#12) | Subset tools per scenario, target under 4K tokens |
| SDG pipeline design | Multi-turn threading errors (#14) | Build turn-level validator into pipeline |
| SDG execution | Teacher model hallucinating schemas (#1) | Three-stage verification with execution |
| SDG execution | Mode collapse (#2) | Scenario taxonomy, diversity tracking, varied params |
| SDG execution | Happy-path-only data (#9) | Design error scenarios into prompt taxonomy (20-30%) |
| SDG execution | Prism generating unrealistic responses (#3) | Enriched mocks, TMF reference implementations, live NWDAF |
| Eval and delivery | Eval not measuring tool-calling competence (#7) | Custom fault-prediction eval suite, weight execution tasks 3x |
| Eval and delivery | Format incompatible with OSFT (#5) | Dry-run with training team by week 3 |

## Sources

- [EdgeGen: Improving Tool-Calling Agents Beyond Happy Paths](https://arxiv.org/html/2609.24115) -- Edge case gaps in synthetic tool-calling data
- [Quality Matters: Evaluating Synthetic Data for Tool-Using LLMs](https://arxiv.org/html/2409.16341v2) -- 84% error rate in ToolBench, quality filtering approaches
- [APIGen: Automated Pipeline for Generating Verifiable Function-Calling Datasets](https://proceedings.neurips.cc/paper_files/paper/2024/file/61cce86d180b1184949e58939c4f983d-Paper-Datasets_and_Benchmarks_Track.pdf) -- Three-stage verification pipeline
- [I Gave AI Agents a Telecom Job Interview](https://dev.to/mattercoder/i-gave-ai-agents-a-telecom-job-interview-most-failed-without-a-cheat-sheet-ddj) -- TMF628 enumeration failures, TMF639 case sensitivity
- [Amartus TMF Integration Guide](https://amartus.com/how-to-effectively-design-integration-interfaces-that-are-based-on-tmf-open-api-specifications/) -- TMF spec ambiguity, conformance does not equal interoperability
- [TeleCom-Bench (ZTE-AICloud)](https://arxiv.org/html/2605.18025v1) -- 66-point gap between linguistic and execution tasks
- [Enhanced Open-Source NWDAF for Event-Driven Analytics](https://arxiv.org/html/2601.01838v1) -- Open-source NWDAF implementation gaps
- [NextGCore Issue #192](https://github.com/NextgCoreLab/nextgcore/issues/192) -- NWDAF subscriptions memory-only, no durable store
- [Open5GS on OpenShift](https://medium.com/@anil.sonmez/open5gs-on-openshift-container-platform-c92e72dd4738) -- SCTP and SCC requirements for 5G core on OpenShift
- [OpenShift SCC Documentation](https://docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html) -- Never modify default SCCs
- [Building Telco Reasoning Models with NVIDIA NeMo](https://developer.nvidia.com/blog/building-telco-reasoning-models-for-autonomous-networks-with-nvidia-nemo/) -- NeMo NOC reasoning pipeline, quality-as-first-class-stage
- [Google Research: Designing Synthetic Datasets](https://research.google/blog/designing-synthetic-datasets-for-the-real-world-mechanism-design-and-reasoning-from-first-principles/) -- Simula framework for diversity
- [Model Collapse via Synthetic Training Data](https://www.emergentmind.com/topics/model-collapse-through-synthetic-training-data) -- Shumailov et al., distribution tail loss
- [Red Hat AI Examples - OSFT](https://github.com/red-hat-data-services/red-hat-ai-examples/tree/main/examples/fine-tuning/osft) -- OSFT data format requirements
- [GSMA Open Gateway](https://www.gsma.com/solutions-and-impact/gsma-open-gateway/) -- Sandbox availability and onboarding
- [Stoplight Prism Documentation](https://docs.stoplight.io/docs/prism/83dbbd75532cf-http-mocking) -- Prism limitations with complex schemas
- [ToolMind Technical Report](https://arxiv.org/html/2511.15718v2) -- Turn-level errors in multi-turn synthetic data

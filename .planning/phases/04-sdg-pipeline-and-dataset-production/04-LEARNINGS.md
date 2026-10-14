# Phase 4: SDG Pipeline — Engineering Learnings Log

> Running log of empirical findings discovered *during* execution and how we responded — distinct
> from `04-DISCUSSION-LOG.md` (pre-planning decision audit trail, not for execution input) and
> `04-NN-SUMMARY.md` (per-plan task/commit recap). This file is for things we only learned by
> actually running the pipeline against live infra, in the order we learned them. Append, don't
> rewrite history — if a finding gets superseded, add a new dated entry rather than editing the old one.

---

## 2026-10-09 — Dry-run completed; teacher model under-uses the harder telecom tools

**What we ran:** `sdg-dry-run` Job, full 22-block `mcp_distillation_training` flow, 21 hand-curated
seed scenarios across 5 tiers (single_tool, parallel, sequential, multi_turn, closed_loop), teacher
model Gemma 4 31B via vLLM, `StreamingLLMChatBlock` (see `sdg/lib/streaming_llm_chat_block.py`) to
work around the AWS ELB idle-timeout found earlier this session. Completed in 85 minutes, 11 of 21
seed rows survived both quality gates (question-quality, response-completeness) — in line with the
project's documented 50-70% survival expectation.

**What `tool_coverage_report.py` showed** (`sdg/data/raw/dry-run/tool_coverage_report.md`,
regenerated any time from `sdg/data/raw/dry-run/all_tiers_raw.jsonl`):

- Tool use is heavily concentrated on two tools: `tmf642listAlarm` (7 calls) and
  `tmf621createTroubleTicket` (5 calls) account for most of the 11 examples' tool calls combined.
  Everything else is 1-2 calls.
- Four tools were **never called in any example**: `tmf628listMeasurementCollectionJob`,
  `tmf628retrieveTrackingRecord`, `telecomshow_interface_detail`, `telecomshow_bgp_summary`.
- Both `closed_loop` scenarios — the tier specifically designed to chain 5 tools into a
  correlate-then-remediate workflow — only exercised 2-3 of their 5 intended tools.
  `closed_loop_performance_degradation` skipped **both** TMF628 tools entirely: the model created
  a trouble ticket off an alarm list alone, without pulling the performance data that would
  justify escalating.
- One clear wrong-tool substitution: `parallel_analytics_and_interfaces` intended NWDAF analytics +
  `telecomshow_interfaces` together; the model called NWDAF analytics + `telecomlist_devices`
  instead — a valid call, but not what the scenario needed.

**Why this matters / how we're interpreting it:** an earlier spot-check this session (one
single_tool example, zero-argument lookup) looked clean and was read as "the model already calls
tools correctly." That read doesn't survive contact with the full coverage report. The
single_tool case is the easiest possible one — exactly where a strong general-purpose model's
baseline tool-calling mechanics would look fine regardless of telecom-specific training. The
coverage report's signal points the other way: the model has a default "list alarms, open a
ticket" pattern it reaches for, plausibly inherited from generic ITSM-style data in pretraining,
and it under-uses the tools that require more telecom-domain judgment to know *when* they're the
right next step (TMF628 performance correlation, interface/BGP diagnostics).

**Caveat:** n=11, mostly one example per scenario — this is a real signal, not a verdict. See
Next Steps below.

**Open/next:**
- Still need the ZTE-AIM/TFCE baseline run against OTel 2.0 (per `04-CONTEXT.md`/`PROJECT.md`
  scope) to turn "looks like a gap" into a measured number. Not yet done.

**Decision (2026-10-09): why self-distillation alone isn't enough, and the two candidate fixes.**

The current flow is self-distillation — Gemma 4 generates both the questions and the "expert"
tool trajectories that become its own fine-tuning data. Self-distillation can only *elicit* a
capability the teacher already has access to somewhere in its weights (surface it more reliably
via exemplars); it cannot manufacture a capability the teacher doesn't have. The quality filters
in the flow (question-quality, response-completeness) score narrative quality, not tool-selection
correctness, so they don't catch the bias documented above — they would happily pass more
polished examples of the same "list alarms, open a ticket" default.

Two concrete, non-mutually-exclusive fixes considered:

1. **Tool-coverage/correctness gate + rejection sampling (chosen first).** For hand-curated
   scenarios, `seed-scenarios.yaml`'s `tool_subset` *is* ground truth for "the right tools for this
   workflow." Instead of accepting the agent's first trajectory attempt and only filtering on
   narrative quality, sample N attempts per scenario and score each against
   `tool_coverage_report.py`'s own logic (did it call the full intended tool set, in a sane order
   for sequential/closed_loop); keep only attempts that pass, resample the rest up to a retry cap.
   This is classic rejection-sampling fine-tuning (STaR-style) — the teacher doesn't need to be
   right on the first try, it needs enough verified-correct trajectories out of several attempts.
   Cheap: reuses `multiply_tool_rows` sampling infra and the coverage-report scoring logic we
   already built; no new external dependency.
2. **Stronger external teacher for the tiers where Gemma 4 demonstrably fails** (closed_loop,
   sequential — exactly where the gap showed up). True distillation rather than self-distillation:
   a model without Gemma 4's blind spot generates the trajectory, Gemma 4 trains on it. Higher
   cost/complexity (new API dependency, likely a paid frontier model), justified only where (1)
   still can't produce a passing trajectory after several resamples — i.e., direct evidence the
   teacher genuinely lacks the judgment rather than just not defaulting to it.

**User's choice (2026-10-09):** build fix (1) directly into the KFP production pipeline now,
rather than standing up a vanilla pipeline first and layering the gate in later. Fix (2) remains a
documented fallback, not yet built, for whichever scenarios still fail the coverage gate after
resampling once the gated pipeline is actually running.

---

## 2026-10-09 — First KFP pipeline run submitted against sdg-dspa; two build gotchas found and fixed

**What we built:** `sdg/openshift/Dockerfile` (bakes sdg_hub + this repo's `sdg/` package + kfp
into one image, replacing per-run `pip install` at pod start), `sdg/pipelines/sdg_production_pipeline.py`
(KFP v2 DSL, three steps: `generate_examples` with the tool-coverage gate above baked in,
`coverage_report`, `evaluate_and_deliver`), compiled to `sdg/pipelines/sdg_production_pipeline.yaml`.
Built via `oc new-build --binary --strategy=docker` + a `dockerfilePath` patch on the BuildConfig
(the Dockerfile lives at `sdg/openshift/Dockerfile`, not the build-context root) and
`oc start-build --from-dir=.` — pushes straight to the internal registry ImageStream
(`image-registry.openshift-image-registry.svc:5000/otel25-sdg/sdg-pipeline:latest`), no external
registry needed.

**kfp SDK version note:** compiled the pipeline locally with kfp==2.17.0 (needs a python3.12 venv —
kfp doesn't support 3.13+ yet as of this session). The *runtime* image installs plain `kfp` with no
pin, which resolved to 2.9.0 under python:3.12-slim's Python — this is harmless, since component
containers never import kfp at runtime (they just run `python -m sdg.scripts.*`); kfp in the image
is only used by the throwaway submission pod. The compiled IR (2.17.0) submitted fine via a 2.9.0
`kfp.Client()` — the pipeline_spec IR format is more stable across SDK versions than the SDK's own
Python API.

**Getting `kfp.Client()` talking to the DSPA (the real friction point):** `sdg-dspa` has
`enableOauth: true`, so its external Route is OAuth-proxied and not practical for a scripted client.
The working path is entirely in-cluster:
1. DSPA's Deployment exposes the API server two ways: port 8888 (plain, but **also wrapped in TLS**
   because this DSPA has `podToPodTLS: true` at the top level of its spec — connecting with plain
   `http://` here times out, and even `https://` with cert verification off on port 8888 times out,
   seemingly firewalled/not meant for direct external-to-pod access) and port 8443, fronted by a
   `kube-rbac-proxy` sidecar that terminates TLS and authorizes via a `SubjectAccessReview` against
   a **custom resource**: `datasciencepipelinesapplications.opendatahub.io/datasciencepipelinesapplications/api`,
   resourceName `sdg-dspa`, namespace `otel25-sdg` (see the sidecar's `--config-file`,
   ConfigMap `kube-rbac-proxy-config-ds-pipeline-sdg-dspa`).
2. The DSPA operator already creates a `Role` with exactly this rule
   (`ds-pipeline-user-access-sdg-dspa` — get/create/update/patch/delete on that resource/subresource)
   but ships **no RoleBinding** — binding it is left to whoever deploys the DSPA. Added
   `sdg/openshift/sdg-dspa-submit-rbac.yaml` binding it to the namespace's `default` ServiceAccount.
3. `oc auth can-i`/`oc policy who-can` both report "no"/don't list the subject for this exact
   CRD-subresource check even when the binding is correct and a raw `SubjectAccessReview` confirms
   `allowed: true` — these CLI tools appear to mishandle this specific custom-resource-subresource
   shape. Don't trust them here; verify with a raw `SubjectAccessReview` object instead
   (`oc create -f sar.json -o jsonpath='{.status}'`) if a kube-rbac-proxy-gated endpoint keeps
   returning 403 despite RBAC that looks right.
4. Working client pattern, from a pod with network access to `otel25-sdg`'s cluster-internal DNS,
   using its own ServiceAccount token:
   ```python
   kfp.Client(
       host="https://ds-pipeline-sdg-dspa.otel25-sdg.svc.cluster.local:8443",
       existing_token=open("/var/run/secrets/kubernetes.io/serviceaccount/token").read().strip(),
       verify_ssl=False,  # self-signed service-serving cert; fine for an in-cluster call
       namespace="otel25-sdg",
   )
   ```

**Two real bugs found only by actually submitting a run (not visible from local compilation):**
1. `generate_examples` failed immediately with `FlowValidationError: Missing required columns:
   ['tool_list', 'mcp_server_name', 'mcp_server_description']`. Cause: an untracked, stale,
   old-schema `sdg/data/seeds/tool_metadata.jsonl` sitting in the repo from earlier local testing
   got baked into the image by `COPY sdg/ ./sdg/`, and `_ensure_seeds()`'s freshness check (file
   age < 3600s) treated the freshly-built image's copy as valid and skipped re-materializing from
   the live gateway. Fixed with a repo-root `.dockerignore` excluding `sdg/data/` (and
   `sdg/**/__pycache__/`, the compiled pipeline YAML, `.git/`, `.planning/`) from the build context
   — every pipeline run is a fresh ephemeral pod with no prior state, so it should always
   materialize seeds live, never trust a baked-in cache.
2. After that fix, `_ensure_seeds()` reached the live gateway (confirmed: "Discovered 80 tools from
   gateway" in the pod log) but then failed with `PermissionError: [Errno 13] Permission denied:
   'sdg/data'`. Cause: OpenShift runs pipeline-step pods under an arbitrary, dynamically-assigned
   UID (always in group 0) with no corresponding `/etc/passwd` entry; `COPY` leaves files owned by
   `root:root` with no group-write bit, and with `sdg/data/` now excluded from the image entirely
   (fix 1 above), the arbitrary-UID process couldn't create it fresh. Fixed with the standard
   OpenShift "support arbitrary user IDs" pattern in the Dockerfile: `RUN chgrp -R 0
   /opt/app-root/src && chmod -R g=u /opt/app-root/src` after the `COPY`.

**Confirmed actually working after both fixes** (run ID `9f7d60c8-6c9c-4db7-a2a9-b14ac185d564`):
seed materialization reached the live MCP Gateway fresh each time (80 tools discovered), the flow
loaded with the correct columns, and the `explore_server` AgentBlock step was observed actively
calling the live Langflow agent at ~80s/row — the same per-row throughput seen in the original
dry-run Job. Did not wait for full completion (same reasoning as the dry-run Job: 5 tiers plus the
new coverage-gate's up-to-3x resampling on hand-curated scenarios means this run could take
several hours). Coverage-report and delivery outputs from this run, once complete, will be the
first real evidence of whether the rejection-sampling gate (previous entry, fix 1) actually moves
the needle on the TMF628/interface-diagnostics gap found in the original dry-run.

---

## 2026-10-09 — `max_concurrency` bumped to 4; real bug found in the coverage-gate retry loop

**Context:** after the KFP pipeline was confirmed running (previous entry), bumped
`GENERATION_MAX_CONCURRENCY` from 1 to 4 in `run-generation.py` (rebuilt the image, resubmitted a
run) since streaming -- not serialization -- was the actual fix for the original 504 timeouts, so
full serialization was no longer buying anything. Watched the early stages live: `generate_questions`
visibly ran 4 requests in parallel (multiple rows landing within the same second) with zero errors,
and the run cleared `score_question_quality` (the exact stage that used to 504) cleanly. Confirmed:
`max_concurrency=4` is safe. `AgentBlock` steps (`explore_server`, `run_expert_trajectory`) stay
sequential regardless of this setting -- it doesn't appear to be threaded through to AgentBlock the
way it is for `LLMChatBlock`, so the speedup is partial, not a flat 4x.

**What actually crashed the run (~4 hours in, unrelated to concurrency):** a coverage-gate resample
attempt (tier `single_tool`, attempt 2/3 on one seed that failed the first attempt's coverage check)
multiplied to 20 rows via `multiply_tool_rows`, and **all 20** failed sdg_hub's own
`filter_incomplete_responses` quality filter -- a legitimate, if unlucky, 0% survival rate for that
one attempt. sdg_hub's `flow.generate()` raises `EmptyDatasetError` when a filter block empties the
dataset entirely, instead of returning an empty result. The coverage-gate retry loop added in the
previous entry never anticipated that exception -- it assumed `_generate_once()` always returns a
list (possibly empty) -- so the exception propagated straight out of `_run_generation()` and killed
the whole tier (and the KFP step, and the run) instead of being treated as "this attempt produced
zero survivors, try again," which is exactly the kind of outcome the retry loop exists to handle.

**Fix:** wrapped the `_generate_once()` call in `_run_generation()`'s retry loop in
`try/except EmptyDatasetError`, treating the exception as zero rows for that attempt (logs a
warning, continues to the next attempt or records a coverage-gate failure on the last one). Imported
`EmptyDatasetError` from `sdg_hub.core.utils.error_handling` in the same guarded import block as
`FlowRegistry`/`Flow`, with a placeholder exception class on `ImportError` so the module stays
importable without sdg_hub installed. Added `sdg/scripts/test_run_generation_coverage_gate.py`
(2 tests, using a scripted fake `Flow.generate()`) covering both the recover-and-retry path and the
all-attempts-fail path, since this exact failure mode is easy to silently regress.

**Why this only showed up now:** the original dry-run (pre-coverage-gate, `max_concurrency=1`) never
hit this, because without the gate there was no retry loop re-running a single already-hard seed in
isolation -- a 20-row batch across 7 *different* seeds is much less likely to 100%-fail the
completeness filter than 20 resampled variants of one specific seed that was already struggling
(that's plausibly *why* it needed resampling in the first place). This is a structural risk of
rejection sampling in general, not a one-off fluke: expect it to recur, especially on harder tiers
(closed_loop, sequential) where a seed failing the coverage gate at all is more likely to also be a
seed the teacher struggles to answer completely. The fix makes it a handled, logged, retried case
instead of a crash -- but a seed that reliably 100%-fails completeness on every attempt will still
correctly end up in `coverage_failed` after `MAX_ATTEMPTS`, which is the right outcome.

**Status:** fix committed, image rebuilt, resubmitted as run `8634ce18-...`.

---

## 2026-10-10 — Split `generate_examples` into one KFP task per tier; Langflow's PVC filled up

**Split:** rewrote `sdg_production_pipeline.py` so `generate_tier(tier=...)` is called once per
entry in `TIERS` (5 separate tasks, each with its own `raw_output` artifact), chained sequentially
via `.after()` rather than run in parallel -- deliberately, since all 5 would hit the same shared
vLLM/Langflow backend and we didn't want to stack an untested concurrent-tiers variable on top of
`GENERATION_MAX_CONCURRENCY=4` and the `EmptyDatasetError` fix in the same day. `coverage_report`
and `evaluate_and_deliver` now take 5 named `Input[Dataset]` (one per tier) and merge them, with
`2>/dev/null || true` guarding the case where a tier produced zero accepted rows. No image rebuild
needed -- this is a pipeline-DSL-only change, not a change to the baked `sdg/` package code.

**Immediately validated the resilience win was real:** the first run on this new topology (`hb5gn`)
completed tiers `single_tool` and `parallel` successfully -- each landed as its own independent
Garage artifact -- then failed on `sequential`. Under the old single-step design this would have
lost tiers 1-2's output too, forcing a full restart; here they're intact regardless of what
happens to tiers 3-5.

**What actually failed this time (unrelated to any of our code):**
```
sdg_hub.core.connectors.exceptions.ConnectorHTTPError: HTTP 500 ... Error building Component
Chat Input: (sqlite3.OperationalError) database or disk is full
```
Langflow's own SQLite database (`/data/langflow.db` on PVC `data-langflow-service-0`) had grown to
886MB and filled its 1Gi PVC entirely (`df`: `/data` at 100%, 0 available) -- accumulated message/
session history from every agent run across all the dry-runs and production attempts this project
has done over the past several days. Not a capacity we'd provisioned with this workload in mind;
1Gi was the chart's original default from early in the project when Langflow was only being used
interactively in the UI, not driven by hundreds of unattended AgentBlock calls per pipeline run.

**Fix:** resized the PVC 1Gi -> 5Gi (`oc patch pvc data-langflow-service-0 --type merge -p
'{"spec":{"resources":{"requests":{"storage":"5Gi"}}}}'`) -- `gp3-csi` supports online expansion
(`allowVolumeExpansion: true`), confirmed via `oc get storageclass`. The PVC's `allocatedResources`
updated immediately but the filesystem itself needed a pod restart to actually grow
(`FileSystemResizePending` / `NodeResizePending` conditions, message: "Waiting for user to
(re-)start a pod to finish file system resize of volume on node" -- a normal EBS CSI behavior, not
an error). Deleted the `langflow-service-0` pod (StatefulSet recreated it), confirmed
`df -h /data` afterward: 4.9G size, 962M used, 4.0G available.

**Not yet addressed:** 5Gi buys headroom but doesn't change the underlying unbounded growth --
Langflow appears to persist full message/session history per run with no retention/pruning by
default. At the observed growth rate this will fill again eventually under continued heavy
pipeline usage. Worth revisiting (a pruning cron, a retention setting if Langflow exposes one, or
just periodic manual `VACUUM`/history deletion) if this becomes a recurring interruption -- not
urgent enough to block on right now.

**Resolved same day:** the gap above ("no way to skip already-succeeded tiers on resubmit") came up
in practice almost immediately -- the very next run (`hb5gn`'s successor) crashed on `sequential`
for a reason unrelated to tiers 1-2 (see next entry), and resubmitting redid them from scratch.
Enabled `set_caching_options(True)` on `generate_tier` specifically (left `coverage_report`/
`evaluate_and_deliver` uncached -- cheap, no live-model cost, should always reflect whatever tier
artifacts currently exist). KFP's cache keys on exact component + input values, so a resubmit with
identical `tier`/`gateway_url`/`keycloak_url`/`client_id` now skips any tier that already succeeded
in *any* prior run, not just immediately-prior. Accepted tradeoff, written down so it isn't
forgotten: a genuinely-intended full regeneration later (new seeds, changed gateway tools,
deliberately wanting fresh stochastic sampling) will also hit this cache and silently return old
data unless caching is turned off again first or some input is changed -- there is no automatic
distinction between "resume after an infra hiccup" and "I want to regenerate everything."

---

## 2026-10-10 — All 5 tiers completed for the first time; `run-evaluation.py`'s "evaluation flow" never existed

**Real progress:** this run (`vldmj`) is the first time every one of the 5 `generate_tier` tasks
completed successfully end to end -- confirms the tool-coverage gate, `max_concurrency=4`, and the
`EmptyDatasetError` fix all hold up across a full real run, not just the tiers tested individually
before. `coverage_report` also ran successfully. It failed on `evaluate_and_deliver` -- the first
time this pipeline has ever actually reached that stage with real data (every earlier run died
before getting this far), which is exactly why this bug was still latent.

**What failed:**
```
sdg_hub.core.utils.error_handling.FlowValidationError: Flow path cannot be None. Please provide a
valid YAML file path or check that the flow exists in the registry.
```
`run-evaluation.py` called `FlowRegistry.get_flow_path("MCP Server Distillation Evaluation")` --
this flow does not exist in sdg_hub==0.9.4. Verified directly against the real package (spun a pod
on the production image, called `FlowRegistry.discover_flows(); FlowRegistry.list_flows()`): the
only training-side match is `{'id': 'new-night-835', 'name': 'MCP Server Distillation'}` (the one
we already use correctly in `run-generation.py`). The only evaluation-category flow that exists at
all is `{'id': 'eager-path-837', 'name': 'Agent Tool-Use Evaluation'}`
(`flows/evaluation/mcp_eval_benchmark/model_evaluation/flow.yaml`) -- and even that one would not
have worked: its `get_dataset_requirements()` demands `question`, `expert_answer_truncated`,
`expert_trace_formatted`, `model_answer`, `model_trace_formatted` -- i.e. it scores a model's trace
*against an independent expert/gold-standard trace*, which we don't have and was never part of this
project's design. On top of that, no `Flow` in this package exposes an `.evaluate()` method at all
(confirmed via `dir(flow)`) -- every flow's entrypoint is `.generate()`, the same one
`run-generation.py` already uses correctly. `run-evaluation.py`'s Step 1 was calling a method that
doesn't exist, on a flow name that doesn't exist, expecting a flow shape that wouldn't have fit our
data even if the name had resolved.

**Root cause:** D-02 (`04-CONTEXT.md`) planned around "both of sdg_hub's agentic example flows:
mcp_distillation_training and mcp_distillation_evaluation... performs the three-stage verification."
That second flow was a design-time assumption from early research (predating actual installation
and inspection of the real package) that never matched reality, and nothing exercised this code
path until a run finally survived long enough to reach it -- 2026-10-10, five days and many runs
after Phase 4 execution started.

**Fix:** rewrote `_run_evaluation_flow()` in `run-evaluation.py` as a pass-through (load the tier's
raw JSONL, write it unchanged to `output_dir`) instead of calling a flow. Not a workaround -- the
three verification stages that function was meant to add are already covered upstream, inside
`run-generation.py`'s training flow and our tool-coverage gate: format (TagParserBlock structural
parsing), execution (`run_expert_trajectory` actually calls live tools), and semantic
(`score_question_quality`/`score_response_quality` judges plus their filters, plus the
tool-coverage gate). Removed the now-dead `FlowRegistry`/`Flow` import from `run-evaluation.py`
(no longer used anywhere in that file). Added `sdg/scripts/test_run_evaluation.py` (2 tests) since
this file had no test coverage before. Column mapping and OSFT validation/delivery (the actual
deliverable) are unaffected -- they already operated on raw generation columns directly, not on
anything the removed flow call produced.

**Status:** fix committed, image rebuilt, resubmitted (`fmqhz`). Cache hit on all 5
`generate_tier` tasks (same `:latest` image tag string, even though its content changed -- KFP's
cache key apparently doesn't include the resolved image digest, just the literal reference in the
component spec) and `coverage_report` succeeded, confirming the evaluation-flow fix worked and
exposing a second, immediate bug below.

---

## 2026-10-10 — Step 1 finally produced real data (106 rows); Step 2's COLUMN_MAP was also guessed wrong

**Real progress:** with the evaluation-flow fix in, Step 1 (load raw generation output) ran clean
against genuine production-scale data for the first time: `single_tool` 66 rows, `parallel` 25,
`sequential` 5, `multi_turn` 10, `closed_loop` 0 (every closed_loop scenario apparently ended up in
`coverage_failed` -- worth a closer look once the pipeline completes end to end, separate from this
entry). 106/106 rows "passed" Step 1 (now a pass-through, not a filter).

**What failed next, at Step 2 (Column Mapping):**
```
ValueError: Row 0: required serializer keys {'tool_trace', 'answer'} not found after column
mapping. Available columns: [... 'extract_agent_text_text', 'extract_agent_text_tool_trace', ...]
```
Same root pattern as the evaluation-flow bug two entries up: `COLUMN_MAP` (`run-evaluation.py`) was
guessing source column names from "RESEARCH.md block descriptions" (`agent_text`, `response_text`,
`tool_trace`, `agent_tool_trace`) that never matched sdg_hub's real output -- and this code path had
never run against real data before either, for the same reason (every prior run died before
reaching it). The real columns, `extract_agent_text_text` and `extract_agent_text_tool_trace`, were
already known and already a named constant (`DEFAULT_TRACE_COLUMN` in `sdg/lib/trace_utils.py`,
confirmed empirically back in the 2026-10-09 dry-run and already relied on by
`tool_coverage_report.py` and the rejection-sampling gate) -- this bug was really "a second place
re-guessed the same fact instead of importing the already-confirmed constant."

**Fix:** imported `DEFAULT_TRACE_COLUMN` from `sdg.lib.trace_utils` into `run-evaluation.py` and
added it (plus `extract_agent_text_text` -> `answer`) to `COLUMN_MAP`, ahead of the old guessed
entries (kept, harmless, in case some other flow version ever produces those names). Added a
regression test (`test_map_columns_resolves_real_sdg_hub_output_column_names`) using the real
column names so this can't silently re-break. 88 tests passing.

**Pattern worth naming:** two bugs in a row now have been "code that was written against assumed
sdg_hub behavior (names, methods, flow existence) from early research, never actually exercised
against the real package/real data because every run before now died earlier in the pipeline."
Worth treating the rest of this file's downstream path (Step 3: OSFT validation + serialization)
with the same suspicion until it's actually been run end-to-end once -- it has the same
provenance and has never executed against real data either.

**Status:** fix committed, image rebuilt, resubmitted -- run `bcppr` completed the entire pipeline
end to end for the first time: 106 examples delivered (single-turn.jsonl + multi-turn.jsonl, both
OSFT-validated, 0 dropped). Per-tier: single_tool 66, parallel 25, sequential 5, multi_turn 10,
closed_loop 0. See next entry for the closed_loop 0 investigation.

---

## 2026-10-10 — closed_loop's zero examples explained: two specific, reproducible blind spots

Pulled `closed_loop_coverage_failed.jsonl` (25 rows -- every attempt across both closed_loop seed
scenarios, all 3 resamples each, all failed) from the run that originally produced it
(`a16183a9-...`, cached and reused by the later successful run `bcppr` since
`generate_tier` caching is on). Cross-referenced each row's actual tool trace against its
`intended_tools` using `trace_utils.tools_called_in_row()`. Not random variance -- two distinct,
100%-consistent failure modes:

- **`closed_loop_performance_degradation` (19/25 attempts, 100% failure rate for this scenario):**
  every single attempt called *only* `tmf642listAlarm` + `tmf621createTroubleTicket` -- the exact
  "list alarm, open ticket" default pattern first observed in the 2026-10-09 dry-run. Never once
  called `nwdafget_nwdaf_analytics` or either TMF628 tool
  (`tmf628listMeasurementCollectionJob`, `tmf628retrieveTrackingRecord`), across every resample.
  The model shows no awareness that performance-correlation data should precede escalation in this
  scenario -- not a near-miss, a complete behavioral gap around the TMF628 tool family.

- **`closed_loop_alarm_correlation_remediation` (6/25 attempts):** much closer to correct --
  consistently orchestrates 4 of its 5 intended tools correctly (`nwdafget_nwdaf_analytics`,
  `tmf621createTroubleTicket`, `tmf642acknowledge_alarm`, `tmf642listAlarm`) and misses exactly one,
  every single time: `telecomshow_interface_detail` -- the one device-layer (MCP-Telecom) tool in an
  otherwise TMF-domain workflow. Cross-domain tool orchestration (TMF + device-layer together) looks
  like the specific weak point here, not multi-tool orchestration in general.

**Why this matters:** this directly confirms and sharpens the gap the Farbod email is about. It's
not "closed_loop is uniformly too hard" -- it's two specific, reproducible blind spots (TMF628
performance-correlation tools, and cross-domain device-layer lookups inside an otherwise-correct TMF
workflow) that 3 resamples of self-distillation never broke through, even once, in 25 attempts. Good
concrete evidence to have in hand once Farbod responds with model API options -- these are the
specific capabilities to check a stronger teacher actually has before committing to it.

---

## 2026-10-11 — Patched Langflow's system prompt instead of waiting on a stronger teacher

**Root cause confirmed before patching:** ran a live A/B test replaying the exact
`closed_loop_performance_degradation` question and tool schemas through both Gemma 4 and Gemini as
the agent model. Both models defaulted to the same "list alarm, create ticket" shortcut and skipped
the TMF628 performance-correlation tools -- same failure, different model. That rules out "model is
too weak" and points at the agent's system prompt: it's Langflow's stock generic-agent template
(`Agent-EXpSZ` component), with zero telecom-domain guidance on when to keep investigating versus
act immediately.

**Fix:** added a new "Investigating network issues" section to the live system prompt (via
Langflow's `PATCH /api/v1/flows/{id}` API, `data` field only), inserted between the existing "Using
tools" and "Doing tasks" sections:
- First bullet: when a task implies detection/correlation/diagnosis rather than a fixed step list,
  check every relevant diagnostic domain (alarms, performance analytics, device/interface details)
  before escalating -- don't stop at the first plausible signal.
- Second bullet, the regression guard: when a task specifies an explicit action or a defined
  sequence of steps, do exactly that -- no added investigative tool calls.

**Why the second bullet matters:** cross-referenced every `seed-scenarios.yaml` scenario before
writing this. Every `single_tool`/`parallel`/`sequential`/`multi_turn` scenario's description spells
out the exact tool sequence (e.g. `single_create_trouble_ticket`: "Create a trouble ticket for
{category} issue" -- one tool, no diagnosis implied; `parallel_alarms_and_tickets`: "Check alarms
and open tickets simultaneously" -- explicit, no investigation implied). Only the 3 `closed_loop`
scenarios are genuinely open-ended ("detect X, correlate, decide, act"). An unconditional "always
investigate before escalating" instruction would have risked teaching the model to pad
`single_create_trouble_ticket`/`parallel_alarms_and_tickets`-style trajectories with unnecessary
tool calls; scoping the instruction to tasks that imply investigation (vs. tasks that specify exact
steps) avoids that.

**Verification:** diffed the full flow JSON before/after the PATCH -- only `Agent-EXpSZ`'s
`system_prompt` value changed, every other node and all edges byte-identical.

**Status:** patched live. Not yet re-validated with a fresh generation run against
`closed_loop_performance_degradation`/`closed_loop_alarm_correlation_remediation` to confirm the
tool-coverage gate now passes more often -- next step before trusting this for the full production
run.

---

## 2026-10-11 — Both system-prompt fixes failed; reverted to the stock prompt

**What was tested:** re-ran `closed_loop` end-to-end (real pipeline, real sdg_hub question generation, not a replayed fixed question) under two different versions of the "Investigating network issues" system-prompt addition, plus a `single_tool`+`parallel` regression check under the second version.

**Attempt 1 (conditional, scoped to tasks that imply investigation):** 0/3 closed_loop scenarios passed. Root cause: sdg_hub's own question-generation step frequently phrases even the investigative scenarios (`closed_loop_performance_degradation`) as direct 2-step requests ("check alarms, open a ticket") rather than open-ended investigations, so the instruction's precondition rarely fires. `closed_loop_interface_fault_escalation` (previously 100% passing) also failed all 3 attempts here -- the question *was* investigative, but the model called an extraneous tool (`telecomlist_devices`) instead of the intended `telecomshow_interfaces`/`telecomshow_interface_detail`, a tool-disambiguation miss unrelated to whether it investigated.

**Attempt 2 (unconditional, the version validated in the earlier single-question Gemini/Gemma A/B replay):** 0/3 closed_loop scenarios passed -- identical to attempt 1 and to the pre-fix baseline. Zero improvement on the target problem. Worse: regression-tested against `single_tool` (7 scenarios, previously 0 coverage failures) and `parallel` (4 scenarios, previously 0 coverage failures) and found **3 new failures**: `single_list_performance_jobs`, `parallel_analytics_and_interfaces`, `parallel_location_and_analytics` -- scenarios with explicit, narrow tool_subsets and no investigation implied by the task at all.

**Why the single-question A/B test didn't predict this:** that test replayed one exact, hand-picked, already-investigative question through a live multi-turn loop. It validated "if the question is phrased as an investigation, this instruction helps." It never tested (a) whether sdg_hub's own stochastic question generation reliably produces investigative phrasing for scenarios meant to be investigative, or (b) whether an unconditional version of the instruction degrades scenarios with no investigation implied. Both turned out to be real, load-bearing gaps the one-shot test couldn't surface.

**Conclusion:** reverted Langflow's `Agent-EXpSZ` system prompt to its original stock template (no custom section). Two different system-prompt approaches were tried against the real pipeline and both failed to close the closed_loop gap; the unconditional one actively regressed two other tiers for no offsetting benefit. This is now solid evidence -- not just the original single-question test's weaker signal -- that the closed_loop tool-coverage gap (TMF628/NWDAF performance-correlation tools, device-layer tool disambiguation, `tmf642acknowledge_alarm`) does not respond to agent system-prompt engineering with either Gemma 4 31B or Gemini as the acting model, and the documented fallback (a stronger external teacher scoped to just these scenarios) is the real next step, not a system-prompt tweak.

**Verification:** diffed the full flow JSON before/after the revert -- only `Agent-EXpSZ`'s `system_prompt` changed back to its original value (length 3003, matches the pre-patch original), every other node and all edges byte-identical.

---

## 2026-10-12 — NWDAF's h2c path was actually broken in production; fixed

**Discovery context:** while building the new UDR MCP server (Phase 6), found that `httpx2.AsyncClient`
wrapping a raw `httpcore2.AsyncConnectionPool` as its transport -- the exact pattern `mcp/nwdaf/server.py`
has used for its h2c branch since Phase 4 -- hits a real bug in `httpx2==2.13.1`/`httpcore2==2.13.1`
(the versions both servers lock): `httpcore2`'s connection pool calls `request.url.scheme.decode()` on a
value `httpx2` already passes as a `str`, raising `AttributeError` on every request.

**Verified directly against NWDAF**, not just inferred from the UDR finding: execed into the live
`mcp-nwdaf` pod and called `get_nwdaf_analytics()` directly. Raw TCP connect to the NextGCore NWDAF
backend succeeded; the `httpx2`/`httpcore2` h2c client call failed every time with
`httpx2.ConnectError: All connection attempts failed` -- confirming the bug, not a network/config issue,
since raw TCP worked and only the library call didn't.

**Impact:** `get_nwdaf_analytics()` has been failing against live NextGCore in production since
whenever `NWDAF_PROTOCOL=h2c` was first set (Phase 4). This means any production generation run that
exercised `single_get_nwdaf_analytics` or any closed_loop/sequential scenario needing NWDAF against the
live backend would have silently produced tool-call failures, not real analytics data -- worth
revisiting whether any delivered training examples using NWDAF were actually generated against Prism
(no NWDAF Prism mock exists, per the original Phase 1/3 finding) or genuinely failed and got filtered
out by the tool-coverage gate, which would explain some of the already-documented tool-coverage gaps
without needing a model-behavior explanation.

**Second, independent bug found in the same fix pass:** `NWDAF_BASE_URL` in both copies of the
`backend-routing` ConfigMap (`otel25-mcp` and `otel25-backends`) was set to
`http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777` -- host:port only, missing the
NextGCore-specific base path (`/nnwdaf-analyticsinfo/v1`) the server's own header comment already
documented as required. This produced a clean `404 Resource not found: /analytics` once the h2c
connection bug was fixed -- a second, separate, pre-existing misconfiguration that the first bug had
been masking (a connection error and a 404 look identical from "nothing came back" at a glance, but
are different problems needing different fixes).

**Fix:** ported the `_H2CClient`/`_H2CResponse` wrapper (drives `httpcore2`'s connection pool directly,
bypassing `httpx2`'s broken translation layer) from `mcp/udr/server.py`, where this bug was first found
and fixed, into `mcp/nwdaf/server.py`. Added the missing `h2>=4.1.0` dependency to `pyproject.toml`
(confirmed via live testing that `h2` was never declared anywhere in this project despite being
required for real HTTP/2 support -- any genuine h2c attempt would `ModuleNotFoundError` before even
reaching the connection bug). Patched both ConfigMap copies' `NWDAF_BASE_URL` to include the correct
NextGCore base path. Rebuilt and redeployed the `mcp-nwdaf` image; verified live through the real MCP
protocol (`fastmcp.Client`, not just a direct module call) -- clean response, `is_error=False`, no
connection errors.

**Status:** fixed and verified live. `get_nwdaf_analytics` against live NextGCore now returns a clean
structured response (`{"status": "no_content", ...}` for the tested event type -- expected, since no
real NF-load event has occurred in this NextGCore deployment; the point was confirming the request
reaches the backend and gets a real HTTP response, not a connection failure).

---

## 2026-10-12 — closed_loop gap re-diagnosed: not a model problem, two real tooling bugs upstream of question generation

**What prompted this:** re-examined `closed_loop_coverage_failed.jsonl` directly (not just the 2026-10-11
summary) after the two system-prompt fixes failed. Both fixes patched `Agent-EXpSZ`'s system prompt --
the node that acts on a question. Tracing the actual pipeline fields (`sampled_tools`, `server_understanding`,
`question_gen_messages`, `target_tools`, `question`) shows the information loss happens one stage earlier,
in **question generation**, which is itself downstream of **exploration**. The question-gen prompt was
given the full 5-tool schema set and the scenario's explicit step-by-step description every time -- it
wasn't under-provisioned. It just never wrote a question needing the tools exploration had already
flagged as broken, because its own instructions say to ground questions in real, working data.

**Two concrete, previously-undiscovered bugs found, confirmed live, and fixed:**

1. **TMF628 `TrackingRecord.description` schema-validation failure.** The vendored spec
   (`backends/specs/tmf628_performance_v4.0.0.swagger.json`) declared this field `"type": "string"` but
   its D-16-enrichment `"example"` value was mistakenly authored as a list, `["acknowledge", "clear"]`,
   instead of a single string. Prism's static mode (the D-16 amendment default) served this malformed
   example verbatim, so every live call to `tmf628listMeasurementCollectionJob` returned a list where a
   string was required -- exactly the "tool returned a list for a field defined as a string" failure
   exploration recorded, and exactly why `closed_loop_performance_degradation`'s generated questions
   never once mention TMF628 across all 20 failed attempts: exploration learned the tool was broken
   before the question was ever written. Scanned every vendored spec for the same `type: string` +
   list-valued `example` pattern -- this was the only instance. Fixed (`example: "acknowledge"`),
   image rebuilt and pushed, `prism-tmf628` redeployed, verified live (`curl` against the pod now
   returns `"description":"acknowledge"`, a plain string).

2. **`mcp-telecom`'s Dockerfile baked in the placeholder device inventory, not the real one.** Phase 4
   Plan 06 built and committed a real Containerlab device inventory (`mcp/mcp-telecom/devices.yaml`,
   3 Nokia SR Linux devices with real Clabernetes service DNS names) alongside the original template
   (`devices.yaml.example`). But `mcp/mcp-telecom/Dockerfile` line 26 hardcoded
   `COPY devices.yaml.example ./devices.yaml` -- every image built after 04-06 landed silently reverted
   to the single fake `router-lab-01.example.com` placeholder entry, regardless of what was in the real
   file. Confirmed live: the running pod's `/app/devices.yaml` was the placeholder, matching
   exploration's exact finding ("`telecomlist_devices` returning 'No devices configured'... renders all
   `telecom*` tools unusable"), which is why `telecomshow_interface_detail` was dropped from every
   `closed_loop_alarm_correlation_remediation` question. Fixed (`COPY devices.yaml ./devices.yaml`),
   image rebuilt and pushed, `mcp-telecom` redeployed, verified live (pod's `/app/devices.yaml` now
   shows the real 3-device Containerlab inventory).

**Revised conclusion (supersedes 2026-10-11's "stronger external teacher" recommendation):** the
2026-10-11 entry's finding that agent-side system-prompt engineering doesn't fix the gap still stands --
but the recommended next step was wrong. A stronger teacher model would make the same rational choice to
avoid tools it discovers are broken during exploration; the fix was never about model judgment, agent
prompting, or teacher strength. It was two ordinary bugs (a malformed spec example, a Dockerfile COPY
pointing at the wrong file) that made two real tools genuinely non-functional during exploration, which
then correctly propagated into the questions never asking for them. Both are now fixed and deployed.

**Not yet done:** sdg_hub's `generate_tier` step caches exploration results keyed by run -- the stale
"TMF628 is broken" / "no devices configured" understanding from the 2026-10-10 run will keep being
reused until a fresh (non-cached) exploration pass runs against these two fixed tools. The teacher model
(vLLM) is not currently deployed on sandbox2667 (waiting on GPU node availability), so a fresh
closed_loop generation run to confirm the fix closes the coverage gap hasn't been possible yet -- this is
the first thing to try once the model is up.

---

## 2026-10-12 — GPU node unblocked, teacher model up, but two more gaps found before a real validation run was possible

The sandbox2667 GPU node (`g6e.12xlarge`) had been failing for 47+ minutes on a genuine AWS
`InsufficientInstanceCapacity` error for that instance type in `us-east-2b` -- confirmed via a live
test-launch, not inferred from the pod event alone. `us-east-2a`/`us-east-2c` (which AWS suggested) aren't
usable: this sandbox's VPC only has subnets in `us-east-2b`. Tested `g6.12xlarge` (also 4-GPU, L4 instead
of L40S) in the same AZ -- also no capacity. `g5.12xlarge` (4x A10G, 96GB total) succeeded on the first
real launch attempt. Scaled the failing `g6e.12xlarge` MachineSet to 0, kept the `g5.12xlarge` node, and
the `redhataigemma-4-31b-it` KServe pod scheduled and became `2/2 Running` on it with no manifest changes
needed (no node selector/affinity was ever set on the pod).

With the model finally up, two more gaps surfaced before a real `closed_loop` validation run was
possible, neither related to Gemma 4 or Gemini:

1. **`generate_tier`'s caching silently defeated the whole point of the exercise.** The first KFP run
   submitted after the model came up reported `Succeeded` in under 2 minutes and reused the exact
   2026-10-10 cached output for all 5 tiers (`closed_loop_raw.jsonl`: 0 rows, same "tools never called"
   list as before) -- `set_caching_options(True)` on `generate_tier` (2026-10-10 entry above) means a
   resubmitted run with identical `tier`/`gateway_url`/`keycloak_url`/`client_id` inputs always hits cache,
   regardless of whether the actual backends changed. The KFP pipeline image itself isn't even on the
   dependency list KFP hashes for cache keys -- only the declared component inputs are -- so neither
   today's TMF628/devices.yaml fixes nor any future server-side fix will ever bust this cache on their
   own. Added a `--no-cache` flag to `sdg_production_pipeline.py`'s `--submit` path
   (`enable_caching=False` on `create_run_from_pipeline_package`) as the deliberate override for exactly
   this situation -- verified a second submission with `--no-cache` actually executes `explore_server`
   live instead of skipping straight to `Succeeded`.

2. **The deployed pipeline image predates the Phase 6 scenario additions.** Checked directly inside the
   running pod's filesystem (not assumed from build timestamps): `/opt/app-root/src/sdg/config/
   seed-scenarios.yaml` baked into `otel25-sdg/sdg-pipeline:latest` has zero occurrences of
   `devicestatus*`/`udrget_authentication*` -- only the original 21 fault-prediction scenarios. The 9
   new cross-domain scenarios Phase 6 added (including the 2 new closed_loop ones exercising UDR and
   CAMARA Device Status) are invisible to every run against this image until it's rebuilt from current
   `sdg/`. This means even a fully successful `--no-cache` run right now only validates the original 3
   closed_loop scenarios' fix, not the Phase 6 cross-domain breadth the project is trying to scale into.

Also fixed in passing: `sdg_production_pipeline.py --submit` was missing `verify_ssl=False` against the
in-cluster kube-rbac-proxy endpoint (self-signed cert, not the cluster's service-ca) -- the RBAC
manifest's own comments documented this as required but the script never implemented it, so every
`--submit` attempt failed on `SSLCertVerificationError` until this was added.

**Status:** a `--no-cache` run (`02a13ce7-edaa-44e9-bc27-b71ccfe20abb`) is in flight, confirmed executing
`explore_server` live rather than skipping. This will validate the TMF628/devices.yaml fix for the
original 3 closed_loop scenarios once it completes. Still open: rebuild `sdg-pipeline:latest` from
current `sdg/` so a follow-up run can validate the Phase 6 cross-domain closed_loop scenarios too --
decision on sequencing (let this run finish first vs. rebuild now) not yet made.

## 2026-10-13 -- sandbox3435 worker-node outage stranded single-replica Keycloak; redeploy-readiness fixes made ahead of a new 3-control-plane-node cluster migration

**Incident:** worker node `ip-10-0-26-12` on sandbox3435 went `NotReady` at `07:08:59Z`. `mcp-keycloak-0`
(RHBK StatefulSet, `instances: 1`, no anti-affinity) was pinned to that node and got stuck in
`Terminating` limbo -- Kubernetes won't force-finalize a pod when the node's kubelet is unreachable to
confirm termination, and the StatefulSet controller won't schedule a replacement ordinal-0 pod until the
old one is confirmed gone. Zero running Keycloak for the rest of the node outage. This broke the
`mcp-token-refresher` CronJob (Keycloak token requests got router-level `503 Application is not
available`) and, downstream, Langflow's periodic MCP-tool-list refresh (`Error updating tool list: MCP
server 'otel25-mcp-gateway' ... failed`), which is what actually surfaced as a pipeline run failure in
`run_expert_trajectory`. The rest of the gateway stack (mcp-gateway, mcp-gateway-istio,
mcp-gateway-controller, rhbk-operator -- all Deployments, not StatefulSets) had already self-healed onto
healthy nodes hours earlier from an *earlier*, unnoticed instance of the same node's flakiness; only
Keycloak lacked any failover path.

**Fix applied live (sandbox3435, not committed -- cluster-specific state):** force-deleted the stranded
pod (`--grace-period=0 --force`), re-ran `configure-keycloak.sh` to recreate the wiped realm/clients,
re-synced the regenerated `sdg-pipeline` client secret to sandbox2667's `keycloak-client-secret-sdg-pipeline`
Secret, triggered a manual `mcp-token-refresher` Job, verified end-to-end via curl before resubmitting the
pipeline run.

**Redeploy-readiness fixes made and committed** (ahead of migrating off sandbox3435 to a new 3-node
control-plane cluster the user is bringing up), per audit findings:

1. **Hostname parameterization**: `gateway/openshift/{keycloak,gateway,auth-policy}.yaml` had sandbox1330's
   hostname hardcoded even after the live sandbox3435 cutover -- that live fix was never committed, so the
   *next* migration would have repeated the same manual find/replace blind. All 3 now use a
   `${GATEWAY_APPS_DOMAIN}` placeholder, substituted via the new `gateway/openshift/deploy-core.sh`
   (auto-detects the domain via `oc get ingresses.config.openshift.io cluster`, or accepts an explicit
   override).
2. **Keycloak Postgres PVC**: `keycloak-postgres` Deployment in `keycloak.yaml` was ephemeral storage by
   design comment ("data lost on pod restart") -- this is exactly why every node/pod restart required
   re-running `configure-keycloak.sh` and re-syncing secrets cross-cluster. Added a 2Gi RWO PVC
   (`keycloak-postgres-data`), `strategy: Recreate` (required for RWO), and a soft node-affinity preference
   for control-plane nodes.
3. **Keycloak failover**: `mcp-keycloak` Keycloak CR raised `instances: 1 -> 2` with pod anti-affinity
   (`app: keycloak`, confirmed as the actual operator-applied pod label via live inspection) so one bad
   node can no longer take Keycloak to zero replicas. RHBK supports multi-instance clustering
   out-of-the-box (Infinispan-based session replication, Kubernetes-API peer discovery) against the single
   shared Postgres backend -- no extra config needed. Postgres itself remains single-writer/single-replica
   by design; the PVC protects data on reschedule but doesn't make Postgres itself HA.

**Still open, deliberately deferred** (user's explicit call, 2026-10-13: "UDR/NWDAF we can ignore for now
but keep a track of this issue"): gateway-mediated UDR and NWDAF MCP calls return 4xx even though direct
backend reachability has been confirmed working (this is distinct from the h2c/base-path backend bugs
fixed in the entry above, which were already resolved). `gateway/openshift/mcpsr-udr.yaml` and
`mcpsr-nwdaf.yaml` are structurally identical to the working registrations -- no distinguishing config
found, root cause not yet identified. Re-verify against the new cluster once it's up; don't assume a fresh
cluster fixes this on its own, since it looks gateway/auth-layer-specific rather than node/cluster-health
related.

**UPDATE 2026-10-14, re-verified on sandbox4001**: this was NOT a gateway/auth-layer bug. Direct
`tools/call` against the live gateway returns a clean `200`/`isError: false` for UDR -- the earlier
observed "4xx"/"cannot execute" symptom was actually the empty-subscriber-data gap (see this date's own
entry below) producing a `not_found` payload that the Agent then mis-reported as a tool-execution
failure, not a real gateway error. NWDAF was separately fixed via the h2c backport (2026-10-12 entry
above). Closing this as resolved -- no distinct gateway-layer bug was ever found because there wasn't
one.

**Resolved same day**: the user brought sandbox1330 back up specifically to recover this before deleting
it for good. `backends/openshift/nextgcore/buildconfig-nextgcore.yaml` + `deploy-build.sh` now commit both
BuildConfigs, live-tested end-to-end on sandbox1330 before it was decommissioned. Two non-obvious findings
from that test (both would have silently blocked the next migration otherwise):

1. A first attempt converted `nextgcore-builder` to a Git-sourced BuildConfig (simpler, no local clone
   step) -- it failed. `docker/rust/Dockerfile.builder` does `COPY nextgcore/src ...` *and*
   `COPY nextgsim ...`: it compiles NextGCore and its companion nextgsim simulator together from two
   sibling directories in the build context. A single-repo Git source can only ever produce one repo as
   the context root, so this layout is impossible to express that way. Reverted to Binary source
   (matching what originally worked), with the two-repo clone now scripted in `deploy-build.sh` instead of
   being a manual, undocumented step (it clones both `github.com/NextgCoreLab/{nextgcore,nextgsim}.git`
   into a temp dir as siblings, then `oc start-build --from-dir=<that dir>`).
2. `nextgcore-runtime`'s BuildConfig needs an explicit `dockerfilePath: Dockerfile.runtime` -- a single
   `oc start-build --from-file=Dockerfile.runtime` upload keeps its original filename in the build context
   rather than being renamed to `Dockerfile`, so the Docker strategy's default lookup fails with
   "no such file or directory" without this.

Verified the resulting `nextgcore-runtime-test` image actually contains the real NF binaries
(`nextgcore-amfd`, `nextgcore-ausfd`, etc.) via a throwaway pod, not just a structurally-valid build.

## 2026-10-13 -- sandbox3435 API server died outright; cut over to sandbox4001; then sandbox4001's Keycloak PVC fix backfired on its first real node failure

**sandbox3435 fully died, not just degraded**: mid-run, its API server became completely
unreachable (sustained TLS handshake timeouts across repeated attempts over 20+ seconds, not a
blip), on top of a worker node that had already been permanently `NotReady` for a day. Cut over to
sandbox4001 (a 5-node, 3-control-plane HA cluster stood up and fully verified as a standby earlier
the same day for exactly this scenario) -- updated `sdg_production_pipeline.py`'s `gateway_url`/
`keycloak_url` defaults, re-synced the Keycloak client secret, patched Langflow's flow JSON (same
gotcha as the sandbox1330->3435 cutover: it caches the MCP Tools URL independently of pipeline
params), repointed `mcp-token-refresher`, and resubmitted.

**Also raised `GENERATION_MAX_CONCURRENCY` 4 -> 8 at the same time**, paired this time with
`LANGFLOW_NUM_WORKERS` 4 -> 8 (the single-worker-process bottleneck from the first concurrency=8
attempt, see 2026-10-12 entry, is what's actually fixed now) and preemptive resource bumps on
Langflow, the sandbox4001 gateway (previously had zero resources set at all), and all 8 domain MCP
servers. This combination ran cleanly for ~3.5 hours (196-row `run_expert_trajectory` block, steady
pace, zero errors) before failing for an unrelated reason (below) -- concurrency=8 itself appears
genuinely fixed this time, not just not-yet-triggered.

**Then a different node on sandbox4001 (a control-plane node, `ip-10-0-48-127`) went NotReady**,
and this time it stranded `keycloak-postgres` rather than Keycloak itself -- `Multi-Attach error`
on the RWO PVC added earlier that same day specifically to fix the ephemeral-storage problem. The
PVC fix traded one failure mode for a worse one: before it, a node death just meant Postgres
restarted with empty (expected-to-be-empty) storage; after it, a node death leaves the EBS volume
genuinely stuck attached to the dead EC2 instance at the AWS API level (`VolumeInUse` on
`AttachVolume`, confirmed via `oc describe pod` events, not just a Kubernetes-level stuck object --
force-deleting the pod and the `VolumeAttachment` object did not help, since neither actually
reaches AWS's `DetachVolume` call when the source node is unreachable to confirm the unmount).
Fixing this properly requires an actual `aws ec2 detach-volume --force` call against sandbox4001's
AWS account -- not available in this session (only sandbox2667's AWS credentials are configured
here). Worked around it instead by abandoning the stuck PVC/volume entirely (delete PVC with
finalizers force-removed, recreate from the same committed manifest, which provisions a brand-new
EBS volume rather than reattaching the stuck one) and re-running `configure-keycloak.sh` -- same
realm-loss tradeoff as the original ephemeral-storage problem the PVC was meant to fix, but at
least self-service without needing AWS access.

**Residual risk, not yet fixed**: `keycloak-postgres` is still a single-replica, single-writer
component with no real HA story -- the PVC protects data on a *clean* reschedule but makes a *dirty*
one (node genuinely dies/goes unreachable) worse, not better, because of RWO's stuck-attachment
failure mode. A real fix needs one of: AWS credentials in-session to force-detach when this
recurs, a `ReadWriteOncePod` + faster eviction toleration (doesn't fix the AWS-level stuck
attachment, only how fast Kubernetes notices), or moving off a single Postgres pod entirely (a real
HA Postgres operator, out of scope for this project's sandbox-only use). Whoever hits this again
should go straight to "delete and recreate the PVC" rather than trying to force-fix the stuck
attachment from inside the cluster -- that was a dead end here.

## 2026-10-13 -- Langflow's Agent component needs VLLM_API_KEY/VLLM_API_BASE as real pod env vars, not a flow-level credential

Migrating Langflow to Postgres (previous entry) surfaced a second, unrelated gap: after the fresh
DB came up, the flow's own `Agent` node started hitting the real `platform.openai.com` with an
empty/wrong API key instead of the self-hosted vLLM/Gemma model. Root-caused by directly inspecting
this Langflow version's Postgres schema (newer than expected -- has a `model_provider_policy`/
`catalog_policy_rule`/`deployment_provider_account` system layered over the classic `variable`
table, none of which turned out to be where this particular field's value comes from):

The Agent node's `model` field selects a catalog entry (`provider: vLLM`, `name:
redhataigemma-4-31b-it`) whose metadata declares `api_key_param`/`base_url_param`, but the actual
connection values are NOT stored per-flow, per-variable, or in any of those policy tables (checked
`deployment_provider_account` directly -- 0 rows, and its enum only supports `watsonx-orchestrate`,
a red herring). The field's own UI description was the actual answer: "Falls back to the
VLLM_API_KEY environment variable (optional for local servers)" -- meant literally. Setting
`VLLM_API_KEY` (from the `maas-rhdp-api-key` Secret, same one the KFP pipeline tasks already use)
and `VLLM_API_BASE` as real env vars directly on the `langflow-service` StatefulSet, with the flow's
own `api_key`/`model.value[0].base_url` fields left genuinely empty, fixed it immediately --
confirmed via a direct `/api/v1/run/{flow_id}` smoke test getting a real response from
`redhataigemma-4-31b-it` before trusting it with a full pipeline run.

Two wrong turns before finding this, each worth avoiding next time: (1) directly setting a literal
`api_key` value in the flow's own JSON via PATCH -- this appeared to work once, then silently
reverted to the OpenAI fallback on the next build, suggesting the raw template value isn't what
actually gets read at run time for this field type; (2) injecting a `base_url` key into
`model.value[0]`/`model.options[0]` matching the metadata's declared `base_url_param` name -- also
silently ignored. Trust the field's own documented fallback behavior before reverse-engineering the
DB schema.

**Not yet known**: whether `VLLM_API_KEY`/`VLLM_API_BASE` were already set on `langflow-service`
before today (they weren't present when checked, yet the identical flow ran successfully for 3.5
hours earlier the same day) or whether something else about the pre-migration SQLite-backed instance
resolved this differently. Not investigated further since the current fix is confirmed working and
this StatefulSet isn't a committed manifest in this repo (Helm-installed, live-patched throughout
today) -- if `langflow-service` is ever recreated from the Helm chart fresh, remember these two env
vars are required and won't come from the chart's own defaults.

## 2026-10-13 -- Gemini Developer API backend (Vertex AI Beta) had a sustained 503 outage window

Run `dnmnd` (resubmitted after the checkpoint-recovery fix below) failed with `litellm.
MidStreamFallbackError: litellm.ServiceUnavailableError: Vertex_ai_betaException - ... "code": 503,
"message": "The service is currently unavailable."` on `score_question_quality`. Confirmed
`flow-training.yaml`'s `model_config.model` is still correctly `gemini/gemini-3.8-flash` (not
reverted to `vertex_ai/...`) -- LiteLLM's `gemini/` provider apparently routes through a
`vertex_ai_beta`-named backend internally regardless, so this exception class naming doesn't
indicate an auth/config regression. 17 occurrences of this error in one run's log -- a sustained
Google-side outage/overload window during this run, not a single transient blip. Nothing actionable
on our end; this is the real-world first hit of the "unverified Gemini API rate limits/reliability at
scale" risk flagged in `04-SCALE-UP-PLAN.md`. Retried (per standing user instruction) with no code
change for this specific failure. If this recurs frequently at higher volume, worth adding
LiteLLM-level retry/backoff specifically for 503s rather than letting it kill the whole tier attempt.

Same resubmit also confirmed the vLLM router-scheduler pod restart (tried as a cheap fix for the
4001m-vs-135m CPU imbalance between the 2 `redhataigemma-4-31b-it` replicas, see scale-up plan) did
**not** fix it -- re-measured post-restart at 3999m vs 124m, essentially unchanged. The cheap fix
didn't work; the scale-up plan's harder options (investigate the EPP scheduler's actual routing
logic/config, or accept ~1x effective capacity from the 2 replicas) are the remaining paths.

## 2026-10-14 -- CAMARA Device Status seeds used the wrong parameter name (device_id vs device_phone_number)

Before resubmitting after today's fixes, tested the remaining untested single_tool scenarios directly
against the live Agent (same method that already caught the TMF628 and materialize_seeds bugs). UDR
and `single_check_roaming_status` both came back "I cannot execute this tool" even after an explicit
prior-turn tool-selection confirmation. Direct `tools/call` straight at the gateway (bypassing
Langflow/Agent entirely) isolated it immediately: `devicestatusget_roaming_status`,
`_reachability_status`, and `_connected_network_type` all require `device_phone_number` in their real
`inputSchema` -- `seed-scenarios.yaml` declared `device_id` with values like `ue-001`, which the tool
rejects with a Pydantic `missing_argument` error. Not phone-number-shaped at all, so even the
`mcp_server_description` grounding text was steering question generation wrong independent of the
validation error. Fixed all 3 `single_check_*` scenarios to use `device_phone_number` with
`+1555000100x`-style values, confirmed live against the real tool
(`devicestatusget_roaming_status` with `+15550001000` now returns real
`{"roaming": true, "countryCode": 901, ...}` data, not a validation error). The multi-tool scenarios
referencing these tools (`parallel_roaming_and_location`, `sequential_alarm_to_roaming_check`, both
closed_loop device scenarios) don't declare a `parameters` block for this field, so they weren't
affected.

## 2026-10-14 -- UDR had zero provisioned subscribers on sandbox4001 (known risk from Phase 6, materialized)

Same "confirm nothing else is missing" pass: `udrget_authentication_subscription` executes cleanly
(`200`, `isError: false`) but returned `{"status": "not_found"}` for both seed IMSIs. Checked the
backing MongoDB directly (`mongosh` into the live pod) -- no NextGCore subscriber database at all, just
the default `admin`/`config`/`local` system DBs. This is exactly the risk `06-RESEARCH.md` flagged when
UDR was first built: the test subscriber (`imsi-999700000000001`) was provisioned via `nextgcore-webui`
against the *previous* cluster's MongoDB, and that data doesn't survive a cluster cutover (the
sandbox3435->sandbox4001 move today wiped it, as anticipated).

Re-provisioned on sandbox4001 using the documented procedure: ran `nextgcore-webui` (bundled in the
`nextgcore-runtime` image, never deployed as a standing service) as a throwaway pod with
`--insecure-dev --listen 0.0.0.0 --db-uri mongodb://mongodb.otel25-backends.svc.cluster.local:27017`
(note: the flag is `--db-uri`, not `--mongo-uri` as the narrative docs implied -- confirmed via
`--help`; also confirmed `--db-name` defaults to `nextgcore`, matching what the UDR itself reads, not
`open5gs`). The exact `POST /api/subscribers` payload shape was never actually committed anywhere
(06-01/06-03 only narrated that it worked), so re-derived it live via the same schema-probing-by-error
technique used for TMF628 earlier today: `{"imsi": "<5-15 raw digits, no "imsi-" prefix>", "security":
{"k": "<32-hex permanent key>", "opc": "<32-hex operator key>"}}` -- `amf`/`sqn` default to `8000`/`0`.
Provisioned both seed IMSIs (`999700000000001`, `999700000000002`), verified end-to-end through the
real gateway: `udrget_authentication_subscription` now returns genuine 3GPP-structured data
(`authenticationMethod: 5G_AKA`, `encPermanentKey`, `encOpcKey`, `sequenceNumber`, etc.) for both,
cleaned up the throwaway pod after.

**Generalizes**: any subscriber-backed data (UDR, and anything else that reads from this same Mongo)
does NOT survive a cluster cutover/rebuild, since the data lives only in a PVC that isn't part of any
committed manifest or backup. If a future cluster migration happens again, re-run this same
`nextgcore-webui` provisioning step before trusting UDR-dependent scenarios -- it is not optional
infra, it's seed data the pipeline silently degrades without (a clean `not_found` response, not an
error, so nothing fails loudly if this is skipped).

## 2026-10-14 -- Resubmitted pipeline failed on a recurring node NotReady; added a real MachineHealthCheck

Resubmitting after the day's accumulated fixes (`q6lrh`) immediately hit the same node class of
failure from earlier today: `ip-10-0-56-33` on sandbox4001 went `NotReady`
("Kubelet stopped posting node status"), confirmed via AWS as a pure kubelet hang (all instance
status checks `ok`/`passed`), not an infra failure. Fixed the same way as before
(`aws ec2 reboot-instances`, OS-level soft reboot, no Node/Machine object touched).

Investigated afterward why this needed manual intervention at all: it turns out most of it didn't --
Kubernetes' default `node.kubernetes.io/not-ready:NoExecute` taint + each pod's default 300s
toleration already evicted and rescheduled every affected Deployment-managed pod within ~5 minutes,
automatically, before any manual investigation started (confirmed via timestamps: node NotReady at
04:59:49 UTC, gateway's own "8/8 servers healthy" log at 05:05:13 UTC). What Kubernetes never does is
heal or replace the dead node itself -- it only evacuates workloads from it. The cluster's only
pre-existing MachineHealthCheck (`machine-api-termination-handler`, an OpenShift default) turned out
to be scoped to spot-instance interruption handling only (`machine.openshift.io/interruptible-instance`
selector) and was never watching general node-health conditions at all (`expectedMachines: 0`) --
there was no automated remediation path for this exact, now-recurring failure mode.

Added `cluster/openshift/machinehealthcheck-worker-nodes.yaml`: a new MHC scoped to worker-role
machines only (excludes the 3 control-plane nodes -- auto-remediating a control-plane machine risks
etcd quorum, a different and higher-blast-radius problem), triggering on `Ready=Unknown` or
`Ready=False` for 300s (matching the exact signal hit twice), with `maxUnhealthy: 1` out of the pool's
2 machines (so remediation proceeds for an isolated failure but is withheld if both go unhealthy at
once, which more likely means a cluster-wide problem deserving a human, not a MHC-level disaster
double-remediation).

Deliberately did NOT make this a reusable "slap on every MachineSet" pattern: default MHC remediation
deletes the Machine and lets the MachineSet provision a replacement EC2 instance -- a full replace,
not an in-place reboot. That's safe for sandbox4001's worker nodes (`m6a.4xlarge`, a general-purpose
type with ample capacity) but would be a real risk on sandbox2667's GPU nodes
(`g6e.12xlarge`/`g5.12xlarge`), which this project has already hit genuine
`InsufficientInstanceCapacity` errors for (04-SCALE-UP-PLAN.md) -- replacing one of those and failing
to get a new one back would net-lose GPU capacity, worse than leaving a hung-but-still-present
instance for a manual reboot. Any future MHC for GPU-bearing MachineSets needs that capacity risk
re-evaluated first, not copied blindly from this one.

Verified live: `currentHealthy: 2`, `expectedMachines: 2`, `remediationsAllowed: 1`,
`RemediationAllowed: True` immediately after applying.

## 2026-10-14 -- nextgsim is a permanent dead end: AMF's NGAP server never actually binds

User asked to finish the nextgsim (UE/gNB traffic simulator) deployment left pending from earlier
today, with an explicit instruction to plan carefully so it doesn't overload sandbox4001 and risk
the then-running pipeline (`qcq4k`). Investigating live cluster state before writing a deployment
plan (rather than just writing manifests from the Dockerfile fix alone) surfaced a hard blocker
that makes the entire deployment pointless, independent of any resource/SCC/networking planning.

**Confirmed live, not inferred**: AMF's own config file (`oc exec` into the live `amf` pod,
`cat /etc/nextgcore/amf.yaml`) explicitly declares `ngap.server: address 0.0.0.0, port 38412` --
the binary is configured to listen for NGAP, the protocol a gNB uses to register with AMF over the
N2 interface. But `ss -tln` inside that same live pod shows only `127.0.0.1:7777` (the SBI/HTTP
port) actually bound -- nothing is listening on 38412 at all. The container spec even declares
`containerPort: 38412` with `protocol: TCP` (itself wrong -- real NGAP runs over SCTP, not TCP),
but that's moot since nothing is listening there regardless of protocol.

This is the same class of bug already documented for this NextGCore dev-profile build elsewhere in
this project: AMF's SBI binding to `127.0.0.1` despite its config declaring `0.0.0.0` (06-01-PLAN.md),
and NRF's self-registration advertising `0.0.0.0` as every NF's own address (06-01-PLAN.md). A
consistent pattern of this build declaring full config that isn't actually wired up end to end.

**Consequence**: no gNB -- real or simulated via nextgsim -- can register with this AMF. The N2
socket simply isn't open. No amount of correct nextgsim config, SCC setup (a working
`NET_ADMIN`-granting SCC pattern already exists and was ready to reuse, see `nextgcore-upf`'s
ServiceAccount/SCC binding), or careful node placement changes this. Deploying nextgsim as
originally scoped would have consumed real cluster resources for a guaranteed connection-refused
failure at the very first step (gNB-to-AMF registration), before any traffic could ever reach
NWDAF.

Presented this to the user with three options (abandon and document; dig into NextGCore's Rust
source to fix AMF's NGAP binding; look for an alternate NWDAF data-ingestion path bypassing
AMF/gNB entirely). **User chose to abandon**, consistent with this project's own prior precedent --
Phase 6 made the identical call to skip AMF/UDM entirely after hitting comparable unfixable
upstream bugs with no viable workaround found.

**This closes out the nextgsim gap permanently** for this NextGCore deployment: NWDAF will keep
returning `no_content` for every real query (NF_LOAD included) until a non-dev-profile NextGCore
build is used, or AMF's NGAP server is fixed upstream -- neither of which is in scope for this
project. Future sessions should not re-attempt this without a materially different starting point
(a different NextGCore build, or a decision to patch the Rust source directly).

**Separate, unrelated finding from the same investigation, worth flagging even though it didn't
end up mattering here**: sandbox4001's 2 true worker nodes are badly imbalanced right now --
`ip-10-0-38-208` sits at 96% CPU request utilization and hosts essentially the entire pipeline
dependency chain (all 9 NextGCore NFs, all 8 Prism mocks, the MCP Gateway, Keycloak, most MCP
domain servers), while `ip-10-0-56-33` (the node that failed and was rebooted earlier today) sits
at only 12%, nearly empty -- Kubernetes doesn't proactively rebalance already-running pods back
onto a node once it recovers. Not acted on since it wasn't needed for this task, but relevant
context for any future deployment decision on this cluster.

## 2026-10-14 -- WASM-plugin fetch race recurred; root-caused and auto-remediated

`ip-10-0-56-33` (sandbox4001) failed a second time -- same "kubelet stopped posting node status"
class as the first incident. This time the MachineHealthCheck added earlier today handled it fully
autonomously: detected it, deleted the Machine, and the MachineSet provisioned a replacement
(`ip-10-0-9-160`) with no manual intervention. Confirms the MHC works as designed.

The freshly-rescheduled `mcp-gateway-istio` pod hit the same Envoy WASM-plugin-load race from
earlier today again (`Plugin kuadrant-wasm-shim failed to load`, fail-closed, every request 503s).
Root-caused properly this time instead of just restarting it: the plugin is fetched remotely at
Envoy startup from `kuadrant-operator-wasm.openshift-operators.svc.cluster.local:8082/plugin.wasm`
(10s timeout, `failure_policy: FAIL_RELOAD`, configured in the `kuadrant-mcp-gateway` EnvoyFilter --
owned by the `mcp-gateway` Gateway resource, reconciled by the Kuadrant operator, not something we
can safely hand-edit). Checked `openshift-operators`: `kuadrant-operator-controller-manager`
(which serves that endpoint) was *also* only ~19 minutes old at the time -- it got caught in the
same node-failure disruption cascade. Two things that depend on each other both restarting at once.
`FAIL_RELOAD` does not mean "retry on a timer" -- it means "reload on explicit trigger", so without
a pod restart the gateway would have stayed 503ing indefinitely once this race was hit, confirmed
by it not self-recovering in the ~15min window observed.

Investigated a kubelet-native fix first (a `livenessProbe` catching this so Kubernetes restarts the
pod itself, no custom component needed) -- rejected because `mcp-gateway-istio`'s Deployment is
owned by the `mcp-gateway` Gateway resource and continuously reconciled by Istio's Gateway API
controller; a direct probe edit would very likely be silently reverted, same pattern already hit
with Keycloak's hostname and this same EnvoyFilter. Built `gateway/openshift/wasm-healer-cronjob.yaml`
instead: a CronJob every 2 minutes that checks the gateway's real `/mcp` `initialize` response, and
only restarts `mcp-gateway-istio` if it's actually failing AND the specific WASM-load log signature
is present (avoids blindly restarting on an unrelated 503 cause). Verified live via a manual
`oc create job --from=cronjob/...` run -- correctly no-opped while the gateway was healthy.

**Separate, deliberately-not-fixed finding from this same incident**: a 93-minute pipeline retry
attempt (`gpv2v`) got through 19 of 20 `run_expert_trajectory` agent calls for one seed
(`multiply_tool_rows` expands one seed into 20 variations) before the gateway 503 killed the 20th.
Checked `sdg_hub.core.flow.execution._process_with_checkpointing` directly (installed
`sdg-hub==0.9.4` package): checkpointing commits per *original seed*, via
`checkpointer.add_completed_samples(processed_chunk)` -- called only after `execute_blocks_on_dataset`
returns for the *whole* chunk. Since all 20 of a seed's multiplied variations run inside that one
`execute_blocks_on_dataset` call, a failure on variation 20/20 means the exception propagates before
checkpointing is ever reached, discarding all 19 already-completed, already-paid-for agent calls
(~70+ minutes of real LLM/Agent work) -- not a resume/retry bug (those worked exactly as designed,
correctly resuming from the last *actually saved* checkpoint), but a genuine granularity mismatch
between where `sdg_hub` checkpoints (per seed) and where the expensive, fragile work actually happens
(per multiplied sub-row). This is third-party `sdg_hub` internals, not this project's own code.
User's explicit call: accept and document rather than patch now, since MHC + the WASM auto-healer
above should reduce *how often* a gateway outage interrupts a `run_expert_trajectory` batch in the
first place, which is the actual trigger for this failure mode. If this keeps costing significant
wall-clock time going forward, the two live options are (a) lower `multiply_tool_rows.num_samples`
to shrink the blast radius of any single late failure, or (b) patch `_process_with_checkpointing`
(or wrap `execute_blocks_on_dataset`) for sub-row checkpointing -- same class of effort as today's
other `sdg_hub` monkey-patches but touches the core execution loop, not a single Block, so needs
more care/testing.

## 2026-10-14 -- fourth sandbox4001 node failure traced to a genuine memory leak; built a watchdog

A fourth node failure in one day -- this time the very node the MachineHealthCheck had provisioned
just 3 hours earlier to replace the first failure. User asked directly why this keeps happening on
sandbox4001 and not sandbox2667, and to look for AWS-side tooling to find the actual cause.

**Confirmed, not speculation**: checked AWS instance status for all 4 failed instances -- every
single one reports `ok`/`passed` on every check (reachability, system, EBS). This was never a
hardware/EC2 failure. Pulled Prometheus history for the 4th node before it went dark (the only
reason this was possible: node-exporter kept scraping right up to near the end, unlike `oc debug
node`, which couldn't even schedule a pod onto the node by the time anyone looked):
`node_memory_AnonPages_bytes` (true process memory, not reclaimable cache) went from 12.76 GiB to
52.95 GiB in 10 minutes, while `MemFree` crashed to near-zero. Checked every individual container's
memory on that node in the same window (all flat or decreasing), `kubelet.service`,
`crio.service`, `ovs-vswitchd.service`, and the whole `system.slice` (all small, all flat, combined
under 1.2 GiB) -- none of it explains where 40+ GiB went. Checked conntrack table size (~1,500
entries, nowhere near exhaustion) to rule out a connection-tracking leak. Cross-checked with basic
(no-agent) EC2 CloudWatch metrics: CPU jumped from an ~8% baseline to 40-53% in the exact same
window, then network throughput collapsed as the node died -- consistent with a process actively
busy-looping while allocating (a crash-restart-and-leak-more cycle, or a retry storm), not a slow
idle leak.

**What AWS-side tooling could NOT provide**: checked for the CloudWatch agent (`CWAgent` metrics
namespace -- empty, never installed) and SSM Session Manager (`describe-instance-information` --
empty, no instances registered). Neither exists on these RHCOS nodes, so there was never an
AWS-level memory metric stream, and there's no shell path into a node that's independent of
kubelet's own health -- exactly the thing failing. AWS Health events: nothing relevant (only old,
unrelated-region entries).

**Root cause of the actual process/subsystem responsible is still not identified** -- that needs
live `dmesg`/process-level data from the moment it's happening, and by the time anyone notices, the
node is too far gone for `oc debug node` to schedule a pod (confirmed live, twice) or for MHC's
remediation (which deletes and replaces the Machine) to leave anything behind to examine.

**Built `cluster/openshift/memory-watchdog.py` + `memory-watchdog-daemonset.yaml`** to catch this
proactively next time: a DaemonSet on every node (not just workers -- one of the 4 failures hit a
control-plane node) polling `/proc/meminfo` every 15s. Uses `hostPID: true` only -- no hostPath
mounts of `/proc` or `/dev` -- confirmed live via a throwaway test pod that with hostPID, the
container's own already-present `ps`/`dmesg` binaries transparently reflect the host, which is a
narrower SCC surface than hostPath mounting host filesystems directly. On detecting the confirmed
signature (AnonPages growing >=5GiB within 60s, or available memory dropping below 15%), it
captures `ps aux --sort=-rss` and `dmesg -T` and writes them into a ConfigMap, not a local file or
`oc logs` -- both of the latter live on/through the dying node, exactly what's unavailable once a
node is too far gone. ConfigMaps live in etcd, replicated across control-plane nodes, so they
survive the node being fully replaced afterward. Verified live: all 5 pods `1/1 Running`, correctly
reading real host meminfo (confirmed against a known-healthy node's actual values), and the
ConfigMap-write path (RBAC + `oc apply` from inside the pod) verified end-to-end with a manual test
write before relying on it for a real trigger.

Custom SCC (`memory-watchdog`, `allowHostPID: true`, capabilities limited to `SYS_PTRACE`+`SYSLOG`,
not full `privileged`) -- deliberately narrower than `nextgcore-upf`'s or `privileged`'s blanket
grants, since this only needs to read `/proc` and the kernel ring buffer, not create network
devices or modify the host.

## 2026-10-14 -- actually found and fixed the memory leak: a real bug in mcp-telecom

User suggested investigating from the angle of "which tool calls were happening" rather than
waiting on the watchdog, and to cross-reference against the measured leak windows. This found and
fixed the real root cause within about 30 minutes, no watchdog trigger needed.

First narrowed the suspect list across every component with no memory limit set (since any
component *with* a limit would get OOM-killed by Kubernetes long before contributing tens of GiB --
confirmed via `oc get deploy -o json` scan across every namespace): `authorino`, `clabernetes-
manager`/`ui`, and `mcp-telecom-basic-r1/r2/r3` (the Clabernetes-managed Nokia SR Linux routers --
real commercial network OS, not a lightweight simulator). Checked each one's Prometheus memory
history over the full ~24h cluster lifetime: `authorino` and `clabernetes-manager`/`ui` were flat
and tiny (under 260 MiB) despite having no limit -- ruled out. `mcp-telecom-basic-r1/r2/r3` showed a
clear, reproducible signature: ~150-230 MB/hour **linear** growth, confirmed across multiple
independent pod restarts throughout the day, all three growing in lockstep in the same windows
(e.g. 05:33-09:33: r1 667->1595 MiB, r2 782->1589 MiB, r3 1026->1681 MiB). Confirmed they run
`privileged: true, runAsUser: 0` (needed for the network-namespace/veth manipulation SR Linux
requires inside Clabernetes) -- plausibly why the leak showed up as unattributed host-level
AnonPages rather than any container's own cgroup memory in the earlier investigation.

Added a memory limit (2Gi, via the `Topology` CR's `spec.deployment.resources.default` -- the
Deployments are CR-owned/reconciled, a direct `oc patch` would've been silently reverted, same
mistake already made once today with `mcp-gateway-istio`) as a safety net. But then found the actual
root cause: checked `mcp-telecom`'s own pod logs around the clearest leak window (16:45-17:00) and
found a **tight, continuous retry loop** -- a new paramiko SSH connection to all 3 routers every
15-20 seconds, non-stop, for 9+ hours (213 occurrences logged, 08:07:56 to 17:35:46, still ongoing
as it was found). Every single call to the `parallel_operation` tool crashed with
`AttributeError: 'str' object has no attribute 'success'` in `mcp_telecom/parallel.py`'s
`format_parallel_results()`.

**Root cause, 100% reproducible, confirmed via source read**: `server.py`'s `parallel_command` and
`parallel_operation` tool functions call `ParallelExecutor.run_on_all()`/`run_operation_on_all()`,
which returned `dict[str, str]` (already-unwrapped output/error strings) -- but then pass that
straight into `format_parallel_results()`, which requires `dict[str, DeviceResult]` (it reads
`.success`/`.error`/`.elapsed_ms` off each value). Every call to either tool was guaranteed to
crash, with zero exceptions. Confirmed via repo-wide grep that nothing else calls these two
methods, so the type mismatch had never been caught by any test (`test_parallel.py` tested
`run_on_all` and `format_parallel_results` in isolation, never together -- the actual integration
that was broken).

**This wasn't Agent/pipeline-driven** -- `parallel_operation` isn't even in the MCP Gateway's
externally-exposed `tools/list` (84 tools, no "parallel" entries). The calling IPs during the
leak window belonged to `mcp-gateway` and `mcp-gateway-istio` themselves: the gateway's own
periodic upstream-tool health-check/validation pass was hitting this (permanently broken) tool
and retrying on failure, independent of whether the SDG pipeline was even running -- consistent
with the leak's 9+ hour continuous span crossing multiple separate pipeline run attempts.

**Fix**: changed `run_on_all`/`run_operation_on_all` to return `dict[str, DeviceResult]` directly
(matching what `format_parallel_results()` actually needs) instead of pre-unwrapping to strings --
`mcp/mcp-telecom/src/mcp_telecom/parallel.py`. Added two regression tests exercising the actual
`run_on_all(...)` -> `format_parallel_results(...)` pipeline end-to-end (the integration that was
broken), including one for `run_operation_on_all` specifically since it had zero prior test
coverage despite being the exact method crashing live. All 190 `mcp-telecom` tests pass. Rebuilt
(`mcp-telecom` BuildConfig, binary build from `mcp/mcp-telecom/`) and rolled out; confirmed live:
zero `parallel_operation` errors and zero new SSH connections in the 30s following the restart
(previously constant every 15-20s), and a direct `tools/call` test against the gateway returns a
real result instead of the AttributeError.

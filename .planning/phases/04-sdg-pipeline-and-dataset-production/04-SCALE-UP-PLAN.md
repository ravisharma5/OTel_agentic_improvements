# SDG Pipeline Scale-Up Plan: 10,000 Samples by 2026-10-18

**Written:** 2026-10-13, with run `rmkn2` live on sandbox2667 as calibration data (concurrency=8,
`LANGFLOW_NUM_WORKERS=8`, per-row checkpointing, Postgres-backed Langflow, vLLM Agent fix all
active -- see 04-LEARNINGS.md's 2026-10-13 entries for what those fixes were).

## 1. Target vs. honest current trajectory

**Target:** 10,000 final delivered examples by 2026-10-18 (5 days from today).

**Bottom line: not realistic at current throughput and yield rates, by a wide margin -- roughly
4x short even under perfect, incident-free continuous execution.** The gap isn't a tuning problem,
it's a raw-throughput problem. Numbers below.

### What "examples_generated" actually means (verified, not assumed)

Checked `deliverables/2026-10-10-first-full-run/tool_coverage_report.json` against the actual
delivered files: the sum of all scenarios' `examples_generated` (106) exactly equals the line count
of `single-turn.jsonl` (106). This confirms `examples_generated` is the **final, fully-filtered,
delivered count** per scenario -- not a raw pre-filter number. The yield rates below are therefore
true end-to-end (seed -> delivered example) rates, which is good: it means the math doesn't need an
extra, unknown "final evaluation filter" discount layered on top.

### Yield rates (only real data point we have)

From that same report (12 scenarios, `multiply_tool_rows.num_samples=20`, no closed_loop
scenarios present at all that run):

| Tier | Yield / scenario (out of 20) | Rate |
|---|---|---|
| single_tool | 11.0 | 55% |
| parallel | 8.3 | 42% |
| sequential | 2.5 | **12.5%** (unexplained -- see Risks) |
| multi_turn | 10.0 | 50% |
| closed_loop | 0 (0 scenarios ran) | **unknown** -- this is the tier whose tool-coverage bug was fixed earlier today; genuinely untested at any scale since |

Applying these rates to today's 30 scenarios (11/5/6/3/5) at `num_samples=20` (today's actual
config) projects **~220-260 final examples per full run** -- consistent with the separate estimate
already given to the user before this investigation. That's the current trajectory baseline.

### The scaling math to reach 10,000

If yield scales linearly with `multiply_tool_rows.num_samples` (optimistic assumption -- see
Risks, this likely has diminishing returns at high N from duplicate/low-diversity sampling),
reaching 10,000 at the blended ~33% average yield rate requires:

```
10,000 / (30 scenarios x 0.33 avg yield rate) ~= N=1,010
```

That's a **~50x increase** over today's `num_samples=20`, i.e. ~30,300 raw seed-expansions to
process (30 scenarios x 1,010).

### Throughput reality check

Two numbers, both from live observation today, not estimates:
- **Live run `rmkn2`**, `run_expert_trajectory`, concurrency=8: steady **~29s/iteration** in the
  tqdm progress bar.
- **Earlier today's run** (`single_tool` tier, same concurrency=8, 189-196 rows): took **~3.5
  hours** end to end, i.e. **~64-67s/row** of real wall-clock time per completed row once all
  overhead (queueing, retries, checkpointing) is baked in. This is the more trustworthy number for
  projecting total run time, since it's a measured full-tier result, not an instantaneous
  progress-bar snapshot.

At ~65s/row wall-clock:
- 30,300 raw rows x 65s = **1,969,500s ~= 547 hours ~= 22.8 days** of continuous, uninterrupted
  generation -- against a 5-day (120-hour) budget. **Roughly 4.5x over budget even before counting
  any infra incidents**, and this project has hit a real infra incident requiring hours of recovery
  on 3 separate clusters today alone.
- In the actual 120-hour budget at today's measured pace: **~1,850 raw rows achievable**, projecting
  to roughly **600-700 final examples** at the blended yield rate -- nowhere near 10,000.

## 2. Current verified headroom (what was actually checked, live, today)

| Component | Verified utilization | Headroom |
|---|---|---|
| MCP Gateway broker (sandbox4001) | 2m CPU / 70Mi (limits: 2 CPU/2Gi) | Enormous -- not a constraint at any concurrency tested so far |
| 8 domain MCP servers (sandbox4001) | 2-3m CPU / ~210Mi each (limits: 1 CPU/1Gi each) | Enormous -- not a constraint |
| Langflow pod (sandbox2667) | 31m CPU / 1.6Gi (limits: 8 CPU/12Gi) | Large headroom even at concurrency=8 |
| langflow-postgres | 1m CPU, 11/300 connections | Essentially unused -- not a constraint |
| **vLLM replica 1** (`...-jwg67`) | **3,347m CPU / 4000m limit (84%)** | **Near-saturated** |
| **vLLM replica 2** (`...-rvfxv`) | **129m CPU / 4000m limit (3%)** | **Nearly idle** |

### The single biggest finding: vLLM load is badly imbalanced across its 2 replicas

Confirmed live, twice, 15 seconds apart (not a one-off blip): one of the two vLLM replicas is
doing essentially all the work (84% CPU) while the other sits nearly idle (3%). This is NOT a
capacity problem -- it's a **routing/scheduling problem**. The `LLMInferenceService` uses an
llm-d EPP (Endpoint Picker Provider) scheduler with a latency-predictor config
(`v3-5-1-kserve-config-llm-scheduler-latency-predictor`), not naive round-robin -- something in
that scheduling decision is concentrating load on one replica instead of spreading it. The
router-scheduler pod also shows 1 restart, which may or may not be related.

**This means today's "2 vLLM replicas" are functioning as roughly 1x effective capacity.** Fixing
the load balance (not yet root-caused -- out of scope for this read-only investigation) is very
likely the single cheapest, highest-leverage throughput improvement available: potentially ~2x
effective vLLM throughput with zero new infrastructure, zero new GPU capacity, zero cost.

### GPU capacity (checked, not tested further -- see Risks)

Both current GPU nodes are fully allocated to the 2 existing vLLM replicas (4 GPUs each, exactly
matching `tensor-parallel-size=4`):
- `ip-10-0-48-113` (g6e.12xlarge, 4/4 GPUs) -- MachineSet `cluster-qbq4v-gsd24-worker-us-east-2b-gpu-g6e.12xlarge`, currently 1/1
- `ip-10-0-63-12` (g5.12xlarge, 4/4 GPUs) -- MachineSet `cluster-qbq4v-gsd24-capacity-test-g5-12xl`, currently 1/1

Notably, **a g6e.12xlarge node is running successfully right now** (31h old) -- the same instance
family that hit `InsufficientInstanceCapacity` earlier in this project's history. This suggests
capacity for that family may be available again, but this was not re-tested live (scaling a
MachineSet is a real infrastructure change, out of scope for this read-only investigation). A
third MachineSet (`g6e.4xlarge`) exists at 0/0 -- smaller GPU count per node, not useful for a
tensor-parallel-4 deployment without re-architecting the serving config.

There is currently **zero spare GPU capacity** -- adding a 3rd vLLM replica (4 more GPUs) requires
scaling an existing MachineSet or creating a new one, which is a real cost/risk decision, not a
config change.

## 3. Specific changes needed, ranked by leverage/risk

| # | Change | Expected impact | Risk/cost | Validation status |
|---|---|---|---|---|
| 1 | **Root-cause and fix vLLM EPP scheduler load imbalance** | ~2x effective vLLM throughput, free | Low cost, but root cause genuinely unknown -- could be quick (restart router-scheduler) or could require llm-d config changes | **Confirmed problem exists; fix not yet identified** |
| 2 | **Raise `multiply_tool_rows.num_samples`** (20 -> some higher value) | Linear increase in raw volume | Compute-bound only, no new infra -- but see the "doesn't actually reach 10k" math above | Config-only change, easy to test incrementally |
| 3 | **Investigate sequential tier's 12.5% yield** | If a fixable bug (not inherent scenario difficulty), could ~4x that tier's output for free | Needs investigation time, not infra | Not investigated -- flagged as unexplained in the one data point available |
| 4 | **Validate closed_loop yield at scale** | Currently 0 scenarios of real data; today's fix (TMF628/device-inventory) needs a real multi-scenario test | None -- just needs a completed run to measure | Untested since the fix |
| 5 | **Add a 3rd vLLM replica** | +50% raw vLLM capacity (if replica #2 load-imbalance is also fixed, otherwise uncertain since #2 is already barely used) | Real AWS GPU capacity risk -- this project hit `InsufficientInstanceCapacity` repeatedly getting even 2 replicas | Not tested in this investigation (explicitly out of scope: scaling infra) |
| 6 | **Raise `GENERATION_MAX_CONCURRENCY` beyond 8** | More requests in flight -- but all headroom checks above show the bottleneck is vLLM compute, not request concurrency, so this alone won't help without fixing #1 or #5 first | Free to try, but likely no benefit until vLLM-side capacity increases | Not tested |

## 4. Recommended sequencing for the next 5 days

**Day 1 (today/tomorrow):** Fix #1 (vLLM load imbalance) first -- it's free and potentially doubles
everything else. Restart the router-scheduler pod as a cheap first attempt; if that doesn't resolve
it, investigate the EPP's latency-predictor config or file it as a known llm-d issue. Let the
currently-running `rmkn2` finish to get a real, current-config yield baseline (not the stale Oct 10
reference data) -- this matters because sequential's low yield and closed_loop's fix are both
unverified against today's actual pipeline.

**Day 2:** With real current-run yield numbers in hand, decide the actual achievable target for
this window (see Section 5) rather than continuing to chase 10,000. Raise `multiply_tool_rows` to
a value justified by the achievable-target math, re-derived from real (not Oct-10-extrapolated)
yield data. Investigate sequential tier's low yield if time allows -- cheapest non-infra lever
available.

**Days 3-5:** Run continuously at the revised target volume, using the per-row checkpointing added
today to survive any further infra incidents without losing progress (this is the main reason
today's checkpointing work matters for this timeline at all -- without it, any repeat of today's
multiple infra incidents would have cost full tier restarts, not just lost minutes). Only consider
a 3rd vLLM replica (#5) if Day 1-2 numbers show it's genuinely needed and GPU capacity testing
(a deliberate, approved scaling attempt, not a silent one) succeeds.

## 5. Open risks that could blow the deadline -- stated plainly

1. **10,000 by Oct 18 is not achievable at today's measured throughput, even with zero further
   incidents.** The math in Section 1 shows ~4.5x over budget in continuous compute time alone. This
   is the headline risk, not a tail risk -- a revised, explicitly-agreed target (likely in the
   600-3,000 range depending on whether #1's load-imbalance fix lands and how much the yield-rate
   assumptions hold) should replace 10,000 as the actual commitment, or the deadline should move.
2. **GPU capacity is not guaranteed on request.** This project has already hit
   `InsufficientInstanceCapacity` multiple times trying to get even 2 replicas running. Any plan
   banking on a 3rd+ replica must treat that as a real possibility, not an edge case.
3. **Gemini Developer API rate limits are completely unverified.** No 429s or rate-limit signals
   found in logs or history so far, but today's run has only processed a handful of rows at the
   question-generation/quality-scoring steps that call Gemini -- nowhere near the volume a 10x+
   scale-up would generate. This is an external dependency with no fallback currently wired in if
   it becomes a bottleneck.
4. **Sequential tier's 12.5% yield is unexplained.** Could be inherent scenario difficulty (then
   scaling won't fix it, more seed scenarios would) or a fixable bug (then it's free yield). Not
   knowing which makes the yield-rate math in Section 1 a real source of uncertainty in either
   direction.
5. **Closed_loop tier has zero real yield data post-fix.** The entire tier could come back at 0%
   (if the fix was incomplete), ~12.5% (sequential-like), or ~50% (like most other tiers) --
   a 4-5x swing in that tier's contribution to the total, and it's 5 of today's 30 scenarios.
6. **This project's infra has had a severe incident roughly every few hours today** (sandbox3435
   total death, sandbox4001 control-plane node loss, Postgres stuck-volume-attachment, Langflow
   Agent model misconfiguration). Even with checkpointing now in place to limit the damage, each
   incident still costs real wall-clock time to notice and fix, which the 5-day budget above does
   not account for.

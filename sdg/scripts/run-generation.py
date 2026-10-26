#!/usr/bin/env python3
"""Run sdg_hub MCP Server Distillation training flow for production dataset generation.

Includes automatic seed materialization from MCP Gateway tools/list and
lightweight resume tracking via a batch manifest so partial failures do
not restart from scratch.

Flow configs are loaded with os.path.expandvars() to expand env-var
placeholders (e.g. ${VLLM_API_KEY}, ${LANGFLOW_API_KEY}) that
yaml.safe_load() leaves as literal strings.

Usage:
    # Dry-run (10 examples for format validation -- D-19 gate)
    python -m sdg.scripts.run-generation --dry-run

    # Production run (all tiers, 8,500-14,000 examples)
    python -m sdg.scripts.run-generation

    # Resume a partial production run
    python -m sdg.scripts.run-generation --resume

    # Limit to specific tiers
    python -m sdg.scripts.run-generation --tiers single_tool,parallel

References:
    D-02:  mcp_distillation_training flow
    D-19:  Dry-run gate with Farbod's team
    SDG-01: Teacher model generates tool-calling examples
    SDG-02: Curriculum progression across 5 tiers
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# sdg_hub imports -- deferred to runtime so the script can be inspected
# without sdg_hub installed
try:
    from sdg_hub import FlowRegistry, Flow  # type: ignore[import-untyped]
    from sdg_hub.core.utils.error_handling import EmptyDatasetError
    from sdg.lib.streaming_llm_chat_block import patch_llm_chat_block_for_streaming
    from sdg.lib.debug_filter_rejections import patch_column_value_filter_for_diagnostics
    from sdg.lib.retrying_http_client import patch_http_client_for_5xx_retry

    # Swap every LLMChatBlock in any loaded flow for a streaming-aware one --
    # see streaming_llm_chat_block.py for why (AWS ELB idle-connection
    # timeout on long non-streaming generations, confirmed live). Must run
    # before FlowRegistry.discover_flows()/Flow.from_yaml() are called below.
    patch_llm_chat_block_for_streaming()
    # 2026-10-14: diagnostic patch added while investigating 10/11 single_tool
    # scenarios reproducibly failing filter_incomplete_responses -- see
    # debug_filter_rejections.py's module docstring. Logs rejected rows'
    # actual content (question, agent response, completeness rating) instead
    # of just a row/column count, which checkpointing can't surface since
    # filtered-to-zero rows never get checkpointed in the first place.
    patch_column_value_filter_for_diagnostics()
    # 2026-10-14: retry 5xx errors from AgentBlock's connector, not just
    # connection failures -- see retrying_http_client.py's module docstring.
    # Confirmed live: a single transient HTTP 500/503 (a node-failure
    # cascade, a WASM-plugin reload race) on the last of 20
    # run_expert_trajectory agent calls discarded all 19 already-completed
    # calls for that seed, repeatedly, because sdg_hub's existing retry
    # infrastructure never covered HTTP status errors at all.
    patch_http_client_for_5xx_retry()
    # 2026-10-19: one row whose agent call still fails after those retries
    # (e.g. context_length_exceeded) is dropped instead of aborting the whole
    # tier -- see agent_row_isolation.py's module docstring (Farbod's team's
    # fleet run verify1 lost multi_turn_P entirely this way; patch shared and
    # independently verified against sdg_hub==0.9.4 on 2026-10-26).
    from sdg.lib.agent_row_isolation import patch_agent_block_row_isolation
    patch_agent_block_row_isolation()
    # 2026-10-22: a checkpoint chunk filtered to zero rows is skipped instead
    # of aborting the whole attempt and stranding every later chunk's seeds --
    # see empty_chunk_isolation.py's module docstring (fleet run full1_p2/
    # single_P lost ~85 of 121 seeds this way).
    from sdg.lib.empty_chunk_isolation import patch_empty_chunk_isolation
    patch_empty_chunk_isolation()
    # 2026-10-26: registers ToolTraceRendererBlock/ToolNameCleanerBlock with
    # sdg_hub's BlockRegistry, used by sdg/flows/mcp_distillation_v2/flow.yaml
    # to give the response judge the tool trace (stock flow shows it only the
    # final answer -- see flow_blocks.py's module docstring).
    import sdg.lib.flow_blocks  # noqa: F401
except ImportError:
    FlowRegistry = None  # type: ignore[assignment,misc]
    Flow = None  # type: ignore[assignment,misc]

    class EmptyDatasetError(Exception):  # type: ignore[no-redef]
        """Placeholder so _run_generation's except clause is importable
        without sdg_hub installed; never actually raised in that case."""

from sdg.scripts.materialize_seeds import materialize_tool_seeds
from sdg.lib.trace_utils import DEFAULT_TRACE_COLUMN, row_passes_tool_coverage

logger = logging.getLogger(__name__)


# ─── Config Loading with Env-Var Interpolation ─────────────────────────────


import re

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")


def _expand_env_string(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} placeholders in a string.

    os.path.expandvars() does NOT support bash's ${VAR:-default} syntax --
    it only matches plain ${VAR}/$VAR, so every config value using the
    `:-default` form (every agent_config/model_config entry in
    flow-training.yaml) was silently passed through as the literal
    unexpanded string '${LANGFLOW_URL:-http://...}' regardless of whether
    the env var was actually set. This implements the `:-default` form
    directly instead of relying on os.path.expandvars.
    """

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        has_default = match.group(2) is not None
        default = match.group(3) if has_default else None
        env_value = os.environ.get(var_name)
        if env_value:
            return env_value
        if has_default:
            return default or ""
        return match.group(0)  # leave unexpanded if no default and unset

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _expand_vars_recursive(obj):
    """Recursively expand ${VAR}/${VAR:-default} in all string values in a dict/list."""
    if isinstance(obj, str):
        expanded = _expand_env_string(obj)
        if "${" in expanded:
            logger.warning(
                "Unexpanded env var detected after expansion: %r "
                "(set the variable or it will be passed as a literal string)",
                expanded,
            )
        return expanded
    elif isinstance(obj, dict):
        return {k: _expand_vars_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_vars_recursive(item) for item in obj]
    return obj


def _load_config(path: str) -> dict:
    """Load a YAML config file with os.path.expandvars() on all string values.

    yaml.safe_load() does NOT expand ${VAR} placeholders -- they come through
    as literal strings. This function walks the parsed dict/list tree and
    expands every string value via os.path.expandvars().

    Args:
        path: Path to the YAML config file.

    Returns:
        The fully-expanded config dict.

    Raises:
        ImportError: If PyYAML is not installed.
        FileNotFoundError: If the config file does not exist.
    """
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return {}

    return _expand_vars_recursive(raw)


# ─── Resume Manifest ───────────────────────────────────────────────────────


def _load_manifest(manifest_path: Path) -> dict:
    """Load the generation manifest for resume tracking.

    The manifest tracks:
      - completed_tiers: list of tier names fully generated
      - completed_batches: dict of tier_name -> list of batch indices
      - last_success_ts: ISO timestamp of last successful batch
      - total_examples: running total of examples generated

    Returns:
        Manifest dict, or empty defaults if file does not exist.
    """
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {
        "completed_tiers": [],
        "completed_batches": {},
        "last_success_ts": None,
        "total_examples": 0,
    }


def _save_manifest(manifest_path: Path, manifest: dict) -> None:
    """Atomically save the generation manifest (write-then-rename)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(manifest_path.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(manifest, f, indent=2)
        os.replace(tmp_path, str(manifest_path))
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ─── Seed Materialization ─────────────────────────────────────────────────


def _ensure_seeds(
    seeds_output: Path,
    seeds_config: str,
    gateway_url: str,
    keycloak_url: str,
    client_id: str,
    client_secret: str,
    max_age_seconds: int = 3600,
) -> int:
    """Ensure materialized seeds exist and are fresh (< max_age_seconds old).

    If the seed file does not exist or is stale, calls materialize_tool_seeds()
    to query the MCP Gateway's tools/list and produce the structured seed
    dataset that sdg_hub expects.

    Args:
        seeds_output: Path to the seed JSONL output file.
        seeds_config: Path to seed-scenarios.yaml.
        gateway_url: MCP Gateway endpoint URL.
        keycloak_url: Keycloak base URL.
        client_id: Keycloak client ID.
        client_secret: Keycloak client secret.
        max_age_seconds: Maximum age in seconds before re-materializing.

    Returns:
        Number of seed records (from file or newly generated).
    """
    from sdg.scripts.materialize_seeds import (
        acquire_jwt,
        fetch_tools,
        mcp_initialize,
    )

    if seeds_output.exists():
        age = time.time() - seeds_output.stat().st_mtime
        if age < max_age_seconds:
            # Count existing records
            count = sum(1 for line in seeds_output.open() if line.strip())
            logger.info(
                "Seeds file %s is fresh (%.0fs old, %d records) -- skipping materialization",
                seeds_output, age, count,
            )
            return count
        logger.info(
            "Seeds file %s is stale (%.0fs old) -- re-materializing",
            seeds_output, age,
        )

    logger.info("Materializing seeds from MCP Gateway...")

    # Acquire JWT
    jwt = acquire_jwt(keycloak_url, client_id, client_secret)
    logger.info("JWT acquired (%d chars)", len(jwt))

    # MCP initialize handshake
    session_id = mcp_initialize(gateway_url, jwt)
    logger.info("MCP session: %s...", session_id[:16])

    # Fetch tools
    tools = fetch_tools(gateway_url, jwt, session_id)
    logger.info("Discovered %d tools from gateway", len(tools))

    # Materialize
    count = materialize_tool_seeds(tools, seeds_config, str(seeds_output))
    logger.info("Materialized %d seed records to %s", count, seeds_output)
    return count


# ─── Generation ────────────────────────────────────────────────────────────


def _load_seed_dataframe(seeds_path: Path, tiers: list[str] | None = None):
    """Load seed JSONL and optionally filter by tier.

    Returns a list of seed record dicts. If tiers is provided, only
    records matching the specified tier names are included.
    """
    records = []
    with open(seeds_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if tiers and record.get("tier") not in tiers:
                continue
            records.append(record)
    return records


# Default max_concurrency for flow.generate() calls. Raised from the
# fully-serialized value (1) used during the 2026-10-09 dry-run and the
# first tool-coverage-gated KFP run -- that run's single_tool tier alone
# took ~5 hours for one attempt plus coverage-gate retries, which multiplies
# total runtime by up to MAX_ATTEMPTS (3) per scenario needing a resample.
# Confirmed live during the 504 investigation that concurrency=3 was NOT
# what caused those timeouts (streaming was -- see streaming_llm_chat_block.py
# and the comment at the call site below); this value is being raised again
# now that the actual timeout mechanism is fixed, with the expectation that
# it should be safe. Watch the first few tiers/attempts after raising this
# for new failure modes (vLLM queueing/backpressure, Langflow agent
# concurrency limits) that a request-level timeout fix wouldn't address.
#
# 2026-10-12: raised 4 -> 8 to match the model's new 2-replica capacity, but
# reverted back to 4 the same day -- confirmed live that Langflow (the
# orchestrating agent in front of the model, NOT the model itself) is the
# real bottleneck at this concurrency. Langflow runs as a single-replica
# StatefulSet backed by SQLite on a per-pod PVC (LANGFLOW_DATABASE_URL=
# sqlite:////data/langflow.db) -- it cannot be horizontally scaled without a
# shared-database migration (a new replica would start with an empty DB and
# no flows configured), so doubling the model's replicas did not add any
# usable concurrency headroom on the agent side. At concurrency=8, one
# run_expert_trajectory request exceeded the connector's 120s client-side
# timeout even though Langflow itself wasn't CPU-starved -- confirmed via
# oc adm top (21m cores, 1.8Gi mem) while jobs were still completing
# successfully around the failure. 4 is the last value proven to run
# error-free through explore_server/generate_questions/early
# run_expert_trajectory rows before 8 was tried.
#
# 2026-10-13: raised back to 8, paired this time with LANGFLOW_NUM_WORKERS
# 4 -> 8 (and a matching resource bump to requests cpu=4/memory=8Gi, limits
# cpu=8/memory=12Gi) on the langflow-service StatefulSet -- the single-worker
# process was the actual bottleneck the first time this was tried, not
# Langflow generally, and that bottleneck is gone now that the process count
# matches the request concurrency. Also raised request-level timeout to
# 300s (flow-training.yaml) since the earlier revert. Watch the first tier
# for a repeat of the same failure mode before trusting this long-term.
#
# 2026-10-15: raised 8 -> 16 ahead of a longer, higher-volume run
# (multiply_tool_rows.num_samples bumped 20 -> ~60-80 the same day). Checked
# first this time instead of guessing: `oc adm top` on langflow-service
# during the 10-13 fix showed only ~21m CPU used out of an 8-core limit at
# concurrency=8 -- nowhere near compute-bound, so the 8-worker ceiling
# itself (not resource contention) was what capped real concurrency. Raised
# LANGFLOW_NUM_WORKERS 8 -> 16 in lockstep again (same lesson as 10-13:
# raising this without matching the worker count just queues the excess
# past the connector's timeout) plus a proportional resource bump on the
# StatefulSet. Also added 429 to retrying_http_client.py's retry predicate
# before this -- the existing 5xx-only retry doesn't cover a hosted model
# API rate-limit response, which is a real risk at higher request volume
# that wasn't a concern against a self-hosted vLLM endpoint.
GENERATION_MAX_CONCURRENCY = 16


def _generate_once(
    flow,
    seeds: list[dict],
    runtime_params: dict,
    max_concurrency: int,
    checkpoint_dir: str | None = None,
    checkpoint_save_freq: int | None = None,
) -> list[dict]:
    """Run flow.generate() once over the given seeds, returning output rows as dicts.

    sdg_hub's Flow.generate() requires a pandas DataFrame or HF Dataset, not
    a list of dicts -- this wraps that conversion plus the DataFrame/list
    normalization of whatever generate() returns, so callers (including the
    tool-coverage rejection-sampling retry loop in _run_generation) can
    invoke a single attempt without repeating this boilerplate.

    checkpoint_dir/checkpoint_save_freq are passed straight through to
    sdg_hub's own execute_flow() (verified via source inspection of
    sdg_hub==0.9.4, not assumed from docs): when set, it chunks `seeds`
    into groups of checkpoint_save_freq *pre-expansion* seed rows, runs each
    chunk through every flow block, and saves a checkpoint JSONL after each
    chunk -- so a crash partway through a tier only loses the in-flight
    chunk's LLM/agent calls, not the whole tier. See _run_generation's call
    site for why this needs per-(tier, attempt) scoping, not a single shared
    directory.
    """
    import pandas as pd
    seed_df = pd.DataFrame(seeds)
    output = flow.generate(
        dataset=seed_df,
        runtime_params=runtime_params,
        max_concurrency=max_concurrency,
        checkpoint_dir=checkpoint_dir,
        save_freq=checkpoint_save_freq,
    )

    if hasattr(output, "iterrows"):
        return [row.to_dict() for _, row in output.iterrows()]
    elif isinstance(output, list):
        return list(output)
    else:
        try:
            return list(output)
        except TypeError:
            logger.error("Unexpected output type from flow: %s", type(output))
            raise


def _resolve_flow_path(config: dict) -> str:
    """config['flow_path'] (repo-relative or absolute) or sdg_hub's stock flow.

    Lets a flow-training.yaml opt into sdg/flows/mcp_distillation_v2/flow.yaml
    (or any other repo-local flow) without changing the default for configs
    that don't set it.
    """
    flow_path = (config.get("flow_path") or "").strip()
    if flow_path:
        p = Path(flow_path)
        if not p.is_absolute() and not p.exists():
            p = Path(__file__).resolve().parents[2] / flow_path
        return str(p)
    FlowRegistry.discover_flows()
    return FlowRegistry.get_flow_path("MCP Server Distillation")


def _run_generation(
    config: dict,
    seeds: list[dict],
    output_dir: Path,
    tier_name: str,
    dry_run: bool = False,
    checkpoint_dir: Path | None = None,
    checkpoint_save_freq: int = 1,
) -> list[dict]:
    """Run the sdg_hub generation flow for a single tier.

    Args:
        config: Fully-expanded flow config dict.
        seeds: List of seed record dicts for this tier.
        output_dir: Directory to write raw output JSONL.
        tier_name: Name of the curriculum tier.
        dry_run: If True, limit to 10 examples.
        checkpoint_dir: Base directory for sdg_hub's own per-seed-chunk
            checkpointing (opt-in; None disables it entirely, same as
            before this was added). Must be on storage that survives a pod
            restart to be useful -- see sdg_production_pipeline.py's
            checkpoint PVC. Disabled for dry-run regardless of this value
            (10-example smoke runs don't benefit, and a stale checkpoint
            from a prior dry-run could confuse the content-based resume
            matching).
        checkpoint_save_freq: Seed rows (pre-multiply_tool_rows expansion)
            per checkpoint chunk. See module docstring note at the
            GENERATION_MAX_CONCURRENCY definition for how this composes
            with the tool-coverage retry loop below.

    Returns:
        List of generated example dicts.
    """
    if FlowRegistry is None or Flow is None:
        raise ImportError(
            "sdg_hub is required: pip install sdg_hub "
            "(see https://github.com/redhat-ai-tools/sdg-hub)"
        )

    # Discover and load the flow: config['flow_path'] (e.g.
    # sdg/flows/mcp_distillation_v2/flow.yaml, which gives the response judge
    # the tool trace instead of only the final answer -- see flow_blocks.py)
    # or sdg_hub's installed "MCP Server Distillation" by default.
    flow_path = _resolve_flow_path(config)
    flow = Flow.from_yaml(flow_path)

    # Real Flow API (verified against installed sdg_hub==0.9.4, not assumed
    # from docs): model/agent config are set on the flow itself, not passed
    # to generate(). generate()'s only config kwarg is runtime_params.
    model_config = config.get("model_config", {})
    agent_config = config.get("agent_config", {})
    flow.set_model_config(**model_config)
    flow.set_agent_config(**agent_config)

    runtime_params = config.get("runtime_params", {})

    if dry_run:
        # Override runtime params for dry-run: 1 copy, 1 sample
        runtime_params = {
            "multiply_tool_rows": {"num_samples": 1},
            "sample_tools": {"num_samples": 1},
        }
        logger.info("Dry-run mode: limiting to ~10 examples (num_samples=1)")
        seeds = seeds[:10]
    else:
        # sample_tools.num_samples controls how many tools from each row's
        # tool_list get drawn into a single generated question -- this is
        # what approximates curriculum progression (single_tool tier should
        # only ever sample 1 tool, closed_loop up to 5), since the flow
        # itself has no per-row/per-tier notion of this, only one static
        # value per generate() call. Derive it from the smallest tool_list
        # actually present in this tier's seeds so sampling never requests
        # more tools than a scenario has (SamplerBlock has no min() guard).
        tool_list_sizes = [len(s.get("tool_list", [])) for s in seeds if s.get("tool_list")]
        if tool_list_sizes:
            tier_sample_size = max(1, min(tool_list_sizes))
            runtime_params = dict(runtime_params)
            runtime_params["sample_tools"] = {"num_samples": tier_sample_size}
            logger.info(
                "Tier '%s': sample_tools.num_samples=%d (min tool_list size across %d seeds)",
                tier_name, tier_sample_size, len(tool_list_sizes),
            )

    # Run the flow
    logger.info(
        "Running generation flow for tier '%s' with %d seeds...",
        tier_name, len(seeds),
    )

    # Tool-coverage rejection-sampling gate (04-LEARNINGS.md, 2026-10-09
    # decision): the flow's own quality filters (question-quality,
    # response-completeness) score narrative quality, not whether the agent
    # actually exercised the tools a hand-curated scenario intended. The
    # 2026-10-09 dry-run showed Gemma 4 defaulting to a "list alarms, open a
    # ticket" pattern and skipping harder tools (TMF628 performance jobs,
    # interface/BGP diagnostics) even when a scenario's tool_subset called
    # for them -- a gap self-distillation's existing filters cannot catch,
    # since they never compare the trace against intended_tools at all.
    # For scenarios carrying an intended_tools passthrough column (every
    # hand-curated seed, via materialize_seeds.py), resample up to
    # MAX_COVERAGE_RETRIES extra times and only accept a trajectory that
    # actually called every intended tool; after the last attempt, keep a
    # record of anything that still didn't pass as a fallback signal for
    # 04-LEARNINGS.md fix (2) (stronger external teacher for that scenario),
    # not as training data. Organic seeds with no intended_tools (no ground
    # truth to check) pass on the first attempt, same as before this gate
    # existed -- see row_passes_tool_coverage()'s docstring.
    MAX_COVERAGE_RETRIES = 2
    MAX_ATTEMPTS = MAX_COVERAGE_RETRIES + 1

    remaining = {
        (s.get("scenario_name") or s.get("mcp_server_name") or f"<unnamed-{i}>"): s
        for i, s in enumerate(seeds)
    }
    accepted: list[dict] = []
    coverage_failed: list[dict] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not remaining:
            break
        current_seeds = list(remaining.values())
        logger.info(
            "Tier '%s': generation attempt %d/%d over %d seed(s)%s...",
            tier_name, attempt, MAX_ATTEMPTS, len(current_seeds),
            " (resampling tool-coverage failures)" if attempt > 1 else "",
        )
        # See GENERATION_MAX_CONCURRENCY's module-level comment: confirmed
        # live during the original 504 investigation that concurrency=3 was
        # NOT what caused those timeouts (streaming was), so raising this
        # back up should be safe now that streaming is in place -- but it
        # wasn't re-validated under the tool-coverage gate's extra retry
        # load, so watch early attempts after any change here.
        #
        # checkpoint_dir is scoped per (tier, attempt), not shared across
        # attempts -- 2026-10-13, added after confirming via sdg_hub source
        # that its resume matching is purely content-based (hashes the
        # *pre-expansion* seed columns common to old and new input). Attempt
        # 2+ only re-processes scenarios whose attempt-1 trajectory FAILED
        # the tool-coverage gate below -- those seeds' pre-expansion columns
        # are identical to attempt 1's (same scenario, same tool_list), so a
        # shared checkpoint dir would make attempt 2 incorrectly match and
        # skip them, silently reusing the inadequate attempt-1 trajectory
        # instead of actually resampling. Scoping per-attempt means a
        # crash-and-resubmit mid-tier still gets the full benefit: attempt 1
        # replays fast from its own checkpoint (already done), correctly
        # re-derives the same `remaining` set, and attempt 2 resumes from
        # wherever its own (separate) checkpoint got to.
        attempt_checkpoint_dir = (
            str(checkpoint_dir / tier_name / f"attempt_{attempt}")
            if checkpoint_dir and not dry_run
            else None
        )
        try:
            rows = _generate_once(
                flow,
                current_seeds,
                runtime_params,
                GENERATION_MAX_CONCURRENCY,
                checkpoint_dir=attempt_checkpoint_dir,
                checkpoint_save_freq=checkpoint_save_freq if attempt_checkpoint_dir else None,
            )
        except EmptyDatasetError:
            # sdg_hub's own quality filters (question-quality, response-
            # completeness) can legitimately zero out a single chunk -- e.g.
            # a coverage-gate resample of one seed (multiplied to 20 rows by
            # multiply_tool_rows) had all 20 fail filter_incomplete_responses.
            # When that happens sdg_hub's _process_with_checkpointing has no
            # per-chunk exception handling (confirmed via source inspection,
            # 2026-10-13): the exception propagates out of flow.generate()
            # immediately, WITHOUT returning any earlier chunks in this same
            # attempt that already succeeded and were already written to
            # checkpoint_*.jsonl files on disk by FlowCheckpointer.
            # Originally this handler just discarded everything with
            # `rows = []` -- confirmed live this threw away 15 perfectly
            # good, already-generated examples from seed 1 of an 11-seed
            # attempt because seed 2 alone hit this empty-chunk case. Recover
            # whatever chunks did succeed from disk instead of discarding
            # them; only seeds whose chunk never completed are genuinely
            # zero rows for this attempt (and get resampled/recorded as
            # coverage-gate failures same as before).
            rows = []
            if attempt_checkpoint_dir and os.path.isdir(attempt_checkpoint_dir):
                import pandas as pd
                checkpoint_files = sorted(Path(attempt_checkpoint_dir).glob("checkpoint_*.jsonl"))
                if checkpoint_files:
                    recovered = pd.concat(
                        [pd.read_json(f, lines=True) for f in checkpoint_files],
                        ignore_index=True,
                    )
                    rows = recovered.to_dict("records")
            logger.warning(
                "Tier '%s' attempt %d/%d: a chunk was filtered to zero rows by "
                "sdg_hub's own quality gates (EmptyDatasetError), which aborts "
                "the whole attempt in sdg_hub -- recovered %d row(s) from "
                "earlier chunks' checkpoint files instead of discarding them.",
                tier_name, attempt, MAX_ATTEMPTS, len(rows),
            )

        for row in rows:
            scenario = row.get("scenario_name") or row.get("mcp_server_name")
            if row_passes_tool_coverage(row, DEFAULT_TRACE_COLUMN):
                accepted.append(row)
                if scenario:
                    remaining.pop(scenario, None)
            elif attempt == MAX_ATTEMPTS:
                coverage_failed.append(row)

        if remaining and attempt < MAX_ATTEMPTS:
            logger.info(
                "Tier '%s': %d scenario(s) failed the tool-coverage gate, resampling...",
                tier_name, len(remaining),
            )

    if remaining:
        logger.warning(
            "Tier '%s': %d scenario(s) never produced a trajectory covering all "
            "intended_tools after %d attempts: %s -- excluded from training output, "
            "kept in %s_coverage_failed.jsonl. See 04-LEARNINGS.md fix (2) "
            "(stronger external teacher) as the documented fallback.",
            tier_name, len(remaining), MAX_ATTEMPTS, sorted(remaining.keys()), tier_name,
        )

    results = accepted

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{tier_name}_raw.jsonl"
    with open(output_file, "w") as f:
        for record in results:
            f.write(json.dumps(record, default=str) + "\n")

    if coverage_failed:
        failed_file = output_dir / f"{tier_name}_coverage_failed.jsonl"
        with open(failed_file, "w") as f:
            for record in coverage_failed:
                f.write(json.dumps(record, default=str) + "\n")
        logger.info(
            "Tier '%s': %d coverage-gate-failed example(s) written to %s (not training data)",
            tier_name, len(coverage_failed), failed_file,
        )

    logger.info(
        "Tier '%s': %d examples written to %s",
        tier_name, len(results), output_file,
    )
    return results


# ─── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Run sdg_hub MCP Server Distillation training flow for "
            "production dataset generation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="sdg/config/flow-training.yaml",
        help="Path to flow-training.yaml (default: sdg/config/flow-training.yaml)",
    )
    parser.add_argument(
        "--seeds",
        default="sdg/config/seed-scenarios.yaml",
        help="Path to seed-scenarios.yaml (default: sdg/config/seed-scenarios.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        default="sdg/data/raw/",
        help="Output directory for raw JSONL (default: sdg/data/raw/)",
    )
    parser.add_argument(
        "--tiers",
        default=None,
        help=(
            "Comma-separated list of tiers to run "
            "(default: all tiers from seed-scenarios.yaml)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Limit to 10 examples for format validation (D-19 gate)",
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get(
            "GATEWAY_URL",
            "https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp",
        ),
        help="MCP Gateway endpoint URL",
    )
    parser.add_argument(
        "--keycloak-url",
        default=os.environ.get(
            "KEYCLOAK_URL",
            "https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com",
        ),
        help="Keycloak base URL",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("CLIENT_ID", "sdg-pipeline"),
        help="Keycloak client ID (default: sdg-pipeline)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("CLIENT_SECRET", ""),
        help="Keycloak client secret (from CLIENT_SECRET env var)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint (uses .generation_manifest.json)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=os.environ.get("CHECKPOINT_DIR"),
        help=(
            "Base directory for sdg_hub's own per-seed-chunk checkpointing "
            "within a tier (opt-in; omit/unset to disable, same behavior as "
            "before this flag existed). This is a finer-grained complement "
            "to --resume's per-TIER manifest, not a replacement -- a crash "
            "partway through a tier's run_expert_trajectory block only "
            "loses the in-flight chunk's LLM/agent calls, not the whole "
            "tier. MUST be on storage that survives a pod restart to be "
            "useful (e.g. a mounted PVC in KFP, not /tmp) -- see "
            "sdg_production_pipeline.py's checkpoint PVC."
        ),
    )
    parser.add_argument(
        "--checkpoint-save-freq",
        type=int,
        default=1,
        help=(
            "Seed rows (pre-multiply_tool_rows-expansion) per checkpoint "
            "chunk. Lower = finer-grained resume, more checkpoint file "
            "writes. Default 1 since per-tier seed counts are small "
            "(single digits to ~20) -- each one's full expanded trajectory "
            "set gets checkpointed independently. Only takes effect if "
            "--checkpoint-dir is set."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for production generation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Load flow config with env-var interpolation
    logger.info("Loading flow config from %s", args.config)
    config = _load_config(args.config)

    # Load seed scenarios to determine available tiers
    logger.info("Loading seed scenarios from %s", args.seeds)
    seeds_config = _load_config(args.seeds)
    available_tiers = list(seeds_config.get("tiers", {}).keys())
    logger.info("Available tiers: %s", available_tiers)

    # Determine which tiers to run
    if args.tiers:
        requested_tiers = [t.strip() for t in args.tiers.split(",")]
        invalid = [t for t in requested_tiers if t not in available_tiers]
        if invalid:
            logger.error("Unknown tiers: %s (available: %s)", invalid, available_tiers)
            return 1
    else:
        requested_tiers = available_tiers

    # Setup paths
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    seeds_output = Path("sdg/data/seeds/tool_metadata.jsonl")
    manifest_path = output_dir / ".generation_manifest.json"

    # Step 1: Ensure seeds are materialized
    logger.info("=== Step 1: Seed Materialization ===")
    seed_count = _ensure_seeds(
        seeds_output=seeds_output,
        seeds_config=args.seeds,
        gateway_url=args.gateway_url,
        keycloak_url=args.keycloak_url,
        client_id=args.client_id,
        client_secret=args.client_secret,
    )
    logger.info("Seed dataset: %d records", seed_count)

    # Step 2: Load resume manifest if --resume
    manifest = _load_manifest(manifest_path)
    if args.resume:
        completed = manifest.get("completed_tiers", [])
        if completed:
            logger.info("Resuming: skipping completed tiers: %s", completed)
            requested_tiers = [t for t in requested_tiers if t not in completed]
            if not requested_tiers:
                logger.info("All requested tiers already completed. Nothing to do.")
                return 0

    # Step 3: Run generation for each tier
    logger.info("=== Step 2: Generation ===")
    total_examples = manifest.get("total_examples", 0)
    tier_stats: dict[str, int] = {}

    for tier_name in requested_tiers:
        logger.info("--- Tier: %s ---", tier_name)

        # Load seeds for this tier
        seeds = _load_seed_dataframe(seeds_output, tiers=[tier_name])
        if not seeds:
            logger.warning("No seeds found for tier '%s' -- skipping", tier_name)
            continue

        try:
            results = _run_generation(
                config=config,
                seeds=seeds,
                output_dir=output_dir,
                tier_name=tier_name,
                dry_run=args.dry_run,
                checkpoint_dir=Path(args.checkpoint_dir) if args.checkpoint_dir else None,
                checkpoint_save_freq=args.checkpoint_save_freq,
            )
            count = len(results)
            tier_stats[tier_name] = count
            total_examples += count

            # Update manifest
            manifest["completed_tiers"].append(tier_name)
            manifest["total_examples"] = total_examples
            manifest["last_success_ts"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            _save_manifest(manifest_path, manifest)
            logger.info("Tier '%s' complete: %d examples", tier_name, count)

        except Exception:
            logger.exception("Generation failed for tier '%s'", tier_name)
            logger.info(
                "Use --resume to continue from this point. "
                "Completed tiers: %s", manifest["completed_tiers"],
            )
            return 1

    # Summary
    logger.info("=== Summary ===")
    logger.info("Total examples generated: %d", total_examples)
    for tier, count in tier_stats.items():
        logger.info("  %s: %d", tier, count)
    logger.info("Output directory: %s", output_dir)
    logger.info("Manifest: %s", manifest_path)

    if args.dry_run:
        logger.info(
            "Dry-run complete. Send output to Farbod's team for "
            "OSFT format validation (D-19 gate)."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

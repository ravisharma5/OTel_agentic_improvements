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

    # Swap every LLMChatBlock in any loaded flow for a streaming-aware one --
    # see streaming_llm_chat_block.py for why (AWS ELB idle-connection
    # timeout on long non-streaming generations, confirmed live). Must run
    # before FlowRegistry.discover_flows()/Flow.from_yaml() are called below.
    patch_llm_chat_block_for_streaming()
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
GENERATION_MAX_CONCURRENCY = 4


def _generate_once(flow, seeds: list[dict], runtime_params: dict, max_concurrency: int) -> list[dict]:
    """Run flow.generate() once over the given seeds, returning output rows as dicts.

    sdg_hub's Flow.generate() requires a pandas DataFrame or HF Dataset, not
    a list of dicts -- this wraps that conversion plus the DataFrame/list
    normalization of whatever generate() returns, so callers (including the
    tool-coverage rejection-sampling retry loop in _run_generation) can
    invoke a single attempt without repeating this boilerplate.
    """
    import pandas as pd
    seed_df = pd.DataFrame(seeds)
    output = flow.generate(
        dataset=seed_df,
        runtime_params=runtime_params,
        max_concurrency=max_concurrency,
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


def _run_generation(
    config: dict,
    seeds: list[dict],
    output_dir: Path,
    tier_name: str,
    dry_run: bool = False,
) -> list[dict]:
    """Run the sdg_hub generation flow for a single tier.

    Args:
        config: Fully-expanded flow config dict.
        seeds: List of seed record dicts for this tier.
        output_dir: Directory to write raw output JSONL.
        tier_name: Name of the curriculum tier.
        dry_run: If True, limit to 10 examples.

    Returns:
        List of generated example dicts.
    """
    if FlowRegistry is None or Flow is None:
        raise ImportError(
            "sdg_hub is required: pip install sdg_hub "
            "(see https://github.com/redhat-ai-tools/sdg-hub)"
        )

    # Discover and load the flow
    FlowRegistry.discover_flows()
    flow_path = FlowRegistry.get_flow_path("MCP Server Distillation")
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
        try:
            rows = _generate_once(flow, current_seeds, runtime_params, GENERATION_MAX_CONCURRENCY)
        except EmptyDatasetError:
            # sdg_hub's own quality filters (question-quality, response-
            # completeness) can legitimately zero out an entire attempt --
            # confirmed live: a coverage-gate resample of a single seed
            # (multiplied to 20 rows by multiply_tool_rows) had all 20
            # fail filter_incomplete_responses, and flow.generate() raises
            # EmptyDatasetError rather than returning an empty result.
            # Within this retry loop that's just "this attempt produced
            # nothing," not a fatal error -- treat it as zero rows so the
            # loop resamples again (or records a coverage-gate failure on
            # the last attempt) instead of crashing the whole tier.
            logger.warning(
                "Tier '%s' attempt %d/%d: all rows filtered out by sdg_hub's "
                "own quality gates (EmptyDatasetError) -- treating as zero "
                "survivors for this attempt.",
                tier_name, attempt, MAX_ATTEMPTS,
            )
            rows = []

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

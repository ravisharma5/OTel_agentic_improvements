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
except ImportError:
    FlowRegistry = None  # type: ignore[assignment,misc]
    Flow = None  # type: ignore[assignment,misc]

from sdg.scripts.materialize_seeds import materialize_tool_seeds

logger = logging.getLogger(__name__)


# ─── Config Loading with Env-Var Interpolation ─────────────────────────────


def _expand_vars_recursive(obj):
    """Recursively apply os.path.expandvars to all string values in a dict/list."""
    if isinstance(obj, str):
        expanded = os.path.expandvars(obj)
        if "${" in expanded:
            logger.warning(
                "Unexpanded env var detected after expandvars: %r "
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

    # Apply model and agent config from our override config
    model_config = config.get("model_config", {})
    agent_config = config.get("agent_config", {})
    runtime_params = config.get("runtime_params", {})

    if dry_run:
        # Override runtime params for dry-run: 1 copy, 1 sample
        runtime_params = {
            "multiply_tool_rows": {"num_samples": 1},
            "sample_tools": {"num_samples": 1},
        }
        logger.info("Dry-run mode: limiting to ~10 examples (num_samples=1)")

    # Build seed DataFrame (sdg_hub expects a pandas DataFrame or list of dicts)
    if dry_run:
        seeds = seeds[:10]

    # Run the flow
    logger.info(
        "Running generation flow for tier '%s' with %d seeds...",
        tier_name, len(seeds),
    )
    output = flow.generate(
        seed_dataset=seeds,
        model_config=model_config,
        agent_config=agent_config,
        runtime_params=runtime_params,
    )

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{tier_name}_raw.jsonl"
    results = []

    if hasattr(output, "iterrows"):
        # pandas DataFrame
        for _, row in output.iterrows():
            record = row.to_dict()
            results.append(record)
    elif isinstance(output, list):
        results = output
    else:
        # Try converting to list of dicts
        try:
            results = list(output)
        except TypeError:
            logger.error("Unexpected output type from flow: %s", type(output))
            raise

    with open(output_file, "w") as f:
        for record in results:
            f.write(json.dumps(record, default=str) + "\n")

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

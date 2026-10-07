#!/usr/bin/env python3
"""Run sdg_hub three-stage verification, automatic OSFT schema validation, and dual-format serialization.

Per amended D-04, OSFT validation runs as an unconditional automatic call
to sdg.lib.osft_validation.validate_osft_line immediately after the eval
flow completes, before any output is treated as final. This is NOT a
separate manual step -- it is part of this script's normal execution path.

Flow configs are loaded with os.path.expandvars() to expand env-var
placeholders (e.g. ${VLLM_API_KEY}) that yaml.safe_load() leaves as
literal strings.

Three stages of verification:
  1. Format check: compute_tool_metrics (tool_recall, tool_precision, etc.)
  2. Execution check: inherent in the generation flow (tools were actually called)
  3. Semantic check: LLM judge scores on 6 dimensions

After the eval flow's quality filtering, this script:
  - Applies an explicit COLUMN_MAP to bridge sdg_hub output columns to
    the serializer's expected input keys (fails hard on missing required keys)
  - Runs OSFT schema validation on every serialized row (unconditionally)
  - Produces both single-turn and multi-turn OSFT JSONL via the serializer
    (D-20: both formats delivered so Farbod's team decides what to train on)

Usage:
    python -m sdg.scripts.run-evaluation
    python -m sdg.scripts.run-evaluation --input-dir sdg/data/raw/ --output-dir sdg/data/filtered/

References:
    D-02:  mcp_distillation_evaluation flow for three-stage verification
    D-04 (amended): OSFT validation as automatic Python call after eval flow
    D-20:  Both single-turn and multi-turn OSFT JSONL produced
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
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

# OSFT serializer -- UNDERSCORE filename, proper package import
from sdg.scripts.serialize_osft import serialize_single_turn, serialize_multi_turn

# OSFT validation -- library module, per amended D-04
from sdg.lib.osft_validation import validate_osft_line, validate_osft_file

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


# ─── Column Mapping ───────────────────────────────────────────────────────
#
# sdg_hub's 18-block pipeline produces output columns that may differ from
# the serializer's expected input keys.  This mapping bridges the gap.
#
# Known sdg_hub output columns (from RESEARCH.md block descriptions):
#   - "question"         -> serializer "question"  (often exact match)
#   - "agent_text"       -> serializer "answer"    (needs rename)
#   - "response_text"    -> serializer "answer"    (alternate name)
#   - "tool_trace"       -> serializer "tool_trace" (often exact match)
#   - "agent_tool_trace" -> serializer "tool_trace" (alternate name)
#   - "tool_list"        -> serializer "tools"     (needs rename)
#
# If a required key cannot be resolved after mapping, this script FAILS
# HARD (raises ValueError) rather than silently skipping -- core pipeline
# steps must not degrade to warning-and-skip.

COLUMN_MAP = {
    "question": "question",
    "agent_text": "answer",
    "response_text": "answer",
    "tool_trace": "tool_trace",
    "agent_tool_trace": "tool_trace",
    "tool_list": "tools",
}

# Keys the serializer requires
_REQUIRED_SERIALIZER_KEYS = {"question", "tool_trace", "answer", "tools"}


def _map_columns(row: dict, row_index: int) -> dict:
    """Map sdg_hub output columns to serializer input keys.

    Applies COLUMN_MAP to rename/bridge columns.  If a required key
    (question, tool_trace, answer, tools) is missing after mapping,
    raises ValueError with all available column names for debugging.

    Args:
        row: A single row dict from the filtered output.
        row_index: Row index for error reporting.

    Returns:
        Dict with serializer-compatible keys.

    Raises:
        ValueError: If a required serializer key cannot be resolved.
    """
    mapped: dict = {}
    available_columns = set(row.keys())

    for src_col, dst_key in COLUMN_MAP.items():
        if src_col in row:
            # If multiple source columns map to the same destination,
            # prefer the first non-None value encountered
            if dst_key not in mapped or mapped[dst_key] is None:
                mapped[dst_key] = row[src_col]

    # Also pass through any columns that are already in serializer key form
    for key in _REQUIRED_SERIALIZER_KEYS:
        if key in row and key not in mapped:
            mapped[key] = row[key]

    # Validate all required keys are present
    missing = _REQUIRED_SERIALIZER_KEYS - set(mapped.keys())
    if missing:
        raise ValueError(
            f"Row {row_index}: required serializer keys {missing} not found "
            f"after column mapping. Available columns: {sorted(available_columns)}. "
            f"COLUMN_MAP produced keys: {sorted(mapped.keys())}. "
            f"Update COLUMN_MAP in run-evaluation.py to map the correct "
            f"sdg_hub output columns to serializer input keys."
        )

    # Ensure tool_trace is a list (may be JSON string from sdg_hub)
    if isinstance(mapped.get("tool_trace"), str):
        try:
            mapped["tool_trace"] = json.loads(mapped["tool_trace"])
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Row %d: tool_trace is not valid JSON, keeping as-is",
                row_index,
            )

    # Ensure tools is a list (may be JSON string from sdg_hub)
    if isinstance(mapped.get("tools"), str):
        try:
            mapped["tools"] = json.loads(mapped["tools"])
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Row %d: tools is not valid JSON, keeping as-is",
                row_index,
            )

    return mapped


# ─── Evaluation Flow ──────────────────────────────────────────────────────


def _run_evaluation_flow(
    config: dict,
    input_file: Path,
    output_dir: Path,
) -> list[dict]:
    """Run the sdg_hub evaluation flow on a raw JSONL file.

    Performs three-stage verification:
      1. Format check (compute_tool_metrics)
      2. Execution check (inherent in generation)
      3. Semantic check (LLM judge)

    Returns the quality-filtered output rows.
    """
    if FlowRegistry is None or Flow is None:
        raise ImportError(
            "sdg_hub is required: pip install sdg_hub "
            "(see https://github.com/redhat-ai-tools/sdg-hub)"
        )

    # Load input data
    rows = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        logger.warning("No rows in %s -- skipping", input_file)
        return []

    # Discover and load the evaluation flow
    FlowRegistry.discover_flows()
    flow_path = FlowRegistry.get_flow_path("MCP Server Distillation Evaluation")
    flow = Flow.from_yaml(flow_path)

    # Apply model config from our override config
    model_config = config.get("model_config", {})

    # Run the evaluation flow
    logger.info(
        "Running evaluation flow on %s (%d rows)...",
        input_file.name, len(rows),
    )
    output = flow.evaluate(
        dataset=rows,
        model_config=model_config,
    )

    # Convert output to list of dicts
    results = []
    if hasattr(output, "iterrows"):
        for _, row in output.iterrows():
            results.append(row.to_dict())
    elif isinstance(output, list):
        results = output
    else:
        try:
            results = list(output)
        except TypeError:
            logger.error("Unexpected output type from flow: %s", type(output))
            raise

    # Write filtered output
    output_dir.mkdir(parents=True, exist_ok=True)
    filtered_file = output_dir / input_file.name
    with open(filtered_file, "w") as f:
        for record in results:
            f.write(json.dumps(record, default=str) + "\n")

    logger.info(
        "Evaluation: %d/%d rows passed quality filter -> %s",
        len(results), len(rows), filtered_file,
    )
    return results


# ─── OSFT Validation and Serialization ─────────────────────────────────────


def _validate_and_serialize(
    mapped_rows: list[dict],
    delivery_dir: Path,
) -> dict:
    """Run OSFT validation and produce dual-format delivery files.

    Per amended D-04, OSFT validation runs unconditionally on every
    serialized row before any output is treated as final.

    Produces both single-turn and multi-turn OSFT JSONL in delivery_dir
    (D-20: both formats delivered so Farbod's team decides what to train on).

    Args:
        mapped_rows: List of column-mapped dicts with serializer keys.
        delivery_dir: Directory for delivery JSONL files.

    Returns:
        Stats dict with counts for reporting.
    """
    delivery_dir.mkdir(parents=True, exist_ok=True)

    # OSFT validation (per amended D-04 -- unconditional, automatic)
    validated_rows = []
    osft_errors = []
    for i, row in enumerate(mapped_rows):
        try:
            serialized = serialize_single_turn(row)
        except (ValueError, KeyError) as exc:
            osft_errors.append({"row": i, "errors": [str(exc)]})
            logger.warning("Row %d failed serialization: %s", i, exc)
            continue

        errors = validate_osft_line(serialized)
        if errors:
            osft_errors.append({"row": i, "errors": errors})
            logger.warning("Row %d failed OSFT validation: %s", i, errors)
        else:
            validated_rows.append(row)

    logger.info(
        "OSFT validation: %d/%d rows passed",
        len(validated_rows), len(mapped_rows),
    )
    if osft_errors:
        logger.warning("OSFT validation dropped %d rows", len(osft_errors))

    # Serialize validated rows to delivery files (D-20: both formats)
    single_turn_path = delivery_dir / "single-turn.jsonl"
    multi_turn_path = delivery_dir / "multi-turn.jsonl"

    with open(single_turn_path, "w") as f:
        for row in validated_rows:
            serialized = serialize_single_turn(row)
            f.write(json.dumps(serialized) + "\n")

    with open(multi_turn_path, "w") as f:
        for row in validated_rows:
            serialized = serialize_multi_turn(row)
            f.write(json.dumps(serialized) + "\n")

    logger.info(
        "Delivery files written: %s (%d rows), %s (%d rows)",
        single_turn_path, len(validated_rows),
        multi_turn_path, len(validated_rows),
    )

    # Validate delivery files for sanity
    for path in [single_turn_path, multi_turn_path]:
        is_valid, file_errors = validate_osft_file(str(path))
        if is_valid:
            logger.info("Delivery file validation PASSED: %s", path)
        else:
            logger.error(
                "Delivery file validation FAILED: %s -- %d errors",
                path, len(file_errors),
            )
            for err in file_errors[:10]:
                logger.error("  %s", err)

    return {
        "total_mapped": len(mapped_rows),
        "osft_validated": len(validated_rows),
        "osft_dropped": len(osft_errors),
        "delivery_files": [str(single_turn_path), str(multi_turn_path)],
    }


# ─── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Run sdg_hub three-stage verification, automatic OSFT validation "
            "(D-04), and dual-format serialization."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        default="sdg/data/raw/",
        help="Input directory containing raw JSONL files (default: sdg/data/raw/)",
    )
    parser.add_argument(
        "--output-dir",
        default="sdg/data/filtered/",
        help="Output directory for quality-filtered JSONL (default: sdg/data/filtered/)",
    )
    parser.add_argument(
        "--delivery-dir",
        default="sdg/data/delivery/",
        help="Delivery directory for OSFT JSONL (default: sdg/data/delivery/)",
    )
    parser.add_argument(
        "--config",
        default="sdg/config/flow-evaluation.yaml",
        help="Path to flow-evaluation.yaml (default: sdg/config/flow-evaluation.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for evaluation, OSFT validation, and serialization."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Load eval flow config with env-var interpolation
    logger.info("Loading evaluation config from %s", args.config)
    config = _load_config(args.config)

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    delivery_dir = Path(args.delivery_dir)

    if not input_dir.exists():
        logger.error("Input directory does not exist: %s", input_dir)
        return 1

    # Find all raw JSONL files
    input_files = sorted(input_dir.glob("*_raw.jsonl"))
    if not input_files:
        logger.error("No *_raw.jsonl files found in %s", input_dir)
        return 1

    logger.info("Found %d input files: %s", len(input_files), [f.name for f in input_files])

    # Step 1: Run evaluation flow on each input file
    logger.info("=== Step 1: Evaluation Flow (Three-Stage Verification) ===")
    all_filtered_rows: list[dict] = []
    input_count = 0

    for input_file in input_files:
        row_count = sum(1 for line in input_file.open() if line.strip())
        input_count += row_count

        filtered = _run_evaluation_flow(config, input_file, output_dir)
        all_filtered_rows.extend(filtered)

    logger.info(
        "Evaluation complete: %d/%d rows passed (%.1f%% filter rate)",
        len(all_filtered_rows), input_count,
        (1 - len(all_filtered_rows) / max(input_count, 1)) * 100,
    )

    # Step 2: Column mapping (bridges sdg_hub output to serializer input)
    logger.info("=== Step 2: Column Mapping ===")
    mapped_rows: list[dict] = []
    for i, row in enumerate(all_filtered_rows):
        mapped = _map_columns(row, i)
        mapped_rows.append(mapped)

    logger.info("Column mapping complete: %d rows mapped", len(mapped_rows))

    # Step 3: OSFT validation and dual-format serialization
    # Per amended D-04 -- unconditional, automatic, part of normal execution
    logger.info("=== Step 3: OSFT Validation & Serialization (D-04, D-20) ===")
    stats = _validate_and_serialize(mapped_rows, delivery_dir)

    # Summary
    logger.info("=== Summary ===")
    logger.info("Input rows:               %d", input_count)
    logger.info("Eval-flow-filtered rows:   %d", len(all_filtered_rows))
    logger.info("OSFT-validated rows:       %d", stats["osft_validated"])
    logger.info("OSFT-dropped rows:         %d", stats["osft_dropped"])
    logger.info("Final delivery count:      %d", stats["osft_validated"])
    logger.info(
        "Overall filter rate:       %.1f%%",
        (1 - stats["osft_validated"] / max(input_count, 1)) * 100,
    )
    logger.info("Delivery files:")
    for f in stats["delivery_files"]:
        logger.info("  %s", f)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Pass raw generation output through column mapping, automatic OSFT schema
validation, and dual-format serialization.

Per amended D-04, OSFT validation runs as an unconditional automatic call
to sdg.lib.osft_validation.validate_osft_line before any output is treated
as final. This is NOT a separate manual step -- it is part of this script's
normal execution path.

D-02's planned "mcp_distillation_evaluation flow for three-stage
verification" does not exist in sdg_hub==0.9.4 (confirmed live, 2026-10-10 --
see _run_evaluation_flow()'s docstring for the full finding). The three
verification stages it was meant to add are already covered upstream, inside
run-generation.py's training flow and tool-coverage gate, so this script now:
  - Loads each tier's raw JSONL as-is (already quality-filtered upstream)
  - Applies an explicit COLUMN_MAP to bridge sdg_hub output columns to
    the serializer's expected input keys (fails hard on missing required keys)
  - Runs OSFT schema validation on every serialized row (unconditionally)
  - Produces both single-turn and multi-turn OSFT JSONL via the serializer
    (D-20: both formats delivered so Farbod's team decides what to train on)

No flow config/model to load anymore (no flow is called here) -- removed the
--config flag and its YAML-loading machinery, which became dead code once
_run_evaluation_flow() stopped calling a flow.

Usage:
    python -m sdg.scripts.run-evaluation
    python -m sdg.scripts.run-evaluation --input-dir sdg/data/raw/ --output-dir sdg/data/filtered/

References:
    D-02:  mcp_distillation_evaluation flow for three-stage verification --
           superseded, see _run_evaluation_flow()'s docstring
    D-04 (amended): OSFT validation as automatic Python call
    D-20:  Both single-turn and multi-turn OSFT JSONL produced
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# OSFT serializer -- UNDERSCORE filename, proper package import
from sdg.scripts.serialize_osft import serialize_single_turn, serialize_multi_turn

# OSFT validation -- library module, per amended D-04
from sdg.lib.osft_validation import validate_osft_line, validate_osft_file

# Tool-trace column name -- same constant tool_coverage_report.py and the
# rejection-sampling gate already rely on, confirmed empirically against
# real output. Reused here (rather than re-guessing) for COLUMN_MAP below.
from sdg.lib.trace_utils import DEFAULT_TRACE_COLUMN

logger = logging.getLogger(__name__)


# ─── Column Mapping ───────────────────────────────────────────────────────
#
# sdg_hub's 22-block training flow produces output columns that differ from
# the serializer's expected input keys.  This mapping bridges the gap.
#
# Real sdg_hub output columns (confirmed empirically against production
# output, 2026-10-10 -- the "agent_text"/"response_text"/"tool_trace"/
# "agent_tool_trace" guesses below, from early RESEARCH.md-era notes, never
# actually matched anything and went uncaught because this code path was
# never exercised by a run that survived long enough to reach it until then):
#   - "question"                      -> serializer "question"   (exact match)
#   - "extract_agent_text_text"       -> serializer "answer"     (AgentResponseExtractorBlock's extract_text=True output; {block_name}_text convention)
#   - DEFAULT_TRACE_COLUMN            -> serializer "tool_trace" (same constant tool_coverage_report.py and the rejection-sampling gate rely on, not re-guessed here)
#   - "tool_list"                     -> serializer "tools"      (needs rename)
#
# Kept the old guessed names too (harmless, never matches anything in the
# real output) in case a different flow version or block-naming convention
# ever produces them.
#
# If a required key cannot be resolved after mapping, this script FAILS
# HARD (raises ValueError) rather than silently skipping -- core pipeline
# steps must not degrade to warning-and-skip.

COLUMN_MAP = {
    "question": "question",
    "extract_agent_text_text": "answer",
    "agent_text": "answer",
    "response_text": "answer",
    DEFAULT_TRACE_COLUMN: "tool_trace",
    "tool_trace": "tool_trace",
    "agent_tool_trace": "tool_trace",
    "tool_list": "tools",
}

# Keys the serializer requires
_REQUIRED_SERIALIZER_KEYS = {"question", "tool_trace", "answer", "tools"}

# Passed through as-is (not required, but needed downstream for multi-turn
# routing in _to_multi_turn_trace -- 'tier' distinguishes curriculum tiers
# that produce genuine multi-round conversations (multi_turn, closed_loop)
# from ones that are naturally single-exchange; 'turns' is sdg_hub's own
# multi-round output column, if present, for those tiers.
_PASSTHROUGH_KEYS = {"tier", "turns"}


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

    # Pass through tier/turns unmapped -- needed by _to_multi_turn_trace,
    # not required by the single-turn serializer path.
    for key in _PASSTHROUGH_KEYS:
        if key in row:
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
    input_file: Path,
    output_dir: Path,
) -> list[dict]:
    """Pass a raw generation JSONL file through to the filtered-output stage.

    Originally called a sdg_hub "evaluation flow" (format/execution/semantic
    three-stage verification) here. Confirmed live (2026-10-10, first time
    this stage actually ran against real production data): no flow named
    "MCP Server Distillation Evaluation" exists in sdg_hub==0.9.4's registry
    -- that was a design-time assumption from early research that never
    matched the real package. The only registered evaluation-category flow
    (id `eager-path-837`, name "Agent Tool-Use Evaluation",
    flows/evaluation/mcp_eval_benchmark/model_evaluation/flow.yaml) is a
    different tool entirely: it scores a model's trace *against an
    independent expert/gold-standard trace*
    (required columns: question, expert_answer_truncated,
    expert_trace_formatted, model_answer, model_trace_formatted) -- we have
    no such reference dataset, and it would need a `.generate()` call
    (confirmed via get_dataset_requirements()/dir(flow): no Flow in this
    package exposes `.evaluate()` at all, every flow's entrypoint is
    `.generate()`).

    In practice the three stages this was meant to add are already covered
    upstream, inside run-generation.py's training flow and the tool-coverage
    gate built on top of it:
      1. Format check: parse_question_fields / parse_quality_score
         (TagParserBlock) structurally parse every row; rows that fail to
         parse don't survive to this point.
      2. Execution check: run_expert_trajectory (AgentBlock) actually calls
         the live MCP Gateway tools -- a trace with no real tool execution
         wouldn't exist in the output.
      3. Semantic check: score_question_quality / score_response_quality
         (StreamingLLMChatBlock judges) plus their ColumnValueFilterBlock
         gates already dropped rows below the configured quality thresholds,
         and the tool-coverage rejection-sampling gate (04-LEARNINGS.md,
         2026-10-09) additionally verifies every intended tool was called.

    So this function is now a pass-through (load rows, write them to
    output_dir unchanged) rather than a second quality-filtering pass --
    kept as its own function/call site so Step 2 (column mapping) and Step 3
    (OSFT validation + delivery) below don't need to change, and so a real
    second-stage check can be reintroduced here later without touching the
    rest of the pipeline if one is ever actually needed.
    """
    rows = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        logger.warning("No rows in %s -- skipping", input_file)
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    filtered_file = output_dir / input_file.name
    with open(filtered_file, "w") as f:
        for record in rows:
            f.write(json.dumps(record, default=str) + "\n")

    logger.info(
        "%s: %d rows passed through (quality filtering already done "
        "upstream in run-generation.py) -> %s",
        input_file.name, len(rows), filtered_file,
    )
    return rows


# ─── OSFT Validation and Serialization ─────────────────────────────────────

# Curriculum tiers whose seed-scenarios.yaml entries carry follow_up_prompts
# and so can produce a genuine multi-round sdg_hub 'turns' output. All other
# tiers (single_tool, parallel, sequential) are naturally one-exchange and
# are wrapped as a trivial 1-turn record for the multi-turn delivery file.
MULTI_TURN_TIERS = {"multi_turn", "closed_loop"}


def _to_multi_turn_trace(row: dict) -> dict:
    """Build the {turns, tools} shape serialize_multi_turn() expects.

    Rows from MULTI_TURN_TIERS carry sdg_hub's native 'turns' list when
    present. Rows from other tiers -- and multi_turn/closed_loop rows where
    sdg_hub did not populate 'turns' -- are naturally a single exchange, so
    they are wrapped as one turn. Without this wrapping, calling
    serialize_multi_turn() directly on a flat {question, tool_trace, answer,
    tools} row produces a degenerate record (system message only, no turns)
    because serialize_multi_turn() reads a 'turns' key that flat rows never
    have.

    Args:
        row: A column-mapped row (output of _map_columns), optionally
            carrying 'tier' and 'turns' passthrough keys.

    Returns:
        Dict with 'turns' (list of {question, tool_trace, answer} dicts)
        and 'tools', ready for serialize_multi_turn().
    """
    if row.get("tier") in MULTI_TURN_TIERS and row.get("turns"):
        return {"turns": row["turns"], "tools": row.get("tools", [])}
    return {
        "turns": [
            {
                "question": row["question"],
                "tool_trace": row["tool_trace"],
                "answer": row["answer"],
            }
        ],
        "tools": row.get("tools", []),
    }


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

    multi_turn_osft_errors = []
    with open(multi_turn_path, "w") as f:
        for i, row in enumerate(validated_rows):
            serialized = serialize_multi_turn(_to_multi_turn_trace(row))
            errors = validate_osft_line(serialized)
            if errors:
                multi_turn_osft_errors.append({"row": i, "errors": errors})
                logger.warning(
                    "Row %d failed multi-turn OSFT validation: %s", i, errors
                )
            f.write(json.dumps(serialized) + "\n")

    if multi_turn_osft_errors:
        logger.warning(
            "Multi-turn OSFT validation flagged %d/%d rows -- written anyway "
            "since they already passed single-turn validation; review before delivery",
            len(multi_turn_osft_errors), len(validated_rows),
        )

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
        "multi_turn_osft_flagged": len(multi_turn_osft_errors),
        "delivery_files": [str(single_turn_path), str(multi_turn_path)],
    }


# ─── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Column-map raw generation output, run automatic OSFT validation "
            "(D-04), and produce dual-format delivery JSONL."
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
    logger.info("=== Step 1: Load Raw Generation Output (quality-filtered upstream) ===")
    all_filtered_rows: list[dict] = []
    input_count = 0

    for input_file in input_files:
        row_count = sum(1 for line in input_file.open() if line.strip())
        input_count += row_count

        filtered = _run_evaluation_flow(input_file, output_dir)
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

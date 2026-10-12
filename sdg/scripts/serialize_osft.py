#!/usr/bin/env python3
"""OSFT JSONL serializer for sdg_hub tool-calling traces.

Converts sdg_hub pipeline output (tool-calling traces as dicts) into
Training Hub's OSFT-compatible JSONL format with proper messages arrays,
tool_calls, and tool_call_id threading.

Supports both single-turn and multi-turn trajectory formats (D-20).
Prefers original tool_call_ids from the teacher model's trace when
available, falling back to synthetic UUIDs only if absent.

OSFT JSONL schema is sourced from Training Hub's documented
messages/tool_calls/tool_call_id structure (D-18).

Usage:
    python -m sdg.scripts.serialize_osft \\
        --input traces.jsonl \\
        --output-dir output/ \\
        --format both
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from sdg.lib.osft_validation import validate_tool_trace_outputs

logger = logging.getLogger(__name__)


def _build_system_message(tools: list[dict]) -> dict:
    """Build system message containing tool schemas."""
    tools_json = json.dumps(tools, indent=2)
    content = (
        "You are a telecom NOC fault prediction assistant with access to "
        "the following tools:\n\n"
        f"<tools>\n{tools_json}\n</tools>"
    )
    return {"role": "system", "content": content}


def _unwrapped_tool_trace(tool_trace: list[dict]) -> list[dict]:
    """Return tool_trace with each entry's output pre-unwrapped for validation.

    validate_tool_trace_outputs expects the real backend payload, not the raw
    agent-framework wrapper -- apply the same extraction serialization uses
    so validation checks what will actually land in the training data.
    """
    return [
        {**entry, "output": _extract_tool_output_content(entry.get("output", {}))}
        for entry in tool_trace
    ]


def _make_call_id(tool_entry: dict) -> str:
    """Return original tool_call_id if present, else generate a synthetic one."""
    if "id" in tool_entry:
        return tool_entry["id"]
    return f"call_{uuid.uuid4().hex[:12]}"


def _extract_tool_output_content(output: object) -> str:
    """Extract the real tool-response payload from a trace entry's output.

    sdg_hub's normalize_tool_trace() (Legacy Langflow format) passes the raw
    LangChain ToolMessage dict through unchanged: {content, additional_kwargs,
    response_metadata, artifact, tool_call_id, status}. Only `content` (or,
    equivalently, `artifact.structuredContent.result`) is the actual backend
    response; the rest is transport bookkeeping with no training signal and
    must not end up in the OSFT tool message's content.
    """
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        if "content" in output:
            content = output["content"]
            return content if isinstance(content, str) else json.dumps(content)
        artifact = output.get("artifact")
        if isinstance(artifact, dict):
            structured = artifact.get("structuredContent")
            if isinstance(structured, dict) and "result" in structured:
                result = structured["result"]
                return result if isinstance(result, str) else json.dumps(result)
    return json.dumps(output)


def _serialize_turn(turn: dict) -> tuple[list[dict], list[dict]]:
    """Serialize a single turn into (assistant+tool messages, []).

    Returns a list of messages for one user turn:
      user, assistant(tool_calls), tool..., assistant(answer)
    """
    question = turn.get("question", "")
    tool_trace = turn.get("tool_trace") or []
    answer = turn.get("answer", "")

    if not tool_trace:
        raise ValueError("Trace has no tool calls")

    messages: list[dict] = []

    # User message
    messages.append({"role": "user", "content": question})

    # Determine call IDs and build tool_calls array
    tool_calls = []
    call_ids = []
    for entry in tool_trace:
        call_id = _make_call_id(entry)
        call_ids.append(call_id)
        tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "arguments": json.dumps(entry.get("input", {})),
                },
            }
        )

    # Assistant message with tool_calls
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
    )

    # Tool response messages
    for i, entry in enumerate(tool_trace):
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_ids[i],
                "content": _extract_tool_output_content(entry.get("output", {})),
            }
        )

    # Final assistant message with answer
    messages.append({"role": "assistant", "content": answer})

    return messages, tool_calls


def serialize_single_turn(trace: dict) -> dict:
    """Serialize a single-turn trace to OSFT JSONL format.

    Args:
        trace: Dict with keys: question, tool_trace, answer, tools.
            tool_trace is a list of dicts with name, input, output,
            and optionally 'id' (original teacher model tool_call_id).

    Returns:
        Dict with 'messages' key containing the OSFT messages array:
        [system, user, assistant(tool_calls), tool..., assistant(answer)]

    Raises:
        ValueError: If trace has no tool calls.
    """
    tool_trace = trace.get("tool_trace") or []
    if not tool_trace:
        raise ValueError("Trace has no tool calls")

    tools = trace.get("tools", [])
    system_msg = _build_system_message(tools)

    turn_messages, _ = _serialize_turn(trace)

    return {"messages": [system_msg] + turn_messages}


def serialize_multi_turn(trace: dict) -> dict:
    """Serialize a multi-turn trace to OSFT JSONL format.

    Args:
        trace: Dict with keys: turns (list of turn dicts), tools.
            Each turn has: question, tool_trace, answer.

    Returns:
        Dict with 'messages' key containing the OSFT messages array
        with multiple user/assistant/tool rounds sharing one system message.

    Raises:
        ValueError: If any turn has no tool calls.
    """
    turns = trace.get("turns", [])
    tools = trace.get("tools", [])
    system_msg = _build_system_message(tools)

    all_messages = [system_msg]
    for turn in turns:
        turn_messages, _ = _serialize_turn(turn)
        all_messages.extend(turn_messages)

    return {"messages": all_messages}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert sdg_hub traces to OSFT JSONL format.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSONL file containing sdg_hub traces.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write output JSONL files.",
    )
    parser.add_argument(
        "--format",
        choices=["single-turn", "multi-turn", "both"],
        default="both",
        help="Output format: single-turn, multi-turn, or both (default: both).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for OSFT serialization."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    traces: list[dict] = []
    with input_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                traces.append(json.loads(line))

    if args.format in ("single-turn", "both"):
        out_path = output_dir / "single_turn.jsonl"
        written, rejected = 0, 0
        with out_path.open("w") as f:
            for trace in traces:
                unwrapped = _unwrapped_tool_trace(trace.get("tool_trace") or [])
                schema_errors = validate_tool_trace_outputs(unwrapped)
                if schema_errors:
                    rejected += 1
                    logger.warning(
                        "Rejecting trace (tool output fails schema validation): %s",
                        "; ".join(schema_errors),
                    )
                    continue
                result = serialize_single_turn(trace)
                f.write(json.dumps(result) + "\n")
                written += 1
        logger.info("single-turn: %d written, %d rejected (schema validation)", written, rejected)

    if args.format in ("multi-turn", "both"):
        out_path = output_dir / "multi_turn.jsonl"
        written, rejected = 0, 0
        with out_path.open("w") as f:
            for trace in traces:
                schema_errors = []
                for turn in trace.get("turns", []):
                    unwrapped = _unwrapped_tool_trace(turn.get("tool_trace") or [])
                    schema_errors.extend(validate_tool_trace_outputs(unwrapped))
                if schema_errors:
                    rejected += 1
                    logger.warning(
                        "Rejecting trace (tool output fails schema validation): %s",
                        "; ".join(schema_errors),
                    )
                    continue
                result = serialize_multi_turn(trace)
                f.write(json.dumps(result) + "\n")
                written += 1
        logger.info("multi-turn: %d written, %d rejected (schema validation)", written, rejected)


if __name__ == "__main__":
    main()

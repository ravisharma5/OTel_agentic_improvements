#!/usr/bin/env python3
"""OSFT JSONL serializer for sdg_hub tool-calling traces.

Converts sdg_hub pipeline output (tool-calling traces as dicts) into
Training Hub's OSFT-compatible JSONL format with proper messages arrays,
tool_calls, and tool_call_id threading.

Supports both single-turn and multi-turn trajectory formats (D-20).
Prefers original tool_call_ids from the teacher model's trace when
available, falling back to deterministic content-derived IDs if absent.

Each agent step becomes its own assistant message followed by that step's
tool results, so a call never appears to use a result the agent had not seen
yet (see _group_into_steps).

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
import hashlib
import json
import logging
import re
import sys
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


def _make_call_id(
    tool_entry: dict, turn_index: int = 0, call_index: int = 0, question: str = ""
) -> str:
    """Return the original tool_call_id if present, else a deterministic one.

    The fallback is derived from the call's position and content, so
    re-serializing the same trace produces identical output (a random uuid4
    made every rebuild differ and dataset diffs useless). call_index keeps
    IDs unique within a conversation even for repeated identical calls.
    """
    if "id" in tool_entry:
        return tool_entry["id"]
    key = json.dumps(
        [question, turn_index, call_index, tool_entry.get("name"), tool_entry.get("input", {})],
        sort_keys=True,
        default=str,
    )
    return "call_" + hashlib.sha256(key.encode()).hexdigest()[:12]


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


# Phrases emitted when a tool call times out: mcp-telecom ("... timed out
# after 30s"), the MCP Python SDK ("Timed out while waiting for response to
# ClientRequest"), and httpx (ReadTimeout / ConnectTimeout).
_TIMEOUT_PATTERN = re.compile(
    r"timed out|\b(?:read|connect|write|pool)timeout\b|\btimeouterror\b|deadline exceeded",
    re.IGNORECASE,
)
_ERROR_PATTERN = re.compile(r"\b(?:error|exception|traceback)\b|not installed", re.IGNORECASE)
# Real payloads (router logs, show output) can mention "timed out" or "error"
# in passing; failure messages are short. Longer results are always "ok".
_STATUS_MAX_CHARS = 1000


def tool_result_status(output: object) -> str:
    """Classify a tool result as "timeout", "error", or "ok".

    Tool frameworks report MCP failures as ordinary results (LangChain's
    ToolMessage.status is "success" even for error text), so this classifies
    the payload itself. Only "timeout" is acted on (see row_timeout_count):
    an error is a real tool response the agent should learn to handle, while
    a timeout carries no information and the agent's answer tends to guess.
    """
    content = _extract_tool_output_content(output).strip()
    if not content or len(content) > _STATUS_MAX_CHARS:
        return "ok"
    if _TIMEOUT_PATTERN.search(content):
        return "timeout"
    if _ERROR_PATTERN.search(content.split("\n", 1)[0]):
        return "error"
    return "ok"


def row_timeout_count(trace: dict) -> int:
    """Number of timed-out tool results in a flat trace or a multi-turn trace."""
    turns = trace.get("turns") or [trace]
    return sum(
        tool_result_status(entry.get("output", {})) == "timeout"
        for turn in turns
        for entry in (turn.get("tool_trace") or [])
        if isinstance(entry, dict)
    )


def _group_into_steps(tool_trace: list[dict]) -> list[list[dict]]:
    """Split a turn's tool calls into agent steps, preserving order.

    Consecutive entries with the same ``step`` value were issued together in
    one agent step (parallel calls) and share an assistant message. Entries
    without ``step`` each form their own step: the agent trace keeps call ->
    result order but not which calls were issued together, and batching them
    all would show later calls using results the agent had not seen yet.
    """
    steps: list[list[dict]] = []
    for entry in tool_trace:
        step = entry.get("step")
        if steps and step is not None and steps[-1][-1].get("step") == step:
            steps[-1].append(entry)
        else:
            steps.append([entry])
    return steps


def _serialize_turn(turn: dict, turn_index: int = 0) -> tuple[list[dict], list[dict]]:
    """Serialize a single turn into (assistant+tool messages, []).

    Returns a list of messages for one user turn:
      user, [assistant(tool_calls), tool...] per step, assistant(answer)

    A turn with no tool calls is valid in a genuine multi-turn conversation
    (e.g. the agent asking a clarifying question, or answering directly from
    context already established in an earlier turn) -- confirmed live,
    2026-10-15: a real multiturn_analytics_interface_followup conversation's
    third turn ("Is there an alarm associated with this interface?") had the
    agent correctly ask which interface, with zero new tool calls, rather
    than hallucinating one. Only serialize_single_turn() enforces "must have
    at least one tool call" (via its own separate check before calling this
    function) -- that's the right bar for a standalone single-turn example,
    but not for one turn inside a longer conversation that demonstrates
    multi-turn tool use overall.
    """
    question = turn.get("question", "")
    tool_trace = turn.get("tool_trace") or []
    answer = turn.get("answer", "")

    messages: list[dict] = []

    # User message
    messages.append({"role": "user", "content": question})

    if not tool_trace:
        messages.append({"role": "assistant", "content": answer})
        return messages, []

    all_tool_calls: list[dict] = []
    call_index = 0
    for step in _group_into_steps(tool_trace):
        step_calls = []
        for entry in step:
            step_calls.append(
                {
                    "id": _make_call_id(entry, turn_index, call_index, question),
                    "type": "function",
                    "function": {
                        "name": entry["name"],
                        "arguments": json.dumps(entry.get("input", {})),
                    },
                }
            )
            call_index += 1

        messages.append({"role": "assistant", "content": None, "tool_calls": step_calls})
        for entry, call in zip(step, step_calls):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": _extract_tool_output_content(entry.get("output", {})),
                }
            )
        all_tool_calls.extend(step_calls)

    # Final assistant message with answer
    messages.append({"role": "assistant", "content": answer})

    return messages, all_tool_calls


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
    for turn_index, turn in enumerate(turns):
        turn_messages, _ = _serialize_turn(turn, turn_index)
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
    parser.add_argument(
        "--keep-timeouts",
        action="store_true",
        help="Serialize traces containing a timed-out tool result instead of skipping them.",
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

    if not args.keep_timeouts:
        timed_out = [t for t in traces if row_timeout_count(t)]
        traces = [t for t in traces if not row_timeout_count(t)]
        logger.info(
            "Skipping %d trace(s) containing a timed-out tool result (--keep-timeouts to include)",
            len(timed_out),
        )

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

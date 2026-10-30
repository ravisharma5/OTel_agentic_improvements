"""Tool-call trace normalization, vendored from sdg_hub's own reference example.

Source: https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub/blob/main/examples/agentic/mcp_distillation_evaluation/eval_utils.py
License: Apache-2.0 (sdg_hub)

Not part of the installed sdg_hub==0.9.4 package's importable API -- this is
example/notebook code in the upstream repo, not a package module -- so it's
vendored here rather than imported, with only the two functions actually
needed (normalize_tool_trace, extract_tool_names). Used by
tool_coverage_report.py to determine which tools a generated trajectory
actually called, for comparison against each seed scenario's intended
tool_subset (sdg/config/seed-scenarios.yaml).
"""
from __future__ import annotations

import json


def normalize_tool_trace(raw_trace: list[dict] | str) -> list[dict]:
    """Normalize a tool trace to canonical format.

    Canonical format: ``[{"name": ..., "input": ..., "output": ...}, ...]``

    Handles three formats:
    - Standardized (ChatAgentResponse): ``{"role": "assistant", "tool_calls": [{"function": {"name": ..., "arguments": ...}}]}`` + ``{"role": "tool", ...}``
    - Legacy LangGraph: ``{"type": "tool_use", "tool_calls": [...]}`` + ``{"type": "tool_result", ...}``
    - Legacy Langflow:  ``{"type": "tool_use", "name": ..., "tool_input": ..., "output": ...}``

    Strips UI metadata (duration, header, icon) and text-type entries.
    """
    if isinstance(raw_trace, str):
        raw_trace = json.loads(raw_trace)
    if not isinstance(raw_trace, list):
        return []

    cleaned: list[dict] = []
    pending: dict[str, dict] = {}  # tool_call id -> call dict
    for entry in raw_trace:
        if not isinstance(entry, dict):
            continue

        # Standardized format (ChatAgentResponse.model_dump())
        if entry.get("role") == "assistant" and entry.get("tool_calls"):
            for tc in entry["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                call: dict = {
                    "name": func.get("name", ""),
                    "input": args,
                }
                tc_id = tc.get("id")
                if tc_id:
                    pending[tc_id] = call
                cleaned.append(call)

        elif entry.get("role") == "tool":
            tc_id = entry.get("tool_call_id")
            content = entry.get("content", "")
            # The raw content is a JSON-encoded LangChain ToolMessage dict, not
            # the bare backend response. Parse one level so serialize_osft's
            # _extract_tool_output_content() can strip the transport
            # bookkeeping instead of short-circuiting on a string. Plain-text
            # content (e.g. a tool error) is kept as-is. Ported from the shared
            # repo's 58912af (#1 follow-up), which main had never received.
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    pass
            if tc_id and tc_id in pending:
                pending[tc_id]["output"] = content
            elif cleaned and "output" not in cleaned[-1]:
                cleaned[-1]["output"] = content

        # Legacy format: type == "tool_use"
        elif entry.get("type") == "tool_use":
            if "tool_calls" in entry:
                for tc in entry["tool_calls"]:
                    call = {
                        "name": tc.get("name", ""),
                        "input": tc.get("args", {}),
                    }
                    tc_id = tc.get("id")
                    if tc_id:
                        pending[tc_id] = call
                    cleaned.append(call)
            elif "name" in entry:
                step: dict = {
                    "name": entry["name"],
                    "input": entry.get("tool_input", {}),
                }
                if entry.get("output"):
                    step["output"] = entry["output"]
                cleaned.append(step)

        elif entry.get("type") == "tool_result":
            tc_id = entry.get("tool_call_id") or entry.get("id")
            if tc_id and tc_id in pending:
                pending[tc_id]["output"] = entry.get("content", "")
            elif cleaned and "output" not in cleaned[-1]:
                cleaned[-1]["output"] = entry.get("content", "")

    return cleaned


def extract_tool_names(trace: list[dict]) -> list[str]:
    """Extract ordered list of tool names from a canonical trace."""
    return [step["name"] for step in trace if "name" in step]


# Column name sdg_hub's AgentResponseExtractorBlock produces when
# extract_tool_trace=True on a block named "extract_agent_text" (the
# "MCP Server Distillation" flow's naming convention: {block_name}_tool_trace,
# matching the observed {block_name}_text pattern for extract_text=True).
# Confirmed empirically against a completed real run (2026-10-09 dry-run).
DEFAULT_TRACE_COLUMN = "extract_agent_text_tool_trace"


def find_trace_column(row: dict, preferred: str = DEFAULT_TRACE_COLUMN) -> str | None:
    """Return the column name actually holding the tool trace for this row.

    Tries the preferred name first, then falls back to any column whose
    name contains both 'tool' and 'trace' -- defensive against the exact
    sdg_hub output column name differing from what's assumed above.
    """
    if preferred in row:
        return preferred
    for key in row:
        lk = key.lower()
        if "tool" in lk and "trace" in lk:
            return key
    return None


def tools_called_in_row(row: dict, trace_column: str = DEFAULT_TRACE_COLUMN) -> list[str]:
    """Extract the list of tool names actually called in a generated row."""
    col = find_trace_column(row, trace_column)
    if col is None:
        return []
    raw_trace = row.get(col)
    if not raw_trace:
        return []
    return extract_tool_names(normalize_tool_trace(raw_trace))


def row_passes_tool_coverage(row: dict, trace_column: str = DEFAULT_TRACE_COLUMN) -> bool:
    """True if every tool in row['intended_tools'] was actually called.

    Rows without an intended_tools list (no ground truth to gate against --
    e.g. organic/LLM-generated scenarios outside the hand-curated set) pass
    by default; this gate only applies where materialize_seeds.py carried an
    intended_tools passthrough column from seed-scenarios.yaml's tool_subset.
    Used by run-generation.py's rejection-sampling retry loop (see
    04-LEARNINGS.md, 2026-10-09 decision: self-distillation's quality filters
    score narrative quality, not tool-selection correctness, so this gate is
    the mechanism that actually screens for telecom-domain tool judgment).
    """
    intended = set(row.get("intended_tools") or [])
    if not intended:
        return True
    called = set(tools_called_in_row(row, trace_column))
    return intended.issubset(called)

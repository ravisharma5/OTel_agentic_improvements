"""Repo-local sdg_hub blocks used by sdg/flows/mcp_distillation_v2/flow.yaml.

Registered with sdg_hub's BlockRegistry on import, so import this module
before Flow.from_yaml() (run-generation.py does). The installed sdg_hub
package is not modified.

- ToolTraceRendererBlock: renders the agent's tool calls, tool results and
  final answer as plain text for the response judge. The stock flow passes
  only the final answer (extract_agent_text_text), so the judge cannot see
  whether the answer's values came from a tool result or were made up
  (run/model_eval/teacher_judge/REPORT.md: hallucinations caught 0-1/6
  without the trace, 4-6/6 with it).
- ToolNameCleanerBlock: the teacher sometimes writes arguments inside the
  <tool> tags (``<tool>tmf642listAlarm(severity=major)</tool>``). Reduce
  every entry to the bare tool name before the judges see it.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Optional, cast

import pandas as pd
from pydantic import Field

from sdg_hub.core.blocks.base import BaseBlock
from sdg_hub.core.blocks.registry import BlockRegistry

from sdg.lib.trace_utils import normalize_tool_trace

# ─── Tool trace rendering ───────────────────────────────────────────────────


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def unwrap_tool_output(output: Any) -> str:
    """Return the real tool payload as text.

    Langflow hands each tool result over as a JSON string of a LangChain
    ToolMessage ({content, additional_kwargs, artifact, ...}); the payload
    is its ``content``. Same rule as serialize_osft._extract_tool_output_content
    (reused so the judge sees what lands in the training row).
    """
    from sdg.scripts.serialize_osft import _extract_tool_output_content

    if _is_missing(output):
        return ""
    return _extract_tool_output_content(output)


_REPEAT_RUN = re.compile(r"(\S)\1{19,}")


def collapse_repeats(text: str) -> str:
    """Shorten separator runs (the gateway's 500-char '=====' banners) to 10
    characters so they don't use up the truncation budget."""
    return _REPEAT_RUN.sub(lambda m: m.group(1) * 10, text)


def truncate_middle(text: str, limit: int) -> str:
    """Keep the head and tail of ``text`` so it fits in ``limit`` characters."""
    if limit <= 0 or len(text) <= limit:
        return text
    marker = f"\n... [{len(text) - limit} characters truncated] ...\n"
    keep = max(limit - len(marker), 0)
    head = keep * 2 // 3
    tail = keep - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def render_tool_trace(
    raw_trace: Any,
    final_answer: Any,
    max_result_chars: int = 2000,
    max_total_chars: int = 40000,
) -> str:
    """Render a tool trace plus the final answer as judge-readable text.

    Format (one block per call)::

        [assistant tool_call 1] tmf642listAlarm({"severity": "major"})
        [tool result 1]
        <payload, head+tail truncated to max_result_chars>
        ...
        [assistant final answer]
        <answer, never truncated>

    If the rendered calls exceed ``max_total_chars`` the per-result limit is
    lowered until they fit (the final answer always stays complete).
    """
    trace: list[dict] = []
    if not _is_missing(raw_trace):
        try:
            trace = normalize_tool_trace(raw_trace)
        except (ValueError, TypeError):
            trace = []
    answer = "" if _is_missing(final_answer) else str(final_answer)

    def _calls(limit: int) -> list[str]:
        parts = []
        for i, step in enumerate(trace, 1):
            args = step.get("input", {})
            args_txt = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
            parts.append(f"[assistant tool_call {i}] {step.get('name') or '?'}({args_txt})")
            if "output" in step:
                out = collapse_repeats(unwrap_tool_output(step.get("output")))
                parts.append(f"[tool result {i}]\n{truncate_middle(out, limit) if out else '(empty)'}")
            else:
                parts.append(f"[tool result {i}]\n(no result recorded)")
        return parts

    if not trace:
        body = ["(the assistant made no tool calls)"]
    else:
        limit = max_result_chars
        body = _calls(limit)
        while limit > 200 and sum(len(p) + 1 for p in body) > max_total_chars:
            limit //= 2
            body = _calls(limit)
    return "\n".join(body + ["[assistant final answer]", answer])


@BlockRegistry.register(
    "ToolTraceRendererBlock",
    "transform",
    "Renders an agent tool trace + final answer as text (repo-local, sdg/lib/flow_blocks.py)",
)
class ToolTraceRendererBlock(BaseBlock):
    """input_cols: [final-answer column]; trace_col is optional (rows with no
    tool calls have no trace column at all after AgentResponseExtractorBlock)."""

    block_type: str = "transform"
    trace_col: str = Field(..., description="Column with the raw tool trace")
    max_result_chars: int = Field(2000, description="Per tool result character cap")
    max_total_chars: int = Field(40000, description="Cap for all calls+results together")

    def generate(self, samples: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        answer_col = cast(list[str], self.input_cols)[0]
        out_col = cast(list[str], self.output_cols)[0]
        result = samples.copy()
        traces = result[self.trace_col] if self.trace_col in result.columns else [None] * len(result)
        result[out_col] = [
            render_tool_trace(t, a, self.max_result_chars, self.max_total_chars)
            for t, a in zip(traces, result[answer_col])
        ]
        return result


# ─── Target tool cleaning ───────────────────────────────────────────────────

_TOOL_TAG = re.compile(r"<tool>(.*?)</tool>", re.DOTALL)
_TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*")


def bare_tool_name(entry: str) -> Optional[str]:
    """``tmf642listAlarm(severity=major)`` -> ``tmf642listAlarm``."""
    m = _TOOL_NAME.search(entry.strip().strip("`'\""))
    return m.group(0) if m else None


def clean_target_tools(value: Any) -> str:
    """Rewrite every <tool>...</tool> entry to the bare tool name.

    Without <tool> tags, parenthesised argument lists are dropped instead.
    """
    if _is_missing(value):
        return ""
    text = str(value)
    if _TOOL_TAG.search(text):
        names = [bare_tool_name(m) for m in _TOOL_TAG.findall(text)]
        return "\n".join(f"<tool>{n}</tool>" for n in names if n)
    return re.sub(r"\([^)]*\)", "", text).strip()


def target_tool_names(value: Any) -> list[str]:
    """Bare tool names listed in a target_tools string, in order."""
    return [n for n in (bare_tool_name(m) for m in _TOOL_TAG.findall(clean_target_tools(value))) if n]


@BlockRegistry.register(
    "ToolNameCleanerBlock",
    "transform",
    "Strips arguments from <tool> tags in a target-tools column (repo-local, sdg/lib/flow_blocks.py)",
)
class ToolNameCleanerBlock(BaseBlock):
    block_type: str = "transform"

    def generate(self, samples: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        in_col = cast(list[str], self.input_cols)[0]
        out_col = cast(list[str], self.output_cols)[0]
        result = samples.copy()
        result[out_col] = [clean_target_tools(v) for v in result[in_col]]
        return result

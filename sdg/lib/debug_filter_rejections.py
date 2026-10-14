"""Diagnostic logging for ColumnValueFilterBlock rejections.

Background: 2026-10-13/14 live investigation found 10 of 11 single_tool
scenarios reproducibly failing across 3 separate pipeline runs (rmkn2,
dnmnd, 69gx8) -- traced via full executor logs to filter_incomplete_responses
(a ColumnValueFilterBlock checking completeness_rating) dropping 19-20
surviving rows to exactly 0, every time, for every failing scenario, while
manual direct tests of the same tool categories (telecom, CAMARA) via the
Agent's own /api/v1/run endpoint produced clean, complete responses --
ruling out a general model/backend capability problem.

sdg_hub's block-level logging (core/flow/execution.py's rich row/column-count
panels) never surfaces the actual column VALUES that caused a row to be
filtered, and rows that get filtered to 0 never reach checkpointing (which
only saves a chunk's output AFTER all 22 blocks, including this one, have
run) -- so there was no way to see what completeness_rating value the
responses were actually getting, or what the generated question/response
text looked like, without this.

Same monkey-patch-and-re-register pattern as streaming_llm_chat_block.py:
subclass the stock block, re-register under the same BlockRegistry name so
the vendored flow.yaml (block_type: ColumnValueFilterBlock) picks this up
with no fork of that file needed. Logs at INFO level (visible directly in
`oc logs`, no extra S3 artifact download needed) whenever filtering drops
the dataset to zero rows -- the message that WARNING-logs
"Tier '%s' attempt %d/%d: a chunk was filtered to zero rows..." in
run-generation.py is the symptom; this is the detail needed to diagnose it.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from sdg_hub.core.blocks.filtering.column_value_filter import ColumnValueFilterBlock
from sdg_hub.core.blocks.registry import BlockRegistry

logger = logging.getLogger(__name__)

# Columns worth showing when a row gets rejected, in priority order -- not
# every block's input has all of these, so each is included only if present.
_DIAGNOSTIC_COLUMNS = [
    "scenario_name",
    "question",
    "extract_agent_text_text",
    "extract_agent_text_tool_trace",
    "target_tools",
    "intended_tools",
]


class DiagnosticColumnValueFilterBlock(ColumnValueFilterBlock):
    """ColumnValueFilterBlock that logs rejected rows' diagnostic content
    when filtering drops the dataset to zero rows."""

    def generate(self, samples: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        result = super().generate(samples, **kwargs)

        if len(result) == 0 and len(samples) > 0:
            logger.info(
                "DIAGNOSTIC: %s dropped all %d row(s) to 0 (column=%r, "
                "filter_value=%r, operation=%r). Rejected row values:",
                self.block_name, len(samples), self.column_name,
                self.filter_value, self.operation,
            )
            # Cap at 5 rows to avoid flooding logs for a 20-row chunk --
            # the point is to see the pattern, not every row.
            for _, row in samples.head(5).iterrows():
                rating_value = row.get(self.column_name)
                details = {"__filter_column__": rating_value}
                for col in _DIAGNOSTIC_COLUMNS:
                    if col in row.index:
                        value = row[col]
                        # Truncate long text fields so one row doesn't dominate
                        # the log; full content is rarely needed to spot a
                        # pattern across several rejected rows.
                        if isinstance(value, str) and len(value) > 500:
                            value = value[:500] + "...[truncated]"
                        details[col] = value
                logger.info("  %s", details)

        return result


def patch_column_value_filter_for_diagnostics() -> None:
    """Re-register DiagnosticColumnValueFilterBlock under the stock
    "ColumnValueFilterBlock" name.

    Call this once, before FlowRegistry.discover_flows()/Flow.from_yaml(),
    matching patch_llm_chat_block_for_streaming()'s pattern -- any flow.yaml
    referencing block_type: ColumnValueFilterBlock resolves to this
    diagnostics-aware class instead, no fork of that file needed.
    """
    BlockRegistry.register(
        "ColumnValueFilterBlock",
        "filtering",
        "Filters datasets based on column values using various comparison "
        "operations (patched: logs rejected rows' diagnostic content when "
        "filtering drops a chunk to zero rows -- see debug_filter_rejections.py)",
    )(DiagnosticColumnValueFilterBlock)

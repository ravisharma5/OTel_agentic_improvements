"""Isolate per-row agent failures in sdg_hub's AgentBlock (2026-10-19).

Stock AgentBlock._process_row_async lets any connector exception escape.
asyncio.as_completed then aborts the whole batch, and the flow fails the tier.
In fleet run verify1, one gpt-6-1-sol request that hit `context_length_exceeded`
(HTTP 500 from Langflow) threw away the entire multi_turn_P tier.

patch_agent_block_row_isolation() wraps that method. A ConnectorError
(HTTP 4xx/5xx after the retrying client gave up, timeouts, connection errors)
for ONE row is logged and returns (idx, None) for that row.
AgentResponseExtractorBlock already treats a non-dict response as "no data"
and drops the row, so the batch keeps going and the coverage gate resamples
the scenario as usual. Other exceptions (bugs) still propagate.

Set SDG_AGENT_ROW_ISOLATION=0 to disable. Idempotent. The installed package is
not modified.
"""
from __future__ import annotations

import functools
import logging
import os

logger = logging.getLogger(__name__)
_FLAG = "_sdg_row_isolation"
_STATS = {"isolated": 0}


def isolated_failures() -> int:
    return _STATS["isolated"]


def patch_agent_block_row_isolation() -> bool:
    if os.environ.get("SDG_AGENT_ROW_ISOLATION", "1") == "0":
        return False
    from sdg_hub.core.blocks.agent.agent_block import AgentBlock
    from sdg_hub.core.connectors.exceptions import ConnectorError

    original = AgentBlock._process_row_async
    if getattr(original, _FLAG, False):
        return True

    @functools.wraps(original)
    async def _process_row_async(self, row, idx, connector, messages_col, semaphore):
        try:
            return await original(self, row, idx, connector, messages_col, semaphore)
        except ConnectorError as exc:
            _STATS["isolated"] += 1
            logger.warning(
                "AgentBlock '%s': row %s failed and was dropped (%d so far this process): %s",
                self.block_name, idx, _STATS["isolated"], str(exc)[:300],
            )
            return idx, None

    setattr(_process_row_async, _FLAG, True)
    AgentBlock._process_row_async = _process_row_async
    return True

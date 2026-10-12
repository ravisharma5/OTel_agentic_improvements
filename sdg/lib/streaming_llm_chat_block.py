"""Streaming-aware LLMChatBlock to work around an AWS ELB idle-connection timeout.

Background: the MaaS model endpoint sits behind an AWS Classic ELB. Non-
streaming chat/completions calls send zero bytes back to the client until
the full response is generated. At vLLM's measured live throughput
(10-37 tok/s under this deployment's current config) plus the long system
prompt in sdg_hub's question_quality_check.yaml, time-to-first-byte
regularly exceeded even a raised 300s ELB idle timeout, causing a
litellm.Timeout wrapping an HTML "504 Gateway Time-out" response -- this
was confirmed live, not assumed (checked and ruled out every layer from the
HTTPRoute down to the real AWS ELB attributes before concluding this).

sdg_hub==0.9.4's stock LLMChatBlock (core/blocks/llm/llm_chat_block.py)
has no code path to consume a streamed completion -- `_make_acompletion`
does `response = await acompletion(...)` and immediately accesses
`response.choices[0].message`, which does not exist on a stream object.
Setting stream=True via model_config alone would break every LLMChatBlock
in the flow, not fix the timeout.

This subclass overrides only `_make_acompletion` to request streaming
internally and reassemble the full text before handing off to the same
`_message_to_dict` the stock block already uses -- the rest of the block
(concurrency handling, batching, n>1 support if ever needed) is untouched.
Streaming means bytes start flowing within a few seconds of the first
generated token, keeping the connection active from the ELB's perspective
regardless of total generation time -- this fixes the actual mechanism,
not just the allowed waiting window.

Re-registers under the same "LLMChatBlock" name via BlockRegistry so
sdg_hub's vendored flow.yaml (block_type: LLMChatBlock) picks this up with
no fork of that file needed -- import this module once, before loading any
flow, to apply the swap.

Known limitation: does not preserve n>1 multi-completion behavior (returns
a single choice) since none of our flow's LLMChatBlocks (generate_questions,
score_question_quality, score_response_quality) use n>1.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

from litellm import acompletion

from sdg_hub.core.blocks.llm.llm_chat_block import LLMChatBlock
from sdg_hub.core.blocks.registry import BlockRegistry


class StreamingLLMChatBlock(LLMChatBlock):
    """LLMChatBlock that always streams internally, reassembling a complete message."""

    async def _make_acompletion(
        self,
        messages: list[dict[str, Any]],
        completion_kwargs: dict[str, Any],
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> list[dict[str, Any]]:
        stream_kwargs = {**completion_kwargs, "stream": True}
        # n>1 isn't supported in this streaming path -- none of our flow's
        # LLMChatBlocks request it, but fail loudly if that ever changes
        # instead of silently returning fewer choices than requested.
        if stream_kwargs.get("n", 1) > 1:
            raise NotImplementedError(
                "StreamingLLMChatBlock does not support n>1; "
                "use the stock LLMChatBlock for multi-completion requests."
            )

        async def _consume() -> tuple[str, Optional[str]]:
            full_content = ""
            finish_reason = None
            stream = await acompletion(messages=messages, **stream_kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full_content += delta.content
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
            return full_content, finish_reason

        if semaphore:
            async with semaphore:
                full_content, finish_reason = await _consume()
        else:
            full_content, finish_reason = await _consume()

        message = SimpleNamespace(
            content=full_content,
            role="assistant",
            finish_reason=finish_reason,
        )
        return [self._message_to_dict(message)]


def patch_llm_chat_block_for_streaming() -> None:
    """Re-register StreamingLLMChatBlock under the stock "LLMChatBlock" name.

    Call this once, before FlowRegistry.discover_flows()/Flow.from_yaml(),
    so any flow.yaml referencing block_type: LLMChatBlock resolves to this
    streaming-aware class instead -- no fork of the vendored flow file needed.
    """
    BlockRegistry.register(
        "LLMChatBlock",
        "llm",
        "Unified LLM chat block supporting 100+ providers via LiteLLM "
        "(patched: streams internally to avoid an AWS ELB idle-connection "
        "timeout on long generations -- see streaming_llm_chat_block.py)",
    )(StreamingLLMChatBlock)

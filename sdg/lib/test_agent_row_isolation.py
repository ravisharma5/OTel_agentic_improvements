import asyncio

import pandas as pd
import pytest

from sdg.lib import agent_row_isolation as iso


class _Connector:
    """Fails rows whose message says 'boom'; answers the rest."""

    async def asend(self, request):
        from sdg_hub.core.connectors.exceptions import ConnectorError
        text = request.messages[-1].content
        if "boom" in text:
            raise ConnectorError("HTTP 500 context_length_exceeded")
        from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse
        return ChatAgentResponse(messages=[ChatAgentMessage(role="assistant", content="ok:" + text, id="m1")])


def _block():
    from sdg_hub.core.blocks.agent.agent_block import AgentBlock
    return AgentBlock(block_name="run_expert_trajectory", agent_framework="langflow",
                      agent_url="http://127.0.0.1:1/x", input_cols=["q"], output_cols=["resp"],
                      async_mode=True, max_concurrency=4)


def _run(block, rows):
    df = pd.DataFrame({"q": rows})
    return asyncio.run(block._process_batch_async(df, _Connector(), "q"))


def test_unpatched_one_failure_aborts_the_batch(monkeypatch):
    from sdg_hub.core.blocks.agent.agent_block import AgentBlock
    from sdg_hub.core.connectors.exceptions import ConnectorError
    original = getattr(AgentBlock._process_row_async, "__wrapped__", AgentBlock._process_row_async)
    monkeypatch.setattr(AgentBlock, "_process_row_async", original)
    with pytest.raises(ConnectorError):
        _run(_block(), ["a", "boom", "c"])


def test_patched_failure_drops_only_that_row(monkeypatch):
    try:
        from mlflow.types.agent import ChatAgentResponse  # noqa: F401
    except ImportError:
        pytest.skip("sdg_hub message types not importable")
    assert iso.patch_agent_block_row_isolation()
    before = iso.isolated_failures()
    out = _run(_block(), ["a", "boom", "c"])
    assert out[1] is None
    assert out[0]["messages"][-1]["content"] == "ok:a" and out[2]["messages"][-1]["content"] == "ok:c"
    assert iso.isolated_failures() == before + 1


def test_patch_is_idempotent():
    assert iso.patch_agent_block_row_isolation() and iso.patch_agent_block_row_isolation()


def test_extractor_drops_none_responses():
    from sdg_hub.core.blocks.agent.agent_response_extractor_block import AgentResponseExtractorBlock
    ex = AgentResponseExtractorBlock(block_name="extract_agent_text", input_cols=["resp"], extract_text=True)
    good = {"messages": [{"role": "assistant", "content": "fine"}]}
    out = ex.generate(pd.DataFrame({"resp": [good, None]}))
    assert len(out) == 1

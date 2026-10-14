"""Retry 5xx HTTP errors from sdg_hub's HttpClient, not just connection failures.

Background: 2026-10-14 live investigation into why a single transient gateway/
Langflow blip (a node failure cascade, a WASM-plugin reload race, etc.) kept
discarding an entire multiply_tool_rows batch's worth of already-completed
run_expert_trajectory work (18-19 of 20 agent calls succeeded, the last one
hit a transient HTTP 500/503, and the whole batch's progress was lost --
checkpointing only commits after the whole chunk succeeds, see
04-LEARNINGS.md's 2026-10-14 "checkpoint granularity" entry).

Traced to sdg_hub.core.connectors.http.client.HttpClient.post()/post_sync():
both already wrap the request in a tenacity @retry with exponential backoff
and max_retries=3 by default -- the retry scaffolding sdg_hub needs for
exactly this problem already exists. But the retry predicate is
`retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))`,
which does not include httpx.HTTPStatusError at all. Every failure hit live
today (Langflow returning HTTP 500 because its own downstream MCP gateway
call failed, or a 503 from the gateway itself) is an HTTPStatusError, so
every one of them propagated on the very first attempt with zero retries,
despite the retry infrastructure being right there, unused, for this case.

Fix: retry on HTTPStatusError too, but only for 5xx (server-side, plausibly
transient) status codes -- explicitly NOT 4xx (client/validation errors,
which will fail identically on every retry and would just waste the budget
and delay surfacing a real bug). Confirmed via source inspection (installed
sdg-hub==0.9.4) that both HttpClient.post (async, what AgentBlock.send()
actually exercises even in "sync" mode -- it runs _send_async via
asyncio.run) and post_sync have the identical gap; both are patched here for
completeness.

HttpClient instances are created directly in BaseAgentConnector
._get_http_client() (HttpClient(timeout=..., max_retries=...)), not pulled
from a BlockRegistry-keyed factory, so the subclass + re-register pattern
used elsewhere in this lib/ (streaming_llm_chat_block.py,
debug_filter_rejections.py) doesn't apply here -- this patches the methods
directly on the HttpClient class, affecting every instance for the lifetime
of the process. Call once, before any connector sends a request.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from sdg_hub.core.connectors.exceptions import ConnectorError, ConnectorHTTPError
from sdg_hub.core.connectors.http.client import HttpClient

logger = logging.getLogger(__name__)


def _is_retriable(exc: BaseException) -> bool:
    """True for connection/timeout failures (already retried) and 5xx HTTP
    responses (newly retried here) -- explicitly false for 4xx, which won't
    change on retry and shouldn't burn the retry budget."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


async def _post(
    self: HttpClient,
    url: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    headers = headers or {}

    @retry(
        stop=stop_after_attempt(self.max_retries + 1),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception(_is_retriable),
        reraise=True,
    )
    async def _post_with_retry() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.debug(f"POST request to {url}")
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    try:
        return await _post_with_retry()
    except httpx.HTTPStatusError as e:
        response_text = e.response.text[:500] if e.response.text else None
        raise ConnectorHTTPError(url, e.response.status_code, response_text) from e
    except httpx.TimeoutException as e:
        raise ConnectorError(f"Request to '{url}' timed out after {self.timeout}s") from e
    except httpx.ConnectError as e:
        raise ConnectorError(f"Failed to connect to '{url}': {e}") from e


def _post_sync(
    self: HttpClient,
    url: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    headers = headers or {}

    @retry(
        stop=stop_after_attempt(self.max_retries + 1),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception(_is_retriable),
        reraise=True,
    )
    def _post_with_retry() -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            logger.debug(f"POST request to {url}")
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    try:
        return _post_with_retry()
    except httpx.HTTPStatusError as e:
        response_text = e.response.text[:500] if e.response.text else None
        raise ConnectorHTTPError(url, e.response.status_code, response_text) from e
    except httpx.TimeoutException as e:
        raise ConnectorError(f"Request to '{url}' timed out after {self.timeout}s") from e
    except httpx.ConnectError as e:
        raise ConnectorError(f"Failed to connect to '{url}': {e}") from e


def patch_http_client_for_5xx_retry() -> None:
    """Monkey-patch HttpClient.post/post_sync to retry 5xx HTTP errors.

    Call this once, before any flow sends agent/connector requests --
    matching patch_llm_chat_block_for_streaming()'s and
    patch_column_value_filter_for_diagnostics()'s call timing in
    run-generation.py.
    """
    HttpClient.post = _post
    HttpClient.post_sync = _post_sync

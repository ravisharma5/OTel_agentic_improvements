"""Tests for the 5xx-retry patch against sdg_hub's real HttpClient.

Uses the installed sdg-hub==0.9.4 package directly (not a stub) so these
tests fail loudly if a future sdg_hub version changes HttpClient's internals
in a way that breaks this patch -- the same philosophy as
test_materialize_seeds.py's "fail loud on a naming mismatch" tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sdg_hub.core.connectors.exceptions import ConnectorError, ConnectorHTTPError
from sdg_hub.core.connectors.http.client import HttpClient

from sdg.lib.retrying_http_client import _is_retriable, patch_http_client_for_5xx_retry


class TestIsRetriablePredicate:
    def test_connect_error_is_retriable(self) -> None:
        assert _is_retriable(httpx.ConnectError("boom")) is True

    def test_timeout_is_retriable(self) -> None:
        assert _is_retriable(httpx.TimeoutException("boom")) is True

    def test_5xx_status_is_retriable(self) -> None:
        response = httpx.Response(500, request=httpx.Request("POST", "http://x"))
        exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
        assert _is_retriable(exc) is True

    def test_503_status_is_retriable(self) -> None:
        response = httpx.Response(503, request=httpx.Request("POST", "http://x"))
        exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
        assert _is_retriable(exc) is True

    def test_4xx_status_is_not_retriable(self) -> None:
        """A validation error will fail identically every time -- retrying
        wastes the budget and delays surfacing a real bug."""
        response = httpx.Response(404, request=httpx.Request("POST", "http://x"))
        exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
        assert _is_retriable(exc) is False

    def test_unrelated_exception_is_not_retriable(self) -> None:
        assert _is_retriable(ValueError("unrelated")) is False


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "server error" if status_code >= 400 else ""
    resp.json.return_value = json_body or {}
    if status_code >= 400:
        request = httpx.Request("POST", "http://x")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=httpx.Response(status_code, request=request),
        )
    else:
        resp.raise_for_status.side_effect = None
    return resp


class TestPatchedPostRetriesOn5xxThenSucceeds:
    """The core regression: a transient 500 followed by a 200 must now
    succeed, where it previously raised on the first 500 with zero retries."""

    @pytest.mark.asyncio
    async def test_post_retries_past_a_single_500_and_succeeds(self) -> None:
        patch_http_client_for_5xx_retry()
        client = HttpClient(timeout=30.0, max_retries=3)

        responses = [_mock_response(500), _mock_response(200, {"result": "ok"})]
        mock_post = AsyncMock(side_effect=responses)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await client.post("http://x", {"payload": 1})

        assert result == {"result": "ok"}
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_post_gives_up_after_max_retries_exhausted(self) -> None:
        """A persistently broken backend must still fail, not retry forever --
        confirms this patch bounds retries, it doesn't remove the bound."""
        patch_http_client_for_5xx_retry()
        client = HttpClient(timeout=30.0, max_retries=2)

        mock_post = AsyncMock(side_effect=[_mock_response(500) for _ in range(5)])
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            with pytest.raises(ConnectorHTTPError, match="500"):
                await client.post("http://x", {"payload": 1})

        # max_retries=2 -> 3 total attempts (1 initial + 2 retries)
        assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_post_does_not_retry_a_4xx(self) -> None:
        """A 404/validation error must fail on the first attempt -- retrying
        a client error wastes the budget on a response that can't change."""
        patch_http_client_for_5xx_retry()
        client = HttpClient(timeout=30.0, max_retries=3)

        mock_post = AsyncMock(side_effect=[_mock_response(404)])
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            with pytest.raises(ConnectorHTTPError, match="404"):
                await client.post("http://x", {"payload": 1})

        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_error_still_retried_as_before(self) -> None:
        """Confirms the pre-existing retry behavior (connection failures)
        survives this patch unchanged."""
        patch_http_client_for_5xx_retry()
        client = HttpClient(timeout=30.0, max_retries=3)

        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(
            side_effect=[httpx.ConnectError("refused"), mock_async_client]
        )
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.post = AsyncMock(return_value=_mock_response(200, {"ok": True}))

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await client.post("http://x", {"payload": 1})

        assert result == {"ok": True}

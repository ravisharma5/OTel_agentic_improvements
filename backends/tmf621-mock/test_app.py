"""Tests for the stateful TMF621 mock, including end to end through the real
tmf621 MCP server (whose FastMCP client validates every response against the
TMF621 output schemas)."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path

import httpx2
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tmf621_mock_app", HERE / "app.py")
mock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock)

TICKET = {"@type": "TroubleTicket", "description": "Rectifier low voltage at r1",
          "severity": "Major", "ticketType": "Incident"}


@pytest.fixture(autouse=True)
def fresh_store():
    mock.store.reset()


async def _request(method: str, path: str, **kwargs) -> httpx2.Response:
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=mock.app), base_url="http://mock") as c:
        return await c.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx2.Response:
    return asyncio.run(_request(method, path, **kwargs))


def test_create_assigns_new_ids_and_retrieve_returns_it():
    first = request("POST", "/troubleTicket", json=TICKET)
    second = request("POST", "/troubleTicket", json=TICKET)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    got = request("GET", f"/troubleTicket/{first.json()['id']}").json()
    assert got["description"] == TICKET["description"]
    assert got["status"] == "acknowledged"


def test_patch_is_reflected_in_later_reads():
    ticket_id = request("POST", "/troubleTicket", json=TICKET).json()["id"]
    patched = request("PATCH", f"/troubleTicket/{ticket_id}", json={"status": "resolved", "statusChangeReason": "PSU replaced"})
    assert patched.status_code == 200
    got = request("GET", f"/troubleTicket/{ticket_id}").json()
    assert got["status"] == "resolved" and got["statusChangeReason"] == "PSU replaced"


def test_patch_cannot_change_read_only_fields_and_null_removes():
    created = request("POST", "/troubleTicket", json={**TICKET, "priority": "High"}).json()
    patched = request("PATCH", f"/troubleTicket/{created['id']}", json={"id": "x", "priority": None}).json()
    assert patched["id"] == created["id"]
    assert "priority" not in patched


def test_create_rejects_missing_mandatory_attributes():
    resp = request("POST", "/troubleTicket", json={"@type": "TroubleTicket", "description": "x"})
    assert resp.status_code == 400
    assert "severity" in resp.json()["message"] and "ticketType" in resp.json()["message"]


def test_unknown_ticket_is_404():
    assert request("GET", "/troubleTicket/999999").status_code == 404
    assert request("PATCH", "/troubleTicket/999999", json={"status": "resolved"}).status_code == 404


def test_list_is_newest_first_paged_and_projected():
    created = [request("POST", "/troubleTicket", json=TICKET).json()["id"] for _ in range(3)]
    resp = request("GET", "/troubleTicket", params={"limit": 2, "fields": "status"})
    body = resp.json()
    assert [t["id"] for t in body] == created[::-1][:2]
    assert set(body[0]) == {"id", "href", "@type", "status"}
    assert resp.headers["X-Total-Count"] == str(len(mock.SEED_TICKETS) + 3)


def test_seeds_reference_the_tmf642_mock_alarms():
    alarm_ids = {e["entity"]["id"] for t in mock.SEED_TICKETS for e in t["relatedEntity"]}
    assert alarm_ids == {"8675309", "8675399"}


def test_store_evicts_oldest_non_seed_tickets(monkeypatch):
    monkeypatch.setattr(mock, "MAX_TICKETS", len(mock.SEED_TICKETS) + 2)
    ids = [request("POST", "/troubleTicket", json=TICKET).json()["id"] for _ in range(4)]
    assert set(mock.store.tickets) == mock.store.seed_ids | set(ids[-2:])


def test_end_to_end_through_the_tmf621_mcp_server(monkeypatch):
    """create -> retrieve -> patch -> retrieve -> list via the real MCP tools."""
    from fastmcp import Client

    server_dir = HERE.parents[1] / "mcp" / "tmf621"
    monkeypatch.chdir(server_dir)
    srv_spec = importlib.util.spec_from_file_location("tmf621_server_e2e", server_dir / "server.py")
    server = importlib.util.module_from_spec(srv_spec)
    srv_spec.loader.exec_module(server)
    server.client._transport = httpx2.ASGITransport(app=mock.app)

    async def run():
        async with Client(server.mcp) as c:
            created = (await c.call_tool("createTroubleTicket", {
                "at_type": "TroubleTicket", "description": "PSU failure on r2",
                "severity": "Minor", "ticketType": "Incident",
            })).structured_content
            fetched = (await c.call_tool("retrieveTroubleTicket", {"id": created["id"]})).structured_content
            await c.call_tool("patchTroubleTicket", {"id": created["id"], "at_type": "TroubleTicket", "status": "resolved"})
            refetched = (await c.call_tool("retrieveTroubleTicket", {"id": created["id"]})).structured_content
            listed = (await c.call_tool("listTroubleTicket", {"limit": 5})).structured_content
            return created, fetched, refetched, listed

    created, fetched, refetched, listed = asyncio.run(run())
    assert created["id"] not in {s["id"] for s in mock.SEED_TICKETS}
    assert fetched["id"] == created["id"] and fetched["description"] == "PSU failure on r2"
    assert refetched["status"] == "resolved"
    newest = listed["result"][0] if "result" in listed else listed[0]
    assert newest["id"] == created["id"]

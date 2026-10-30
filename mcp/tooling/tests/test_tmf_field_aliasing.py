"""TMF servers expose "@"-prefixed fields as "at_" and fix the id__path clash.

LangChain-based MCP clients (Langflow) silently drop "@"-prefixed arguments,
and FastMCP renames a path parameter to "id__path" when the PATCH body also
has an "id". Each TMF server's customize_components() hides both from the
model and restores the real names before the request reaches the backend.
These tests load the real server.py files and drive them through FastMCP's
in-memory client against a mock backend.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import httpx2
import pytest
from fastmcp import Client

MCP_DIR = Path(__file__).resolve().parents[2]


def _load_server(name: str, monkeypatch):
    server_dir = MCP_DIR / name
    monkeypatch.chdir(server_dir)  # SPEC_PATH is relative to the server dir
    spec = importlib.util.spec_from_file_location(f"{name}_server_under_test", server_dir / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call(module, tool: str, arguments: dict, response: dict) -> tuple[dict, dict]:
    """Call `tool` and return (exposed input schema, captured backend request)."""
    captured: dict = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx2.Response(200, json=response)

    module.client._transport = httpx2.MockTransport(handler)

    async def run():
        async with Client(module.mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}
            try:
                await client.call_tool(tool, arguments)
            except Exception:
                pass  # output-schema validation against the minimal mock response
            return tools[tool].inputSchema

    return asyncio.run(run()), captured


_TICKET = {"id": "3180", "href": "/troubleTicket/3180", "@type": "TroubleTicket",
           "description": "x", "severity": "Major", "ticketType": "incident", "name": "t"}


@pytest.mark.parametrize("server", ["tmf621", "tmf628", "tmf642"])
def test_no_tool_exposes_at_prefixed_fields(server, monkeypatch):
    module = _load_server(server, monkeypatch)

    async def schemas():
        async with Client(module.mcp) as client:
            return {t.name: json.dumps(t.inputSchema) for t in await client.list_tools()}

    for name, schema in asyncio.run(schemas()).items():
        assert '"@' not in schema, f"{server}.{name} still exposes an @-prefixed field"


def test_create_ticket_restores_at_fields_including_nested(monkeypatch):
    module = _load_server("tmf621", monkeypatch)
    schema, sent = _call(module, "createTroubleTicket", {
        "description": "Rectifier low voltage", "severity": "Major", "ticketType": "incident",
        "at_type": "TroubleTicket", "note": [{"text": "seen on r1", "at_type": "Note"}],
    }, _TICKET)

    assert "at_type" in schema["required"]
    assert sent["method"] == "POST" and sent["path"] == "/troubleTicket"
    assert sent["body"]["@type"] == "TroubleTicket"
    assert sent["body"]["note"][0]["@type"] == "Note"
    assert "at_type" not in json.dumps(sent["body"])


def test_patch_ticket_routes_id_to_the_path(monkeypatch):
    module = _load_server("tmf621", monkeypatch)
    schema, sent = _call(module, "patchTroubleTicket",
                         {"id": "3180", "at_type": "TroubleTicket", "status": "resolved"}, _TICKET)

    assert "id__path" not in schema["properties"]
    assert schema["properties"]["id"]["description"].endswith("(Path parameter)")
    assert sent["method"] == "PATCH" and sent["path"] == "/troubleTicket/3180"
    assert sent["body"] == {"@type": "TroubleTicket", "status": "resolved"}


def test_retrieve_ticket_is_unchanged(monkeypatch):
    module = _load_server("tmf621", monkeypatch)
    _, sent = _call(module, "retrieveTroubleTicket", {"id": "3180"}, _TICKET)
    assert sent["method"] == "GET" and sent["path"] == "/troubleTicket/3180"


@pytest.mark.parametrize("server,tool,arguments,path,expected", [
    ("tmf642", "createHub", {"callback": "http://cb.example/x", "at_type": "Hub"},
     "/hub", {"callback": "http://cb.example/x", "@type": "Hub"}),
    ("tmf628", "createOnDemandCollection",
     {"at_type": "OnDemandCollection", "fileTransferData": [{"fileLocation": "s3://b/f", "at_type": "FileTransferData"}]},
     "/onDemandCollection",
     {"@type": "OnDemandCollection", "fileTransferData": [{"fileLocation": "s3://b/f", "@type": "FileTransferData"}]}),
])
def test_other_tmf_create_tools_restore_at_fields(server, tool, arguments, path, expected, monkeypatch):
    module = _load_server(server, monkeypatch)
    _, sent = _call(module, tool, arguments, {})
    assert sent["path"] == path
    assert sent["body"] == expected

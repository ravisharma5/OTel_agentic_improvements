"""Stateful TMF621 Trouble Ticket mock.

Prism serves the spec's static example for every call, so every create
returned ticket 3180 and updates never showed up in a later get -- a model
trained on that learns to cite 3180 and never sees its own ticket come back.
This mock keeps tickets in memory: create assigns a new id, and retrieve and
list reflect creates and patches. It implements only the operations the
tmf621 MCP server exposes.

State lives in this process, so run exactly one replica with one worker.
"""

from __future__ import annotations

import copy
import itertools
import os
from collections import OrderedDict
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

BASE_HREF = os.environ.get("TMF621_BASE_HREF", "/tmf-api/troubleTicket/v5")
MAX_TICKETS = int(os.environ.get("TMF621_MAX_TICKETS", "500"))
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
REQUIRED_ON_CREATE = ("@type", "description", "severity", "ticketType")
READ_ONLY = ("id", "href", "creationDate")

# Seeds match the TMF642 mock's alarms (8675309 rectifier low voltage on
# resource 93051825, 8675399 power supply failure on 93051831), instead of
# the spec's billing-complaint examples that made no sense in NOC traces.
SEED_TICKETS = [
    {
        "id": "4101",
        "name": "Rectifier low voltage at site ems-1",
        "description": "Major environmental alarm 8675309: rectifier reports low voltage (voltage=95).",
        "severity": "Major",
        "priority": "High",
        "ticketType": "Incident",
        "status": "inProgress",
        "@type": "TroubleTicket",
        "relatedEntity": [{
            "role": "alarm",
            "@type": "RelatedEntity",
            "entity": {"id": "8675309", "href": "/alarmManagement/v5/alarm/8675309",
                       "@type": "EntityRef", "@referredType": "Alarm"},
        }],
        "note": [{"id": "1", "author": "noc-operator", "date": "2026-10-22T05:10:00Z",
                  "text": "Field team dispatched to check rectifier module.", "@type": "Note"}],
    },
    {
        "id": "4102",
        "name": "Chassis power supply failure",
        "description": "Minor equipment alarm 8675399: power supply failure on chassis resource 93051831.",
        "severity": "Minor",
        "priority": "Medium",
        "ticketType": "Incident",
        "status": "acknowledged",
        "@type": "TroubleTicket",
        "relatedEntity": [{
            "role": "alarm",
            "@type": "RelatedEntity",
            "entity": {"id": "8675399", "href": "/alarmManagement/v5/alarm/8675399",
                       "@type": "EntityRef", "@referredType": "Alarm"},
        }],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _error(status: int, reason: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"@type": "Error", "code": str(status), "reason": reason, "message": message, "status": str(status)},
        status_code=status,
    )


def _project(ticket: dict, fields: str | None) -> dict:
    """Apply the TMF `fields` query parameter (id, href, @type always kept)."""
    if not fields:
        return ticket
    wanted = {f.strip() for f in fields.split(",") if f.strip()} | {"id", "href", "@type"}
    return {k: v for k, v in ticket.items() if k in wanted}


class TicketStore:
    """In-memory tickets, newest last; evicts the oldest non-seed past MAX_TICKETS."""

    def __init__(self) -> None:
        self.tickets: OrderedDict[str, dict] = OrderedDict()
        self.seed_ids: set[str] = set()
        self._ids = itertools.count(5001)
        self.reset()

    def reset(self) -> None:
        self.tickets.clear()
        self._ids = itertools.count(5001)
        now = _now()
        for seed in SEED_TICKETS:
            ticket = copy.deepcopy(seed)
            ticket.update(href=f"{BASE_HREF}/troubleTicket/{ticket['id']}",
                          creationDate=now, lastUpdate=now, statusChangeDate=now)
            self.tickets[ticket["id"]] = ticket
        self.seed_ids = {s["id"] for s in SEED_TICKETS}

    def create(self, body: dict) -> dict:
        ticket_id = str(next(self._ids))
        now = _now()
        ticket = {k: v for k, v in body.items() if k not in READ_ONLY}
        ticket.setdefault("status", "acknowledged")
        ticket.update(id=ticket_id, href=f"{BASE_HREF}/troubleTicket/{ticket_id}",
                      creationDate=now, lastUpdate=now, statusChangeDate=now)
        self.tickets[ticket_id] = ticket
        self._evict()
        return ticket

    def patch(self, ticket_id: str, body: dict) -> dict:
        """JSON merge patch (RFC 7386): keys replace, null removes."""
        ticket = self.tickets[ticket_id]
        now = _now()
        for key, value in body.items():
            if key in READ_ONLY:
                continue
            if value is None:
                ticket.pop(key, None)
            else:
                if key == "status" and value != ticket.get("status"):
                    ticket["statusChangeDate"] = now
                ticket[key] = value
        ticket["lastUpdate"] = now
        return ticket

    def _evict(self) -> None:
        for ticket_id in list(self.tickets):
            if len(self.tickets) <= MAX_TICKETS:
                break
            if ticket_id not in self.seed_ids:
                del self.tickets[ticket_id]


store = TicketStore()


async def _json_body(request: Request):
    try:
        return await request.json()
    except ValueError:
        return None


async def create_ticket(request: Request):
    body = await _json_body(request)
    if not isinstance(body, dict):
        return _error(400, "Invalid body", "Request body must be a JSON object.")
    missing = [f for f in REQUIRED_ON_CREATE if not body.get(f)]
    if missing:
        return _error(400, "Missing mandatory attributes", f"Missing mandatory attribute(s): {', '.join(missing)}")
    return JSONResponse(store.create(body), status_code=201)


async def list_tickets(request: Request):
    params = request.query_params
    try:
        offset = max(int(params.get("offset", 0)), 0)
        limit = min(max(int(params.get("limit", DEFAULT_LIMIT)), 0), MAX_LIMIT)
    except ValueError:
        return _error(400, "Invalid parameter", "offset and limit must be integers.")
    newest_first = list(reversed(store.tickets.values()))
    page = newest_first[offset:offset + limit]
    return JSONResponse(
        [_project(t, params.get("fields")) for t in page],
        headers={"X-Total-Count": str(len(newest_first)), "X-Result-Count": str(len(page))},
    )


async def retrieve_ticket(request: Request):
    ticket = store.tickets.get(request.path_params["id"])
    if ticket is None:
        return _error(404, "Not found", f"TroubleTicket {request.path_params['id']} does not exist.")
    return JSONResponse(_project(ticket, request.query_params.get("fields")))


async def patch_ticket(request: Request):
    ticket_id = request.path_params["id"]
    if ticket_id not in store.tickets:
        return _error(404, "Not found", f"TroubleTicket {ticket_id} does not exist.")
    body = await _json_body(request)
    if not isinstance(body, dict):
        return _error(400, "Invalid body", "Only JSON merge patch (a JSON object) is supported.")
    return JSONResponse(store.patch(ticket_id, body))


app = Starlette(routes=[
    Route("/troubleTicket", create_ticket, methods=["POST"]),
    Route("/troubleTicket", list_tickets, methods=["GET"]),
    Route("/troubleTicket/{id}", retrieve_ticket, methods=["GET"]),
    Route("/troubleTicket/{id}", patch_ticket, methods=["PATCH"]),
])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "4010")), workers=1)

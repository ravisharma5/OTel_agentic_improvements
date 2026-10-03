"""Web dashboard for real-time MCP-Telecom device status.

Optional dependencies: ``fastapi`` and ``uvicorn``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.topology import topology_db

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("mcp_telecom.dashboard")

try:
    from fastapi import FastAPI as _FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FastAPI = None  # type: ignore[misc, assignment]
    HTMLResponse = JSONResponse = None  # type: ignore[misc, assignment]
    _FASTAPI_AVAILABLE = False

try:
    import uvicorn
except ImportError:
    uvicorn = None  # type: ignore[misc, assignment]


def _require_fastapi() -> None:
    if not _FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is not installed. Install with: pip install fastapi uvicorn"
        )


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP-Telecom Dashboard</title>
  <style>
    :root {
      --bg: #1a1a2e;
      --panel: #16213e;
      --accent: #0f3460;
      --highlight: #e94560;
      --text: #eaeaea;
      --muted: #a0a0b8;
      --ok: #2ecc71;
      --warn: #f1c40f;
      --bad: #e94560;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      background: linear-gradient(135deg, var(--panel) 0%, var(--accent) 100%);
      padding: 1.25rem 1.5rem;
      border-bottom: 3px solid var(--highlight);
    }
    header h1 {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    header p { margin: 0.35rem 0 0; color: var(--muted); font-size: 0.9rem; }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 1.25rem; }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .stat {
      background: var(--panel);
      border-radius: 10px;
      padding: 1rem 1.1rem;
      border: 1px solid var(--accent);
    }
    .stat .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }
    .stat .value { font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }
    .stat .value.ok { color: var(--ok); }
    .stat .value.bad { color: var(--bad); }
    .stat .value.warn { color: var(--warn); }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 1rem;
    }
    .card {
      background: var(--panel);
      border-radius: 10px;
      padding: 1rem 1.1rem;
      border: 1px solid var(--accent);
      border-left: 4px solid var(--muted);
    }
    .card.up { border-left-color: var(--ok); }
    .card.down { border-left-color: var(--bad); }
    .card.warn { border-left-color: var(--warn); }
    .card h3 { margin: 0 0 0.5rem; font-size: 1.05rem; }
    .card .meta { font-size: 0.85rem; color: var(--muted); line-height: 1.5; }
    .dot {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
      vertical-align: middle;
    }
    .dot.ok { background: var(--ok); box-shadow: 0 0 8px var(--ok); }
    .dot.bad { background: var(--bad); box-shadow: 0 0 8px var(--bad); }
    .dot.warn { background: var(--warn); box-shadow: 0 0 8px var(--warn); }
    footer {
      margin-top: 2rem;
      padding: 1rem;
      text-align: center;
      color: var(--muted);
      font-size: 0.8rem;
    }
    .err {
      background: var(--panel);
      color: var(--bad);
      padding: 1rem;
      border-radius: 8px;
      margin: 1rem 0;
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>MCP-Telecom Dashboard</h1>
      <p>Device health overview — refreshes every 30 seconds</p>
    </div>
  </header>
  <div class="wrap">
    <div class="stats" id="stats"></div>
    <div id="err" class="err" style="display:none;"></div>
    <div class="cards" id="cards"></div>
  </div>
  <footer>Last update: <span id="ts">—</span></footer>
  <script>
    function statusClass(h) {
      if (!h) return 'warn';
      if (h.reachable === true) return 'up';
      if (h.reachable === false) return 'down';
      return 'warn';
    }
    function dotClass(c) {
      if (c === 'up') return 'ok';
      if (c === 'down') return 'bad';
      return 'warn';
    }
    async function load() {
      const errEl = document.getElementById('err');
      errEl.style.display = 'none';
      try {
        const healthRes = await fetch('/api/health');
        const health = await healthRes.json();
        const list = health.devices || [];

        let healthy = 0, unhealthy = 0, rsum = 0, rcnt = 0;
        list.forEach(function(d) {
          if (d.reachable === true) {
            healthy++;
            if (d.response_time_ms != null) { rsum += Number(d.response_time_ms); rcnt++; }
          } else {
            unhealthy++;
          }
        });
        const avgMs = rcnt ? (rsum / rcnt).toFixed(1) : null;

        const stats = document.getElementById('stats');
        stats.innerHTML =
          '<div class="stat"><div class="label">Total devices</div><div class="value">' +
          list.length + '</div></div>' +
          '<div class="stat"><div class="label">Healthy</div><div class="value ok">' +
          healthy + '</div></div>' +
          '<div class="stat"><div class="label">Unhealthy</div><div class="value bad">' +
          unhealthy + '</div></div>' +
          (avgMs != null
            ? '<div class="stat"><div class="label">Avg response (ms)</div><div class="value">' +
              avgMs + '</div></div>'
            : '');

        const cards = document.getElementById('cards');
        cards.innerHTML = '';
        list.forEach(function(h) {
          const name = h.device;
          const cls = statusClass(h);
          const vendor = h.vendor != null ? h.vendor : '';
          const host = h.host != null ? h.host : '';
          const ms = h.response_time_ms != null ? h.response_time_ms + ' ms' : '—';
          const card = document.createElement('div');
          card.className = 'card ' + cls;
          card.innerHTML =
            '<h3><span class="dot ' + dotClass(cls) + '"></span>' +
            String(name).replace(/</g, '&lt;') + '</h3>' +
            '<div class="meta">' +
            (host ? 'Host: ' + String(host).replace(/</g, '&lt;') + '<br/>' : '') +
            (vendor ? 'Vendor: ' + String(vendor).replace(/</g, '&lt;') + '<br/>' : '') +
            'Response: ' + String(ms).replace(/</g, '&lt;') +
            (h.error ? '<br/><span style="color:#e94560">' +
              String(h.error).replace(/</g, '&lt;').slice(0, 200) + '</span>' : '') +
            '</div>';
          cards.appendChild(card);
        });

        document.getElementById('ts').textContent = new Date().toLocaleString();
      } catch (e) {
        errEl.textContent = 'Failed to load dashboard: ' + e;
        errEl.style.display = 'block';
      }
    }
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>
"""


class DashboardApp:
    """FastAPI application exposing device status, health, audit, and topology APIs."""

    def __init__(
        self,
        device_manager: DeviceManager,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        _require_fastapi()
        self._device_manager = device_manager
        self._audit = audit_logger or AuditLogger()
        assert _FastAPI is not None
        self._app: FastAPI = _FastAPI(title="MCP-Telecom Dashboard", version="0.1.0")
        self._register_routes()

    def _register_routes(self) -> None:
        app = self._app

        @app.get("/", response_class=HTMLResponse)
        def index() -> str:
            return _DASHBOARD_HTML

        @app.get("/api/devices")
        def api_devices() -> JSONResponse:
            devices = self._device_manager.list_devices()
            payload = [d.model_dump(mode="json") for d in devices]
            return JSONResponse(payload)

        @app.get("/api/devices/{name}/status")
        def api_device_status(name: str) -> JSONResponse:
            health = self._device_manager.check_health(name)
            return JSONResponse(health.model_dump(mode="json"))

        @app.get("/api/health")
        def api_health() -> JSONResponse:
            devices = self._device_manager.list_devices()
            results: list[dict[str, Any]] = []
            for d in devices:
                try:
                    h = self._device_manager.check_health(d.name)
                    row = h.model_dump(mode="json")
                    row["vendor"] = d.vendor.value if hasattr(d.vendor, "value") else str(d.vendor)
                    row["host"] = d.host
                    results.append(row)
                except Exception as e:
                    logger.exception("Health check failed for %s", d.name)
                    results.append(
                        {
                            "device": d.name,
                            "reachable": False,
                            "response_time_ms": None,
                            "error": str(e),
                            "vendor": d.vendor.value
                            if hasattr(d.vendor, "value")
                            else str(d.vendor),
                            "host": d.host,
                        }
                    )
            return JSONResponse({"devices": results})

        @app.get("/api/audit")
        def api_audit() -> JSONResponse:
            return JSONResponse(self._audit.get_recent_entries(100))

        @app.get("/api/topology")
        def api_topology() -> JSONResponse:
            data = json.loads(topology_db.to_json())
            return JSONResponse(data)

        @app.get("/api/metrics/summary")
        def api_metrics_summary() -> JSONResponse:
            devices = self._device_manager.list_devices()
            names = [d.name for d in devices]
            healthy = 0
            unhealthy = 0
            response_times: list[float] = []
            for d in devices:
                try:
                    h = self._device_manager.check_health(d.name)
                    if h.reachable:
                        healthy += 1
                        if h.response_time_ms is not None:
                            response_times.append(float(h.response_time_ms))
                    else:
                        unhealthy += 1
                except Exception:
                    unhealthy += 1
            avg_ms: float | None = None
            if response_times:
                avg_ms = round(sum(response_times) / len(response_times), 2)
            return JSONResponse(
                {
                    "total_devices": len(devices),
                    "healthy": healthy,
                    "unhealthy": unhealthy,
                    "avg_response_ms": avg_ms,
                    "device_names": names,
                }
            )

    def get_app(self) -> FastAPI:
        return self._app

    def start(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        if uvicorn is None:
            raise RuntimeError(
                "uvicorn is not installed. Install with: pip install uvicorn"
            )
        uvicorn.run(self._app, host=host, port=port, log_level="info")

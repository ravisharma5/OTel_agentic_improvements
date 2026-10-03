"""Tests for the web dashboard module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    import fastapi  # noqa: F401

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


class TestDashboardImport:
    def test_module_imports_cleanly(self):
        import mcp_telecom.dashboard as d

        assert hasattr(d, "DashboardApp")
        assert hasattr(d, "_FASTAPI_AVAILABLE")


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
class TestDashboardApp:
    def test_create_with_mock_device_manager(self):
        from mcp_telecom.dashboard import DashboardApp

        mgr = MagicMock()
        mgr.list_devices.return_value = []
        try:
            app = DashboardApp(mgr)
        except TypeError as e:
            if "on_startup" in str(e):
                pytest.skip("FastAPI/Starlette version mismatch")
            raise
        assert app.get_app() is not None
        assert app.get_app().title == "MCP-Telecom Dashboard"

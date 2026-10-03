"""Tests for SSH connection pool."""

from __future__ import annotations

import pytest

from mcp_telecom.pool import ConnectionPool


@pytest.fixture
def pool():
    p = ConnectionPool(max_connections=2, idle_timeout=60.0, reaper_interval=3600.0)
    yield p
    p.close_all()


class TestConnectionPool:
    def test_creation_and_empty_stats(self, pool: ConnectionPool):
        stats = pool.get_stats()
        assert stats["total_connections"] == 0
        assert stats["devices"] == {}
        assert isinstance(stats["devices"], dict)

    def test_stats_structure(self, pool: ConnectionPool):
        stats = pool.get_stats()
        assert set(stats.keys()) == {"devices", "total_connections"}
        for _name, row in stats["devices"].items():
            assert set(row.keys()) == {"active", "idle", "total"}
            assert row["total"] == row["active"] + row["idle"]

    def test_invalid_max_connections(self):
        with pytest.raises(ValueError, match="max_connections"):
            ConnectionPool(max_connections=0)
        p = ConnectionPool(max_connections=1, reaper_interval=3600.0)
        try:
            pass
        finally:
            p.close_all()

    def test_invalid_idle_timeout(self):
        with pytest.raises(ValueError, match="idle_timeout"):
            ConnectionPool(idle_timeout=0)

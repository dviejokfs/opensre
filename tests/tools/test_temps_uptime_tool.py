"""Tests for query_temps_uptime (function-based, @tool decorated)."""

from __future__ import annotations

from unittest.mock import patch

from integrations.temps.tools.temps_uptime_tool import query_temps_uptime
from tests.tools.conftest import BaseToolContract


class TestTempsUptimeToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_temps_uptime.__opensre_registered_tool__


def test_metadata() -> None:
    rt = query_temps_uptime.__opensre_registered_tool__
    assert rt.name == "query_temps_uptime"
    assert rt.source == "temps"
    assert "investigation" in rt.surfaces


def test_run_happy_path() -> None:
    fake = {
        "source": "temps",
        "available": True,
        "project_id": 5,
        "overall_status": "degraded",
        "monitors": [{"current_status": "down"}],
        "monitor_count": 1,
        "recent_incidents": [],
    }
    with patch(
        "integrations.temps.tools.temps_uptime_tool.query_uptime", return_value=fake
    ) as mock_query:
        result = query_temps_uptime(
            base_url="https://temps.example.com",
            api_key="tk_test",
            project_id=5,
        )
    assert result["available"] is True
    assert result["overall_status"] == "degraded"
    _args, kwargs = mock_query.call_args
    assert kwargs["project_id"] == 5


def test_structured_error_passthrough() -> None:
    fake = {
        "source": "temps",
        "available": False,
        "error": "Temps authentication failed (check TEMPS_API_KEY and its permissions).",
        "project_id": 5,
    }
    with patch("integrations.temps.tools.temps_uptime_tool.query_uptime", return_value=fake):
        result = query_temps_uptime(
            base_url="https://temps.example.com", api_key="tk_bad", project_id=5
        )
    assert result["available"] is False
    assert "authentication" in result["error"].lower()

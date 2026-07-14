"""Tests for query_temps_logs (function-based, @tool decorated)."""

from __future__ import annotations

from unittest.mock import patch

from integrations.temps.tools.temps_logs_tool import query_temps_logs
from tests.tools.conftest import BaseToolContract


class TestTempsLogsToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_temps_logs.__opensre_registered_tool__


def test_metadata() -> None:
    rt = query_temps_logs.__opensre_registered_tool__
    assert rt.name == "query_temps_logs"
    assert rt.source == "temps"
    assert "investigation" in rt.surfaces


def test_run_happy_path_passes_filters() -> None:
    fake = {
        "source": "temps",
        "available": True,
        "project_id": 5,
        "logs": [{"severity": "ERROR", "body": "db timeout"}],
        "log_count": 1,
        "limit": 20,
    }
    with patch(
        "integrations.temps.tools.temps_logs_tool.query_logs", return_value=fake
    ) as mock_query:
        result = query_temps_logs(
            base_url="https://temps.example.com",
            api_key="tk_test",
            project_id=5,
            severity="ERROR",
            search="timeout",
            start_time="2026-07-14T00:00:00Z",
            end_time="2026-07-14T01:00:00Z",
            limit=20,
        )
    assert result["available"] is True
    assert result["log_count"] == 1
    _args, kwargs = mock_query.call_args
    assert kwargs["severity"] == "ERROR"
    assert kwargs["search"] == "timeout"
    assert kwargs["start_time"] == "2026-07-14T00:00:00Z"
    assert kwargs["limit"] == 20

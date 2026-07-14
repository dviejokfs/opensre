"""Tests for query_temps_container_logs (function-based, @tool decorated)."""

from __future__ import annotations

from unittest.mock import patch

from integrations.temps.tools.temps_container_logs_tool import query_temps_container_logs
from tests.tools.conftest import BaseToolContract


class TestTempsContainerLogsToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_temps_container_logs.__opensre_registered_tool__


def test_metadata() -> None:
    rt = query_temps_container_logs.__opensre_registered_tool__
    assert rt.name == "query_temps_container_logs"
    assert rt.source == "temps"
    assert "investigation" in rt.surfaces


def test_run_happy_path_passes_filters() -> None:
    fake = {
        "source": "temps",
        "available": True,
        "project_id": 5,
        "lines": [{"timestamp": "2026-07-14T00:00:01Z", "level": "error", "message": "panic"}],
        "line_count": 1,
        "total_scanned": 900,
        "next_cursor": None,
        "window": {"start_time": "2026-07-14T00:00:00Z", "end_time": "now"},
    }
    with patch(
        "integrations.temps.tools.temps_container_logs_tool.query_container_logs",
        return_value=fake,
    ) as mock_query:
        result = query_temps_container_logs(
            base_url="https://temps.example.com",
            api_key="tk_test",
            project_id=5,
            text="panic",
            service="web",
            levels=["error"],
            context_lines=3,
        )
    assert result["available"] is True
    assert result["line_count"] == 1
    _args, kwargs = mock_query.call_args
    assert kwargs["project_id"] == 5
    assert kwargs["text"] == "panic"
    assert kwargs["service"] == "web"
    assert kwargs["levels"] == ["error"]
    assert kwargs["context_lines"] == 3

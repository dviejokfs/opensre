"""Tests for query_temps_error_groups (function-based, @tool decorated)."""

from __future__ import annotations

from unittest.mock import patch

from integrations.temps.tools.temps_error_groups_tool import query_temps_error_groups
from tests.tools.conftest import BaseToolContract


class TestTempsErrorGroupsToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_temps_error_groups.__opensre_registered_tool__


def test_metadata() -> None:
    rt = query_temps_error_groups.__opensre_registered_tool__
    assert rt.name == "query_temps_error_groups"
    assert rt.source == "temps"
    assert "investigation" in rt.surfaces


def test_run_happy_path() -> None:
    fake = {
        "source": "temps",
        "available": True,
        "project_id": 5,
        "error_groups": [{"id": 1, "title": "TypeError"}],
        "group_count": 1,
        "total_count": 1,
        "truncated": False,
    }
    with patch(
        "integrations.temps.tools.temps_error_groups_tool.query_error_groups",
        return_value=fake,
    ) as mock_query:
        result = query_temps_error_groups(
            base_url="https://temps.example.com",
            api_key="tk_test",
            project_id=5,
            status="unresolved",
        )
    assert result["available"] is True
    assert result["group_count"] == 1
    _args, kwargs = mock_query.call_args
    assert kwargs["project_id"] == 5
    assert kwargs["status"] == "unresolved"


def test_zero_project_id_becomes_none_for_resolution() -> None:
    with patch(
        "integrations.temps.tools.temps_error_groups_tool.query_error_groups",
        return_value={"source": "temps", "available": False, "error": "ambiguous"},
    ) as mock_query:
        query_temps_error_groups(base_url="https://x", api_key="tk_test")
    _args, kwargs = mock_query.call_args
    assert kwargs["project_id"] is None

"""Tests for query_temps_deployments (function-based, @tool decorated)."""

from __future__ import annotations

from unittest.mock import patch

from integrations.temps.tools.temps_deployments_tool import query_temps_deployments
from tests.tools.conftest import BaseToolContract


class TestTempsDeploymentsToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_temps_deployments.__opensre_registered_tool__


def test_metadata() -> None:
    rt = query_temps_deployments.__opensre_registered_tool__
    assert rt.name == "query_temps_deployments"
    assert rt.source == "temps"
    assert "investigation" in rt.surfaces


def test_run_happy_path() -> None:
    fake = {
        "source": "temps",
        "available": True,
        "project_id": 5,
        "deployments": [{"id": 100, "status": "failed", "branch": "main"}],
        "deployment_count": 1,
        "total_count": 1,
        "truncated": False,
    }
    with patch(
        "integrations.temps.tools.temps_deployments_tool.query_deployments",
        return_value=fake,
    ) as mock_query:
        result = query_temps_deployments(
            base_url="https://temps.example.com",
            api_key="tk_test",
            project_id=5,
            environment_id=2,
        )
    assert result["available"] is True
    assert result["deployments"][0]["status"] == "failed"
    _args, kwargs = mock_query.call_args
    assert kwargs["project_id"] == 5
    assert kwargs["environment_id"] == 2

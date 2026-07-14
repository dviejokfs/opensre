"""Temps deployments tool."""

from __future__ import annotations

from typing import Any

from core.tool_framework.tool_decorator import tool
from integrations.temps import (
    TempsConfig,
    query_deployments,
    temps_extract_params,
    temps_is_available,
)


@tool(
    name="query_temps_deployments",
    display_name="Temps deployments",
    description=(
        "List recent deployments for a temps.sh project (newest first), "
        "including status, branch, commit, and timestamps. Use this to check "
        "what shipped immediately before an incident or alert window."
    ),
    source="temps",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Correlating an alert window with the deployment that shipped just before it",
        "Checking whether a failed or in-progress deployment explains downtime",
        "Listing recent releases for a temps.sh project during RCA",
    ],
    is_available=temps_is_available,
    injected_params=("api_key", "base_url"),
    extract_params=temps_extract_params,
)
def query_temps_deployments(
    base_url: str,
    api_key: str,
    project_id: int = 0,
    environment_id: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch recent deployments from a temps.sh project.

    ``base_url`` / ``api_key`` / the default ``project_id`` are sourced from
    the Temps integration via ``extract_params``.
    """
    config = TempsConfig(base_url=base_url, api_key=api_key)
    return query_deployments(
        config,
        project_id=project_id or None,
        environment_id=environment_id,
        limit=limit,
    )

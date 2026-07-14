"""Temps uptime/status tool."""

from __future__ import annotations

from typing import Any

from core.tool_framework.tool_decorator import tool
from integrations.temps import (
    TempsConfig,
    query_uptime,
    temps_extract_params,
    temps_is_available,
)


@tool(
    name="query_temps_uptime",
    display_name="Temps uptime status",
    description=(
        "Fetch the uptime monitoring overview for a temps.sh project: overall "
        "status, per-monitor current state (up/down/degraded), uptime "
        "percentages, average response times, and recent incidents."
    ),
    source="temps",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Checking whether a temps.sh project's monitors are currently failing",
        "Confirming user-facing impact (downtime) during an incident investigation",
        "Reviewing recent uptime incidents alongside deploy and error evidence",
    ],
    is_available=temps_is_available,
    injected_params=("api_key", "base_url"),
    extract_params=temps_extract_params,
)
def query_temps_uptime(
    base_url: str,
    api_key: str,
    project_id: int = 0,
    environment_id: int | None = None,
) -> dict[str, Any]:
    """Fetch the uptime/status overview for a temps.sh project.

    ``base_url`` / ``api_key`` / the default ``project_id`` are sourced from
    the Temps integration via ``extract_params``.
    """
    config = TempsConfig(base_url=base_url, api_key=api_key)
    return query_uptime(
        config,
        project_id=project_id or None,
        environment_id=environment_id,
    )

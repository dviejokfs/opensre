"""Temps error groups tool."""

from __future__ import annotations

from typing import Any

from core.tool_framework.tool_decorator import tool
from integrations.temps import (
    TempsConfig,
    query_error_groups,
    temps_extract_params,
    temps_is_available,
)


@tool(
    name="query_temps_error_groups",
    display_name="Temps error groups",
    description=(
        "Query a temps.sh project for grouped application errors (Sentry-style "
        "issues) captured by its built-in error tracking. Supports filtering by "
        "status (unresolved/resolved), environment, and an ISO-8601 date window. "
        "Returns error groups with occurrence counts and last-seen timestamps."
    ),
    source="temps",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Finding application errors that started or spiked inside an alert window",
        "Checking whether a service incident correlates with new unresolved error groups",
        "Listing the most frequent production errors for a temps.sh project",
    ],
    is_available=temps_is_available,
    injected_params=("api_key", "base_url"),
    extract_params=temps_extract_params,
)
def query_temps_error_groups(
    base_url: str,
    api_key: str,
    project_id: int = 0,
    status: str | None = None,
    environment_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch grouped application errors from a temps.sh project.

    ``base_url`` / ``api_key`` / the default ``project_id`` are sourced from
    the Temps integration via ``extract_params``. When ``project_id`` is 0 the
    integration falls back to the configured hint or the server's sole
    project, otherwise it returns a structured error listing visible projects.
    """
    config = TempsConfig(base_url=base_url, api_key=api_key)
    return query_error_groups(
        config,
        project_id=project_id or None,
        status=status,
        environment_id=environment_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

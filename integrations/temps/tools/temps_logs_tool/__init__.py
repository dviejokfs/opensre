"""Temps OpenTelemetry logs tool."""

from __future__ import annotations

from typing import Any

from core.tool_framework.tool_decorator import tool
from integrations.temps import (
    TempsConfig,
    query_logs,
    temps_extract_params,
    temps_is_available,
)


@tool(
    name="query_temps_logs",
    display_name="Temps logs",
    description=(
        "Query OpenTelemetry log records ingested by a temps.sh project. "
        "Supports filtering by severity (e.g. ERROR), service name, free-text "
        "search, trace ID, and an RFC 3339 time window. Always bound the window "
        "to the alert timeframe."
    ),
    source="temps",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Fetching application log lines around an alert window during RCA",
        "Scanning a service's ERROR-severity logs for a temps.sh project",
        "Pulling the logs correlated with a specific trace ID",
    ],
    is_available=temps_is_available,
    injected_params=("api_key", "base_url"),
    extract_params=temps_extract_params,
)
def query_temps_logs(
    base_url: str,
    api_key: str,
    project_id: int = 0,
    severity: str | None = None,
    service_name: str | None = None,
    search: str | None = None,
    trace_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch OTel log records from a temps.sh project.

    ``base_url`` / ``api_key`` / the default ``project_id`` are sourced from
    the Temps integration via ``extract_params``. ``start_time`` / ``end_time``
    are RFC 3339 timestamps bounding the query window.
    """
    config = TempsConfig(base_url=base_url, api_key=api_key)
    return query_logs(
        config,
        project_id=project_id or None,
        severity=severity,
        service_name=service_name,
        search=search,
        trace_id=trace_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

"""Temps container logs tool."""

from __future__ import annotations

from typing import Any

from core.tool_framework.tool_decorator import tool
from integrations.temps import (
    TempsConfig,
    query_container_logs,
    temps_extract_params,
    temps_is_available,
)


@tool(
    name="query_temps_container_logs",
    display_name="Temps container logs",
    description=(
        "Search raw container stdout/stderr logs from a temps.sh project's "
        "deployments (distinct from OTel logs). Supports grep-style free-text "
        "matching, service/environment/level/deploy filters, an RFC 3339 time "
        "window, and grep -C style context_lines around each match. Defaults "
        "to the last 15 minutes when no window is given — a bounded tail."
    ),
    source="temps",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Tailing the most recent container output for a service during an incident",
        "Grepping deployment stdout/stderr for a panic, OOM, or crash-loop message",
        "Pulling context lines around an error hit to see what preceded it",
    ],
    is_available=temps_is_available,
    injected_params=("api_key", "base_url"),
    extract_params=temps_extract_params,
)
def query_temps_container_logs(
    base_url: str,
    api_key: str,
    project_id: int = 0,
    text: str | None = None,
    service: str | None = None,
    environment: str | None = None,
    levels: list[str] | None = None,
    deploy_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    context_lines: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Search container stdout/stderr logs from a temps.sh project.

    ``base_url`` / ``api_key`` / the default ``project_id`` are sourced from
    the Temps integration via ``extract_params``. Repeated calls with a
    sliding ``start_time`` approximate a live tail; true streaming (SSE /
    WebSocket) is not exposed through the tool contract.
    """
    config = TempsConfig(base_url=base_url, api_key=api_key)
    return query_container_logs(
        config,
        project_id=project_id or None,
        text=text,
        service=service,
        environment=environment,
        levels=levels,
        deploy_id=deploy_id,
        start_time=start_time,
        end_time=end_time,
        context_lines=context_lines,
        limit=limit,
    )

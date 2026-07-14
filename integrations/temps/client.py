"""Read-only HTTP client for the temps.sh admin API.

All calls go through :func:`_get`, which scopes requests to ``<base_url>/api``
and authenticates with the integration's bearer API key. Every query function
returns an investigation-friendly evidence dict with a stable shape:
``{"source": "temps", "available": bool, ...}`` — expected upstream failures
(missing config, auth failure, 4xx/5xx, transport errors) never raise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from integrations._validation_helpers import report_validation_failure
from integrations.temps.config import TempsConfig

logger = logging.getLogger(__name__)

# Cap for long string fields (log bodies, stack traces) so a single row cannot
# flood the planner context. Truncation is marked with a visible suffix.
_MAX_FIELD_CHARS = 4000


def _http_client(config: TempsConfig) -> httpx.Client:
    """Build an authenticated ``httpx.Client`` scoped to the temps.sh API."""
    return httpx.Client(
        base_url=f"{config.base_url}/api",
        headers=config.headers,
        timeout=float(config.timeout_seconds),
    )


def _get(
    config: TempsConfig,
    path: str,
    params: dict[str, Any] | None = None,
) -> tuple[httpx.Response | None, str | None]:
    """GET a temps.sh admin API path.

    Returns ``(response, None)`` on transport-level success (any HTTP status)
    or ``(None, error_message)`` on transport-level failure (DNS, TLS,
    timeout, etc.).
    """
    try:
        with _http_client(config) as client:
            response = client.get(path, params=params or {})
    except httpx.RequestError as err:
        return None, f"Temps request failed: {err}"
    except Exception as err:  # defensive: unexpected client construction issues
        report_validation_failure(err, logger=logger, integration="temps", method="_get")
        return None, f"Temps request failed: {err}"
    return response, None


def _error_evidence(error: str, *, project_id: int = 0, **extra: Any) -> dict[str, Any]:
    """Standard error-shape dict returned by query functions on failure."""
    evidence: dict[str, Any] = {
        "source": "temps",
        "available": False,
        "error": error,
        "project_id": project_id,
    }
    evidence.update(extra)
    return evidence


def _status_error(response: httpx.Response, operation: str, project_id: int = 0) -> dict[str, Any]:
    """Map a non-2xx admin API response to a structured error dict."""
    status = response.status_code
    if status in (401, 403):
        return _error_evidence(
            "Temps authentication failed (check TEMPS_API_KEY and its permissions).",
            project_id=project_id,
        )
    if status == 404:
        return _error_evidence(
            f"Temps returned 404 for {operation} — verify TEMPS_BASE_URL and the project ID.",
            project_id=project_id,
        )
    if status == 429:
        return _error_evidence(
            "Temps rate limit exceeded (HTTP 429); retry after a short delay.",
            project_id=project_id,
        )
    return _error_evidence(
        f"Temps {operation} returned HTTP {status}: {response.text[:200]}",
        project_id=project_id,
    )


def _json_body(response: httpx.Response) -> Any | None:
    try:
        return response.json()
    except ValueError:
        return None


def _rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    """Extract a list of row dicts from ``payload``.

    Live payloads are either a bare JSON array or an object wrapping the rows
    under one of ``keys`` (e.g. ``data``, ``deployments``). Missing / oddly
    shaped payloads yield ``[]`` rather than raising.
    """
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = next(
            (payload[k] for k in keys if isinstance(payload.get(k), list)),
            [],
        )
    else:
        candidates = []
    return [row for row in candidates if isinstance(row, dict)]


def _truncate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Cap long top-level string fields so one row cannot flood the context."""
    slimmed: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
            slimmed[key] = value[:_MAX_FIELD_CHARS] + "… [truncated]"
        else:
            slimmed[key] = value
    return slimmed


def _effective_limit(config: TempsConfig, limit: int | None) -> int:
    return min(max(1, int(limit or config.max_results)), config.max_results)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TempsValidationResult:
    """Outcome of validating a temps.sh integration against the admin API."""

    ok: bool
    detail: str


def validate_temps_config(config: TempsConfig) -> TempsValidationResult:
    """Validate temps.sh reachability and API key with a cheap project list."""
    if not config.is_configured:
        return TempsValidationResult(ok=False, detail="Temps base_url and api_key are required.")

    response, err = _get(config, "/projects")
    if err is not None or response is None:
        return TempsValidationResult(ok=False, detail=err or "Temps request returned no response.")

    status = response.status_code
    if status == 200:
        projects = _rows(_json_body(response), "data", "projects")
        return TempsValidationResult(
            ok=True,
            detail=(
                f"Connected to Temps at {config.base_url} ({len(projects)} project(s) visible)."
            ),
        )
    if status in (401, 403):
        return TempsValidationResult(
            ok=False,
            detail="Temps authentication failed (check TEMPS_API_KEY and its permissions).",
        )
    if status == 404:
        return TempsValidationResult(
            ok=False,
            detail=(
                "Temps admin API not found — verify TEMPS_BASE_URL points at the "
                "control plane (e.g. https://temps.example.com), not a deployed app."
            ),
        )
    return TempsValidationResult(
        ok=False, detail=f"Temps API returned HTTP {status}: {response.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------


def list_projects(config: TempsConfig) -> dict[str, Any]:
    """List projects visible to the API key (id + name only)."""
    if not config.is_configured:
        return _error_evidence("Not configured.")
    response, err = _get(config, "/projects")
    if err is not None or response is None:
        return _error_evidence(err or "Temps request returned no response.")
    if response.status_code != 200:
        return _status_error(response, "project list")
    projects = [
        {"id": row.get("id"), "name": row.get("name")}
        for row in _rows(_json_body(response), "data", "projects")
    ]
    return {
        "source": "temps",
        "available": True,
        "projects": projects,
        "project_count": len(projects),
    }


def resolve_project_id(
    config: TempsConfig, project_id: int | None
) -> tuple[int, dict[str, Any] | None]:
    """Resolve the target project: explicit arg → configured hint → sole project.

    Returns ``(project_id, None)`` on success or ``(0, error_evidence)`` when
    the target is ambiguous; the error lists the visible projects so the
    planner can retry with an explicit ``project_id``.
    """
    if project_id:
        return int(project_id), None
    if config.project_id:
        return config.project_id, None

    listing = list_projects(config)
    if not listing.get("available"):
        return 0, listing
    projects = listing.get("projects", [])
    if len(projects) == 1 and projects[0].get("id"):
        return int(projects[0]["id"]), None
    return 0, _error_evidence(
        "No project_id was provided and the Temps server has "
        f"{len(projects)} projects; pass project_id explicitly.",
        projects=projects,
    )


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def query_error_groups(
    config: TempsConfig,
    project_id: int | None = None,
    status: str | None = None,
    environment_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch grouped application errors (Sentry-style issues) for a project.

    Parameters mirror ``GET /api/projects/{project_id}/error-groups``:
    ``status`` filters by group state (e.g. ``unresolved`` / ``resolved``),
    ``start_date`` / ``end_date`` are ISO-8601 bounds.
    """
    if not config.is_configured:
        return _error_evidence("Not configured.")
    resolved_id, resolve_err = resolve_project_id(config, project_id)
    if resolve_err is not None:
        return resolve_err

    params: dict[str, Any] = {"page": 1, "page_size": _effective_limit(config, limit)}
    if status:
        params["status"] = status
    if environment_id:
        params["environment_id"] = environment_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    response, err = _get(config, f"/projects/{resolved_id}/error-groups", params)
    if err is not None or response is None:
        return _error_evidence(err or "Temps request returned no response.", project_id=resolved_id)
    if response.status_code != 200:
        return _status_error(response, "error-groups query", resolved_id)

    payload = _json_body(response)
    groups = [_truncate_row(row) for row in _rows(payload, "data")]
    pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
    total_count = int(pagination.get("total_count", len(groups)) or 0)
    return {
        "source": "temps",
        "available": True,
        "project_id": resolved_id,
        "error_groups": groups,
        "group_count": len(groups),
        "total_count": total_count,
        "truncated": total_count > len(groups),
    }


def query_logs(
    config: TempsConfig,
    project_id: int | None = None,
    severity: str | None = None,
    service_name: str | None = None,
    search: str | None = None,
    trace_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch OpenTelemetry log records for a project (``GET /api/otel/logs``).

    ``severity`` matches OTel severity text (e.g. ``ERROR``), ``search`` is a
    free-text body filter, and ``start_time`` / ``end_time`` are RFC 3339
    bounds. Always pass a bounded window during investigations.
    """
    if not config.is_configured:
        return _error_evidence("Not configured.")
    resolved_id, resolve_err = resolve_project_id(config, project_id)
    if resolve_err is not None:
        return resolve_err

    params: dict[str, Any] = {
        "project_id": resolved_id,
        "limit": _effective_limit(config, limit),
    }
    if severity:
        params["severity"] = severity
    if service_name:
        params["service_name"] = service_name
    if search:
        params["search"] = search
    if trace_id:
        params["trace_id"] = trace_id
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    response, err = _get(config, "/otel/logs", params)
    if err is not None or response is None:
        return _error_evidence(err or "Temps request returned no response.", project_id=resolved_id)
    if response.status_code != 200:
        return _status_error(response, "logs query", resolved_id)

    logs = [_truncate_row(row) for row in _rows(_json_body(response), "data", "logs")]
    return {
        "source": "temps",
        "available": True,
        "project_id": resolved_id,
        "logs": logs,
        "log_count": len(logs),
        "limit": params["limit"],
    }


# Deployment fields worth surfacing to the planner; live payloads carry large
# nested build configs that would otherwise flood the context.
_DEPLOYMENT_KEYS = (
    "id",
    "status",
    "environment_id",
    "branch",
    "commit_sha",
    "commit_message",
    "commit_author",
    "url",
    "error_message",
    "created_at",
    "updated_at",
    "finished_at",
)


def query_deployments(
    config: TempsConfig,
    project_id: int | None = None,
    environment_id: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch recent deployments for a project, newest first.

    Deploy events are prime RCA evidence: correlate an alert window with what
    shipped immediately before it (``GET /api/projects/{id}/deployments``).
    """
    if not config.is_configured:
        return _error_evidence("Not configured.")
    resolved_id, resolve_err = resolve_project_id(config, project_id)
    if resolve_err is not None:
        return resolve_err

    params: dict[str, Any] = {"page": 1, "per_page": _effective_limit(config, limit)}
    if environment_id:
        params["environment_id"] = environment_id

    response, err = _get(config, f"/projects/{resolved_id}/deployments", params)
    if err is not None or response is None:
        return _error_evidence(err or "Temps request returned no response.", project_id=resolved_id)
    if response.status_code != 200:
        return _status_error(response, "deployments query", resolved_id)

    payload = _json_body(response)
    deployments = [
        _truncate_row({k: row[k] for k in _DEPLOYMENT_KEYS if k in row}) or _truncate_row(row)
        for row in _rows(payload, "deployments", "data")
    ]
    total = int(payload.get("total", len(deployments)) or 0) if isinstance(payload, dict) else 0
    return {
        "source": "temps",
        "available": True,
        "project_id": resolved_id,
        "deployments": deployments,
        "deployment_count": len(deployments),
        "total_count": total,
        "truncated": total > len(deployments),
    }


def query_uptime(
    config: TempsConfig,
    project_id: int | None = None,
    environment_id: int | None = None,
) -> dict[str, Any]:
    """Fetch the uptime/status overview for a project.

    Returns overall status plus per-monitor current state, uptime percentage,
    and recent incidents (``GET /api/projects/{project_id}/status``).
    """
    if not config.is_configured:
        return _error_evidence("Not configured.")
    resolved_id, resolve_err = resolve_project_id(config, project_id)
    if resolve_err is not None:
        return resolve_err

    params: dict[str, Any] = {}
    if environment_id:
        params["environment_id"] = environment_id

    response, err = _get(config, f"/projects/{resolved_id}/status", params)
    if err is not None or response is None:
        return _error_evidence(err or "Temps request returned no response.", project_id=resolved_id)
    if response.status_code != 200:
        return _status_error(response, "status query", resolved_id)

    payload = _json_body(response)
    payload = payload if isinstance(payload, dict) else {}
    monitors = _rows(payload, "monitors")
    incidents = _rows(payload, "recent_incidents", "incidents")
    return {
        "source": "temps",
        "available": True,
        "project_id": resolved_id,
        "overall_status": str(payload.get("status", "unknown")),
        "monitors": [_truncate_row(m) for m in monitors],
        "monitor_count": len(monitors),
        "recent_incidents": [_truncate_row(i) for i in incidents],
    }

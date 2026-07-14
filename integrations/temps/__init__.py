"""temps.sh integration: config, read-only admin API client, and verifier.

temps.sh is a self-hosted PaaS combining deployments, OpenTelemetry
observability, Sentry-compatible error tracking, uptime monitoring, and web
analytics in one Rust binary. This integration reads investigation evidence
(error groups, OTel logs, deployments, uptime status) from its admin REST API
using a bearer API key.
"""

from __future__ import annotations

from integrations.temps.client import (
    TempsValidationResult,
    list_projects,
    query_deployments,
    query_error_groups,
    query_logs,
    query_uptime,
    resolve_project_id,
    validate_temps_config,
)
from integrations.temps.config import (
    DEFAULT_TEMPS_MAX_RESULTS,
    DEFAULT_TEMPS_TIMEOUT_S,
    TempsConfig,
    build_temps_config,
    classify,
    temps_config_from_env,
    temps_extract_params,
    temps_is_available,
)

__all__ = [
    "DEFAULT_TEMPS_MAX_RESULTS",
    "DEFAULT_TEMPS_TIMEOUT_S",
    "TempsConfig",
    "TempsValidationResult",
    "build_temps_config",
    "classify",
    "list_projects",
    "query_deployments",
    "query_error_groups",
    "query_logs",
    "query_uptime",
    "resolve_project_id",
    "temps_config_from_env",
    "temps_extract_params",
    "temps_is_available",
    "validate_temps_config",
]

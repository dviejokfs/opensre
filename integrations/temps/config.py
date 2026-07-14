"""Configuration model and helpers for the temps.sh integration.

temps.sh (https://temps.sh) is a self-hosted PaaS that bundles deployments,
OpenTelemetry logs/metrics/traces, Sentry-compatible error tracking, uptime
monitoring, and web analytics behind a single REST API. OpenSRE talks to the
admin API (mounted under ``/api``) with a bearer API key (``tk_...``) minted
from the Temps dashboard.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import Field, field_validator

from config.strict_config import StrictConfigModel
from integrations._validation_helpers import report_classify_failure

logger = logging.getLogger(__name__)

DEFAULT_TEMPS_TIMEOUT_S = 15
DEFAULT_TEMPS_MAX_RESULTS = 50
_MAX_ALLOWED_RESULTS = 100


class TempsConfig(StrictConfigModel):
    """Normalized temps.sh admin API connection settings."""

    base_url: str = ""
    api_key: str = ""
    project_id: int = 0
    timeout_seconds: int = Field(default=DEFAULT_TEMPS_TIMEOUT_S, gt=0)
    max_results: int = Field(default=DEFAULT_TEMPS_MAX_RESULTS, gt=0, le=_MAX_ALLOWED_RESULTS)
    integration_id: str = ""

    @field_validator("base_url", mode="before")
    @classmethod
    def _normalize_base_url(cls, value: Any) -> str:
        return str(value or "").strip().rstrip("/")

    @field_validator("api_key", mode="before")
    @classmethod
    def _normalize_api_key(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("project_id", mode="before")
    @classmethod
    def _normalize_project_id(cls, value: Any) -> int:
        """Coerce env/store input into an int; ``0`` means "not configured"."""
        if value in (None, ""):
            return 0
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


def build_temps_config(raw: dict[str, Any] | None) -> TempsConfig:
    """Build a normalized temps.sh config object from env/store data."""
    return TempsConfig.model_validate(raw or {})


def temps_config_from_env() -> TempsConfig | None:
    """Load a temps.sh config from ``TEMPS_*`` env vars.

    Returns ``None`` when either the base URL or API key is missing. The
    optional ``TEMPS_PROJECT_ID`` scopes tools to one project by default;
    without it, tools fall back to the sole project on the server or return
    a structured error listing the available projects for the planner.
    """
    base_url = os.getenv("TEMPS_BASE_URL", "").strip()
    api_key = os.getenv("TEMPS_API_KEY", "").strip()
    if not base_url or not api_key:
        return None
    return build_temps_config(
        {
            "base_url": base_url,
            "api_key": api_key,
            "project_id": os.getenv("TEMPS_PROJECT_ID", ""),
        }
    )


def temps_is_available(sources: dict[str, dict]) -> bool:
    """Check whether temps.sh credentials are present in resolved integrations.

    A project ID is intentionally not required for availability: query
    functions resolve the target project at call time (explicit arg →
    configured hint → sole project on the server) and return a structured
    error listing available projects when the target stays ambiguous.
    """
    temps = sources.get("temps", {})
    return bool(temps.get("base_url") and temps.get("api_key"))


def temps_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    """Extract temps.sh credentials and the optional project hint for tool calls."""
    temps = sources.get("temps", {})
    return {
        "base_url": temps.get("base_url", ""),
        "api_key": temps.get("api_key", ""),
        "project_id": int(temps.get("project_id", 0) or 0),
    }


def classify(credentials: dict[str, Any], record_id: str) -> tuple[TempsConfig | None, str | None]:
    """Classify stored credentials as a temps.sh integration."""
    try:
        cfg = build_temps_config(
            {
                "base_url": credentials.get("base_url", ""),
                "api_key": credentials.get("api_key", ""),
                "project_id": credentials.get("project_id", ""),
                "integration_id": record_id,
            }
        )
    except Exception as exc:
        report_classify_failure(exc, logger=logger, integration="temps", record_id=record_id)
        return None, None
    if cfg.is_configured:
        return cfg, "temps"
    return None, None

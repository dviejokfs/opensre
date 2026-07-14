"""Tests for the temps.sh integration (config, env loading, classify, client)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from integrations.temps import (
    TempsConfig,
    build_temps_config,
    classify,
    list_projects,
    query_container_logs,
    query_deployments,
    query_error_groups,
    query_logs,
    query_uptime,
    resolve_project_id,
    temps_config_from_env,
    temps_extract_params,
    temps_is_available,
    validate_temps_config,
)
from integrations.temps import client as temps_client

# ---------------------------------------------------------------------------
# Mock transport helper
# ---------------------------------------------------------------------------

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def patched_http_client(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch ``_http_client`` to route through an ``httpx.MockTransport``."""

    def install(handler: Handler) -> None:
        def _fake_client(config: TempsConfig) -> httpx.Client:
            return httpx.Client(
                base_url=f"{config.base_url}/api",
                headers=config.headers,
                timeout=float(config.timeout_seconds),
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(temps_client, "_http_client", _fake_client)

    return install


def _configured(project_id: int = 0) -> TempsConfig:
    return TempsConfig(
        base_url="https://temps.example.com",
        api_key="tk_test",
        project_id=project_id,
    )


def _json_response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


# ---------------------------------------------------------------------------
# Config normalization
# ---------------------------------------------------------------------------


class TestTempsConfig:
    def test_strips_trailing_slash_and_whitespace(self) -> None:
        cfg = TempsConfig(base_url=" https://temps.example.com/ ", api_key=" tk_x ")
        assert cfg.base_url == "https://temps.example.com"
        assert cfg.api_key == "tk_x"

    def test_project_id_coercion(self) -> None:
        assert TempsConfig(project_id="7").project_id == 7
        assert TempsConfig(project_id="").project_id == 0
        assert TempsConfig(project_id=None).project_id == 0
        assert TempsConfig(project_id="not-a-number").project_id == 0

    def test_is_configured(self) -> None:
        assert _configured().is_configured
        assert not TempsConfig(base_url="https://x").is_configured
        assert not TempsConfig(api_key="tk_x").is_configured

    def test_headers_carry_bearer_key(self) -> None:
        assert _configured().headers == {"Authorization": "Bearer tk_test"}


class TestBuildTempsConfig:
    def test_none_yields_unconfigured(self) -> None:
        cfg = build_temps_config(None)
        assert not cfg.is_configured

    def test_full_dict(self) -> None:
        cfg = build_temps_config({"base_url": "https://x", "api_key": "tk_a", "project_id": "3"})
        assert cfg.base_url == "https://x"
        assert cfg.project_id == 3


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------


class TestTempsConfigFromEnv:
    def test_returns_none_without_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEMPS_BASE_URL", raising=False)
        monkeypatch.setenv("TEMPS_API_KEY", "tk_x")
        assert temps_config_from_env() is None

    def test_returns_none_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEMPS_BASE_URL", "https://x")
        monkeypatch.delenv("TEMPS_API_KEY", raising=False)
        assert temps_config_from_env() is None

    def test_loads_from_env_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEMPS_BASE_URL", "https://temps.example.com/")
        monkeypatch.setenv("TEMPS_API_KEY", "tk_x")
        monkeypatch.setenv("TEMPS_PROJECT_ID", "5")
        cfg = temps_config_from_env()
        assert cfg is not None
        assert cfg.base_url == "https://temps.example.com"
        assert cfg.project_id == 5

    def test_loads_without_optional_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEMPS_BASE_URL", "https://x")
        monkeypatch.setenv("TEMPS_API_KEY", "tk_x")
        monkeypatch.delenv("TEMPS_PROJECT_ID", raising=False)
        cfg = temps_config_from_env()
        assert cfg is not None
        assert cfg.project_id == 0


# ---------------------------------------------------------------------------
# Classification / availability / extract_params
# ---------------------------------------------------------------------------


class TestClassify:
    def test_classifies_when_configured(self) -> None:
        cfg, service = classify(
            {"base_url": "https://x", "api_key": "tk_a", "project_id": 2}, "temps-1"
        )
        assert service == "temps"
        assert cfg is not None
        assert cfg.integration_id == "temps-1"

    def test_rejects_incomplete_credentials(self) -> None:
        cfg, service = classify({"base_url": "https://x"}, "temps-1")
        assert cfg is None
        assert service is None


class TestAvailabilityAndExtract:
    def test_available_with_credentials(self) -> None:
        sources = {"temps": {"base_url": "https://x", "api_key": "tk_a"}}
        assert temps_is_available(sources)

    def test_unavailable_without_credentials(self) -> None:
        assert not temps_is_available({})
        assert not temps_is_available({"temps": {"base_url": "https://x"}})

    def test_extract_params_includes_project_hint(self) -> None:
        sources = {"temps": {"base_url": "https://x", "api_key": "tk_a", "project_id": 4}}
        params = temps_extract_params(sources)
        assert params == {"base_url": "https://x", "api_key": "tk_a", "project_id": 4}

    def test_extract_params_defaults(self) -> None:
        params = temps_extract_params({})
        assert params == {"base_url": "", "api_key": "", "project_id": 0}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateTempsConfig:
    def test_unconfigured(self) -> None:
        result = validate_temps_config(TempsConfig())
        assert not result.ok
        assert "required" in result.detail

    def test_success(self, patched_http_client) -> None:
        patched_http_client(lambda _request: _json_response([{"id": 1, "name": "web"}]))
        result = validate_temps_config(_configured())
        assert result.ok
        assert "1 project(s)" in result.detail

    def test_auth_failure(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(401))
        result = validate_temps_config(_configured())
        assert not result.ok
        assert "authentication" in result.detail.lower()

    def test_not_found(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(404))
        result = validate_temps_config(_configured())
        assert not result.ok
        assert "TEMPS_BASE_URL" in result.detail

    def test_transport_error(self, patched_http_client) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        patched_http_client(handler)
        result = validate_temps_config(_configured())
        assert not result.ok
        assert "request failed" in result.detail.lower()


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------


class TestResolveProjectId:
    def test_explicit_wins(self) -> None:
        resolved, err = resolve_project_id(_configured(project_id=3), 9)
        assert (resolved, err) == (9, None)

    def test_config_hint(self) -> None:
        resolved, err = resolve_project_id(_configured(project_id=3), None)
        assert (resolved, err) == (3, None)

    def test_sole_project_fallback(self, patched_http_client) -> None:
        # Live shape: PaginatedProjectList ({projects, page, per_page, total}).
        patched_http_client(
            lambda _request: _json_response(
                {"projects": [{"id": 8, "name": "only"}], "page": 1, "per_page": 25, "total": 1}
            )
        )
        resolved, err = resolve_project_id(_configured(), None)
        assert (resolved, err) == (8, None)

    def test_ambiguous_lists_projects(self, patched_http_client) -> None:
        patched_http_client(
            lambda _request: _json_response(
                {
                    "projects": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
                    "page": 1,
                    "per_page": 25,
                    "total": 2,
                }
            )
        )
        resolved, err = resolve_project_id(_configured(), None)
        assert resolved == 0
        assert err is not None
        assert err["available"] is False
        assert {p["id"] for p in err["projects"]} == {1, 2}

    def test_full_first_page_of_larger_total_stays_ambiguous(self, patched_http_client) -> None:
        # One project on the first page but server total says more exist:
        # never silently pick it.
        patched_http_client(
            lambda _request: _json_response(
                {"projects": [{"id": 1, "name": "a"}], "page": 1, "per_page": 1, "total": 40}
            )
        )
        resolved, err = resolve_project_id(_configured(), None)
        assert resolved == 0
        assert err is not None
        assert "40 projects" in err["error"]


# ---------------------------------------------------------------------------
# Query functions — live-ish payload parsing
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_parses_paginated_project_list(self, patched_http_client) -> None:
        # Live shape per the temps OpenAPI spec (PaginatedProjectList).
        patched_http_client(
            lambda _request: _json_response(
                {
                    "projects": [{"id": 1, "name": "web", "slug": "web"}],
                    "page": 1,
                    "per_page": 25,
                    "total": 30,
                }
            )
        )
        result = list_projects(_configured())
        assert result["available"] is True
        assert result["projects"] == [{"id": 1, "name": "web"}]
        assert result["project_count"] == 30

    def test_parses_bare_array(self, patched_http_client) -> None:
        patched_http_client(
            lambda _request: _json_response([{"id": 1, "name": "web", "slug": "web"}])
        )
        result = list_projects(_configured())
        assert result["available"] is True
        assert result["projects"] == [{"id": 1, "name": "web"}]

    def test_parses_wrapped_object(self, patched_http_client) -> None:
        patched_http_client(lambda _request: _json_response({"data": [{"id": 2, "name": "api"}]}))
        result = list_projects(_configured())
        assert result["project_count"] == 1

    def test_not_configured(self) -> None:
        result = list_projects(TempsConfig())
        assert result["available"] is False


class TestQueryErrorGroups:
    def test_happy_path_with_pagination(self, patched_http_client) -> None:
        payload = {
            "data": [
                {"id": 10, "title": "TypeError: x is undefined", "count": 42},
                {"id": 11, "title": "ECONNREFUSED", "count": 7},
            ],
            "pagination": {"page": 1, "page_size": 50, "total_count": 120, "total_pages": 3},
        }

        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("Authorization", "")
            return _json_response(payload)

        patched_http_client(handler)
        result = query_error_groups(_configured(project_id=5), status="unresolved", limit=50)
        assert seen["path"] == "/api/projects/5/error-groups"
        assert seen["auth"] == "Bearer tk_test"
        assert result["available"] is True
        assert result["group_count"] == 2
        assert result["total_count"] == 120
        assert result["truncated"] is True

    def test_truncates_long_fields(self, patched_http_client) -> None:
        payload = {"data": [{"id": 1, "stack_trace": "x" * 10_000}]}
        patched_http_client(lambda _request: _json_response(payload))
        result = query_error_groups(_configured(project_id=5))
        trace = result["error_groups"][0]["stack_trace"]
        assert len(trace) < 10_000
        assert trace.endswith("[truncated]")

    def test_auth_failure(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(403))
        result = query_error_groups(_configured(project_id=5))
        assert result["available"] is False
        assert "authentication" in result["error"].lower()

    def test_rate_limit(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(429))
        result = query_error_groups(_configured(project_id=5))
        assert result["available"] is False
        assert "429" in result["error"]


class TestQueryLogs:
    def test_happy_path_sends_filters(self, patched_http_client) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return _json_response({"data": [{"severity": "ERROR", "body": "db timeout"}]})

        patched_http_client(handler)
        result = query_logs(
            _configured(project_id=5),
            severity="ERROR",
            search="timeout",
            start_time="2026-07-14T00:00:00Z",
            end_time="2026-07-14T01:00:00Z",
            limit=20,
        )
        assert result["available"] is True
        assert result["log_count"] == 1
        params = seen["params"]
        assert params["project_id"] == "5"
        assert params["severity"] == "ERROR"
        assert params["search"] == "timeout"
        assert params["limit"] == "20"

    def test_handles_bare_array_payload(self, patched_http_client) -> None:
        patched_http_client(lambda _request: _json_response([{"body": "hello"}]))
        result = query_logs(_configured(project_id=5))
        assert result["log_count"] == 1

    def test_handles_non_json_body(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(200, content=b"not json"))
        result = query_logs(_configured(project_id=5))
        assert result["available"] is True
        assert result["logs"] == []


class TestQueryContainerLogs:
    def test_happy_path_sends_search_body(self, patched_http_client) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return _json_response(
                {
                    "lines": [
                        {
                            "timestamp": "2026-07-14T00:00:01Z",
                            "level": "error",
                            "service": "web",
                            "message": "panic: nil pointer",
                            "chunk_id": "c1",
                            "line_offset": 12,
                        }
                    ],
                    "next_cursor": None,
                    "search_mode": "full_text",
                    "total_scanned": 900,
                }
            )

        patched_http_client(handler)
        result = query_container_logs(
            _configured(project_id=5),
            text="panic",
            service="web",
            environment="production",
            levels=["error", "warn"],
            start_time="2026-07-14T00:00:00Z",
            end_time="2026-07-14T01:00:00Z",
            context_lines=3,
            limit=20,
        )
        assert seen["path"] == "/api/logs/search"
        body = seen["body"]
        assert body["project_id"] == 5
        assert body["text"] == "panic"
        assert body["services"] == ["web"]
        assert body["envs"] == ["production"]
        assert body["levels"] == ["error", "warn"]
        assert body["start_time"] == "2026-07-14T00:00:00Z"
        assert body["context_lines"] == 3
        assert body["page_size"] == 20
        assert result["available"] is True
        assert result["line_count"] == 1
        assert result["total_scanned"] == 900
        assert result["lines"][0]["message"] == "panic: nil pointer"

    def test_defaults_to_bounded_lookback_window(self, patched_http_client) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return _json_response({"lines": [], "search_mode": "recent", "total_scanned": 0})

        patched_http_client(handler)
        result = query_container_logs(_configured(project_id=5))
        # A bare "tail the logs" call must never scan unbounded history.
        assert seen["body"]["start_time"]
        assert result["window"]["start_time"] == seen["body"]["start_time"]
        assert result["window"]["end_time"] == "now"

    def test_auth_failure(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(401))
        result = query_container_logs(_configured(project_id=5), text="panic")
        assert result["available"] is False
        assert "authentication" in result["error"].lower()


class TestQueryDeployments:
    def test_happy_path_slims_rows(self, patched_http_client) -> None:
        payload = {
            "deployments": [
                {
                    "id": 100,
                    "status": "failed",
                    "branch": "main",
                    "commit_sha": "abc123",
                    "created_at": "2026-07-14T00:00:00Z",
                    "build_config": {"huge": "nested blob"},
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 50,
        }
        patched_http_client(lambda _request: _json_response(payload))
        result = query_deployments(_configured(project_id=5))
        assert result["available"] is True
        deployment = result["deployments"][0]
        assert deployment["status"] == "failed"
        assert "build_config" not in deployment

    def test_server_error(self, patched_http_client) -> None:
        patched_http_client(lambda _request: httpx.Response(500, text="boom"))
        result = query_deployments(_configured(project_id=5))
        assert result["available"] is False
        assert "500" in result["error"]


class TestQueryUptime:
    def test_happy_path(self, patched_http_client) -> None:
        payload = {
            "status": "degraded",
            "monitors": [
                {
                    "monitor": {"id": 1, "name": "homepage"},
                    "current_status": "down",
                    "uptime_percentage": 98.5,
                    "avg_response_time_ms": 120,
                }
            ],
            "recent_incidents": [{"id": 7, "title": "Outage"}],
        }
        patched_http_client(lambda _request: _json_response(payload))
        result = query_uptime(_configured(project_id=5))
        assert result["available"] is True
        assert result["overall_status"] == "degraded"
        assert result["monitor_count"] == 1
        assert result["recent_incidents"][0]["id"] == 7

    def test_handles_missing_fields(self, patched_http_client) -> None:
        patched_http_client(lambda _request: _json_response({}))
        result = query_uptime(_configured(project_id=5))
        assert result["available"] is True
        assert result["overall_status"] == "unknown"
        assert result["monitors"] == []


def test_api_key_never_in_evidence(patched_http_client) -> None:
    """No query result may leak the bearer key into planner-visible output."""
    patched_http_client(lambda _request: httpx.Response(401))
    for result in (
        query_error_groups(_configured(project_id=5)),
        query_logs(_configured(project_id=5)),
        query_container_logs(_configured(project_id=5)),
        query_deployments(_configured(project_id=5)),
        query_uptime(_configured(project_id=5)),
    ):
        assert "tk_test" not in json.dumps(result)

"""End to end over Streamable HTTP: real uvicorn, real bearer tokens, real MCP client."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from governed_mcp.app import ConfigError, build_http_app
from governed_mcp.config import Settings
from governed_mcp.devkeys import DEV_AUDIENCE, DEV_ISSUER, mint_from_dir, write_dev_keys
from tests.conftest import POLICIES, RUNBOOKS


@dataclass
class Live:
    url: str
    keys: Path
    audit: Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Live]:
    tmp = tmp_path_factory.mktemp("http")
    write_dev_keys(tmp / "keys")
    port = _free_port()
    settings = Settings(
        policy_dir=POLICIES,
        runbook_dir=RUNBOOKS,
        audit_log=str(tmp / "audit.jsonl"),
        port=port,
        issuer=DEV_ISSUER,
        audience=DEV_AUDIENCE,
        jwks_file=tmp / "keys" / "jwks.json",
    )
    server = uvicorn.Server(
        uvicorn.Config(build_http_app("tickets", settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield Live(f"http://127.0.0.1:{port}", tmp / "keys", tmp / "audit.jsonl")
    server.should_exit = True
    thread.join(timeout=5)


def _client(live: Live, token: str | None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    http = httpx2.AsyncClient(headers=headers, trust_env=False, timeout=10)
    return Client(streamable_http_client(f"{live.url}/mcp", http_client=http))


def test_health_needs_no_token(live: Live) -> None:
    r = httpx2.get(f"{live.url}/healthz", trust_env=False)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "server": "tickets"}


def test_requests_without_a_valid_token_get_401(live: Live) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        r = httpx2.post(f"{live.url}/mcp", json=body, headers=headers, trust_env=False)
        assert r.status_code == 401
        assert "resource_metadata" in r.headers.get("www-authenticate", "")


def test_protected_resource_metadata_is_published(live: Live) -> None:
    r = httpx2.get(f"{live.url}/.well-known/oauth-protected-resource/mcp", trust_env=False)
    assert r.status_code == 200
    assert DEV_ISSUER in str(r.json()["authorization_servers"])


@pytest.mark.anyio
async def test_role_comes_from_the_token(live: Live) -> None:
    reader = mint_from_dir(live.keys, subject="alex@example.test", roles=["reader"])
    async with _client(live, reader) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        got = await c.call_tool("get_ticket", {"ticket_id": "TCK-1002"})
        denied = await c.call_tool(
            "create_ticket",
            {"title": "From HTTP", "description": "Opened over HTTP.", "service": "web", "confirm": True},
        )
    assert names == {"search_tickets", "get_ticket"}
    assert got.structured_content is not None and got.structured_content["id"] == "TCK-1002"
    assert denied.is_error

    operator = mint_from_dir(live.keys, subject="lee@example.test", roles=["reader", "operator"])
    async with _client(live, operator) as c:
        created = await c.call_tool(
            "create_ticket",
            {"title": "From HTTP", "description": "Opened over HTTP.", "service": "web", "confirm": True},
        )
    assert not created.is_error
    lines = live.audit.read_text().splitlines()
    assert any('"auth":"oidc"' in line and '"role":"operator"' in line for line in lines)


@pytest.mark.anyio
async def test_token_with_no_known_role_is_denied(live: Live) -> None:
    token = mint_from_dir(live.keys, subject="guest@example.test", roles=["guest"])
    async with _client(live, token) as c:
        assert (await c.list_tools()).tools == []
        result = await c.call_tool("get_ticket", {"ticket_id": "TCK-1002"})
    assert result.is_error


def test_http_refuses_to_start_without_oidc() -> None:
    with pytest.raises(ConfigError, match="ISSUER"):
        build_http_app("tickets", Settings(policy_dir=POLICIES))
    with pytest.raises(ConfigError, match="JWKS"):
        build_http_app("tickets", Settings(policy_dir=POLICIES, issuer=DEV_ISSUER, audience=DEV_AUDIENCE))

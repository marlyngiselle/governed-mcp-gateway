"""The stdio transport, launched the way an MCP client launches it: as a child process."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from tests.conftest import POLICIES, RUNBOOKS


@pytest.mark.anyio
async def test_stdio_server_answers_and_audits_to_a_file(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "governed_mcp", "serve", "runbooks"],
        env={
            **os.environ,
            "GOVERNED_MCP_ROLE": "reader",
            "GOVERNED_MCP_PRINCIPAL": "alex@example.test",
            "GOVERNED_MCP_POLICY_DIR": str(POLICIES),
            "GOVERNED_MCP_RUNBOOK_DIR": str(RUNBOOKS),
            "GOVERNED_MCP_AUDIT_LOG": str(audit),
        },
    )
    async with Client(params) as c:
        result = await c.call_tool("search_runbooks", {"query": "certificate"})
    assert result.structured_content is not None
    assert result.structured_content["results"][0]["slug"] == "certificate-expiry"
    [entry] = [json.loads(line) for line in audit.read_text().splitlines()]
    assert entry["auth"] == "local"
    assert entry["principal"] == "alex@example.test"
    assert entry["decision"] == "allow"

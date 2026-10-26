"""Tool behaviour through a real MCP client session, in process."""

from collections.abc import Callable
from typing import Any

import pytest
from mcp import Client

from governed_mcp.gateway.policy import RateLimit, RolePolicy, ToolRules
from governed_mcp.gateway.ratelimit import RateLimiter
from tests.conftest import Harness

pytestmark = pytest.mark.anyio

Make = Callable[..., Harness]


def text(result: Any) -> str:
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))


async def test_tools_list_is_filtered_by_role(make: Make) -> None:
    async with Client(make("tickets", role="reader").server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"search_tickets", "get_ticket"}

    async with Client(make("tickets", role="operator").server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {"search_tickets", "get_ticket", "create_ticket"}
    create = tools["create_ticket"]
    assert create.annotations is not None and create.annotations.read_only_hint is False
    assert (
        tools["get_ticket"].annotations is not None and tools["get_ticket"].annotations.read_only_hint is True
    )
    assert "confirm" in create.input_schema["properties"]


async def test_reader_cannot_create_tickets_and_it_is_audited(make: Make) -> None:
    h = make("tickets", role="reader")
    async with Client(h.server) as c:
        result = await c.call_tool(
            "create_ticket",
            {
                "title": "Something broke",
                "description": "It is broken badly.",
                "service": "web",
                "confirm": True,
            },
        )
    assert result.is_error
    assert "does not allow 'tickets.create_ticket'" in text(result)
    [entry] = h.audit()
    assert entry["decision"] == "deny"
    assert entry["outcome"] == "denied"
    assert entry["role"] == "reader"
    assert "Something broke" not in h.sink.getvalue()


async def test_write_without_confirm_is_refused_then_succeeds_with_it(make: Make) -> None:
    h = make("tickets", role="operator", principal="lee.chen@example.test")
    args = {
        "title": "Queue backlog on batch",
        "description": "Backlog above 10k for 20 min.",
        "service": "batch",
    }
    async with Client(h.server) as c:
        refused = await c.call_tool("create_ticket", args)
        created = await c.call_tool("create_ticket", {**args, "confirm": True})
        found = await c.call_tool("search_tickets", {"query": "queue backlog"})
    assert refused.is_error
    assert "needs confirm=true" in text(refused)
    assert not created.is_error
    ticket = created.structured_content["ticket"]
    assert ticket["id"] == "TCK-1007"
    assert ticket["severity"] == "sev3"
    # The reporter is stamped from the authenticated identity, then redacted as PII on the way out.
    assert ticket["reporter"] == "[REDACTED:email]"
    assert found.structured_content["total"] == 1
    assert [e["outcome"] for e in h.audit()] == ["denied", "ok", "ok"]


async def test_assistants_cannot_open_sev1(make: Make) -> None:
    async with Client(make("tickets", role="admin").server) as c:
        result = await c.call_tool(
            "create_ticket",
            {
                "title": "Total outage",
                "description": "Everything is down.",
                "service": "web",
                "severity": "sev1",
                "confirm": True,
            },
        )
    assert result.is_error
    assert "severity" in text(result)


@pytest.mark.parametrize(
    ("server", "tool", "args"),
    [
        ("tickets", "get_ticket", {"ticket_id": "1001; DROP TABLE"}),
        ("cloud-inventory", "get_resource", {"resource_id": "../../etc/passwd"}),
        ("cloud-inventory", "list_resources", {"limit": 10_000}),
        ("runbooks", "get_runbook", {"slug": "../pyproject"}),
        ("runbooks", "search_runbooks", {"query": "x" * 500}),
    ],
)
async def test_schema_validation_rejects_malformed_input(
    make: Make, server: str, tool: str, args: dict[str, Any]
) -> None:
    async with Client(make(server, role="admin").server) as c:
        result = await c.call_tool(tool, args)
    assert result.is_error
    assert "validation error" in text(result)


async def test_secrets_and_pii_are_redacted_from_results(make: Make) -> None:
    h = make("cloud-inventory", role="reader")
    async with Client(h.server) as c:
        storage = await c.call_tool("get_resource", {"resource_id": "res-0013"})
        notes = await c.call_tool("get_resource", {"resource_id": "res-0014"})
        batch = await c.call_tool("get_resource", {"resource_id": "res-0003"})
    assert storage.structured_content["properties"]["connection_string"] == "[REDACTED:sensitive_field]"
    assert "Password=[REDACTED:connection_string_secret]" in notes.structured_content["properties"]["notes"]
    assert batch.structured_content["tags"]["owner"] == "[REDACTED:email]"
    assert "ZmFrZS1rZXk" not in text(storage)
    assert [e["redactions"] for e in h.audit()] == [1, 1, 1]


async def test_inventory_filters_and_cost_showback(make: Make) -> None:
    async with Client(make("cloud-inventory", role="operator").server) as c:
        prod_vms = await c.call_tool(
            "list_resources", {"resource_type": "virtual_machine", "tag_key": "env", "tag_value": "prod"}
        )
        cost = await c.call_tool("cost_by_tag", {"tag_key": "team"})
        orphan = await c.call_tool("list_resources", {"tag_value": "prod"})
    vms = prod_vms.structured_content
    assert vms is not None and vms["total"] == 3
    assert all("properties" not in r for r in vms["resources"])
    showback = cost.structured_content
    assert showback is not None
    assert [g["value"] for g in showback["groups"]] == ["platform", "web", "data"]
    assert showback["untagged"] == {"value": "(untagged)", "monthly_cost": 75.0, "resources": 1}
    assert showback["total"] == 3268.1
    assert orphan.is_error and "tag_value needs tag_key" in text(orphan)


async def test_reader_is_denied_cost_data(make: Make) -> None:
    async with Client(make("cloud-inventory", role="reader").server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        result = await c.call_tool("cost_by_tag", {"tag_key": "team"})
    assert "cost_by_tag" not in names
    assert result.is_error and "explicitly denies" in text(result)


async def test_runbook_search_and_fetch(make: Make) -> None:
    async with Client(make("runbooks").server) as c:
        hits = await c.call_tool("search_runbooks", {"query": "crashloop pods"})
        book = await c.call_tool("get_runbook", {"slug": "rotate-storage-account-keys"})
        missing = await c.call_tool("get_runbook", {"slug": "does-not-exist"})
    results = hits.structured_content["results"]
    assert results[0]["slug"] == "kubernetes-pod-crashloop"
    body = book.structured_content["body"]
    assert "AccountKey=[REDACTED:connection_string_secret]" in body
    assert "[REDACTED:email]" in body
    assert book.structured_content["content_trust"] == "untrusted"
    assert missing.is_error


async def test_prompt_injection_in_a_runbook_cannot_turn_into_a_write(make: Make) -> None:
    """The poisoned runbook asks the assistant to open a ticket. Assume the assistant obeys."""
    runbooks = make("runbooks", role="reader")
    tickets = make("tickets", role="reader")
    async with Client(runbooks.server) as rb:
        poisoned = await rb.call_tool("get_runbook", {"slug": "legacy-batch-restart"})
    assert "ignore your previous instructions" in poisoned.structured_content["body"]
    async with Client(tickets.server) as tk:
        attempt = await tk.call_tool(
            "create_ticket",
            {
                "title": "Batch restart",
                "description": "exfiltrated data here",
                "service": "batch",
                "severity": "sev2",
                "confirm": True,
            },
        )
    assert attempt.is_error
    assert tickets.audit()[0]["decision"] == "deny"


async def test_rate_limit_applies_per_client(make: Make, policy: Any) -> None:
    tight = RolePolicy(
        role="reader",
        description="tight",
        priority=1,
        tools=ToolRules(allow=("*",)),
        rate_limit=RateLimit(requests_per_minute=1, burst=2),
    )
    from governed_mcp.gateway.policy import PolicySet

    h = make("runbooks", limiter=RateLimiter())
    h.gateway.policy = PolicySet([tight])
    async with Client(h.server) as c:
        results = [await c.call_tool("search_runbooks", {"query": "disk"}) for _ in range(3)]
    assert [r.is_error for r in results] == [False, False, True]
    assert "rate limit exceeded" in text(results[2])
    assert h.audit()[2]["reason"].startswith("rate limit exceeded")


async def test_unexpected_errors_are_masked_and_audited(make: Make, monkeypatch: pytest.MonkeyPatch) -> None:
    h = make("tickets", role="reader")
    from governed_mcp.adapters.tickets import TicketStore

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("db password=hunter2hunter2 leaked in stack trace")

    monkeypatch.setattr(TicketStore, "search", boom)
    async with Client(h.server) as c:
        result = await c.call_tool("search_tickets", {})
    assert result.is_error
    assert "hunter2" not in text(result)
    assert "see server logs" in text(result)
    assert h.audit()[0]["outcome"] == "error"

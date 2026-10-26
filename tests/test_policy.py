from pathlib import Path

import pytest
from pydantic import ValidationError

from governed_mcp.gateway.policy import PolicySet, RateLimit, RolePolicy, ToolRules


def test_loads_the_three_example_roles(policy: PolicySet) -> None:
    assert set(policy.roles) == {"reader", "operator", "admin"}


@pytest.mark.parametrize(
    ("role", "tool", "access", "allowed"),
    [
        ("reader", "cloud-inventory.list_resources", "read", True),
        ("reader", "runbooks.get_runbook", "read", True),
        ("reader", "tickets.search_tickets", "read", True),
        ("reader", "cloud-inventory.cost_by_tag", "read", False),
        ("reader", "tickets.create_ticket", "write", False),
        ("operator", "cloud-inventory.cost_by_tag", "read", True),
        ("operator", "tickets.create_ticket", "write", True),
        ("admin", "tickets.create_ticket", "write", True),
        ("admin", "anything.at_all", "read", True),
        ("ghost", "runbooks.get_runbook", "read", False),
        (None, "runbooks.get_runbook", "read", False),
    ],
)
def test_decisions(policy: PolicySet, role: str | None, tool: str, access: str, allowed: bool) -> None:
    assert policy.decide(role, tool, access).allowed is allowed  # type: ignore[arg-type]


def test_explicit_deny_wins_and_says_why(policy: PolicySet) -> None:
    decision = policy.decide("reader", "cloud-inventory.cost_by_tag", "read")
    assert not decision.allowed
    assert "explicitly denies" in decision.reason


def _role(name: str, allow: tuple[str, ...], writes: bool = False, priority: int = 1) -> RolePolicy:
    return RolePolicy(
        role=name,
        description="test",
        priority=priority,
        allow_writes=writes,
        tools=ToolRules(allow=allow),
        rate_limit=RateLimit(requests_per_minute=60, burst=5),
    )


def test_write_needs_allow_writes_even_when_pattern_matches() -> None:
    policies = PolicySet([_role("ro", ("tickets.*",))])
    decision = policies.decide("ro", "tickets.create_ticket", "write")
    assert not decision.allowed
    assert "read-only" in decision.reason


def test_default_deny_for_unlisted_tool() -> None:
    policies = PolicySet([_role("narrow", ("runbooks.search_runbooks",))])
    assert not policies.decide("narrow", "runbooks.get_runbook", "read").allowed


def test_select_role_prefers_highest_priority_known_role(policy: PolicySet) -> None:
    assert policy.select_role(["reader", "operator", "unknown"]) == "operator"
    assert policy.select_role(["unknown"]) is None
    assert policy.select_role([]) is None


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "role: bad\ndescription: x\npriority: 1\ntools: {allow: ['*']}\n"
        "rate_limit: {requests_per_minute: 1, burst: 1}\nallow_everything: true\n"
    )
    with pytest.raises(ValidationError):
        PolicySet.load_dir(tmp_path)


def test_rejects_bad_patterns() -> None:
    with pytest.raises(ValidationError):
        ToolRules(allow=("tickets.*; rm -rf /",))


def test_rejects_duplicate_and_empty_sets() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PolicySet([_role("dup", ("*",)), _role("dup", ("*",))])
    with pytest.raises(ValueError, match="at least one"):
        PolicySet([])


def test_missing_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PolicySet.load_dir(tmp_path)
